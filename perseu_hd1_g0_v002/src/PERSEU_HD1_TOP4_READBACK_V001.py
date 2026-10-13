#!/usr/bin/env python3
# coding: utf-8
"""PERSEU_HD1_TOP4_READBACK_V001 -- SOURCE_ONLY until Windows target G0 qualification.

Full SHA-256 readback of the TOP4 archive on HD1 (Seagate ST3500418AS, serial 6VMCLT3M) against the
canonical manifest ARCHIVE_SOURCE_MANIFEST_SHA256.csv (SHA 416A385C...). Read-only on HD1: files are
opened 'rb' only; nothing is ever written to the HD1 volume. Active state (append-only journal, lock)
lives in --state-root on C:, separated from reports. Launched by PERSEU_HD1_TOP4_READBACK_V001.ps1.

Modes:
  --selftest   synthetic end-to-end tests (schema, mapping, exact-set, mismatch, resume, locks, torn journal)
  --readback   Windows only: bind HD1 from the wrapper snapshot, preflight metadata, hash, resume
  --fixture-child  internal fixtures for the wrapper harness

Exit codes: 0=PASS  1=FAIL_READBACK_MISMATCH (no effects)  2=BLOCKED  130=SAFE_STOP (resumable)
Resume granularity: one file (a file is committed only after its full hash is journaled and fsynced).
MULTIWORK: not applicable by design -- a single HDD is read sequentially by one reader; parallel reads
would thrash the spindle and lower throughput. AUTOCPU: not applicable (I/O bound, SHA-256 in C).
"""
from __future__ import annotations

import argparse
import codecs
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time

PROJECT = 'Perseu MT5 (Astra)'
THREAD = 'PERSEU_C2_DISK_SPACE_RECONCILIATION'
SUBFRONT = 'PERSEU_HD1_ARCHIVE_RECONCILIATION'
REVISION = 'PERSEU_HD1_TOP4_READBACK_V001'
POLICY_MASTER_SHA256_AT_BUILD = '5B135DA0CA7C3BFE992F364720605522FB939977772C6D5A6FD3811A8288B302'

HD1_MODEL = 'ST3500418AS'
HD1_SERIAL = '6VMCLT3M'
HD1_BYTES = 500107862016
HD2_SERIAL = 'WD-WCAYUS916314'
MANIFEST_PATH = r'C:\Users\silvi\Downloads\HD500_FINAL_MANIFEST_HASH_TOP4_CONTROL_V001\ARCHIVE_SOURCE_MANIFEST_SHA256.csv'
MANIFEST_SHA256 = '416A385CCAEBCCC95A7806A4EF37F7092A58CF2375162B6FDF09735F716AD90C'
PAYLOAD_SEGMENTS = ('ARQUIVO_FRIO', 'TOP4_V001', 'PAYLOAD')
EXPECTED_SETS = {
    'PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R2_PILOTO_202501': (45, 167103249108),
    'PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R9_CONFIRM_C1_202502': (45, 140265426698),
    'PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R8_SEP2026': (44, 62918933298),
    'MINOTAURO_R1R11_FULL_CORRECT_C1_V001_20260928': (1396, 43732996720),
}

PATH_COLS = ('path', 'relative_path', 'rel_path', 'relpath', 'file', 'file_path', 'filepath', 'source_path',
             'src_path', 'fullname', 'full_name', 'full_path', 'source')
SIZE_COLS = ('size', 'bytes', 'size_bytes', 'length', 'file_size', 'source_bytes')
SHA_COLS = ('sha256', 'sha_256', 'hash', 'sha256_hex', 'file_sha256', 'source_sha256')
LITERAL_CODECS = ('utf-8', 'utf-8-sig', 'ascii')
PASS_RESULTS = frozenset({'PASS_SELFTEST_ONLY', 'PASS_READBACK', 'FIXTURE_PASS'})
FAIL_RESULTS = frozenset({'FAIL_READBACK_MISMATCH'})
ALL_RESULTS = PASS_RESULTS | FAIL_RESULTS | {'BLOCKED', 'SAFE_STOP', 'FIXTURE_BLOCKED'}
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
CHUNK = 8 * 1024 * 1024
HEARTBEAT_S = 30.0
JOURNAL_SCHEMA = 'PERSEU_TOP4_READBACK_JOURNAL_V001'


class Blocked(Exception):
    """Fail-closed condition with a stable reason code."""


class SafeStop(Exception):
    """Cooperative stop at a file boundary; journal is consistent and resumable."""


def heartbeat(**fields) -> None:
    sys.stderr.write('HEARTBEAT REVISION=' + REVISION + ' ' + ' '.join(f'{k}={v}' for k, v in fields.items()) + '\n')
    sys.stderr.flush()


