#!/usr/bin/env python3
from __future__ import annotations

import argparse
import calendar
import csv
import ctypes
import hashlib
import math
import os
from pathlib import Path
import random
import shutil
import statistics
import struct
import sys
import tempfile
import time
import zipfile

MAGIC = b"PTS2G001"
FORMAT_VERSION = 1
CODEC_ID_ZSTD = 1
CODEC_LEVEL = 9
GROUP_TICKS = 262_144
SECTION_NAMES = ("TIME","MASK","BID","ASK","LAST","F6","F7","FLAGS","OFFSET")
SECTION_COUNT = len(SECTION_NAMES)

# Index layout:
# group_no u32, row_start i64, row_count u32,
# source_first i64, source_end i64, offset_seconds i64,
# alias u8, 3 reserved bytes, group_semantic_sha32, group_offset_sha32
GROUP_BASE_FMT = "<IqIqqqB3x32s32s"
GROUP_BASE_SIZE = struct.calcsize(GROUP_BASE_FMT)
# name8, payload_offset i64, raw_len i64, stored_len i64, raw_sha32
SECTION_FMT = "<8sqqq32s"
SECTION_SIZE = struct.calcsize(SECTION_FMT)
INDEX_ENTRY_SIZE = GROUP_BASE_SIZE + SECTION_COUNT * SECTION_SIZE

class Blocked(RuntimeError):
    pass

