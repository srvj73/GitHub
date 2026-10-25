"""Finalizador de entrega R19: gera bootstrap/runner PS5.1 (a partir dos modelos R18R2, por
substituicao de nome/SHA do ZIP e do manifesto), START_HERE e RESPOSTA, remove os artefatos R18R2 da
pasta de entrega e escreve PREDELIVERY_ADMISSION_RECEIPT + DELIVERY_MANIFEST (SHA de todos os membros).
Nao executa economia; nao le politica. Uso:
  python -IB finalize_delivery_v008r19.py <delivery_dir> <tree_dir> <zip_path>
"""
import hashlib, json, sys
from pathlib import Path

DEL = Path(sys.argv[1]).resolve()
TREE = Path(sys.argv[2]).resolve()
ZIP = Path(sys.argv[3]).resolve()
FOOT = "ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 15"

ZIP_NAME = "PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R19_20261025.zip"
BOOT_NAME = "BOOTSTRAP_PEGASUS_FULL_2026_V008R19_PS51.ps1"
RUN_NAME = "RUN_WINDOWS_IDENTITY_QUALIFICATION_R19_PS51.ps1"
START_NAME = "00_START_HERE_PEGASUS_V008R19.md"
RESP_NAME = "RESPOSTA_CHATGPT_RUNNER_PARALELO_15_V008R19.md"
ADM_NAME = "PREDELIVERY_ADMISSION_RECEIPT_V008R19.json"
MAN_NAME = "DELIVERY_MANIFEST_SHA256.json"

ENTRY_SHA = "F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB"
R18_ZIP = "1A2DED4C6D8109357296DD7F739E3BAF13280E29C28F828BFE76CA643338417B"
R18R1_ZIP = "5D5EBAE1A2DB734FBA37A2610C41290F0EED197B241BC253F0DC313F243FFEC1"
R18R2_ZIP = "09E4759308DBD68762F331820D23B9BEC6FC504BFA0BC2685DDEB588E4A62A2D"


def sha_file(p):
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest().upper()


# ---- SHAs finais ----
zsha = sha_file(ZIP)
msha = sha_file(TREE / "MANIFEST_SHA256.json")
sup_sha = sha_file(TREE / "supervisor/pegasus_supervisor_v008.py")
m1_sha = json.loads((DEL / "TESTED_EQUALS_PACKAGED_DELIVERED_RECEIPT_V008R19.json").read_text())["tested_manifest_sha256_m1"]
members = int(json.loads((DEL / "G0_OFFLINE_RECEIPT_V008R19.json").read_text())["final_bytes"]["zip"]["members"]) \
    if (DEL / "G0_OFFLINE_RECEIPT_V008R19.json").exists() else None
zbytes = ZIP.stat().st_size

# ---- bootstrap R19 (modelo R18R2, substituicao de nome/SHA/manifesto; preserva bytes/CRLF) ----
boot_tpl = (DEL / "BOOTSTRAP_PEGASUS_FULL_2026_V008R18R2_PS51.ps1").read_bytes().decode("utf-8")
boot = (boot_tpl
        .replace("V008R18R2", "V008R19")
        .replace("PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R19_20261024.zip", ZIP_NAME)
        .replace("09E4759308DBD68762F331820D23B9BEC6FC504BFA0BC2685DDEB588E4A62A2D", zsha)
        .replace("381A039602BB139C83E60DCCE58EAAB06B78A7EA47A7DF9CF23FF0DACED7FCEE", msha))
(DEL / BOOT_NAME).write_bytes(boot.encode("utf-8"))