def emit(outcome: str, out_json: Path | None, exit_code: int | None = None, **fields) -> int:
    if outcome not in ALL_RESULTS:
        outcome, fields = 'BLOCKED', {'reason': 'RESULT_NOT_IN_ALLOWLIST'}
    if exit_code is None:
        exit_code = 0 if outcome in PASS_RESULTS else (1 if outcome in FAIL_RESULTS else (130 if outcome == 'SAFE_STOP' else 2))
    rec = {'PROJECT': PROJECT, 'THREAD': THREAD, 'SUBFRONT': SUBFRONT, 'REVISION': REVISION,
           'POLICY_MASTER_SHA256_AT_BUILD': POLICY_MASTER_SHA256_AT_BUILD, 'MODE': 'READ_ONLY_ON_HD1',
           'SOURCE_DELETE': 'NO', 'TARGET_DISK_MUTATION': 'NO', 'C2_FULL_STARTED': 'NO',
           'python_version': sys.version.split()[0], 'python_executable': sys.executable,
           'RESULT': outcome, 'EXIT_CODE': exit_code, **fields}
    text = json.dumps(rec, sort_keys=True, ensure_ascii=True, separators=(',', ':'))
    if out_json is not None:
        try:
            atomic_write_new(out_json, (text + '\n').encode('utf-8'))
        except (OSError, Blocked) as exc:
            sys.stdout.write(json.dumps({'RESULT': 'BLOCKED', 'EXIT_CODE': 2, 'REVISION': REVISION,
                                         'reason': f'OUT_JSON_WRITE_FAILED:{type(exc).__name__}:{exc}'}) + '\n')
            sys.stdout.flush()
            return 2
    summary = {k: rec[k] for k in ('RESULT', 'EXIT_CODE', 'REVISION') if k in rec}
    for k in ('reason', 'committed_files', 'total_files', 'matched', 'mismatched'):
        if k in rec:
            summary[k] = rec[k]
    sys.stdout.write(json.dumps(summary, sort_keys=True, ensure_ascii=True) + '\n')
    sys.stdout.flush()
    return exit_code


def atomic_write_new(path: Path, data: bytes) -> None:
    if path.exists():
        raise Blocked('OUT_PATH_PREEXISTS')
    tmp = path.with_name(path.name + '.partial')
    with open(tmp, 'xb') as dst:
        dst.write(data)
        dst.flush()
        os.fsync(dst.fileno())
    os.replace(tmp, path)


def validate_new_path(raw: str | None, label: str) -> Path | None:
    if raw is None:
        return None
    p = Path(raw)
    if not p.is_absolute() or p.exists() or not p.parent.is_dir():
        raise Blocked(label + '_INVALID_OR_PREEXISTS')
    return p


def codec_check() -> dict:
    out = {n: codecs.lookup(n).name for n in LITERAL_CODECS}
    s = 'a\u00e7\u00e3o'
    if (b'\xef\xbb\xbf' + s.encode('utf-8')).decode('utf-8-sig') != s:
        raise Blocked('CODEC_UTF8SIG_ROUNDTRIP')
    return out


# ------------------------------------------------------------------ binding (same contract as probe V002)

def seq(v):
    return [] if v is None else (v if isinstance(v, list) else [v])


def strict_int(v):
    return v if type(v) is int else None


def norm_text(v) -> str:
    return v.strip() if isinstance(v, str) else ''


def letter_of(v):
    if not isinstance(v, str):
        return None
    s = v.strip().upper()
    return s if re.fullmatch('[A-Z]', s) else None


def bind_hd1(snapshot: object) -> dict:
    if not isinstance(snapshot, dict):
        raise Blocked('SNAPSHOT_NOT_OBJECT')
    disks, parts = seq(snapshot.get('disks')), seq(snapshot.get('partitions'))
    if any(not isinstance(x, dict) for x in disks + parts):
        raise Blocked('SNAPSHOT_ITEM_NOT_OBJECT')
    for d in disks:
        if strict_int(d.get('Number')) is None or strict_int(d.get('Size')) is None:
            raise Blocked('DISK_NUMBER_OR_SIZE_NOT_INT')
    for p in parts:
        if strict_int(p.get('DiskNumber')) is None:
            raise Blocked('PARTITION_DISKNUMBER_NOT_INT')
    nums = [d['Number'] for d in disks]
    if len(nums) != len(set(nums)):
        raise Blocked('DISK_NUMBER_DUPLICATED')
    hd1 = [d for d in disks if norm_text(d.get('SerialNumber')).upper() == HD1_SERIAL]
    if len(hd1) != 1:
        raise Blocked(f'HD1_SERIAL_CARDINALITY_{len(hd1)}')
    disk = hd1[0]
    if norm_text(disk.get('FriendlyName')) != HD1_MODEL:
        raise Blocked('HD1_MODEL_MISMATCH')
    if disk['Size'] != HD1_BYTES:
        raise Blocked('HD1_SIZE_MISMATCH')
    if disk.get('OperationalStatus') != 'Online':
        raise Blocked('HD1_NOT_ONLINE_NO_MUTATION_ATTEMPTED')
    letters = [letter_of(p.get('DriveLetter')) for p in parts if p['DiskNumber'] == disk['Number']]
    letters = [x for x in letters if x]
    if len(letters) != 1:
        raise Blocked(f'HD1_DRIVE_LETTER_CARDINALITY_{len(letters)}')
    if sum(1 for p in parts if letter_of(p.get('DriveLetter')) == letters[0]) != 1:
        raise Blocked('HD1_DRIVE_LETTER_OWNED_BY_MULTIPLE_PARTITIONS')
    hd2_numbers = {d['Number'] for d in disks if norm_text(d.get('SerialNumber')).upper() == HD2_SERIAL}
    if disk['Number'] in hd2_numbers:
        raise Blocked('HD1_HD2_DISK_NUMBER_COLLISION')
    return {'disk_number': disk['Number'], 'drive_letter': letters[0], 'serial': HD1_SERIAL, 'model': HD1_MODEL,
            'size_bytes': HD1_BYTES, 'is_read_only': disk.get('IsReadOnly')}


