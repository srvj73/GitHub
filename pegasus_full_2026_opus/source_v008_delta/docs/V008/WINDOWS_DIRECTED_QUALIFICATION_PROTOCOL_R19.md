# Protocolo de qualificação dirigida Windows — V008R19 (identidade física + resistência a rename de ancestral)

Prova nativa, no PC do titular, da **identidade física de arquivo** e da **resistência a corridas** —
inclusive a **troca/rename de diretório ancestral após a abertura** — que o POSIX fecha por
`openat2`+`RESOLVE_BENEATH` (resolução atômica pelo kernel) e o Windows por **handle nativo**
(`FILE_SHARE_READ` deny-write/deny-delete cobrindo o ancestral + `GetFinalPathNameByHandleW`). **Seguro
pré-efeito**: sem economia, sem instalação produtiva, sem tocar as três árvores protegidas, sem ler
política; **D4 não autorizado**; hash-bound. Complementa (não substitui) a campanha R9 (23/23, MET).

## Runner entregue (autocontido)
- Driver: `supervisor/tests/windows_identity_qualifier_v008r19.py` (dentro do ZIP selado, hash-bound).
- Bootstrap: `RUN_WINDOWS_IDENTITY_QUALIFICATION_R19_PS51.ps1` (na entrega, ao lado do ZIP).

## Instrução ÚNICA de execução (a partir de `PS C:\Users\silvi>`, sem `cd`)
```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\RUN_WINDOWS_IDENTITY_QUALIFICATION_R19_PS51.ps1
```
O bootstrap: confere o SHA-256 do ZIP contra o pin, extrai para uma pasta de trabalho nova, localiza o
Python alvo, executa o driver com `--out` numa **pasta de log absoluta fixa, nova por execução,
independente da pasta atual** —
`C:\Users\silvi\Downloads\PEGASUS_FULL_2026_RUNS\WINIDENT_<yyyyMMdd_HHmmss_fff>_<PID>\` — e devolve o
exit code e o recibo primário.

## Alvos (fixtures sintéticos, isolados)

| # | Caso | Veredito esperado |
|---|---|---|
| 1 | módulo regular autêntico (fora do selado, SHA bate) | carrega; bytes autenticados == executados |
| 2 | módulo por **symlink** de arquivo | recusa `*_REPARSE_OR_ALIAS` |
| 3 | módulo por **symlink de diretório ancestral** | recusa `*_REPARSE_OR_ALIAS` |
| 4 | módulo por **junction de diretório ancestral** (`mklink /J`) | recusa (caminho real ≠ esperado / fora de escopo) |
| 5 | **troca concorrente** do arquivo/ancestral após abrir o handle | handle deny-write/deny-delete impede troca; SHA sobre bytes do handle |
| 6 | **rename de ANCESTRAL antes da abertura** (POSIX `openat2 RESOLVE_BENEATH`) | controle positivo OK **e** recusa `*_OUTSIDE_AUTHORIZED_TREE`/`*_ABSENT` |
| 7 | **escape** do pacote selado | recusa `*_OUTSIDE_AUTHORIZED_TREE`/`*_INSIDE_SEALED_PACKAGE_FORBIDDEN` |
| 8 | módulo/bundle **dentro** do pacote selado | recusa `*_INSIDE_SEALED_PACKAGE_FORBIDDEN` |
| 9 | **SHA-256 incorreto** | recusa `*_IDENTITY_MISMATCH_OR_CONCURRENT_SWAP` |
| 10 | **arquivo ausente** | `*_ABSENT` (distinto de alias/escape) |
| 11 | bundle com **pin de conteúdo** adulterado | `AUTHORIZATION_BUNDLE_CONTENT_SHA_MISSING_OR_MISMATCH` |
| 12 | **sem garantia nativa** (`openat2` indisponível, não-Windows) | fail-closed `*_NATIVE_IDENTITY_GUARANTEE_UNAVAILABLE_FAIL_CLOSED` |

> Os casos reproduzíveis fora de junction (2,3,5–12) **já passam no POSIX** (openat2 RESOLVE_BENEATH),
> no runner e na suíte unitária (12/12; junction pulado — Windows-only). Os casos 1,4 e a semântica
> nativa de **handle deny-write/deny-delete + GetFinalPathNameByHandle** exigem o Windows e são provados
> por este runner no alvo.

## Exit codes e recibo
`0` = todos os casos obrigatórios da plataforma conforme esperado; `3` = violação de contrato. Recibo
primário `WINDOWS_IDENTITY_QUALIFICATION_R19_RESULT.json` (hash-bound ao SHA do supervisor), com
`native_read_path` (`WIN32_HANDLE_DENY_WRITE_DELETE` no Windows; `POSIX_OPENAT2_RESOLVE_BENEATH` no
POSIX; `NONE_FAIL_CLOSED` sem garantia), casos, pulados e `result`.

## Contrato de retorno
Enviar o recibo primário + o log à origem. Enquanto este runner não executar no alvo, a identidade
nativa Windows é **TARGET_RUNTIME_PENDING** — **não se declara `TARGET_RUNTIME=PASS`**. A classe lógica
(incluindo o rename de ancestral) está fechada e provada no POSIX por resolução atômica do kernel; a
confirmação nativa Windows é do titular.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 15`
