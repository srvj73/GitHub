# PEGASUS FULL 2026 — ENTREGA DE ENGENHARIA V008R19 (Opus, 25/10/2026)

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
| ZIP `…_FINAL_V008R19_20261025.zip` (2990 membros, 87586229 bytes) | `6159D126A741C749882FC1DC77339DCF88E934660099D021E9DF79595147C457` |
| Manifesto final (M2) | `3EB6A5625BC5376EE416B04B9F888837AC3A1FB3E91D85B07963EE824828B7AB` |
| Manifesto testado (M1) | `59E4DC75C26A677F4DF9DD514F05FEE5281FFA396EAED595630315FCDD35FE1F` |
| Bootstrap `BOOTSTRAP_PEGASUS_FULL_2026_V008R19_PS51.ps1` | `5767D61306704C5D7B638FC53159AEC72B793B0E17AC18BE873243631280E0A1` |
| Runner Windows `RUN_WINDOWS_IDENTITY_QUALIFICATION_R19_PS51.ps1` | `30AE903670957480C39D5BC5BE7477FA654F1E0B8A188559E6CD8E09F0862668` |
| Supervisor `supervisor/pegasus_supervisor_v008.py` | `84D662ED65BD9E3499B4624EDC99246A8BF353F324FD2D4FA14681C5211A08D5` |
| Entry `CODE/pegasus_entry.py` (V003, inalterado) | `F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB` |

**tested=packaged=delivered:** M1→M2 difere só por evidência de `offline_final`; **código e docs
byte-idênticos**; os bytes **entregues** (ZIP extraído) verificam `supervisor verify=PASS` e
`entry verify=PACKAGE_INTEGRITY=PASS`. Unit **220/220**; mutantes **48/48**; qualificação de identidade
POSIX **12/12** (junction = alvo Windows); R9 23/23 MET preservada. Supersede V008R18R2 (`09E47593…`).

## Prova nativa Windows — runner ENTREGUE e pronto (instrução única, a partir de `PS C:\Users\silvi>`)

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\RUN_WINDOWS_IDENTITY_QUALIFICATION_R19_PS51.ps1
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