# ------------------------------------------------------------------ manifest

def sha256_file(path: Path, stop_check=None) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as src:
        while True:
            chunk = src.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
            if stop_check is not None:
                stop_check(len(chunk))
    return h.hexdigest().upper()


def norm_col(name: str) -> str:
    return re.sub(r'[\s\-]+', '_', name.strip().lower())


def load_manifest(path: Path, expected_sha: str, expected_rows: int, expected_bytes: int) -> dict:
    """Strict, introspected schema: exactly one path, one size and one sha256 column from allowlists."""
    try:
        st = os.stat(path, follow_symlinks=False)
    except FileNotFoundError:
        raise Blocked('MANIFEST_NOT_FOUND')
    if is_reparse(st) or not stat.S_ISREG(st.st_mode):
        raise Blocked('MANIFEST_REPARSE_OR_NOT_REGULAR')
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest().upper()
    if digest != expected_sha:
        raise Blocked('MANIFEST_SHA_MISMATCH:' + digest)
    try:
        text = raw.decode('utf-8-sig', errors='strict')
    except UnicodeDecodeError:
        raise Blocked('MANIFEST_NOT_UTF8')
    reader = csv.reader(io.StringIO(text, newline=''))
    try:
        header = next(reader)
    except StopIteration:
        raise Blocked('MANIFEST_EMPTY')
    cols = [norm_col(h) for h in header]
    pick = {}
    for kind, allow in (('path', PATH_COLS), ('size', SIZE_COLS), ('sha', SHA_COLS)):
        idx = [i for i, c in enumerate(cols) if c in allow]
        if len(idx) != 1:
            raise Blocked(f'MANIFEST_SCHEMA_UNRESOLVED_{kind.upper()}_{len(idx)}:' + '|'.join(header))
        pick[kind] = idx[0]
    rows, seen, total = [], set(), 0
    for n, rec in enumerate(reader, start=2):
        if not rec or all(not x.strip() for x in rec):
            continue
        if len(rec) != len(header):
            raise Blocked(f'MANIFEST_ROW_WIDTH_{n}')
        p, sz, sh = rec[pick['path']].strip(), rec[pick['size']].strip(), rec[pick['sha']].strip().upper()
        if not re.fullmatch(r'\d+', sz):
            raise Blocked(f'MANIFEST_SIZE_NOT_INT_{n}')
        if not re.fullmatch(r'[0-9A-F]{64}', sh):
            raise Blocked(f'MANIFEST_SHA_NOT_HEX64_{n}')
        key = p.replace('\\', '/').casefold()
        if key in seen:
            raise Blocked(f'MANIFEST_DUPLICATE_PATH_{n}')
        seen.add(key)
        total += int(sz)
        rows.append({'line': n, 'path': p, 'size': int(sz), 'sha256': sh})
    if len(rows) != expected_rows:
        raise Blocked(f'MANIFEST_ROW_COUNT_{len(rows)}_EXPECTED_{expected_rows}')
    if total != expected_bytes:
        raise Blocked(f'MANIFEST_TOTAL_BYTES_{total}_EXPECTED_{expected_bytes}')
    return {'sha256': digest, 'header': header, 'columns': {k: header[v] for k, v in pick.items()},
            'rows': rows, 'total_bytes': total}


# ------------------------------------------------------------------ mapping and preflight

def is_reparse(st) -> bool:
    return bool(getattr(st, 'st_file_attributes', 0) & FILE_ATTRIBUTE_REPARSE_POINT) or stat.S_ISLNK(st.st_mode)


def walk(root: Path, limit: int = 20000) -> tuple[list, list]:
    st = os.stat(root, follow_symlinks=False)
    if is_reparse(st) or not stat.S_ISDIR(st.st_mode):
        raise Blocked('PAYLOAD_ROOT_REPARSE_OR_NOT_DIR')
    files, dirs, stack = [], [()], [(root, ())]
    while stack:
        cur, rel = stack.pop()
        with os.scandir(cur) as it:
            for e in it:
                r = rel + (e.name,)
                est = e.stat(follow_symlinks=False)
                if is_reparse(est):
                    raise Blocked('PAYLOAD_REPARSE_REFUSED:' + '/'.join(r))
                if stat.S_ISDIR(est.st_mode):
                    dirs.append(r)
                    stack.append((Path(e.path), r))
                elif stat.S_ISREG(est.st_mode):
                    files.append((r, int(est.st_size), int(est.st_mtime_ns)))
                else:
                    raise Blocked('PAYLOAD_UNSUPPORTED_ENTRY:' + '/'.join(r))
                if len(files) + len(dirs) > limit:
                    raise Blocked('PAYLOAD_ENTRY_LIMIT')
    return files, dirs


