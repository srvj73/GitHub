# Protocolo de qualificação dirigida Windows — V008R15 (processos sintéticos)

Prova nativa, no PC do titular, das propriedades que **não** podem ser demonstradas em sandbox POSIX.
Processos **exclusivamente sintéticos**, hash-bound, sem instalação produtiva, sem economia, sem kill
não autorizado. O Opus pode coordenar diretamente com o titular, sem revisão intermediária da origem.

## Pré-condições
- `-Mode Verify` do bootstrap R15 PASS (identidade do pacote e dos pais conferida).
- Python 3.14.7 fixado (SHA conferido pelo bootstrap).
- Execução elevada apenas onde o USN exige; nenhum efeito fora do diretório de trabalho sintético.

## Alvos (cada um com árvore sintética própria, curta, controlada)

| # | Propriedade (invariante) | Processo sintético | Observação esperada | NO_KILL |
|---|---|---|---|---|
| D1 | `observe_tree` tri-estado em árvore viva | neto que dorme N s dentro do Job | `LIVE` enquanto vivo; `EMPTY` só após drenar | sim |
| D2 | `request_stop` falho (helper nonzero/timeout) com árvore viva | helper forçado a sair !=0 | custodiante VIVO, erro persistido, sem close/kill | sim |
| D3 | custódia durável até `TREE_EMPTY` | neto que ignora o 1º SAFE_STOP, drena depois | hold; finaliza só com árvore vazia | sim |
| D4 | `KILL_ON_JOB_CLOSE` **ativo**: queda do supervisor | matar o supervisor (autorizado) com árvore viva | kernel encerra a árvore (fail-safe); recibo reservado | morte pelo kernel, não pelo supervisor |
| D5 | `KILL_ON_JOB_CLOSE` **removido** (disposição do titular) | disposição explícita + flag removido | handles fecham, árvore segue rodando, sem W04 | sim |
| D6 | leitura USN real: cursor não progressivo / EOF antes do fim | escrita controlada + consulta forçada | `read_complete=False`, W04 `BLOCKED` | n/a |
| D7 | identidade do neto `(pid, creation_time)` independente | `_JOB_GRANDCHILD` sintético | par independente casa com a observação do Job | n/a |
| D8 | evidência terminal vinculada | cadeia V003 sintética completa | `terminal=COMPLETE`; STATUS do produtor na árvore | n/a |

## Salvaguardas
- Prazo e condição de parada por alvo; nenhuma espera infinita não observável (CUSTODY_STATE a cada heartbeat).
- D4 é o **único** alvo com término de processo, pelo **kernel** (fail-safe), autorizado pelo titular, sobre
  processo sintético; o supervisor nunca mata por iniciativa própria.
- Cada recibo primário retorna hash-bound; nenhum resultado é promovido a PASS sem a observação exigida.

## Retorno
Recibos primários (`*_DIRECTED_*.json`) com SHA-256 dos bytes, identidades e observações. A qualificação
dirigida complementa (não substitui) a campanha R9 (23/23, MET) preservada e os controles negativos offline.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
