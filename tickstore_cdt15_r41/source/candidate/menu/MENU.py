#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
menu.py  --  CLD_SRVJ_V1

Menu interativo do pipeline. Nao reimplementa nada: importa a lista ETAPAS
diretamente de GERAR_BASE_COMPLETA.py (a MESMA lista que o orquestrador usa),
entao nunca fica desatualizado em relacao a ela, e so monta a linha de
comando certa antes de chamar o proprio orquestrador via subprocess.

POR QUE --somente E NAO --pular
----------------------------------
Rodar uma etapa isolada usa `GERAR_BASE_COMPLETA.py --somente <chave>`, que
NAO grava PULADA em nenhuma outra etapa (ver o comentario de --somente em
GERAR_BASE_COMPLETA.py). Isolar uma etapa por aqui nunca corrompe o
checkpoint das demais.

USO (PowerShell, que abre em C:\Users\silvi)
---------------------------------------------
    cd "D:\Base CSV"
    py Scripts\Biblioteca\MENU.py
"""

from __future__ import annotations

import subprocess
import sys
import os
import re
import json
import hashlib
import stat
from pathlib import Path

try:
    from .paths import PATHS
except ImportError:  # execucao direta pelo BAT da raiz
    from paths import PATHS

SCRIPT_DIR = PATHS.BIBLIOTECA_ROOT
PROJECT_ROOT = PATHS.BASE_ROOT

sys.path.insert(0, str(SCRIPT_DIR))
try:
    from . import GERAR_BASE_COMPLETA as orq
except ImportError:  # execucao direta
    import GERAR_BASE_COMPLETA as orq


def escolher_base_dir() -> Path:
    padrao = str(PROJECT_ROOT)
    resp = input(f"Pasta da base [{padrao}]: ").strip()
    return Path(resp) if resp else Path(padrao)


def imprimir_cabecalho(base: Path) -> None:
    print("\n" * 2)
    print("=" * 78)
    print("MENU DO PIPELINE  --  CLD_SRVJ")
    print("=" * 78)
    print(f"base: {base}")
    print()


def imprimir_etapas() -> None:
    print("")
    print("ETAPAS DISPONIVEIS")
    print("-" * 78)
    for i, (chave, titulo, script, extra, minutos, *_r) in enumerate(orq.ETAPAS, 1):
        print(f"  {i:2}) {chave:18} {titulo:50} ~{minutos:>3} min")
    print("")


def escolher_indices(prompt: str, minimo: int = 1) -> list[int]:
    resp = input(prompt).strip()
    try:
        indices = [int(x) for x in resp.replace(" ", "").split(",") if x]
    except ValueError:
        return []
    if len(indices) < minimo:
        return []
    if any(i < 1 or i > len(orq.ETAPAS) for i in indices):
        return []
    return indices


def rodar(cmd: list) -> int:
    print(f"\n> {' '.join(str(c) for c in cmd)}\n")
    try:
        return subprocess.call(cmd)
    except KeyboardInterrupt:
        print("\nInterrompido com Ctrl+C.")
        return 130


def _reject_deployment_reparse(path: Path) -> None:
    """Deny symlinks and Windows junctions anywhere in the deployment path.

    This static check does not by itself prove atomic path/handle identity under
    concurrent mutation; final Windows admission remains separately gated.
    """
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(info.st_mode) or
                (getattr(info, 'st_file_attributes', 0) &
                 getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400))):
            raise ValueError('DEPLOYMENT_REPARSE')


def _tickstore_committed_deployment(active_path: Path, menu_path: Path) -> dict:
    """Fail-closed MENU consumer admission for proposed two-artifact commit.

    The producer must create exact transaction/PLAN.json and JOURNAL.json
    under TICKSTORE/MENU_TRANSACTION. This reader alone does not prove a
    trusted writer, ACL/lease, concurrent identity, or global atomicity.
    """
    def _pinned_read(p: Path) -> bytes:
        _reject_deployment_reparse(p)
        if not p.is_file():
            raise ValueError('TX_REQUIRED_FILE_MISSING')
        st = p.stat()
        if st.st_nlink != 1:
            raise ValueError('TX_HARDLINK')
        return p.read_bytes()

    tx = active_path.parent / 'MENU_TRANSACTION'
    plan_path, journal_path = tx / 'PLAN.json', tx / 'JOURNAL.json'
    plan_raw = _pinned_read(plan_path)
    journal_raw = _pinned_read(journal_path)
    try:
        plan = json.loads(plan_raw)
        journal = json.loads(journal_raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError('TX_RECORD_INVALID') from exc
    fields = {'schema', 'menu_before_sha256', 'menu_after_sha256',
              'active_before_sha256', 'active_after_sha256'}
    if not isinstance(plan, dict) or set(plan) != fields or plan['schema'] != 'TICKSTORE_MENU_INSTALL_TRANSACTION_V001':
        raise ValueError('TX_PLAN_SCHEMA')
    if not isinstance(journal, dict) or set(journal) != {'schema', 'plan_sha256', 'phase'}:
        raise ValueError('TX_JOURNAL_SCHEMA')
    def _hash_valid(x):
        return isinstance(x, str) and re.fullmatch(r'[0-9A-F]{64}', x) is not None
    if any(not _hash_valid(plan[k]) for k in ('menu_before_sha256', 'menu_after_sha256', 'active_after_sha256')):
        raise ValueError('TX_PLAN_DIGEST')
    if plan['active_before_sha256'] is not None and not _hash_valid(plan['active_before_sha256']):
        raise ValueError('TX_PLAN_OLD_ACTIVE_DIGEST')
    canonical = (json.dumps(plan, sort_keys=True, ensure_ascii=False,
                separators=(',', ':')) + '\n').encode('utf-8')
    if plan_raw != canonical:
        raise ValueError('TX_PLAN_NOT_CANONICAL')
    if journal_raw != (json.dumps(journal, sort_keys=True, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8'):
        raise ValueError('TX_JOURNAL_NOT_CANONICAL')
    if journal['schema'] != plan['schema'] or journal['plan_sha256'] != hashlib.sha256(canonical).hexdigest().upper():
        raise ValueError('TX_PLAN_JOURNAL_BINDING')
    if journal['phase'] != 'COMMITTED':
        raise ValueError('TX_NOT_COMMITTED')
    menu_raw = _pinned_read(menu_path)
    active_raw = _pinned_read(active_path)
    if hashlib.sha256(menu_raw).hexdigest().upper() != plan['menu_after_sha256']:
        raise ValueError('TX_MENU_DRIFT')
    if hashlib.sha256(active_raw).hexdigest().upper() != plan['active_after_sha256']:
        raise ValueError('TX_ACTIVE_DRIFT')
    try:
        deploy = json.loads(active_raw.decode('utf-8-sig'))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError('TX_ACTIVE_SCHEMA') from exc
    if (not isinstance(deploy, dict) or deploy.get('schema') != 'TICKSTORE_DEPLOYMENT_V001'
            or deploy.get('status') != 'INSTALLED_NOT_PRODUCTION_ADMISSION'
            or deploy.get('production_started') is not False
            or not _hash_valid(deploy.get('package_sha256'))):
        raise ValueError('TX_ACTIVE_SCHEMA')
    # Re-read the boundary records and both targets after the check. This
    # detects many intervening writes but is NOT a native atomic snapshot.
    if (_pinned_read(plan_path) != plan_raw or _pinned_read(journal_path) != journal_raw
            or _pinned_read(menu_path) != menu_raw or _pinned_read(active_path) != active_raw):
        raise ValueError('TX_CONCURRENT_DRIFT')
    return deploy


TICKSTORE_STAGES = ('Check', 'Monitor', 'D4', 'D4Close', 'D5', 'CANARY', 'FULL_PREP', 'FULL_ADMIT',
                    'FULL_READMIT', 'FULL', 'Stop')
TICKSTORE_POLICY_STAGES = ('D4', 'D5', 'CANARY', 'FULL_PREP', 'FULL_ADMIT', 'FULL_READMIT', 'FULL')


def rodar_tickstore_full(base: Path) -> int:
    try:
        receipt_path = Path(os.environ['LOCALAPPDATA'])/'TICKSTORE/ACTIVE_DEPLOYMENT.json'
        deploy = _tickstore_committed_deployment(receipt_path, Path(__file__))
        if deploy.get('schema') != 'TICKSTORE_DEPLOYMENT_V001': raise ValueError('DEPLOYMENT_SCHEMA')
        release = Path(deploy['installation_root'])
        expected = Path(os.environ['LOCALAPPDATA'])/'TICKSTORE/Candidates'/deploy['package_sha256']
        if release.absolute() != expected.absolute(): raise ValueError('DEPLOYMENT_ROOT')
        _reject_deployment_reparse(release)
        launcher = release/'implementation_v001/candidate/control/RUN_TICKSTORE_FULL.ps1'
        _reject_deployment_reparse(launcher)
        if hashlib.sha256(launcher.read_bytes()).hexdigest().upper() != deploy['launcher_sha256']:
            raise ValueError('DEPLOYMENT_LAUNCHER_DRIFT')
        print('TICKSTORE: Check / Monitor / D4 / D4Close / D5 / CANARY / FULL_PREP / FULL_ADMIT / FULL_READMIT / FULL / Stop')
        stage = input('Etapa [Check]: ').strip() or 'Check'
        if stage not in TICKSTORE_STAGES:
            raise ValueError('ETAPA_INVALIDA')
        chain = input('Arquivo EXECUTION_CHAIN.json: ').strip()
        chain_sha = input('SHA-256 da cadeia: ').strip().upper()
        b06_sha = input('SHA-256 externo do recibo B06 independente: ').strip().upper()
        if not all(re.fullmatch(r'[0-9A-F]{64}', v) for v in (chain_sha, b06_sha)):
            raise ValueError('RECEIPT_DIGEST_REQUIRED')
        shell = Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        cmd = [str(shell), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(launcher),
               '-Stage', stage, '-ChainFile', chain, '-ChainSha256', chain_sha, '-B06Sha256', b06_sha]
        if stage in TICKSTORE_POLICY_STAGES:
            # R44-B2C: every effectful stage needs the CURRENT origin reconciliation; its SHA-256
            # is typed separately (never read from the record itself).
            reconciliation = input('Arquivo de reconciliacao de politica da origem: ').strip()
            reconciliation_sha = input('SHA-256 da reconciliacao (fornecido separadamente): ').strip().upper()
            if not reconciliation or not re.fullmatch(r'[0-9A-F]{64}', reconciliation_sha):
                raise ValueError('POLICY_RECONCILIATION_REQUIRED')
            cmd += ['-PolicyReconciliation', reconciliation, '-PolicyReconciliationSha256', reconciliation_sha]
        if stage == 'D4' and input('Retomar instancia D4 existente? [s/N]: ').strip().lower() == 's':
            cmd.append('-Resume')
        if stage in ('D5','CANARY','FULL_PREP','FULL_ADMIT','FULL') and input('Somente fechar recibo de nos ja concluidos? [s/N]: ').strip().lower() == 's':
            cmd.append('-CloseOnly')
        return rodar(cmd)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('TICKSTORE_FULL=BLOCKED:' + str(exc))
        return 2


def menu_principal() -> None:
    base = escolher_base_dir()
    orquestrador = str(SCRIPT_DIR / "GERAR_BASE_COMPLETA.py")
    expurgo = str(SCRIPT_DIR / "expurgar_exports_mt5.py")
    consultar_range = str(SCRIPT_DIR / "consultar_range_base.py")
    auditoria_integral = str(SCRIPT_DIR / "AUDITAR_HISTORICO_COMPLETO.py")
    backup_homologado = str(SCRIPT_DIR / "backup_base_homologada.py")

    while True:
        imprimir_cabecalho(base)
        print("1) Rodar TUDO -- ATUALIZACAO INCREMENTAL COMPLETA")
        print("   (continua do checkpoint e processa somente o delta afetado)")
        print("2) Rodar SO uma ou mais etapas especificas (--somente)")
        print("3) Ver o plano inteiro sem executar nada (--dry-run)")
        print("4) Rodar ate uma etapa (inclusive) e parar ai (--ate)")
        print("5) Trocar a pasta da base")
        print("6) Expurgar exports do MT5 -- SEPARADO da base, irreversivel")
        print("   (roda em modo RELATORIO por padrao; nada e apagado aqui)")
        print("7) Consultar o range da base de dados atual")
        print("8) Auditoria integral de TODO o historico")
        print("   (lenta; revalida a base inteira desde 2020; uso manual)")
        print("9) Backup da base homologada para o pendrive")
        print("   (WIN@N + IND@N em 7z; teste de integridade + SHA-256)")
        print("10) TICKSTORE -- verificar, executar etapa ou solicitar SAFE_STOP")
        print("0) Sair")
        print("")
        escolha = input("Escolha: ").strip()

        if escolha == "0":
            print("Saindo.")
            return

        if escolha == "5":
            base = escolher_base_dir()
            continue

        if escolha == "1":
            rodar([sys.executable, orquestrador, "--base-dir", str(base)])

        elif escolha == "2":
            imprimir_etapas()
            indices = escolher_indices(
                "Numero(s) da(s) etapa(s), separados por virgula: ")
            if not indices:
                print("Entrada invalida -- use numeros da lista, ex.: 11,12")
            else:
                chaves = [orq.ETAPAS[i - 1][0] for i in indices]
                rodar([sys.executable, orquestrador, "--base-dir", str(base),
                       "--somente", *chaves])

        elif escolha == "3":
            rodar([sys.executable, orquestrador, "--base-dir", str(base),
                   "--dry-run"])

        elif escolha == "4":
            imprimir_etapas()
            indices = escolher_indices("Numero da etapa em que PARAR: ")
            if len(indices) != 1:
                print("Entrada invalida -- escolha exatamente UM numero.")
            else:
                chave = orq.ETAPAS[indices[0] - 1][0]
                rodar([sys.executable, orquestrador, "--base-dir", str(base),
                       "--ate", chave])

        elif escolha == "6":
            print("")
            print("Modo RELATORIO (nada e apagado sem --executar, que este")
            print("menu nunca passa sozinho -- confirme rodando o script")
            print("diretamente somente com proveniencia content-addressed completa).")
            rodar([sys.executable, expurgo, "--base-dir", str(base)])

        elif escolha == "7":
            rodar([sys.executable, consultar_range, "--base-dir", str(base)])

        elif escolha == "8":
            print("\nEsta auditoria e somente leitura, pode levar horas e nao e")
            print("necessaria em cada atualizacao semanal.")
            rodar([sys.executable, auditoria_integral,
                   "--base-dir", str(base)])

        elif escolha == "9":
            print("\nBackup fail-closed: exige RANGE_HOMOLOGADO=APROVADO,")
            print("confere WIN@N, IND@N e o certificado antes de compactar.")
            destino = input(
                "Unidade/pasta do pendrive [Enter=detectar automaticamente]: "
            ).strip()
            cmd = [sys.executable, backup_homologado,
                   "--base-dir", str(base)]
            if destino:
                cmd += ["--destino", destino]
            rodar(cmd)

        elif escolha == "10":
            codigo = rodar_tickstore_full(base)
            print(f"TICKSTORE_MENU_EXIT_CODE={codigo}")

        else:
            print("Opcao invalida.")

        input("\nEnter para voltar ao menu...")


if __name__ == "__main__":
    try:
        menu_principal()
    except KeyboardInterrupt:
        print("\nInterrompido.")
        sys.exit(130)