# ---- runner R19 (modelo R18R2; preserva bytes/CRLF) ----
run_tpl = (DEL / "RUN_WINDOWS_IDENTITY_QUALIFICATION_R18R2_PS51.ps1").read_bytes().decode("utf-8")
run = (run_tpl
       .replace("V008R18R2", "V008R19")
       .replace("windows_identity_qualifier_v008r18r2", "windows_identity_qualifier_v008r19")
       .replace("WINDOWS_IDENTITY_QUALIFICATION_R18R2_RESULT.json", "WINDOWS_IDENTITY_QUALIFICATION_R19_RESULT.json")
       .replace("RUN_WINDOWS_IDENTITY_QUALIFICATION_R18R2_PS51.ps1", RUN_NAME)
       .replace("PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R19_20261024.zip", ZIP_NAME)
       .replace("PEGASUS_WINDOWS_IDENTITY_R18R2", "PEGASUS_WINDOWS_IDENTITY_R19")
       .replace("09E4759308DBD68762F331820D23B9BEC6FC504BFA0BC2685DDEB588E4A62A2D", zsha))
(DEL / RUN_NAME).write_bytes(run.encode("utf-8"))
boot_sha = sha_file(DEL / BOOT_NAME)
run_sha = sha_file(DEL / RUN_NAME)