def map_and_preflight(payload_root: Path, manifest: dict, set_names) -> dict:
    files, dirs = walk(payload_root)
    names = {n.casefold(): n for n in set_names}
    roots = {}
    for rel in dirs:
        if rel and rel[-1].casefold() in names:
            roots.setdefault(names[rel[-1].casefold()], []).append(rel)
    for n in set_names:
        if len(roots.get(n, [])) != 1:
            raise Blocked(f'SET_ROOT_CARDINALITY_{len(roots.get(n, []))}:{n}')
    roots = {n: r[0] for n, r in roots.items()}
    for a in roots.values():
        for b in roots.values():
            if a != b and b[:len(a)] == a:
                raise Blocked('NESTED_SET_ROOTS')
    disk = {}
    for rel, size, mtime in files:
        for n, r in roots.items():
            if rel[:len(r)] == r:
                disk['/'.join(rel).casefold()] = (rel, size, mtime)
                break
    targets = []
    for row in manifest['rows']:
        segs = [s for s in re.split(r'[\\/]+', row['path']) if s]
        hits = [i for i, s in enumerate(segs) if s.casefold() in names]
        if len(hits) != 1:
            raise Blocked(f'MANIFEST_ROW_SET_UNRESOLVED_{row["line"]}_{len(hits)}')
        set_name = names[segs[hits[0]].casefold()]
        remainder = segs[hits[0] + 1:]
        if not remainder or any(s in ('.', '..') for s in remainder):
            raise Blocked(f'MANIFEST_ROW_REMAINDER_INVALID_{row["line"]}')
        rel = roots[set_name] + tuple(remainder)
        targets.append({**row, 'set': set_name, 'rel': '/'.join(rel), 'key': '/'.join(rel).casefold()})
    expected = {t['key'] for t in targets}
    extra = sorted(k for k in disk if k not in expected)
    missing = sorted(t['rel'] for t in targets if t['key'] not in disk)
    if missing or extra:
        raise Blocked(f'EXACT_SET_MISMATCH_MISSING_{len(missing)}_EXTRA_{len(extra)}:' + ';'.join((missing + extra)[:10]))
    size_bad = [t['rel'] for t in targets if disk[t['key']][1] != t['size']]
    if size_bad:
        raise Blocked(f'SIZE_MISMATCH_{len(size_bad)}:' + ';'.join(size_bad[:10]))
    for t in targets:
        t['mtime_ns'] = disk[t['key']][2]
    per_set = {n: {'files': sum(1 for t in targets if t['set'] == n), 'bytes': sum(t['size'] for t in targets if t['set'] == n)}
               for n in set_names}
    return {'targets': targets, 'set_roots': {n: '/'.join(r) for n, r in roots.items()}, 'per_set': per_set}


# ------------------------------------------------------------------ state: lock + journal

def pid_alive(pid: int) -> bool:
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        h = k32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            code = wintypes.DWORD()
            if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class StateLock:
    def __init__(self, path: Path):
        self.path, self.owned, self.reclaimed = path, False, None

    def acquire(self):
        body = json.dumps({'pid': os.getpid(), 'started_ns': time.time_ns(), 'revision': REVISION}).encode()
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                old = json.loads(self.path.read_text(encoding='utf-8'))
                old_pid = int(old['pid'])
            except (OSError, ValueError, KeyError, TypeError):
                raise Blocked('STATE_LOCK_UNREADABLE_MANUAL_RECONCILIATION')
            if pid_alive(old_pid):
                raise Blocked(f'STATE_LOCK_HELD_BY_LIVE_PID_{old_pid}')
            self.reclaimed = old
            os.replace(self.path, self.path.with_name(f'LOCK.stale_{old_pid}_{time.time_ns()}.json'))
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, 'wb') as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        self.owned = True

    def release(self) -> str:
        if not self.owned:
            return 'NOT_OWNED'
        try:
            os.unlink(self.path)
            self.owned = False
            return 'RELEASED'
        except OSError as exc:
            return f'RELEASE_FAILED_{type(exc).__name__}'


def read_journal(path: Path, targets: list, header: dict) -> tuple[dict, dict]:
    committed, info = {}, {'lines': 0, 'torn_tail': False}
    if not path.exists():
        return committed, info
    raw = path.read_bytes()
    lines = raw.split(b'\n')
    if lines and lines[-1] != b'':
        info['torn_tail'] = True  # crash during append: incomplete last record is ignored, never trusted
    lines = lines[:-1]
    if not lines:
        raise Blocked('JOURNAL_WITHOUT_HEADER')
    try:
        head = json.loads(lines[0])
    except json.JSONDecodeError:
        raise Blocked('JOURNAL_HEADER_CORRUPT')
    for k in ('schema', 'manifest_sha256', 'payload_sha256', 'hd1_serial', 'total_files'):
        if head.get(k) != header.get(k):
            raise Blocked('JOURNAL_IDENTITY_MISMATCH_' + k.upper())
    for ln in lines[1:]:
        info['lines'] += 1
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            raise Blocked(f'JOURNAL_RECORD_CORRUPT_{info["lines"]}')
        i = r.get('i')
        if type(i) is not int or not 0 <= i < len(targets) or r.get('rel') != targets[i]['rel'] \
                or r.get('expected') != targets[i]['sha256'] or not re.fullmatch('[0-9A-F]{64}', str(r.get('actual'))):
            raise Blocked(f'JOURNAL_RECORD_INVALID_{info["lines"]}')
        if i in committed:
            raise Blocked(f'JOURNAL_DUPLICATE_COMMIT_{i}')
        committed[i] = r
    return committed, info


def append_record(fh, rec: dict) -> None:
    fh.write((json.dumps(rec, sort_keys=True, ensure_ascii=True, separators=(',', ':')) + '\n').encode('utf-8'))
    fh.flush()
    os.fsync(fh.fileno())


