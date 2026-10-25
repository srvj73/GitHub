# Auditoria interna — V008R18R1 (correção do defeito de preflight: classe TOCTOU/alias)

Continuação da **mesma engenharia**. O **preflight independente reprovou a R18 por defeito material**
(nenhuma auditoria formal iniciada). O achado é correto e foi reproduzido nos bytes do ZIP R18
(`1A2DED4C…`):

> Em `supervisor/pegasus_supervisor_v008.py`, `load_external_admission_module` chamava
> `Path(module_path).resolve()` **antes** de `is_symlink()`/`is_junction()`. A resolução elimina a
> identidade do link, então o check morre e um módulo sintético é aceito **por alias**. O **mesmo
> defeito** estava em `_load_bundle` (um JSON sintético por link simbólico também era aceito).

A R18R1 corrige **a classe inteira** da falha nas **três** rotas de leitura de arquivo externo (gate,
bundle, módulo de admissão), incluindo **componentes ancestrais** do caminho e **proteção contra
substituição entre verificação e uso (TOCTOU)**. Preserva a leitura/execução dos bytes efetivamente
autenticados. **R18 permanece congelada (não modificada); este é o sucessor corrigido.**

## Correção (família de helpers)

- **`_reparse_free_chain(path, kind)`** — prova, **componente a componente e SEM resolver**, que
  **nenhum ancestral nem o alvo** é `symlink`/`junction`. A verificação ocorre **antes** de qualquer
  `resolve()`, fechando o defeito de ordem.
- **`_read_fd_nofollow(path, kind)`** (POSIX) — abre cada componente com `openat`+`O_NOFOLLOW`
  relativo ao descritor do componente anterior: um symlink em **qualquer** componente (inclusive
  trocado concorrentemente) falha ali, de forma **race-free**; lê os bytes do descritor final e
  confirma arquivo regular.
- **`_read_authenticated_bytes(path, *, expected_sha256, forbid_under, kind)`** — orquestra: cadeia
  livre de reparse → (opcional) fora do pacote selado → leitura race-free → quando há SHA fixado, o
  hash é conferido **sobre os mesmos bytes lidos** (fecha a substituição entre verificação e uso).
  **Retorna os bytes autenticados** — é deles que o chamador parte.

### Rotas migradas

| Rota | Antes (R18) | Agora (R18R1) |
|---|---|---|
| **gate** (`verify_gate_file`) | `_safe_under` + `sha256_file(p)` (re-abria por caminho) | `_safe_under` + `_read_authenticated_bytes` (SHA sobre os bytes lidos) |
| **bundle** (`_load_bundle`) | `resolve()` → `is_symlink()` (check morto) | `_reparse_free_chain` + leitura autenticada; ausência genuína → `ABSENT`; alias → recusa |
| **módulo externo** (`load_external_admission_module`) | `resolve()` → `is_symlink()`; `spec_from_file_location` (reabria) | `_read_authenticated_bytes` + `compile`/`exec` **dos bytes autenticados** (sem reabrir) |

## Semântica nativa (Windows)

No POSIX a leitura é **race-free** via `openat`+`O_NOFOLLOW`. No Windows a cadeia é provada livre de
reparse (`is_symlink`/`is_junction`) lexicalmente e a semântica nativa de **junction/reparse** é
qualificada na **prova dirigida do alvo** — **não se declara PASS nativo a partir do Linux**
(ver `WINDOWS_DIRECTED_QUALIFICATION_PROTOCOL_R18R1.md`).

## Controles negativos dirigidos (teste)

`R18R1ReparseHardening`: módulo por **symlink direto**, por **alias ancestral**, **dentro do pacote
selado**, **SHA incorreto**, **troca concorrente de identidade** (bytes lidos ≠ SHA fixado), e
**bytes autênticos executam**; bundle por **symlink direto** e **alias ancestral**; **ausência
genuína** → veredito `ABSENT` (não confundida com alias, distinguida por `errno`). Junctions nativos
ficam para a qualificação Windows.

## Evidência

`receipts/V008/offline_final/r18r1_origin_fixes/` (`ORIGIN_FIXES_CLOSURE_V008R18R1.json`,
`all_closed=true`: R18-PREFLIGHT-01, PRIOR_PRESERVED, com `live_control.symlink_rejected=true`;
`FALSE_COMPLETENESS_SEARCH_V008R18R1.json` = `…REPARSE_CLASS_CLOSED`). Unit **208/208**; mutantes do
supervisor **48/48**. Fronteiras preservadas: `G4=FROZEN · QS4=NO · RUN_RELEASED=NO`; execução
econômica real permanece **`RESERVED_OWNER_RELEASE_DECISION`**; política não lida; D4 não autorizado.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 15`