# ---- START_HERE R19 ----
start = """# PEGASUS FULL 2026 — ENTREGA DE ENGENHARIA V008R19 (Opus, 25/10/2026)

**Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 15. **Sucessor corrigido da R18R2 (R18, R18R1 e R18R2 permanecem congeladas). Única intervenção Opus restante.**

## O que é — fechamento da corrida de rename de ancestral (POSIX) por resolução atômica do kernel

O preflight independente apontou, **corretamente**, um defeito material residual na R18R2: no POSIX a
leitura autenticada (`_read_fd_nofollow`) era um **walk multi-passo** — abria cada ancestral por
`openat`+`O_NOFOLLOW` relativo ao `dirfd` anterior e só ao final comparava o caminho **lexical** contra
`require_under`. Entre abrir o `dirfd` do ancestral e abrir o alvo há uma janela: mover o ancestral
para **fora** da árvore confiável *antes* da abertura final faz o `openat` seguir o inode já aberto e
devolver bytes **fora de escopo**, enquanto a verificação lexical ainda parece dentro (TOCTOU). A
contraprova da origem foi **reproduzida** nos bytes R18R2 (`REPRODUCED_VULNERABILITY`) antes de corrigir.
A R19 fecha a classe com **resolução atômica pelo kernel**. **Nenhuma economia; nenhum gate liberado;
nada forjado; política não lida; D4 não autorizado.**

- **POSIX (`_read_fd_openat2`)**: `openat2(2)` com **`RESOLVE_BENEATH`** relativo a um **FD de root
  confiável** (`require_under`) — o kernel recusa **atomicamente** (`EXDEV`) qualquer escape, inclusive
  por `..`, symlink **ou ancestral movido durante a resolução** — mais `RESOLVE_NO_SYMLINKS` e
  `RESOLVE_NO_MAGICLINKS`. Os bytes são **lidos do fd devolvido**; não há janela entre verificar e abrir.
- **FAIL-CLOSED**: sem `openat2` (POSIX antigo/sandbox) e fora do Windows ⇒
  `…_NATIVE_IDENTITY_GUARANTEE_UNAVAILABLE_FAIL_CLOSED`; **nenhuma** simulação por
  `realpath`/`/proc`/dupla-verificação/`flock`.
- **Windows preservado** (R18R2): `CreateFileW` `FILE_SHARE_READ` apenas (nega WRITE/DELETE/rename →
  objeto **pinado**, cobrindo o ancestral) + `FILE_FLAG_OPEN_REPARSE_POINT` + `GetFinalPathNameByHandleW`
  (escopo sobre o caminho real) + leitura do handle.
- **Três rotas** fechadas: `verify_gate_file`, `_load_bundle`, `load_external_admission_module`.
- **Risco de release (honesto)**: `bundle_content_sha256` autentica **conteúdo**, **não o emissor**; a
  rota econômica permanece bloqueada por `RESERVED_OWNER_RELEASE_DECISION`; **nada** promovido.

### Bytes finais (fora do ZIP)

| Artefato | SHA-256 |
|---|---|
| ZIP `…_FINAL_V008R19_20261025.zip` ({members} membros, {zbytes} bytes) | `{zsha}` |
| Manifesto final (M2) | `{msha}` |
| Manifesto testado (M1) | `{m1_sha}` |
| Bootstrap `{boot_name}` | `{boot_sha}` |
| Runner Windows `{run_name}` | `{run_sha}` |
| Supervisor `supervisor/pegasus_supervisor_v008.py` | `{sup_sha}` |
| Entry `CODE/pegasus_entry.py` (V003, inalterado) | `{entry_sha}` |

**tested=packaged=delivered:** M1→M2 difere só por evidência de `offline_final`; **código e docs
byte-idênticos**; os bytes **entregues** (ZIP extraído) verificam `supervisor verify=PASS` e
`entry verify=PACKAGE_INTEGRITY=PASS`. Unit **220/220**; mutantes **48/48**; qualificação de identidade
POSIX **12/12** (junction = alvo Windows); R9 23/23 MET preservada. Supersede V008R18R2 (`09E47593…`).

## Prova nativa Windows — runner ENTREGUE e pronto (instrução única, a partir de `PS C:\\Users\\silvi>`)

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\\Users\\silvi\\Downloads\\{run_name}
```
Confere o SHA do ZIP, extrai, acha o Python alvo e roda `supervisor/tests/windows_identity_qualifier_v008r19.py`
(hash-bound, **pré-efeito**) contra fixtures sintéticas: symlink de arquivo/ancestral, **junction de
ancestral**, **rename de ancestral antes da abertura**, troca concorrente, escape, dentro do selado, SHA
incorreto, ausência, pin de conteúdo adulterado, fail-closed. Log em pasta absoluta fixa nova por
execução. **Os casos reproduzíveis já passam no POSIX (12/12)**; **junction e a identidade por handle
nativo são provados no alvo**. **Não declaro `TARGET_RUNTIME=PASS` enquanto o runner não rodar no PC do
titular.** Contrato de retorno: enviar `WINDOWS_IDENTITY_QUALIFICATION_R19_RESULT.json` + o log.

## Estado honesto dos cinco eixos

| Eixo | Estado |
|---|---|
| ENGINEERING_COMPLETE | **SIM** — corrida de rename de ancestral fechada (POSIX openat2 BENEATH) + identidade física Windows + fail-closed + R18R2/R18R1/R18/R17/R16 preservados |
| NATIVE_QUALIFICATION | **MET nos bytes R9**; identidade nativa Windows = **TARGET_RUNTIME_PENDING** (runner entregue) |
| CANDIDATE_COMPLETENESS | **engenharia completa**; selagem `=PASS` é da origem |
| INDEPENDENT_AUDIT | **pendente** — da origem |
| PRODUCTION_AUTHORIZED / RUN_RELEASED | **NO** — execução econômica real = **DECISÃO RESERVADA do titular** |

Fronteiras: `G4=FROZEN · QS4=NO · FULL_ECONOMIC=NOT_STARTED · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO`.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 15`
""".format(members=members, zbytes=zbytes, zsha=zsha, msha=msha, m1_sha=m1_sha, boot_name=BOOT_NAME,
           boot_sha=boot_sha, run_name=RUN_NAME, run_sha=run_sha, sup_sha=sup_sha, entry_sha=ENTRY_SHA)
(DEL / START_NAME).write_text(start, encoding="utf-8")