def readback(payload_root: Path, manifest: dict, state_dir: Path, payload_sha: str, set_names, volume_root: Path,
             stop_after_files: int | None = None, clock=time.monotonic) -> dict:
    """Core engine. Raises SafeStop on cooperative stop; returns a result dict when all files are committed."""
    plan = map_and_preflight(payload_root, manifest, set_names)
    targets = plan['targets']
    total_bytes = sum(t['size'] for t in targets)
    header = {'schema': JOURNAL_SCHEMA, 'manifest_sha256': manifest['sha256'], 'payload_sha256': payload_sha,
              'hd1_serial': HD1_SERIAL, 'total_files': len(targets)}
    state_dir.mkdir(parents=True, exist_ok=True)
    lock = StateLock(state_dir / 'LOCK.json')
    lock.acquire()
    jpath = state_dir / 'JOURNAL.jsonl'
    try:
        committed, jinfo = read_journal(jpath, targets, header)
        if jinfo['torn_tail']:
            good = jpath.read_bytes().rsplit(b'\n', 1)[0] + b'\n'
            os.replace(jpath, jpath.with_name(f'JOURNAL.torn_{time.time_ns()}.jsonl'))
            with open(jpath, 'xb') as f:
                f.write(good)
                f.flush()
                os.fsync(f.fileno())
        dev = os.stat(volume_root).st_dev
        resumed = len(committed)
        done_bytes = sum(targets[i]['size'] for i in committed)
        t0 = last = clock()
        session_bytes = 0
        hashed_this_session = 0
        with open(jpath, 'ab') as jf:
            if jpath.stat().st_size == 0:
                append_record(jf, header)
            for i, t in enumerate(targets):
                if i in committed:
                    continue
                if stop_after_files is not None and hashed_this_session >= stop_after_files:
                    raise SafeStop('STOP_AFTER_FILES_TEST')
                if os.stat(volume_root).st_dev != dev:
                    raise Blocked('VOLUME_IDENTITY_CHANGED_DURING_READBACK')
                path = payload_root.joinpath(*t['rel'].split('/'))
                pre = os.stat(path, follow_symlinks=False)
                if is_reparse(pre) or pre.st_size != t['size'] or int(pre.st_mtime_ns) != t['mtime_ns']:
                    raise Blocked('SOURCE_CHANGED_SINCE_PREFLIGHT:' + t['rel'])

                def tick(n, _t=t):
                    nonlocal last, session_bytes
                    session_bytes += n
                    now = clock()
                    if now - last >= HEARTBEAT_S:
                        last = now
                        el = max(now - t0, 1e-9)
                        rate = session_bytes / el
                        remaining = total_bytes - done_bytes - session_bytes
                        eta = int(remaining / rate) if rate > 0 else -1
                        heartbeat(PHASE='HASH', PROGRESS=f'{100.0 * done_bytes / max(total_bytes, 1):.2f}%',
                                  COMMITTED=f'{len(committed)}/{len(targets)}', TOTAL=total_bytes,
                                  RATE_MIB_S=f'{rate / 1048576:.1f}', ETA_S=eta,
                                  FINISH=time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(time.time() + max(eta, 0))),
                                  ACTIVE=_t['rel'][-80:], READY_WAITING=len(targets) - len(committed) - 1,
                                  CHECKPOINT=len(committed), SAFE_STOP='FILE_BOUNDARY')

                actual = sha256_file(path, stop_check=tick)
                post = os.stat(path, follow_symlinks=False)
                if post.st_size != pre.st_size or post.st_mtime_ns != pre.st_mtime_ns:
                    raise Blocked('SOURCE_CHANGED_DURING_HASH:' + t['rel'])
                rec = {'i': i, 'rel': t['rel'], 'bytes': t['size'], 'expected': t['sha256'], 'actual': actual,
                       'match': actual == t['sha256']}
                append_record(jf, rec)
                committed[i] = rec
                done_bytes += t['size']
                hashed_this_session += 1
        mism = [committed[i] for i in sorted(committed) if not committed[i]['match']]
        return {'total_files': len(targets), 'total_bytes': total_bytes, 'committed_files': len(committed),
                'resumed_files': resumed, 'hashed_this_session': hashed_this_session,
                'matched': len(targets) - len(mism), 'mismatched': len(mism), 'mismatches': mism[:200],
                'per_set': plan['per_set'], 'set_roots': plan['set_roots'], 'journal': str(jpath),
                'journal_torn_tail_repaired': jinfo['torn_tail'], 'lock_reclaimed': lock.reclaimed,
                'manifest_columns': manifest['columns']}
    finally:
        lock.release()


# ------------------------------------------------------------------ selftest

