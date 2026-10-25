# Auditoria interna — V008R18R2 (identidade física de arquivo no Windows + pin de conteúdo do bundle)

Continuação da **mesma engenharia**. O preflight apontou, corretamente, que a correção R18R1 ainda não
oferecia no **Windows** garantia equivalente à do POSIX (`openat`+`O_NOFOLLOW`): em
`_read_authenticated_bytes`, o ramo não-POSIX verificava lexicalmente a cadeia e depois **reabria por
nome** com `p.read_bytes()` — entre a verificação e a abertura, um ancestral ou o arquivo podia ser
trocado por junction/symlink. Além disso: o **bundle** não tinha pinagem de conteúdo obrigatória;
`forbid_under` comparava apenas strings de caminho; `_load_bundle` pré-classificava ausência por
`p.exists()` (segue ancestrais); e `_safe_under` resolvia `root` antecipadamente.

A R18R2 fecha a classe de **identidade física de arquivo** em ambas as plataformas. **R18 e R18R1
permanecem congeladas.** Nenhuma economia; nenhum gate liberado; nada forjado; política não lida; D4
não autorizado.

## Correção

### Windows: identidade por handle nativo (`_win_read_authenticated_bytes`)
- `CreateFileW` com **`FILE_SHARE_READ` apenas** — nega WRITE/DELETE/rename enquanto o handle vive: o
  objeto fica **pinado**, fechando a troca concorrente entre verificação e uso.
- `FILE_FLAG_OPEN_REPARSE_POINT` — **não segue** um reparse no alvo; `GetFileInformationByHandle`
  recusa se o objeto é reparse point ou diretório.
- `GetFinalPathNameByHandleW` — caminho **canônico real** do objeto efetivamente aberto (reflete
  ancestrais reais); o escopo (`forbid_under`/`require_under`) é verificado sobre esse caminho REAL,
  não sobre a string de entrada → **a árvore física autorizada permanece vinculada ao objeto aberto**.
- Os bytes são **lidos do próprio handle** (`ReadFile`), nunca reabrindo por caminho; o SHA (quando
  fixado) é conferido sobre esses bytes.

### POSIX: preservado (`openat`+`O_NOFOLLOW`, race-free).

### Dispatcher (`_read_authenticated_bytes`)
POSIX → `_read_fd_nofollow`; Windows → `_win_read_authenticated_bytes`; **nenhum** → **FAIL-CLOSED**
(`…_NATIVE_IDENTITY_GUARANTEE_UNAVAILABLE_FAIL_CLOSED`) — nunca cai em leitura por caminho vulnerável.
Escopo físico sobre o caminho REAL: `forbid_under` (não pode estar dentro do pacote selado) e
`require_under` (tem de estar dentro da árvore autorizada). Ausência genuína (ENOENT/FILE_NOT_FOUND)
distinguida de alias/identidade/escopo.

### Pontos adjacentes
- `_safe_under` **não resolve mais `root` antecipadamente** (preserva identidade); a garantia física
  do gate sob a árvore do bundle passou para o leitor via `require_under=bundle_root`.
- `_load_bundle` **não pré-classifica ausência por `p.exists()`** (que segue ancestrais e mascararia
  alias): a ausência vem do próprio leitor autenticado (ENOENT), distinta de alias.
- `production_admission_verdict` exige **pinagem de conteúdo obrigatória** do bundle
  (`bundle_content_sha256`, auto-hash canônico sobre todo o conteúdo exceto o próprio campo):
  adulteração de qualquer campo (gates/external_module/phase_chain/release_id) é detectada.

## Qualificação

`supervisor/tests/windows_identity_qualifier_v008r18r2.py` (hash-bound, **seguro pré-efeito**: sem
economia, sem instalação, sem tocar as árvores protegidas) exercita as três rotas contra fixtures
sintéticas: módulo autêntico/SHA incorreto/troca concorrente/ausente/dentro do selado/symlink de
arquivo/symlink de ancestral/**junction de ancestral (Windows)**; bundle autêntico/pin adulterado/
symlink; fail-closed sem garantia nativa. Os casos reproduzíveis **PASSAM agora no POSIX (11/11)**;
**junction de ancestral e a identidade por handle nativo são provadas no alvo Windows** pelo runner
`RUN_WINDOWS_IDENTITY_QUALIFICATION_R18R2_PS51.ps1` (bootstrap PS 5.1). **Não se declara
`TARGET_RUNTIME=PASS` enquanto a prova nativa não existir.**

Unit do supervisor **216/216**; mutantes **48/48**. Testes novos: `R18R2IdentityAndContentPin`
(pin de conteúdo obrigatório/adulterado, fail-closed, require/forbid_under físico) e o qualificador.

## Evidência
`receipts/V008/offline_final/r18r2_origin_fixes/` (`ORIGIN_FIXES_CLOSURE_V008R18R2.json`,
`all_closed=true`: R18R1-PREFLIGHT-02, PRIOR_PRESERVED, com o resultado POSIX do qualificador embutido;
`FALSE_COMPLETENESS_SEARCH_V008R18R2.json` = `…FILE_IDENTITY_CLASS_CLOSED_WINDOWS_NATIVE_RUNNER_DELIVERED`).

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 15`