# ---- RESPOSTA R19 ----
resp = """# Resposta ao ChatGPT — Pegasus Original · Implementação Runner Paralelo 15 (V008R19)

O achado do preflight está **correto** e foi **reproduzido** (`REPRODUCED_VULNERABILITY`) antes de
corrigir. Entrego o **sucessor único integrado**; R18, R18R1 e R18R2 permanecem **congeladas**. Esta é a
**única intervenção Opus restante**.

## Defeito e correção (corrida de rename de ancestral após abertura por dirfd, POSIX)

No POSIX, `_read_fd_nofollow` era um **walk multi-passo**: abria cada ancestral por `openat`+`O_NOFOLLOW`
relativo ao `dirfd` anterior e, só ao final, comparava o caminho **lexical** contra `require_under`.
Entre abrir o `dirfd` do ancestral e abrir o alvo há uma janela — mover o ancestral para **fora** da
árvore confiável *antes* da abertura final faz o `openat` seguir o inode já aberto e devolver bytes
**fora de escopo**, enquanto a verificação lexical ainda parece dentro. A R19 remove o walk:

1. `openat2(2)` com **`RESOLVE_BENEATH`** relativo a um **FD de root confiável** (`require_under`): o
   kernel aplica o escopo **atomicamente** (`EXDEV`) — cobre `..`, symlink **e rename de ancestral
   durante a resolução**. A verificação **é** a abertura; não há janela.
2. `RESOLVE_NO_SYMLINKS` + `RESOLVE_NO_MAGICLINKS`: nenhum componente symlink/magic-link.
3. Bytes **lidos do fd devolvido** por `openat2`; o SHA é conferido sobre eles.
4. **FAIL-CLOSED** sem `openat2` e fora do Windows — **nenhuma** simulação por `realpath`/`/proc`/
   dupla-verificação/`flock`. Promessa que o kernel não dá, o código não finge.
5. **Windows preservado** (handle nativo deny-write/deny-delete + `GetFinalPathNameByHandle`). As
   **três rotas** (`verify_gate_file`, `_load_bundle`, `load_external_admission_module`) roteiam pelo
   mesmo dispatcher.

## Risco de release (revisado, honesto)
`bundle_content_sha256` é auto-hash canônico do conteúdo — detecta adulteração, mas **não autentica o
emissor**. A rota econômica permanece bloqueada por `RESERVED_OWNER_RELEASE_DECISION`; **não** promovi
`RUN_RELEASED`, **não** criei emissor administrativo em `PolicyRoot`, **não** alterei G4/V003.

## Prova
- **POSIX (agora)**: suíte unit **220/220** (inclui `R19AncestorRenameRace`: RED reconstruindo o walk
  vulnerável que aceita o ancestral movido; GREEN R19 que recusa; **stress concorrente de 400
  iterações** que nunca aceita fora da árvore); mutantes **48/48**; qualificador dirigido
  `windows_identity_qualifier_v008r19.py` **12/12** (junction pulado — Windows-only); prova inline
  RED→GREEN = `RED_REPRODUCED_GREEN_BLOCKS`.
- **Windows (entregue, pronto)**: runner `{run_name}` (bootstrap PS5.1, hash-bound, **pré-efeito**).
  **Não declaro `TARGET_RUNTIME=PASS` enquanto o runner não rodar no PC do titular** — a execução Windows
  e seus resultados podem ser tratados neste mesmo contexto.

## PASS preservados
R18R2 (handle Windows + pin), R18R1 (reparse), R18 (I-03A/B/C), R17 (I-01/I-02), R16 (N1/N2/N3), R15,
F01–F04, R9 23/23 MET — bytes idênticos onde aplicável.

## Bytes finais
- ZIP: `{zsha}` ({members} membros, {zbytes} bytes)
- Manifesto M2: `{msha}` · testado M1: `{m1_sha}` (M1→M2 = só evidência offline_final; código/docs
  byte-idênticos); bytes entregues verificam `supervisor verify=PASS` e `entry PACKAGE_INTEGRITY=PASS`.
- Supervisor: `{sup_sha}` · Bootstrap: `{boot_sha}` · Supersede V008R18R2 (`09E47593…`).

## Entrega física verificável
O ZIP binário é entregue diretamente ao titular nesta conversa (arquivo anexado) para leitura física e
SHA-256, além do commit na branch `claude/new-session-dtpyxc`. Um commit + SHA declarado não substitui os
bytes: o arquivo acompanha esta entrega.

## Fronteiras
`G4/V003 FROZEN · QS4=NO · RUN_RELEASED=NO · FULL_ECONOMIC=NOT_STARTED`; execução econômica real =
**`RESERVED_OWNER_RELEASE_DECISION`**; MASTER/HEAD não lidos. Sucessor único; sem patches intermediários;
sem cadeia R18R3/R18R4; sem pedir nova auditoria.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 15`
""".format(run_name=RUN_NAME, zsha=zsha, members=members, zbytes=zbytes, msha=msha, m1_sha=m1_sha,
           sup_sha=sup_sha, boot_sha=boot_sha)