def sha256_bytes(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def fmt_eta(seconds: float) -> str:
    if not math.isfinite(seconds) or seconds < 0:
        seconds = 0
    t = int(math.ceil(seconds))
    d, rem = divmod(t, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    return f"{d}.{h:02d}.{m:02d}.{s:02d}"

def rss_bytes() -> int:
    if os.name == "nt":
        class PMC(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]
        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(pmc), pmc.cb
        )
        return int(pmc.WorkingSetSize) if ok else 0
    try:
        import resource
        v = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(v * 1024)
    except Exception:
        return 0

def require_zstd():
    try:
        from compression import zstd
    except Exception as e:
        raise Blocked("PYTHON_COMPRESSION_ZSTD_UNAVAILABLE") from e
    probe = (b"pegasus-tickstore-zstd-self-test-" * 1000)
    c = zstd.compress(probe, level=9)
    d = zstd.decompress(c)
    if d != probe:
        raise Blocked("PYTHON_ZSTD_SELF_TEST_MISMATCH")
    return zstd

def write_varuint(buf: bytearray, v: int) -> None:
    if v < 0:
        raise Blocked("VARUINT_NEGATIVE")
    while v >= 0x80:
        buf.append((v & 0x7F) | 0x80)
        v >>= 7
    buf.append(v)

def read_varuint(data: bytes, pos: int) -> tuple[int,int]:
    result = 0
    shift = 0
    start = pos
    for i in range(10):
        if pos >= len(data):
            raise Blocked("VARUINT_EOF")
        b = data[pos]
        pos += 1
        payload = b & 0x7F
        if i == 9 and payload > 1:
            raise Blocked("VARUINT_OVERFLOW")
        if i > 0 and (b & 0x80) == 0 and payload == 0:
            raise Blocked("NON_CANONICAL_VARUINT")
        result |= payload << shift
        if (b & 0x80) == 0:
            return result, pos
        shift += 7
    raise Blocked("VARUINT_OVERFLOW")

def zigzag_encode(v: int) -> int:
    return ((v << 1) ^ (v >> 63)) & ((1 << 64) - 1)

def zigzag_decode(v: int) -> int:
    return (v >> 1) ^ -(v & 1)

def parse_integer_decimal(tok: bytes) -> int:
    if not tok:
        raise Blocked("EMPTY_NUMERIC_TOKEN")
    neg = False
    if tok[:1] in (b"+", b"-"):
        neg = tok[:1] == b"-"
        tok = tok[1:]
        if not tok:
            raise Blocked("SIGN_ONLY_NUMERIC_TOKEN")
    if b"." in tok:
        if tok.count(b".") != 1:
            raise Blocked("MULTIPLE_DECIMAL_POINTS")
        ip, frac = tok.split(b".", 1)
        if not ip or not frac or any(c != 48 for c in frac):
            raise Blocked("NON_INTEGER_DECIMAL")
    else:
        ip = tok
    if not ip or any(c < 48 or c > 57 for c in ip):
        raise Blocked("BAD_INTEGER_TOKEN")
    v = int(ip)
    return -v if neg else v

def parse_long(tok: bytes) -> int:
    if not tok:
        raise Blocked("EMPTY_LONG_TOKEN")
    try:
        s = tok.decode("ascii")
    except UnicodeDecodeError as e:
        raise Blocked("NON_ASCII_LONG_TOKEN") from e
    if s[0] in "+-":
        if len(s) == 1 or not s[1:].isdigit():
            raise Blocked("BAD_LONG_TOKEN")
    elif not s.isdigit():
        raise Blocked("BAD_LONG_TOKEN")
    v = int(s)
    if v < -(1<<63) or v > (1<<63)-1:
        raise Blocked("LONG_OUT_OF_RANGE")
    return v

def midnight_epoch_from_datekey(date_key: int) -> int:
    y = date_key // 10000
    m = (date_key // 100) % 100
    d = date_key % 100
    return calendar.timegm((y,m,d,0,0,0))

def parse_text_time(tok: bytes, date_key: int, midnight_epoch: int) -> int:
    if len(tok) != 19:
        raise Blocked("BAD_TEXT_TIME_LENGTH")
    if not (tok[4:5]==b"." and tok[7:8]==b"." and tok[10:11]==b" "
            and tok[13:14]==b":" and tok[16:17]==b":"):
        raise Blocked("BAD_TEXT_TIME_SHAPE")
    try:
        y=int(tok[0:4]); mo=int(tok[5:7]); d=int(tok[8:10])
        h=int(tok[11:13]); mi=int(tok[14:16]); s=int(tok[17:19])
    except Exception as e:
        raise Blocked("BAD_TEXT_TIME_DIGITS") from e
    if y*10000+mo*100+d != date_key:
        raise Blocked("TEXT_DATEKEY_MISMATCH")
    if not (0 <= h <= 23 and 0 <= mi <= 59 and 0 <= s <= 59):
        raise Blocked("BAD_TEXT_CLOCK")
    return midnight_epoch + h*3600 + mi*60 + s

def parse_row(line: bytes, date_key: int, midnight_epoch: int):
    parts = line.split(b";")
    if len(parts) != 9:
        raise Blocked("FIELD_COUNT_NOT_9")
    if parts[0] != b"WIN@N":
        raise Blocked("BAD_SYMBOL")
    text_epoch = parse_text_time(parts[1], date_key, midnight_epoch)
    msc = parse_long(parts[2])
    bid = parse_integer_decimal(parts[3])
    ask = parse_integer_decimal(parts[4])
    last = parse_integer_decimal(parts[5])
    f6 = parse_integer_decimal(parts[6])
    f7 = parse_integer_decimal(parts[7])
    flags = parse_long(parts[8])
    if min(msc,bid,ask,last,f6,f7,flags) < 0:
        raise Blocked("NEGATIVE_VALUE_UNSUPPORTED")
    if ((bid and bid % 5) or (ask and ask % 5) or (last and last % 5)):
        raise Blocked("PRICE_NOT_MULTIPLE_OF_5")
    offset = msc//1000 - text_epoch
    return (msc,bid,ask,last,f6,f7,flags,offset)

def semantic_preamble(date_key: int) -> bytes:
    return b"WIN@N" + struct.pack("<i", date_key)

def group_preamble(date_key: int, group_no: int, row_start: int) -> bytes:
    return b"WIN@N" + struct.pack("<iIq", date_key, group_no, row_start)

def row_semantic_bytes(row) -> bytes:
    return struct.pack("<8q", *row)

def offset_bytes(v: int) -> bytes:
    return struct.pack("<q", v)

class GroupBuilder:
    def __init__(self, date_key: int, group_no: int, row_start: int):
        self.date_key=date_key
        self.group_no=group_no
        self.row_start=row_start
        self.time=bytearray()
        self.mask=bytearray()
        self.bid=bytearray()
        self.ask=bytearray()
        self.last=bytearray()
        self.f6=bytearray()
        self.f7=bytearray()
        self.flags=bytearray()
        self.offset_stream=bytearray()
        self.rows=0
        self.offset_seconds=None
        self.prev_time=None
        self.prev_bid=None
        self.prev_ask=None
        self.prev_last=None
        self.prev_source_offset=None
        self.alias=True
        self.first_source_offset=None
        self.block_end_source_offset=None
        self.group_sem=hashlib.sha256()
        self.group_sem.update(group_preamble(date_key,group_no,row_start))
        self.group_off=hashlib.sha256()

    def add(self, row, source_offset: int, line_end_offset: int):
        msc,bid,ask,last,f6,f7,flags,offsec=row
        if self.offset_seconds is None:
            self.offset_seconds=offsec
        elif offsec != self.offset_seconds:
            raise Blocked("OFFSET_NOT_CONSTANT_WITHIN_GROUP")
        if self.prev_time is None:
            write_varuint(self.time, msc)
        else:
            d=msc-self.prev_time
            if d < 0:
                raise Blocked("TIME_MSC_DECREASE")
            write_varuint(self.time,d)
        self.prev_time=msc

        m=0
        if bid>0:m|=1
        if ask>0:m|=2
        if last>0:m|=4
        self.mask.append(m)

        def wp(buf, value, attr):
            prev=getattr(self, attr)
            tick=value//5
            if prev is None:
                write_varuint(buf,tick)
            else:
                write_varuint(buf,zigzag_encode(tick-prev))
            setattr(self,attr,tick)
        if m&1: wp(self.bid,bid,"prev_bid")
        if m&2: wp(self.ask,ask,"prev_ask")
        if m&4: wp(self.last,last,"prev_last")

        write_varuint(self.f6,f6)
        write_varuint(self.f7,f7)
        write_varuint(self.flags,flags)
        if f6 != f7:
            self.alias=False

        if self.prev_source_offset is None:
            write_varuint(self.offset_stream,source_offset)
            self.first_source_offset=source_offset
        else:
            d=source_offset-self.prev_source_offset
            if d <= 0:
                raise Blocked("SOURCE_OFFSET_NOT_INCREASING")
            write_varuint(self.offset_stream,d)
        self.prev_source_offset=source_offset
        self.block_end_source_offset=line_end_offset

        rb=row_semantic_bytes(row)
        self.group_sem.update(rb)
        self.group_off.update(offset_bytes(source_offset))
        self.rows += 1

    def finalize(self, zstd):
        if self.rows <= 0:
            raise Blocked("EMPTY_GROUP")
        raws = {
            "TIME":bytes(self.time),
            "MASK":bytes(self.mask),
            "BID":bytes(self.bid),
            "ASK":bytes(self.ask),
            "LAST":bytes(self.last),
            "F6":bytes(self.f6),
            "F7":b"" if self.alias else bytes(self.f7),
            "FLAGS":bytes(self.flags),
            "OFFSET":bytes(self.offset_stream),
        }
        sections=[]
        for name in SECTION_NAMES:
            raw=raws[name]
            stored=b"" if len(raw)==0 else zstd.compress(raw, level=CODEC_LEVEL)
            sections.append({
                "name":name,
                "raw_len":len(raw),
                "stored_len":len(stored),
                "raw_sha":sha256_bytes(raw),
                "stored":stored,
            })
        return {
            "group_no":self.group_no,
            "row_start":self.row_start,
            "row_count":self.rows,
            "source_first":self.first_source_offset,
            "source_end":self.block_end_source_offset,
            "offset_seconds":self.offset_seconds,
            "alias":self.alias,
            "group_semantic_sha":self.group_sem.digest(),
            "group_offset_sha":self.group_off.digest(),
            "sections":sections,
        }

def load_contracts(path: Path):
    with path.open(newline="",encoding="utf-8") as f:
        rows=list(csv.DictReader(f))
    if not rows:
        raise Blocked("NO_SELECTED_CONTRACTS")
    return rows

def source_path(source_root: Path, c) -> Path:
    return source_root / f"WIN@N_ticks_{c['month_id']}.csv"

def snapshot(path: Path):
    st=path.stat()
    return (st.st_size, st.st_mtime_ns)

def encode_day(contract, source_root: Path, out_path: Path, zstd):
    src=source_path(source_root,contract)
    if not src.is_file():
        raise Blocked(f"SOURCE_MISSING:{src}")
    before=snapshot(src)

    date_key=int(contract["date_key"])
    expected_rows=int(contract["rows"])
    start=int(contract["first_offset"])
    end=int(contract["block_end_offset"])
    expected_bytes=int(contract["source_day_bytes"])
    if end-start != expected_bytes:
        raise Blocked("CONTRACT_DAY_BYTES_MISMATCH")

    midnight=midnight_epoch_from_datekey(date_key)
    day_sem=hashlib.sha256()
    day_sem.update(semantic_preamble(date_key))
    day_off=hashlib.sha256()

    groups=[]
    current=None
    total_rows=0
    first_offset=None
    last_line_start=None
    offset_seconds=None
    peak_rss=rss_bytes()
    t0=time.perf_counter()

    with src.open("rb", buffering=8*1024*1024) as f:
        f.seek(start)
        while f.tell() < end:
            line_start=f.tell()
            raw=f.readline()
            line_end=f.tell()
            if not raw:
                raise Blocked("UNEXPECTED_EOF_IN_DAY_SLICE")
            if line_end > end:
                raise Blocked("LINE_CROSSES_DAY_END")
            logical=raw
            if logical.endswith(b"\n"):
                logical=logical[:-1]
                if logical.endswith(b"\r"):
                    logical=logical[:-1]
            if not logical:
                raise Blocked("EMPTY_LINE")
            try:
                logical.decode("utf-8","strict")
            except UnicodeDecodeError as e:
                raise Blocked("INVALID_UTF8") from e

            row=parse_row(logical,date_key,midnight)
            if offset_seconds is None:
                offset_seconds=row[7]
            elif row[7] != offset_seconds:
                raise Blocked("OFFSET_CHANGE_IN_SELECTED_DAY")

            if current is None:
                current=GroupBuilder(date_key,len(groups),total_rows)

            current.add(row,line_start,line_end)
            day_sem.update(row_semantic_bytes(row))
            day_off.update(offset_bytes(line_start))

            if first_offset is None:
                first_offset=line_start
            last_line_start=line_start
            total_rows += 1

            if current.rows == GROUP_TICKS:
                groups.append(current.finalize(zstd))
                current=None

            if total_rows % 1_000_000 == 0:
                elapsed=time.perf_counter()-t0
                rate=(line_end-start)/elapsed if elapsed>0 else 0
                remain=end-line_end
                eta=remain/rate if rate>0 else 0
                print(
                    f"P4B_BUILD_PROGRESS DATE={date_key} ROWS={total_rows} "
                    f"PCT={100*(line_end-start)/(end-start):.2f} "
                    f"MIBPS={rate/1048576:.1f} ETA={fmt_eta(eta)}",
                    flush=True,
                )
            peak_rss=max(peak_rss,rss_bytes())

        if f.tell() != end:
            raise Blocked("DAY_END_OFFSET_NOT_EXACT")

    if current is not None:
        groups.append(current.finalize(zstd))

    build_seconds=time.perf_counter()-t0

    if total_rows != expected_rows:
        raise Blocked(f"ROW_COUNT_MISMATCH:{total_rows}:{expected_rows}")
    sem_hex=day_sem.hexdigest()
    off_hex=day_off.hexdigest()
    if sem_hex != contract["semantic_sha256"].lower():
        raise Blocked("SOURCE_SEMANTIC_SHA_MISMATCH")
    if off_hex != contract["offset_values_sha256"].lower():
        raise Blocked("SOURCE_OFFSET_SHA_MISMATCH")
    if first_offset != start:
        raise Blocked("FIRST_SOURCE_OFFSET_MISMATCH")
    if last_line_start != int(contract["last_offset"]):
        raise Blocked("LAST_SOURCE_OFFSET_MISMATCH")
    if offset_seconds != int(contract["offset_seconds_first"]):
        raise Blocked("OFFSET_SECONDS_CONTRACT_MISMATCH")

    # Header.
    header=bytearray()
    header += b"WIN@N"
    header += struct.pack("<I",FORMAT_VERSION)
    header += struct.pack("<i",date_key)
    header += struct.pack("<q",total_rows)
    header += struct.pack("<q",offset_seconds)
    header += struct.pack("<I",GROUP_TICKS)
    header += struct.pack("<I",len(groups))
    header += struct.pack("<BBBB",CODEC_ID_ZSTD,CODEC_LEVEL,SECTION_COUNT,0)
    header += bytes.fromhex(sem_hex)
    header += bytes.fromhex(off_hex)
    header += struct.pack("<qqq",start,end,expected_bytes)
    header=bytes(header)

    index_len=len(groups)*INDEX_ENTRY_SIZE
    payload_base=8+4+len(header)+32+8+index_len+32
    cursor=payload_base
    for g in groups:
        for s in g["sections"]:
            s["payload_offset"]=cursor
            cursor += s["stored_len"]

    index=bytearray()
    for g in groups:
        index += struct.pack(
            GROUP_BASE_FMT,
            g["group_no"],g["row_start"],g["row_count"],
            g["source_first"],g["source_end"],g["offset_seconds"],
            1 if g["alias"] else 0,
            g["group_semantic_sha"],g["group_offset_sha"],
        )
        for s in g["sections"]:
            name=s["name"].encode("ascii").ljust(8,b"\0")
            index += struct.pack(
                SECTION_FMT,name,s["payload_offset"],
                s["raw_len"],s["stored_len"],s["raw_sha"]
            )
    index=bytes(index)
    if len(index) != index_len:
        raise Blocked("INDEX_LENGTH_INTERNAL_MISMATCH")

    tmp=out_path.with_suffix(out_path.suffix+".partial")
    if tmp.exists(): tmp.unlink()
    try:
        with tmp.open("wb") as f:
            f.write(MAGIC)
            f.write(struct.pack("<I",len(header)))
            f.write(header)
            f.write(sha256_bytes(header))
            f.write(struct.pack("<Q",len(index)))
            f.write(index)
            f.write(sha256_bytes(index))
            for g in groups:
                for s in g["sections"]:
                    f.write(s["stored"])
        os.replace(tmp,out_path)
    finally:
        if tmp.exists(): tmp.unlink()

    after=snapshot(src)
    if after != before:
        raise Blocked("SOURCE_SNAPSHOT_CHANGED")

    return {
        "date_key":date_key,
        "rows":total_rows,
        "groups":len(groups),
        "source_bytes":expected_bytes,
        "container_bytes":out_path.stat().st_size,
        "semantic_sha256":sem_hex,
        "offset_values_sha256":off_hex,
        "build_seconds":build_seconds,
        "peak_rss_bytes":peak_rss,
        "source_snapshot":"PASS",
        "container_sha256":sha256_file(out_path),
    }

def parse_container(path: Path, expected_contract=None):
    size=path.stat().st_size
    with path.open("rb") as f:
        if f.read(8) != MAGIC:
            raise Blocked("BAD_MAGIC")
        x=f.read(4)
        if len(x)!=4: raise Blocked("HEADER_LEN_EOF")
        header_len=struct.unpack("<I",x)[0]
        if header_len <= 0 or header_len > 4096:
            raise Blocked("BAD_HEADER_LEN")
        header=f.read(header_len)
        hh=f.read(32)
        if len(header)!=header_len or len(hh)!=32:
            raise Blocked("HEADER_EOF")
        if sha256_bytes(header) != hh:
            raise Blocked("HEADER_SHA_MISMATCH")
        p=0
        symbol=header[p:p+5]; p+=5
        if symbol != b"WIN@N": raise Blocked("BAD_HEADER_SYMBOL")
        fmtver=struct.unpack_from("<I",header,p)[0]; p+=4
        if fmtver != FORMAT_VERSION: raise Blocked("BAD_FORMAT_VERSION")
        date_key=struct.unpack_from("<i",header,p)[0]; p+=4
        total_rows=struct.unpack_from("<q",header,p)[0]; p+=8
        offsec=struct.unpack_from("<q",header,p)[0]; p+=8
        group_ticks=struct.unpack_from("<I",header,p)[0]; p+=4
        group_count=struct.unpack_from("<I",header,p)[0]; p+=4
        codec_id,level,section_count,reserved=struct.unpack_from("<BBBB",header,p); p+=4
        sem=header[p:p+32]; p+=32
        offsha=header[p:p+32]; p+=32
        source_first,source_end,source_bytes=struct.unpack_from("<qqq",header,p); p+=24
        if p != len(header): raise Blocked("HEADER_NOT_EXACT")
        if codec_id != CODEC_ID_ZSTD or level != CODEC_LEVEL:
            raise Blocked("UNSUPPORTED_CODEC_HEADER")
        if section_count != SECTION_COUNT or reserved != 0:
            raise Blocked("BAD_HEADER_SECTION_META")
        if group_ticks != GROUP_TICKS:
            raise Blocked("BAD_GROUP_TICKS")
        if total_rows <= 0 or group_count <= 0:
            raise Blocked("EMPTY_HEADER")
        if source_end-source_first != source_bytes:
            raise Blocked("HEADER_SOURCE_BYTES_MISMATCH")

        ib=f.read(8)
        if len(ib)!=8: raise Blocked("INDEX_LEN_EOF")
        index_len=struct.unpack("<Q",ib)[0]
        if index_len != group_count*INDEX_ENTRY_SIZE:
            raise Blocked("INDEX_LEN_NOT_FIXED_EXPECTED")
        index=f.read(index_len)
        ih=f.read(32)
        if len(index)!=index_len or len(ih)!=32:
            raise Blocked("INDEX_EOF")
        if sha256_bytes(index) != ih:
            raise Blocked("INDEX_SHA_MISMATCH")
        payload_base=f.tell()

    groups=[]
    pos=0
    expected_row_start=0
    expected_source_first=source_first
    expected_payload=payload_base
    for gi in range(group_count):
        entry_start=pos
        vals=struct.unpack_from(GROUP_BASE_FMT,index,pos); pos+=GROUP_BASE_SIZE
        group_no,row_start,row_count,g_src_first,g_src_end,g_offsec,alias,group_sem,group_off=vals
        if group_no != gi: raise Blocked("GROUP_NO_MISMATCH")
        if row_start != expected_row_start: raise Blocked("ROW_START_GAP_OR_OVERLAP")
        if row_count <= 0 or row_count > GROUP_TICKS: raise Blocked("BAD_GROUP_ROW_COUNT")
        if gi < group_count-1 and row_count != GROUP_TICKS:
            raise Blocked("NONFINAL_GROUP_NOT_FULL")
        if g_src_first != expected_source_first: raise Blocked("SOURCE_GROUP_GAP_OR_OVERLAP")
        if g_src_end <= g_src_first: raise Blocked("BAD_GROUP_SOURCE_RANGE")
        if g_offsec != offsec: raise Blocked("GROUP_OFFSET_SECONDS_MISMATCH")
        if alias not in (0,1): raise Blocked("BAD_ALIAS_FLAG")
        sections=[]
        for si,name in enumerate(SECTION_NAMES):
            sec_start=pos
            n,payload_off,raw_len,stored_len,raw_sha=struct.unpack_from(SECTION_FMT,index,pos)
            pos+=SECTION_SIZE
            n=n.rstrip(b"\0").decode("ascii")
            if n != name: raise Blocked("SECTION_NAME_OR_ORDER_MISMATCH")
            if raw_len < 0 or stored_len < 0: raise Blocked("NEGATIVE_SECTION_LENGTH")
            if payload_off != expected_payload: raise Blocked("PAYLOAD_GAP_OR_OVERLAP")
            if alias and name=="F7" and (raw_len != 0 or stored_len != 0):
                raise Blocked("ALIAS_F7_NOT_EMPTY")
            if (not alias) and name=="F7" and raw_len == 0:
                raise Blocked("NONALIAS_F7_EMPTY")
            if raw_len == 0 and stored_len != 0:
                raise Blocked("ZERO_RAW_NONZERO_STORED")
            if raw_len != 0 and stored_len <= 0:
                raise Blocked("NONZERO_RAW_EMPTY_STORED")
            sections.append({
                "name":name,"payload_offset":payload_off,
                "raw_len":raw_len,"stored_len":stored_len,"raw_sha":raw_sha,
                "index_offset":sec_start,
            })
            expected_payload += stored_len
        groups.append({
            "group_no":group_no,"row_start":row_start,"row_count":row_count,
            "source_first":g_src_first,"source_end":g_src_end,
            "offset_seconds":g_offsec,"alias":bool(alias),
            "group_semantic_sha":group_sem,"group_offset_sha":group_off,
            "sections":sections,"index_offset":entry_start,
        })
        expected_row_start += row_count
        expected_source_first=g_src_end

    if pos != len(index): raise Blocked("INDEX_NOT_EXACT")
    if expected_row_start != total_rows: raise Blocked("TOTAL_ROWS_INDEX_MISMATCH")
    if expected_source_first != source_end: raise Blocked("SOURCE_END_INDEX_MISMATCH")
    if expected_payload != size: raise Blocked("TRAILING_OR_TRUNCATED_PAYLOAD")

    h={
        "date_key":date_key,"total_rows":total_rows,"offset_seconds":offsec,
        "group_ticks":group_ticks,"group_count":group_count,
        "semantic_sha":sem,"offset_sha":offsha,
        "source_first":source_first,"source_end":source_end,"source_bytes":source_bytes,
        "header_len":header_len,"header":header,"header_hash_offset":8+4+header_len,
        "index_len":index_len,"index":index,
        "index_offset":8+4+header_len+32+8,
        "index_hash_offset":8+4+header_len+32+8+index_len,
        "payload_base":payload_base,"groups":groups,"file_size":size,
    }
    if expected_contract is not None:
        if date_key != int(expected_contract["date_key"]): raise Blocked("DATEKEY_CONTRACT")
        if total_rows != int(expected_contract["rows"]): raise Blocked("ROWS_CONTRACT")
        if sem.hex() != expected_contract["semantic_sha256"].lower(): raise Blocked("SEMANTIC_CONTRACT")
        if offsha.hex() != expected_contract["offset_values_sha256"].lower(): raise Blocked("OFFSET_SHA_CONTRACT")
        if source_first != int(expected_contract["first_offset"]): raise Blocked("SOURCE_FIRST_CONTRACT")
        if source_end != int(expected_contract["block_end_offset"]): raise Blocked("SOURCE_END_CONTRACT")
        if offsec != int(expected_contract["offset_seconds_first"]): raise Blocked("OFFSET_SECONDS_CONTRACT")
    return h

def decode_group(path: Path, parsed, gi: int, zstd, day_sem=None, day_off=None):
    g=parsed["groups"][gi]
    raw={}
    with path.open("rb") as f:
        for s in g["sections"]:
            f.seek(s["payload_offset"])
            stored=f.read(s["stored_len"])
            if len(stored)!=s["stored_len"]: raise Blocked("PAYLOAD_EOF")
            if s["raw_len"]==0:
                x=b""
            else:
                try:
                    x=zstd.decompress(stored)
                except Exception as e:
                    raise Blocked("ZSTD_DECOMPRESS_FAIL_"+s["name"]) from e
            if len(x)!=s["raw_len"]: raise Blocked("RAW_LENGTH_MISMATCH_"+s["name"])
            if sha256_bytes(x)!=s["raw_sha"]: raise Blocked("RAW_SHA_MISMATCH_"+s["name"])
            raw[s["name"]]=x

    gp_sem=hashlib.sha256()
    gp_sem.update(group_preamble(parsed["date_key"],g["group_no"],g["row_start"]))
    gp_off=hashlib.sha256()

    pos={n:0 for n in SECTION_NAMES}
    prev_time=None
    prev_bid=prev_ask=prev_last=None
    prev_source=None
    first_source=None
    last_source=None

    def rv(name):
        v,p2=read_varuint(raw[name],pos[name])
        pos[name]=p2
        return v

    for i in range(g["row_count"]):
        tv=rv("TIME")
        if prev_time is None:
            msc=tv
        else:
            msc=prev_time+tv
        if msc > (1<<63)-1: raise Blocked("TIME_OUT_OF_RANGE")
        prev_time=msc

        if pos["MASK"] >= len(raw["MASK"]): raise Blocked("MASK_EOF")
        m=raw["MASK"][pos["MASK"]]; pos["MASK"]+=1
        if m & 0xF8: raise Blocked("INVALID_MASK_BITS")

        def rp(name, prev):
            v=rv(name)
            if prev is None:
                tick=v
            else:
                tick=prev+zigzag_decode(v)
            if tick < 0 or tick > (1<<63)-1: raise Blocked("PRICE_TICK_OUT_OF_RANGE")
            return tick
        bid=ask=last=0
        if m&1:
            prev_bid=rp("BID",prev_bid); bid=prev_bid*5
        if m&2:
            prev_ask=rp("ASK",prev_ask); ask=prev_ask*5
        if m&4:
            prev_last=rp("LAST",prev_last); last=prev_last*5

        f6=rv("F6")
        if g["alias"]:
            f7=f6
        else:
            f7=rv("F7")
        flags=rv("FLAGS")
        for v in (f6,f7,flags):
            if v > (1<<63)-1: raise Blocked("VALUE_OUT_OF_RANGE")

        ov=rv("OFFSET")
        if prev_source is None:
            src_off=ov
            first_source=src_off
        else:
            src_off=prev_source+ov
        if prev_source is not None and src_off <= prev_source:
            raise Blocked("DECODED_SOURCE_OFFSET_NOT_INCREASING")
        prev_source=src_off
        last_source=src_off

        row=(msc,bid,ask,last,f6,f7,flags,g["offset_seconds"])
        rb=row_semantic_bytes(row)
        gp_sem.update(rb)
        gp_off.update(offset_bytes(src_off))
        if day_sem is not None: day_sem.update(rb)
        if day_off is not None: day_off.update(offset_bytes(src_off))

    for n in SECTION_NAMES:
        if g["alias"] and n=="F7":
            if len(raw[n]) != 0: raise Blocked("ALIAS_F7_DECODE_NONEMPTY")
        elif pos[n] != len(raw[n]):
            raise Blocked("STREAM_NOT_EXACT_"+n)
    if gp_sem.digest()!=g["group_semantic_sha"]: raise Blocked("GROUP_SEMANTIC_SHA_MISMATCH")
    if gp_off.digest()!=g["group_offset_sha"]: raise Blocked("GROUP_OFFSET_SHA_MISMATCH")
    if first_source!=g["source_first"]: raise Blocked("GROUP_SOURCE_FIRST_MISMATCH")
    if last_source is None or last_source >= g["source_end"]: raise Blocked("GROUP_LAST_SOURCE_RANGE")
    return g["row_count"]

def decode_full(path: Path, contract, zstd):
    parsed=parse_container(path,contract)
    sem=hashlib.sha256(); sem.update(semantic_preamble(parsed["date_key"]))
    off=hashlib.sha256()
    rows=0
    peak=rss_bytes()
    t0=time.perf_counter()
    for gi in range(parsed["group_count"]):
        rows += decode_group(path,parsed,gi,zstd,sem,off)
        peak=max(peak,rss_bytes())
    sec=time.perf_counter()-t0
    if rows != parsed["total_rows"]: raise Blocked("FULL_DECODE_ROWS")
    if sem.digest()!=parsed["semantic_sha"]: raise Blocked("FULL_SEMANTIC_SHA_MISMATCH")
    if off.digest()!=parsed["offset_sha"]: raise Blocked("FULL_OFFSET_SHA_MISMATCH")
    return {
        "decode_seconds":sec,"decode_rows":rows,"peak_rss_bytes":peak,
    }

def percentile95(xs):
    if not xs:return float("nan")
    ys=sorted(xs)
    return ys[max(0,math.ceil(.95*len(ys))-1)]

def benchmark_random(path: Path, contract, zstd, rounds=3):
    parsed=parse_container(path,contract)
    results=[]
    peak=rss_bytes()
    for r in range(rounds):
        order=list(range(parsed["group_count"]))
        random.Random(0x50474200 + r).shuffle(order)
        for pos,gi in enumerate(order):
            t=time.perf_counter()
            decode_group(path,parsed,gi,zstd)
            sec=time.perf_counter()-t
            peak=max(peak,rss_bytes())
            results.append(sec)
    return {
        "rounds":rounds,
        "measurements":len(results),
        "median_seconds":statistics.median(results),
        "p95_seconds":percentile95(results),
        "max_seconds":max(results),
        "peak_rss_bytes":peak,
    }

def mutate_byte(src: Path, dst: Path, offset: int):
    shutil.copyfile(src,dst)
    with dst.open("r+b") as f:
        f.seek(offset)
        b=f.read(1)
        if len(b)!=1: raise Blocked("MUTATE_OFFSET_EOF")
        f.seek(offset)
        f.write(bytes([b[0]^0x01]))

def expect_reject(path: Path, contract, zstd, full=True):
    try:
        if full: decode_full(path,contract,zstd)
        else: parse_container(path,contract)
    except Exception as e:
        return True, type(e).__name__+":"+str(e)
    return False,"UNEXPECTED_PASS"

def recompute_index_hash(path: Path, parsed):
    with path.open("r+b") as f:
        f.seek(parsed["index_offset"])
        idx=f.read(parsed["index_len"])
        f.seek(parsed["index_hash_offset"])
        f.write(sha256_bytes(idx))

def recompute_header_hash(path: Path, parsed):
    with path.open("r+b") as f:
        f.seek(12)
        header=f.read(parsed["header_len"])
        f.seek(parsed["header_hash_offset"])
        f.write(sha256_bytes(header))

def fault_matrix(base: Path, contract, temp_dir: Path, zstd):
    parsed=parse_container(base,contract)
    target=parsed["group_count"]//2
    rows=[]
    counter=0

    def add(case,passed,reason,neighbors="NA"):
        rows.append({
            "case":case,"expected":"REJECT","pass":"YES" if passed else "NO",
            "reason":reason,"neighbor_independence":neighbors,
        })
        if not passed:
            raise Blocked("FAULT_CASE_FAILED:"+case+":"+reason)

    # Simple metadata corruption.
    cases=[
        ("HEADER_BYTE_FLIP",12+min(10,parsed["header_len"]-1),True),
        ("HEADER_HASH_FLIP",parsed["header_hash_offset"],True),
        ("INDEX_BYTE_FLIP",parsed["index_offset"]+min(10,parsed["index_len"]-1),True),
        ("INDEX_HASH_FLIP",parsed["index_hash_offset"],True),
    ]
    for name,off,_ in cases:
        p=temp_dir/f"fault_{counter}.pts"; counter+=1
        mutate_byte(base,p,off)
        ok,reason=expect_reject(p,contract,zstd)
        add(name,ok,reason)
        p.unlink()

    # Every nonempty payload section in middle group.
    for s in parsed["groups"][target]["sections"]:
        if s["stored_len"]==0:
            rows.append({
                "case":"PAYLOAD_"+s["name"]+"_FLIP",
                "expected":"SKIP_ALIAS_EMPTY","pass":"YES",
                "reason":"SECTION_EMPTY_BY_ALIAS","neighbor_independence":"NA",
            })
            continue
        p=temp_dir/f"fault_{counter}.pts"; counter+=1
        mutate_byte(base,p,s["payload_offset"] + s["stored_len"]//2)
        corrupted=parse_container(p,contract)
        try:
            decode_group(p,corrupted,target,zstd)
            target_rejected=False; reason="TARGET_UNEXPECTED_PASS"
        except Exception as e:
            target_rejected=True; reason=type(e).__name__+":"+str(e)
        neigh=[]
        for ngi in (target-1,target+1):
            if 0 <= ngi < corrupted["group_count"]:
                try:
                    decode_group(p,corrupted,ngi,zstd)
                    neigh.append(True)
                except Exception:
                    neigh.append(False)
        neighbors_ok=all(neigh) if neigh else True
        add("PAYLOAD_"+s["name"]+"_FLIP",
            target_rejected and neighbors_ok,reason,
            "PASS" if neighbors_ok else "FAIL")
        p.unlink()

    # Truncations.
    trunc_points=[
        ("TRUNCATE_MAGIC",4),
        ("TRUNCATE_HEADER",parsed["header_hash_offset"]-1),
        ("TRUNCATE_INDEX",parsed["index_hash_offset"]-1),
        ("TRUNCATE_MID_PAYLOAD",(parsed["payload_base"]+parsed["file_size"])//2),
        ("TRUNCATE_LAST_BYTE",parsed["file_size"]-1),
    ]
    for name,nbytes in trunc_points:
        p=temp_dir/f"fault_{counter}.pts"; counter+=1
        shutil.copyfile(base,p)
        with p.open("r+b") as f:f.truncate(max(0,nbytes))
        ok,reason=expect_reject(p,contract,zstd)
        add(name,ok,reason)
        p.unlink()

    # Trailing byte.
    p=temp_dir/f"fault_{counter}.pts"; counter+=1
    shutil.copyfile(base,p)
    with p.open("ab") as f:f.write(b"\x00")
    ok,reason=expect_reject(p,contract,zstd)
    add("TRAILING_BYTE",ok,reason)
    p.unlink()

    # Coherent header total_rows tamper + recomputed header hash.
    p=temp_dir/f"fault_{counter}.pts"; counter+=1
    shutil.copyfile(base,p)
    with p.open("r+b") as f:
        total_rows_off=12 + 5 + 4 + 4
        f.seek(total_rows_off)
        old=struct.unpack("<q",f.read(8))[0]
        f.seek(total_rows_off)
        f.write(struct.pack("<q",old+1))
    recompute_header_hash(p,parsed)
    ok,reason=expect_reject(p,None,zstd,full=False)
    add("COHERENT_HEADER_ROWS_TAMPER",ok,reason)
    p.unlink()

    # Coherent index row_count tamper + recomputed index hash.
    p=temp_dir/f"fault_{counter}.pts"; counter+=1
    shutil.copyfile(base,p)
    g=parsed["groups"][target]
    rowcount_abs=parsed["index_offset"] + g["index_offset"] + 4 + 8
    with p.open("r+b") as f:
        f.seek(rowcount_abs)
        old=struct.unpack("<I",f.read(4))[0]
        f.seek(rowcount_abs)
        f.write(struct.pack("<I",old+1))
    recompute_index_hash(p,parsed)
    ok,reason=expect_reject(p,None,zstd,full=False)
    add("COHERENT_INDEX_ROWCOUNT_TAMPER",ok,reason)
    p.unlink()

    # Coherent payload offset overlap + recomputed index hash.
    p=temp_dir/f"fault_{counter}.pts"; counter+=1
    shutil.copyfile(base,p)
    g=parsed["groups"][target]
    sec0=g["sections"][0]
    sec1=g["sections"][1]
    sec1_payload_abs=(
        parsed["index_offset"] + sec1["index_offset"] + 8
    )
    with p.open("r+b") as f:
        f.seek(sec1_payload_abs)
        f.write(struct.pack("<q",sec0["payload_offset"]))
    recompute_index_hash(p,parsed)
    ok,reason=expect_reject(p,None,zstd,full=False)
    add("COHERENT_INDEX_PAYLOAD_OVERLAP",ok,reason)
    p.unlink()

    return rows

def synthetic_source(path: Path):
    # Deliberately non-alias F7 in one row to exercise F7 physical payload.
    lines=[]
    date_key=20260923
    midnight=midnight_epoch_from_datekey(date_key)
    offs=[]
    sem=hashlib.sha256(); sem.update(semantic_preamble(date_key))
    oh=hashlib.sha256()
    with path.open("wb") as f:
        for i in range(1000):
            pos=f.tell(); offs.append(pos)
            sec=9*3600 + (i//20)
            h=sec//3600; mi=(sec%3600)//60; s=sec%60
            txt=f"2026.09.23 {h:02d}:{mi:02d}:{s:02d}"
            msc=(midnight+sec+10800)*1000 + (i%1000)
            bid=100000 if i%7==0 else 0
            ask=100005 if i%11==0 else 0
            last=100010+(i%5)*5
            f6=7
            f7=8 if i==500 else 7
            flags=2
            line=f"WIN@N;{txt};{msc};{bid};{ask};{last};{f6};{f7};{flags}\n".encode()
            f.write(line)
            row=(msc,bid,ask,last,f6,f7,flags,10800)
            sem.update(row_semantic_bytes(row)); oh.update(offset_bytes(pos))
    st=path.stat()
    return {
        "month_id":"SYNTH","date_key":str(date_key),"rows":"1000",
        "first_offset":"0","last_offset":str(offs[-1]),
        "block_end_offset":str(st.st_size),"source_day_bytes":str(st.st_size),
        "semantic_sha256":sem.hexdigest(),"offset_values_sha256":oh.hexdigest(),
        "offset_seconds_first":"10800","first_time_msc":"0","last_time_msc":"0",
    }

def run_self_test(zstd):
    td=Path(tempfile.mkdtemp(prefix="PEGASUS_P4B_SELFTEST_"))
    try:
        srcroot=td/"src"; srcroot.mkdir()
        src=srcroot/"WIN@N_ticks_SYNTH.csv"
        c=synthetic_source(src)
        out=td/"synth.pts2g"
        r=encode_day(c,srcroot,out,zstd)
        d=decode_full(out,c,zstd)
        p=parse_container(out,c)
        if p["groups"][0]["alias"]:
            raise Blocked("SYNTH_F7_NONALIAS_NOT_EXERCISED")
        fm=fault_matrix(out,c,td,zstd)
        if not all(x["pass"]=="YES" for x in fm):
            raise Blocked("SYNTH_FAULT_MATRIX_FAIL")
        print("P4B_RUNTIME_SELF_TEST=PASS", flush=True)
    finally:
        shutil.rmtree(td,ignore_errors=True)

def run(source_root: Path, contracts_path: Path, out_root: Path):
    zstd=require_zstd()
    run_self_test(zstd)

    contracts=load_contracts(contracts_path)
    out_root.mkdir(parents=True,exist_ok=True)
    work=out_root/"WORK"
    work.mkdir(exist_ok=True)

    baseline=[]
    containers={}
    snapshots={}
    overall_t0=time.perf_counter()

    for idx,c in enumerate(contracts,1):
        src=source_path(source_root,c)
        snapshots[c["month_id"]]=snapshot(src)
        container=work/f"{c['date_key']}.pts2g"
        print(
            f"P4B_DAY_START={c['date_key']} INDEX={idx}/{len(contracts)} "
            f"ROWS={c['rows']}", flush=True
        )
        # Reuse only after a complete semantic decode.
        if container.exists():
            try:
                dec=decode_full(container,c,zstd)
                enc={
                    "date_key":int(c["date_key"]),"rows":int(c["rows"]),
                    "groups":parse_container(container,c)["group_count"],
                    "source_bytes":int(c["source_day_bytes"]),
                    "container_bytes":container.stat().st_size,
                    "semantic_sha256":c["semantic_sha256"],
                    "offset_values_sha256":c["offset_values_sha256"],
                    "build_seconds":0.0,"peak_rss_bytes":rss_bytes(),
                    "source_snapshot":"PASS",
                    "container_sha256":sha256_file(container),
                }
                reused="YES"
            except Exception:
                container.unlink(missing_ok=True)
                enc=encode_day(c,source_root,container,zstd)
                dec=decode_full(container,c,zstd)
                reused="NO"
        else:
            enc=encode_day(c,source_root,container,zstd)
            dec=decode_full(container,c,zstd)
            reused="NO"

        parsed=parse_container(container,c)
        ratio=enc["source_bytes"]/enc["container_bytes"]
        bpt=enc["container_bytes"]/enc["rows"]
        row=dict(enc)
        row.update(dec)
        row["ratio_vs_csv"]=ratio
        row["bytes_per_tick"]=bpt
        row["reused"]=reused
        row["roundtrip"]="PASS"
        baseline.append(row)
        containers[c["date_key"]]=container
        print(
            f"P4B_DAY_PASS={c['date_key']} ROWS={enc['rows']} "
            f"GROUPS={enc['groups']} BPT={bpt:.6f} RATIO={ratio:.3f}",
            flush=True
        )

    # Fault matrix on the global-max activity day.
    fault_contract=next(c for c in contracts if c["date_key"]=="20211022")
    fault_rows=fault_matrix(containers["20211022"],fault_contract,work,zstd)

    # Random access benchmark on same largest day.
    ra=benchmark_random(containers["20211022"],fault_contract,zstd,rounds=3)

    # Source snapshot re-check.
    for c in contracts:
        src=source_path(source_root,c)
        if snapshot(src) != snapshots[c["month_id"]]:
            raise Blocked("SOURCE_MUTATION_DETECTED:"+c["month_id"])

    # Reports.
    baseline_path=out_root/"P4B_BASELINE.csv"
    with baseline_path.open("w",newline="",encoding="utf-8") as f:
        fields=list(baseline[0].keys())
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(baseline)

    fault_path=out_root/"P4B_FAULT_MATRIX.csv"
    with fault_path.open("w",newline="",encoding="utf-8") as f:
        fields=["case","expected","pass","reason","neighbor_independence"]
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(fault_rows)

    with (out_root/"P4B_RANDOM_ACCESS.csv").open("w",newline="",encoding="utf-8") as f:
        fields=list(ra.keys()); w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerow(ra)

    total_rows=sum(int(x["rows"]) for x in baseline)
    total_csv=sum(int(x["source_bytes"]) for x in baseline)
    total_cont=sum(int(x["container_bytes"]) for x in baseline)
    fault_pass=sum(1 for x in fault_rows if x["pass"]=="YES")
    fault_total=len(fault_rows)
    alias_skips=sum(1 for x in fault_rows if x["expected"]=="SKIP_ALIAS_EMPTY")

    summary=[
        "PEGASUS_TICKSTORE_V001_P4B_FINAL_FORMAT_HOMOLOGATION",
        "FORMAT_CANDIDATE=PTS2G001",
        "CODEC_CANDIDATE=ZSTD9",
        f"ROW_GROUP_TICKS={GROUP_TICKS}",
        f"SELECTED_DAYS={len(baseline)}",
        f"SELECTED_ROWS={total_rows}",
        f"SELECTED_SOURCE_BYTES={total_csv}",
        f"SELECTED_CONTAINER_BYTES={total_cont}",
        f"AGGREGATE_RATIO_VS_CSV={total_csv/total_cont:.9f}",
        f"AGGREGATE_BYTES_PER_TICK={total_cont/total_rows:.9f}",
        "FULL_SEMANTIC_ROUNDTRIP_ALL_DAYS=PASS",
        "FULL_OFFSET_ROUNDTRIP_ALL_DAYS=PASS",
        f"FAULT_CASES={fault_total}",
        f"FAULT_CASES_PASS={fault_pass}",
        f"FAULT_ALIAS_EMPTY_SKIPS={alias_skips}",
        "HEADER_CORRUPTION_GATE=PASS",
        "INDEX_CORRUPTION_GATE=PASS",
        "PAYLOAD_CORRUPTION_GATE=PASS",
        "TRUNCATION_GATE=PASS",
        "TRAILING_BYTES_GATE=PASS",
        "COHERENT_METADATA_TAMPER_GATE=PASS",
        "NEIGHBOR_INDEPENDENCE_GATE=PASS",
        f"RANDOM_ACCESS_MEASUREMENTS={ra['measurements']}",
        f"RANDOM_ACCESS_MEDIAN_SECONDS={ra['median_seconds']:.9f}",
        f"RANDOM_ACCESS_P95_SECONDS={ra['p95_seconds']:.9f}",
        f"RANDOM_ACCESS_MAX_SECONDS={ra['max_seconds']:.9f}",
        f"RANDOM_ACCESS_PEAK_RSS_BYTES={ra['peak_rss_bytes']}",
        "COLD_CACHE_CLAIM=NO",
        "SOURCE_MUTATION=NO",
        "FULL_HISTORY_SCAN=NO",
        "HISTORICAL_CONVERSION=NO",
        "FORMAT_PROMOTION=NO",
        "CODEC_PROMOTION=NO",
        "CSV_DELETION=NO",
        "WORK_ASTRA_FINAL_AUDIT_REQUIRED=YES",
        "P4B_HOMOLOGATION_GATE=PASS",
        "P4B_STATUS=PASS",
        "",
    ]
    (out_root/"P4B_SUMMARY.txt").write_text("\n".join(summary),encoding="utf-8")

    # Compact evidence before deleting temp containers.
    with (out_root/"P4B_CONTAINER_HASHES.csv").open("w",newline="",encoding="utf-8") as f:
        fields=["date_key","container_sha256","container_bytes"]
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for x in baseline:
            w.writerow({
                "date_key":x["date_key"],
                "container_sha256":x["container_sha256"],
                "container_bytes":x["container_bytes"],
            })

    # Clean temporary containers only after all reports were successfully written.
    for p in work.glob("*"):
        if p.is_file(): p.unlink()
    try: work.rmdir()
    except OSError: pass

    if work.exists():
        raise Blocked("TEMP_WORK_NOT_DELETED")

    print("P4B_STATUS=PASS",flush=True)
    print("P4B_HOMOLOGATION_GATE=PASS",flush=True)
    print("SOURCE_MUTATION=NO",flush=True)
    print("FULL_HISTORY_SCAN=NO",flush=True)
    print("HISTORICAL_CONVERSION=NO",flush=True)
    print("FORMAT_PROMOTION=NO",flush=True)
    print("CODEC_PROMOTION=NO",flush=True)
    print("CSV_DELETION=NO",flush=True)
    print("TEMP_FILES_DELETED=YES",flush=True)
    print("WORK_ASTRA_FINAL_AUDIT_REQUIRED=YES",flush=True)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--self-test",action="store_true")
    ap.add_argument("--run",action="store_true")
    ap.add_argument("--source-root")
    ap.add_argument("--contracts")
    ap.add_argument("--out-root")
    args=ap.parse_args()
    zstd=require_zstd()
    if args.self_test:
        run_self_test(zstd); return
    if args.run:
        if not args.source_root or not args.contracts or not args.out_root:
            raise Blocked("RUN_ARGS_MISSING")
        run(Path(args.source_root),Path(args.contracts),Path(args.out_root)); return
    raise Blocked("NO_MODE_SELECTED")

if __name__=="__main__":
    try:
        main()
    except Blocked as e:
        print("P4B_STATUS=BLOCKED",flush=True)
        print("REASON="+str(e),flush=True)
        raise SystemExit(2)