def selftest(work: Path) -> dict:
    checks = {}
    sets = ('SET_A_' + 'X' * 3, 'MINOTAURO_SYNTH', 'SET_C')
    def build(root: Path):
        payload = root / 'ARQUIVO_FRIO' / 'TOP4_V001' / 'PAYLOAD'
        rows = []
        for si, sname in enumerate(sets):
            base = payload / ('PerseuRuns' if si != 1 else 'MinotauroRuns') / sname
            for k in range(3):
                sub = base / ('d%d' % (k % 2))
                sub.mkdir(parents=True, exist_ok=True)
                data = (f'{sname}-{k}-' * (k + 1)).encode()
                (sub / f'f{k}.bin').write_bytes(data)
                rows.append((f'D:\\PerseuRuns\\{sname}\\d{k % 2}\\f{k}.bin', len(data), hashlib.sha256(data).hexdigest().upper()))
        return payload, rows
    def manifest_file(path: Path, rows, header=('path', 'size_bytes', 'sha256')) -> tuple[str, int]:
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator='\r\n')
        w.writerow(header)
        for r in rows:
            w.writerow(r)
        b = b'\xef\xbb\xbf' + buf.getvalue().encode('utf-8')
        path.write_bytes(b)
        return hashlib.sha256(b).hexdigest().upper(), sum(r[1] for r in rows if isinstance(r[1], int))
    def expect_block(fn, prefix):
        try:
            fn()
        except Blocked as exc:
            if not str(exc).startswith(prefix):
                raise AssertionError(f'{prefix}!={exc}')
            return str(exc)
        raise AssertionError('ACCEPTED_' + prefix)

    root = work / 'vol'
    payload, rows = build(root)
    mpath = work / 'm.csv'
    msha, mbytes = manifest_file(mpath, rows)
    man = load_manifest(mpath, msha, len(rows), mbytes)
    checks['manifest_schema_introspection'] = man['columns'] == {'path': 'path', 'size': 'size_bytes', 'sha': 'sha256'}
    expect_block(lambda: load_manifest(mpath, '0' * 64, len(rows), mbytes), 'MANIFEST_SHA_MISMATCH')
    expect_block(lambda: load_manifest(mpath, msha, len(rows) + 1, mbytes), 'MANIFEST_ROW_COUNT')
    expect_block(lambda: load_manifest(mpath, msha, len(rows), mbytes + 1), 'MANIFEST_TOTAL_BYTES')
    amb = work / 'amb.csv'
    asha, _ = manifest_file(amb, [r + (r[2],) for r in rows], header=('path', 'bytes', 'sha256', 'hash'))
    expect_block(lambda: load_manifest(amb, asha, len(rows), mbytes), 'MANIFEST_SCHEMA_UNRESOLVED_SHA_2')
    nos = work / 'nosize.csv'
    nsha, _ = manifest_file(nos, [(r[0], r[2]) for r in rows], header=('path', 'sha256'))
    expect_block(lambda: load_manifest(nos, nsha, len(rows), mbytes), 'MANIFEST_SCHEMA_UNRESOLVED_SIZE_0')
    dup = work / 'dup.csv'
    dsha, dbytes = manifest_file(dup, rows + [rows[0]])
    expect_block(lambda: load_manifest(dup, dsha, len(rows) + 1, dbytes), 'MANIFEST_DUPLICATE_PATH')
    checks['manifest_negatives'] = True
    state = work / 'state'
    # resume: stop after 4 files, then resume without re-hashing committed files
    try:
        readback(payload, man, state, 'P' * 64, sets, root, stop_after_files=4)
        raise AssertionError('STOP_NOT_RAISED')
    except SafeStop:
        pass
    jl = (state / 'JOURNAL.jsonl').read_bytes().split(b'\n')
    checks['safe_stop_journal_4_commits'] = len([x for x in jl if x]) == 5 and not (state / 'LOCK.json').exists()
    with open(state / 'JOURNAL.jsonl', 'ab') as f:
        f.write(b'{"i":4,"rel":"torn')  # simulated crash in the middle of an append
    res = readback(payload, man, state, 'P' * 64, sets, root)
    checks['resume_no_rehash'] = res['resumed_files'] == 4 and res['hashed_this_session'] == len(rows) - 4
    checks['torn_tail_repaired'] = res['journal_torn_tail_repaired'] is True and any(state.glob('JOURNAL.torn_*.jsonl'))
    checks['pass_all_match'] = res['matched'] == len(rows) and res['mismatched'] == 0 and res['committed_files'] == len(rows)
    res2 = readback(payload, man, state, 'P' * 64, sets, root)
    checks['idempotent_rerun_zero_hash'] = res2['hashed_this_session'] == 0 and res2['matched'] == len(rows)
    expect_block(lambda: readback(payload, man, state, 'Q' * 64, sets, root), 'JOURNAL_IDENTITY_MISMATCH_PAYLOAD_SHA256')
    # live lock (this process) blocks; stale lock (dead pid) is reclaimed and archived
    (state / 'LOCK.json').write_text(json.dumps({'pid': os.getpid()}), encoding='utf-8')
    expect_block(lambda: readback(payload, man, state, 'P' * 64, sets, root), 'STATE_LOCK_HELD_BY_LIVE_PID')
    (state / 'LOCK.json').unlink()
    (state / 'LOCK.json').write_text(json.dumps({'pid': 4194302}), encoding='utf-8')
    r3 = readback(payload, man, state, 'P' * 64, sets, root)
    checks['stale_lock_reclaimed'] = r3['lock_reclaimed'] == {'pid': 4194302} and any(state.glob('LOCK.stale_*.json'))
    # duplicate commit in journal is never trusted
    dj = work / 'state_dup'
    dj.mkdir()
    lines = (state / 'JOURNAL.jsonl').read_bytes().split(b'\n')
    (dj / 'JOURNAL.jsonl').write_bytes(b'\n'.join(lines[:3] + [lines[2], b'']))
    expect_block(lambda: readback(payload, man, dj, 'P' * 64, sets, root), 'JOURNAL_DUPLICATE_COMMIT')
    # content mismatch -> FAIL (counted), size and exact-set divergences -> BLOCKED before hashing
    victim = payload / 'PerseuRuns' / sets[0] / 'd0' / 'f0.bin'
    original = victim.read_bytes()
    victim.write_bytes(bytes([original[0] ^ 1]) + original[1:])
    r4 = readback(payload, man, work / 'state_mm', 'P' * 64, sets, root)
    checks['content_mismatch_counted'] = r4['mismatched'] == 1 and r4['mismatches'][0]['rel'].endswith('d0/f0.bin')
    victim.write_bytes(original + b'x')
    expect_block(lambda: readback(payload, man, work / 'state_sz', 'P' * 64, sets, root), 'SIZE_MISMATCH_1')
    victim.write_bytes(original)
    (victim.parent / 'EXTRA.bin').write_bytes(b'e')
    expect_block(lambda: readback(payload, man, work / 'state_ex', 'P' * 64, sets, root), 'EXACT_SET_MISMATCH_MISSING_0_EXTRA_1')
    (victim.parent / 'EXTRA.bin').unlink()
    os.rename(victim, victim.with_name('moved.bin'))
    expect_block(lambda: readback(payload, man, work / 'state_mi', 'P' * 64, sets, root), 'EXACT_SET_MISMATCH_MISSING_1_EXTRA_1')
    os.rename(victim.with_name('moved.bin'), victim)
    expect_block(lambda: readback(payload, man, work / 'state_ns', 'P' * 64, sets + ('ABSENT_SET',), root), 'SET_ROOT_CARDINALITY_0')
    try:
        link = victim.parent / 'LNK'
        os.symlink(victim.parent, link, target_is_directory=True)
        expect_block(lambda: readback(payload, man, work / 'state_ln', 'P' * 64, sets, root), 'PAYLOAD_REPARSE_REFUSED')
        os.unlink(link)
        checks['reparse_refused'] = True
    except OSError:
        checks['reparse_refused'] = 'SKIPPED_SYMLINK_NOT_CREATABLE'
    big = [(f'D:\\PerseuRuns\\{sets[0]}\\b{i}.bin', 3 * 1024 ** 3, 'A' * 64) for i in range(2)]
    bsha, bbytes = manifest_file(work / 'big.csv', big)
    checks['int64_totals_over_2gib'] = load_manifest(work / 'big.csv', bsha, 2, bbytes)['total_bytes'] == 6 * 1024 ** 3
    checks['binding_negatives'] = all([
        expect_block(lambda: bind_hd1({'disks': [], 'partitions': []}), 'HD1_SERIAL_CARDINALITY_0'),
        expect_block(lambda: bind_hd1({'disks': [{'Number': 1, 'FriendlyName': 'WDC WD5000AAKX-003CA0', 'SerialNumber': HD2_SERIAL,
                                                  'Size': 500107862016, 'OperationalStatus': 'Online'}], 'partitions': []}), 'HD1_SERIAL_CARDINALITY_0'),
        expect_block(lambda: bind_hd1({'disks': [{'Number': 4, 'FriendlyName': HD1_MODEL, 'SerialNumber': HD1_SERIAL, 'Size': HD1_BYTES,
                                                  'OperationalStatus': 'Offline'}], 'partitions': []}), 'HD1_NOT_ONLINE'),
    ])
    good = {'disks': [{'Number': 4, 'FriendlyName': HD1_MODEL, 'SerialNumber': ' ' + HD1_SERIAL, 'Size': HD1_BYTES,
                       'OperationalStatus': 'Online', 'IsReadOnly': True}], 'partitions': [{'DiskNumber': 4, 'DriveLetter': 'G'}]}
    checks['binding_positive'] = bind_hd1(good)['drive_letter'] == 'G'
    bad = [k for k, v in checks.items() if v is not True and not str(v).startswith('SKIPPED')]
    if bad:
        raise AssertionError('SELFTEST_FAILED:' + ','.join(bad))
    return checks