(DEL / RESP_NAME).write_text(resp, encoding="utf-8")

# ---- remover artefatos R18R2 da pasta de entrega ----
for p in sorted(DEL.glob("*")):
    if p.is_file() and ("R18R2" in p.name or "V008R18R2" in p.name):
        p.unlink()
# ZIP R18R2 antigo
old_zip = DEL / "PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R18R2_20261024.zip"
if old_zip.exists():
    old_zip.unlink()

# ---- recibos de admissao + manifesto de entrega ----
components = {}
man_members = []
for p in sorted(DEL.rglob("*")):
    if p.is_file() and p.name not in (ADM_NAME, MAN_NAME):
        rel = p.relative_to(DEL).as_posix()
        s = sha_file(p)
        components[rel] = s
        man_members.append({"path": rel, "bytes": p.stat().st_size, "sha256": s})

adm = {
    "schema": "PEGASUS_FULL_2026_V008R19_PREDELIVERY_ADMISSION_RECEIPT",
    "final_bytes": {"zip_sha256": zsha, "manifest_sha256_m2": msha},
    "admitted_for": "OWNER_WINDOWS_IDENTITY_QUALIFICATION (runner pre-efeito, hash-bound) + ORIGIN_FOCAL_REAUDIT",
    "windows_identity_runner": RUN_NAME + " (pronto; TARGET_RUNTIME_PENDING ate rodar no PC do titular)",
    "real_economic_execution": "RESERVED_OWNER_RELEASE_DECISION",
    "release_authentication_note": "bundle_content_sha256 autentica CONTEUDO, nao o EMISSOR; rota economica permanece reservada ao titular",
    "not_admitted_for": ["QS4", "FULL economico", "Phase B/C economicas", "reselection", "RUN_RELEASED",
                         "Install/Rollback produtivo sem autorizacao", "alteracao de politica/MASTER/HEAD"],
    "supersedes_frozen": {"r18": R18_ZIP, "r18r1": R18R1_ZIP, "r18r2": R18R2_ZIP},
    "g4": "FROZEN", "qs4": "NO", "full_economic": "NOT_STARTED", "phase_c": "FORBIDDEN",
    "reselection_2026": "FORBIDDEN", "run_released": "NO", "full_released": "NO", "paid_credit": "NOT_USED",
    "result_return_to": FOOT, "components": components}
(DEL / ADM_NAME).write_text(json.dumps(adm, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
# recomputa com o ADM presente para o manifesto final
adm_sha = sha_file(DEL / ADM_NAME)
man_members.append({"path": ADM_NAME, "bytes": (DEL / ADM_NAME).stat().st_size, "sha256": adm_sha})
man_members.sort(key=lambda m: m["path"])
manifest = {"schema": "PEGASUS_FULL_2026_V008R19_DELIVERY_MANIFEST", "members": man_members}
(DEL / MAN_NAME).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

print(json.dumps({"zip_sha256": zsha, "manifest_sha256_m2": msha, "m1": m1_sha, "bootstrap_sha256": boot_sha,
                  "runner_sha256": run_sha, "members_zip": members, "delivery_files": len(man_members)}, indent=1))
