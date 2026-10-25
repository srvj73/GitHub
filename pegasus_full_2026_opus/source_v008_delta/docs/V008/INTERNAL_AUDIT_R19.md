# Auditoria interna — V008R19 (corrida de rename de ancestral após abertura por dirfd)

Continuação da **mesma engenharia**. O preflight independente apontou, **corretamente**, um defeito
material residual na R18R2: no POSIX a leitura autenticada (`_read_fd_nofollow`) era uma **caminhada em
vários passos** — abria cada componente do caminho com `openat`+`O_NOFOLLOW` relativo ao `dirfd` do
componente anterior e, só ao final, comparava o caminho **lexical** contra `require_under` via
`_canon(...)`. Entre a abertura do `dirfd` de um ancestral e a abertura do arquivo-alvo (`gate.bin`)
existe uma janela: se o ancestral (`trusted/nested`) for **movido para fora** da árvore confiável
*antes* da abertura final, o `openat` segue o **inode já aberto** (o descritor preso ao diretório que
agora vive fora da árvore) e devolve bytes **fora de escopo**, enquanto a verificação lexical compara a
string de entrada `trusted/nested/gate.bin` — que **continua** parecendo dentro de `trusted`. Resultado:
R18R2 **aceita** bytes fora da árvore autorizada sob rename concorrente de ancestral (TOCTOU).

A contraprova da origem foi **reproduzida** nos bytes R18R2 (`REPRODUCED_VULNERABILITY`) antes de
corrigir. A R19 fecha esta classe com **resolução atômica pelo kernel**. **R18, R18R1 e R18R2
permanecem congeladas.** Nenhuma economia; nenhum gate liberado; nada forjado; política não lida; D4
não autorizado.

## Correção — resolução atômica de caminho (POSIX `openat2` + `RESOLVE_BENEATH`)

A caminhada em vários passos foi **removida**. A leitura POSIX autenticada passa a usar o syscall
`openat2(2)` (nr 437) com `struct open_how`:

- **`RESOLVE_BENEATH`** (`0x08`) — quando há `require_under`, abre o arquivo **relativo a um dirfd da
  raiz autorizada** (`require_under`, aberto com `O_PATH|O_DIRECTORY`); o kernel recusa
  **atomicamente** (`EXDEV`) qualquer resolução que escape da raiz, **inclusive** por `..`, por
  symlink **ou por ancestral que seja movido durante a resolução**. Não há janela entre "verificar" e
  "abrir": a verificação **é** a abertura.
- **`RESOLVE_NO_SYMLINKS`** (`0x04`) — nenhum componente pode ser symlink; torna sólida também a
  comparação lexical de `forbid_under` (não há alias a desfazer).
- **`RESOLVE_NO_MAGICLINKS`** (`0x02`) — recusa magic-links (`/proc/*/fd`, etc.).
- Sem `require_under`, resolve por `AT_FDCWD` com `RESOLVE_NO_SYMLINKS|RESOLVE_NO_MAGICLINKS`.
- Os bytes são **lidos do fd devolvido** por `openat2` (nunca reabrindo por caminho); o SHA (quando
  fixado) é conferido sobre esses bytes.

Mapeamento de errno: `ENOENT`/`FILE_NOT_FOUND` → **ausência genuína** (distinta de escape);
`EXDEV` → **escape da árvore** (`…OUTSIDE_AUTHORIZED_TREE`); `ELOOP` → reparse/alias;
`ENOSYS`/`EPERM`/`EINVAL` (kernel/sandbox sem `openat2`) → **garantia nativa indisponível**.

### FAIL-CLOSED quando a garantia nativa não existe
Sem `openat2` (POSIX antigo/sandbox) e fora do Windows, o dispatcher **não** cai em leitura por caminho
vulnerável nem simula a garantia por `realpath`/`/proc`/dupla-verificação/`flock`: levanta
`…_NATIVE_IDENTITY_GUARANTEE_UNAVAILABLE_FAIL_CLOSED`. Promessa que o kernel não dá, o código não finge.

### Windows: preservado (handle nativo R18R2)
`_win_read_authenticated_bytes` segue idêntico: `CreateFileW` com `FILE_SHARE_READ` apenas (nega
WRITE/DELETE/rename → objeto **pinado**, cobrindo o **ancestral** enquanto o handle vive) +
`FILE_FLAG_OPEN_REPARSE_POINT`; escopo verificado sobre `GetFinalPathNameByHandleW` (caminho real);
bytes lidos do handle. A identidade física nativa Windows permanece **TARGET_RUNTIME_PENDING** até o
runner rodar no PC do titular — **não se declara `TARGET_RUNTIME=PASS`**.

### Dispatcher (`_read_authenticated_bytes`)
Windows → `_win_read_authenticated_bytes`; POSIX com `openat2` → `_read_fd_openat2(...require_under=...)`
(o kernel aplica `require_under` atomicamente; `forbid_under` lexical é sólido sob `NO_SYMLINKS`);
**nenhum** → **FAIL-CLOSED**. As **três rotas** (`verify_gate_file`,
`ProductionReleaseAdmission._load_bundle`, `load_external_admission_module`) roteiam por este
dispatcher — a classe é fechada em todas.

## Risco de release (revisado, honesto)
`bundle_content_sha256` é **auto-hash canônico do conteúdo** — detecta adulteração do bundle, mas **não
autentica o emissor**: qualquer parte que produza um bundle pode recomputar o pin. A rota econômica
permanece bloqueada por `RESERVED_OWNER_RELEASE_DECISION`; **não** se promove `RUN_RELEASED`, **não** se
cria emissor administrativo adicional em `PolicyRoot`, **não** se altera G4/V003.

## Qualificação
`supervisor/tests/windows_identity_qualifier_v008r19.py` (hash-bound, **seguro pré-efeito**) exercita as
três rotas e inclui o caso novo **`GATE_ANCESTOR_MOVED_BEFORE_OPEN`** (controle positivo + ancestral
movido para fora *antes* da abertura ⇒ `openat2 RESOLVE_BENEATH` recusa). Casos reproduzíveis **PASSAM
no POSIX (12/12)**; junction de ancestral e identidade por handle nativo são provadas no alvo Windows
pelo runner `RUN_WINDOWS_IDENTITY_QUALIFICATION_R19_PS51.ps1`.

Unit do supervisor **220/220**; mutantes **48/48**. Testes novos: classe `R19AncestorRenameRace`
(referência RED reconstruindo a caminhada vulnerável que aceita o ancestral movido; GREEN R19 que
recusa; autêntico sob a árvore; **stress concorrente de 400 iterações** que nunca aceita fora da
árvore) e o qualificador atualizado (fail-closed via `_openat2_supported`→False).

## Evidência
`receipts/V008/offline_final/r19_origin_fixes/` (`ORIGIN_FIXES_CLOSURE_V008R19.json`, `all_closed=true`:
R18R2-PREFLIGHT-ANCESTOR-RENAME, PRIOR_PRESERVED, com o resultado POSIX do qualificador e o resultado
da contraprova RED→GREEN embutidos; `FALSE_COMPLETENESS_SEARCH_V008R19.json` =
`…ANCESTOR_RENAME_RACE_CLOSED_OPENAT2_FAIL_CLOSED_REAL_RELEASE_RESERVED_TO_OWNER`).

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 15`