# ------------------------------------------------------------------ CLI

def fixture_child(kind: str, out: Path | None, echo: list) -> int:
    if kind == 'pass':
        return emit('FIXTURE_PASS', out, fixture=kind)
    if kind == 'blocked':
        return emit('FIXTURE_BLOCKED', out, fixture=kind)
    if kind == 'fail':
        return emit('FAIL_READBACK_MISMATCH', out, fixture=kind)
    if kind == 'safe-stop':
        return emit('SAFE_STOP', out, fixture=kind)
    if kind == 'contradict':
        return emit('FIXTURE_BLOCKED', out, exit_code=0, fixture=kind)
    if kind == 'nofile':
        return emit('FIXTURE_PASS', None, fixture=kind)
    if kind == 'argv-echo':
        return emit('FIXTURE_PASS', out, fixture=kind, argv=list(echo))
    if kind == 'sleep':
        time.sleep(6.0)
        return emit('FIXTURE_PASS', out, fixture=kind)
    body = b'not-json\n' if kind == 'malformed' else (
        b'\xef\xbb\xbf' + json.dumps({'RESULT': 'FIXTURE_PASS', 'EXIT_CODE': 0}).encode('utf-8') + b'\n')
    if out is not None:
        atomic_write_new(out, body)
    sys.stdout.write(body.decode('utf-8', errors='replace'))
    sys.stdout.flush()
    return 0


