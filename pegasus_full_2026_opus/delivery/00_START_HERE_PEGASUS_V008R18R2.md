# PEGASUS FULL 2026 — ENTREGA DE ENGENHARIA V008R18R2 (Opus, 25/10/2026)

**Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 15. **Sucessor corrigido da R18R1 (R18 e R18R1 permanecem congeladas).**

## O que é — identidade física de arquivo no Windows + pin de conteúdo do bundle

O preflight apontou, corretamente, que a correção R18R1 ainda não dava no **Windows** a garantia do POSIX
(`openat`+`O_NOFOLLOW`): em `_read_authenticated_bytes` o ramo não-POSIX verificava lexicalmente e **reabria
por nome** (`p.read_bytes()`) — entre verificação e abertura, um ancestral ou o arquivo podia virar
junction/symlink. Também: o **bundle** não tinha pinagem de conteúdo obrigatória; `forbid_under` comparava só
strings; `_load_bundle` pré-classificava ausência por `p.exists()`; `_safe_under` resolvia `root` cedo. A
R18R2 fecha a **identidade física de arquivo** em ambas as plataformas. **Nenhuma economia; nenhum gate
liberado; nada forjado; política não lida; D4 não autorizado.**

- **Windows (`_win_read_authenticated_bytes`)**: `CreateFileW` com **`FILE_SHARE_READ` apenas** (nega
  WRITE/DELETE/rename → objeto **pinado** enquanto o handle vive) + `FILE_FLAG_OPEN_REPARSE_POINT` (não segue
  reparse no alvo); recusa reparse/diretório por atributo; `GetFinalPathNameByHandleW` dá o **caminho real** do
  objeto aberto, sobre o qual o escopo (`require_under`/`forbid_under`) é verificado; os bytes são **lidos do
  handle** (sem reabrir). **POSIX preservado** (`openat`+`O_NOFOLLOW`). Sem garantia nativa ⇒ **FAIL-CLOSED**.
- **Bundle**: `production_admission_verdict` exige **`bundle_content_sha256`** (auto-hash canônico) — adulteração
  de qualquer campo é detectada.
- `_safe_under` não resolve `root` cedo (preserva identidade); `_load_bundle` não pré-checa `p.exists()`
  (distingue ausência de alias pela leitura autenticada).

### Bytes finais (fora do ZIP)

| Artefato | SHA-256 |
|---|---|
| ZIP `…_FINAL_V008R18R2_20261024.zip` (2.986 membros, 87.572.048 bytes) | `09E4759308DBD68762F331820D23B9BEC6FC504BFA0BC2685DDEB588E4A62A2D` |
| Manifesto final (M2) | `381A039602BB139C83E60DCCE58EAAB06B78A7EA47A7DF9CF23FF0DACED7FCEE` |
| Manifesto testado (M1) | `8B637D5D892CA75756E95E03E64D43A8A064DCAEC4104D3BDC2CA1B707CE00C3` |
| Bootstrap `BOOTSTRAP_…_V008R18R2_PS51.ps1` | `18C5CA408D1B6A7292553DFA45669C90CEF6A123CBF14B5433ACD52C9451D76F` |
| Runner Windows `RUN_WINDOWS_IDENTITY_QUALIFICATION_R18R2_PS51.ps1` | ver `DELIVERY_MANIFEST_SHA256.json` |
| Supervisor `supervisor/pegasus_supervisor_v008.py` | `00560307A62FB164AD76D93C715EB6DA6D8EEBA19D6DDF999611B44C5A3683CC` |
| Entry `CODE/pegasus_entry.py` (V003, inalterado) | `F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB` |

**tested=packaged=delivered:** M1→M2 difere só por **18** arquivos de evidência; **código e docs
byte-idênticos**; os bytes **entregues** (ZIP extraído) verificam `supervisor verify=PASS_PACKAGE_VERIFIED` e
`entry verify=PACKAGE_INTEGRITY=PASS` (2.986 arquivos). Unit **216/216**; mutantes **48/48**; qualificação
**18 PASS + 2 SKIPPED_NON_NATIVE**; R9 23/23 MET preservada. Supersede V008R18R1 (`5D5EBAE1…`).

## Prova nativa Windows — runner ENTREGUE e pronto (instrução única)

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\RUN_WINDOWS_IDENTITY_QUALIFICATION_R18R2_PS51.ps1
```
Confere o SHA do ZIP, extrai, acha o Python alvo e roda `supervisor/tests/windows_identity_qualifier_v008r18r2.py`
(hash-bound, **pré-efeito**) contra fixtures sintéticas: symlink de arquivo/ancestral, **junction de ancestral**,
troca concorrente, escape, dentro do selado, SHA incorreto, ausência, pin de conteúdo adulterado, fail-closed.
Log em pasta absoluta fixa nova por execução. **Os casos reproduzíveis já passam no POSIX (11/11)**; **junction e
a identidade por handle nativo são provados no alvo**. **Não declaro `TARGET_RUNTIME=PASS` enquanto o runner não
rodar no PC do titular.** Contrato de retorno: enviar `WINDOWS_IDENTITY_QUALIFICATION_R18R2_RESULT.json` + o log.

## Estado honesto dos cinco eixos

| Eixo | Estado |
|---|---|
| ENGINEERING_COMPLETE | **SIM** — identidade física de arquivo (POSIX+Windows) + pin de conteúdo + R18R1/R18/R17/R16 preservados |
| NATIVE_QUALIFICATION | **MET nos bytes R9**; identidade nativa Windows = **TARGET_RUNTIME_PENDING** (runner entregue) |
| CANDIDATE_COMPLETENESS | **engenharia completa**; selagem `=PASS` é da origem |
| INDEPENDENT_AUDIT | **pendente** — da origem |
| PRODUCTION_AUTHORIZED / RUN_RELEASED | **NO** — execução econômica real = **DECISÃO RESERVADA do titular** |

Fronteiras: `G4=FROZEN · QS4=NO · FULL_ECONOMIC=NOT_STARTED · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO`.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 15`