def payload_sha() -> str:
    return hashlib.sha256(Path(__file__).resolve(strict=True).read_bytes()).hexdigest().upper()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='PERSEU HD1 TOP4 full SHA readback V001 (SOURCE_ONLY)')
    m = ap.add_mutually_exclusive_group(required=True)
    m.add_argument('--selftest', action='store_true')
    m.add_argument('--readback', action='store_true')
    m.add_argument('--fixture-child', choices=('pass', 'blocked', 'fail', 'safe-stop', 'contradict', 'malformed', 'nofile',
                                                'bom', 'sleep', 'argv-echo'), help=argparse.SUPPRESS)
    ap.add_argument('--echo', action='append', default=[], help=argparse.SUPPRESS)
    ap.add_argument('--require-readonly', action='store_true')
    ap.add_argument('--out-json')
    ap.add_argument('--report-json')
    ap.add_argument('--snapshot')
    ap.add_argument('--state-root')
    ap.add_argument('--work-dir')
    a = ap.parse_args(argv)
    out = None
    try:
        out = validate_new_path(a.out_json, 'OUT_JSON')
        if a.fixture_child:
            return fixture_child(a.fixture_child, out, a.echo)
        if out is None:
            raise Blocked('OUT_JSON_REQUIRED')
        codecs_ok = codec_check()
        if a.selftest:
            if not a.work_dir or not Path(a.work_dir).is_dir():
                raise Blocked('WORK_DIR_REQUIRED')
            with tempfile.TemporaryDirectory(prefix='top4_st_', dir=a.work_dir, ignore_cleanup_errors=True) as td:
                checks = selftest(Path(td))
            return emit('PASS_SELFTEST_ONLY', out, checks=checks, codecs=codecs_ok, payload_sha256=payload_sha())
        if os.name != 'nt':
            return emit('BLOCKED', out, reason='WINDOWS_TARGET_REQUIRED')
        report = validate_new_path(a.report_json, 'REPORT_JSON')
        if report is None or not a.state_root or not a.snapshot:
            raise Blocked('READBACK_ARGS_REQUIRED')
        raw = Path(a.snapshot).read_bytes()
        if raw.startswith(b'\xef\xbb\xbf'):
            raise Blocked('SNAPSHOT_BOM_FORBIDDEN')
        binding = bind_hd1(json.loads(raw.decode('utf-8')))
        if a.require_readonly and binding.get('is_read_only') is not True:
            raise Blocked('D2_READONLY_ATTRIBUTE_DECLARED_BUT_DISK_NOT_READ_ONLY')
        vol = Path(binding['drive_letter'] + ':\\')
        payload = vol.joinpath(*PAYLOAD_SEGMENTS)
        man = load_manifest(Path(MANIFEST_PATH), MANIFEST_SHA256, 1530, 414020605824)
        psha = payload_sha()
        state = Path(a.state_root) / f'{HD1_SERIAL}_{MANIFEST_SHA256[:16]}_{psha[:16]}'
        try:
            res = readback(payload, man, state, psha, tuple(EXPECTED_SETS), vol)
        except SafeStop as exc:
            return emit('SAFE_STOP', out, reason=str(exc), binding=binding, state_dir=str(state), SAFE_TO_RERUN='YES_RESUMES')
        except KeyboardInterrupt:
            return emit('SAFE_STOP', out, reason='CTRL_C_FILE_NOT_COMMITTED', binding=binding, state_dir=str(state),
                        SAFE_TO_RERUN='YES_RESUMES')
        per_set_ok = all(res['per_set'][n] == {'files': f, 'bytes': b} for n, (f, b) in EXPECTED_SETS.items())
        full = dict(res, binding=binding, state_dir=str(state), per_set_expected_match=per_set_ok,
                    manifest_sha256=man['sha256'], payload_sha256=psha)
        atomic_write_new(report, (json.dumps(full, indent=1, sort_keys=True) + '\n').encode('utf-8'))
        fields = {k: res[k] for k in ('total_files', 'total_bytes', 'committed_files', 'resumed_files', 'hashed_this_session',
                                       'matched', 'mismatched')}
        fields.update(binding=binding, report_json=str(report), report_sha256=sha256_file(report),
                      per_set_expected_match=per_set_ok, codecs=codecs_ok, HD1_FULL_READBACK='COMPLETED')
        if res['mismatched'] == 0 and per_set_ok and res['committed_files'] == 1530:
            return emit('PASS_READBACK', out, HD1_CUSTODY_READBACK='PASS_1530_OF_1530', **fields)
        return emit('FAIL_READBACK_MISMATCH', out, reason='SHA_OR_SET_MISMATCH', **fields)
    except KeyboardInterrupt:
        return emit('SAFE_STOP', out, reason='CTRL_C_BEFORE_OR_BETWEEN_FILES', SAFE_TO_RERUN='YES_RESUMES')
    except Blocked as exc:
        return emit('BLOCKED', out, reason=str(exc))
    except Exception as exc:  # fail-closed: unexpected defect recorded, never PASS
        return emit('BLOCKED', out, reason=f'UNEXPECTED_{type(exc).__name__}:{exc}')


if __name__ == '__main__':
    raise SystemExit(main())
