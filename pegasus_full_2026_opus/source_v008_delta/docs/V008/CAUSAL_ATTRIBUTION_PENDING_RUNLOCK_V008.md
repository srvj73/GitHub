# Atribuição causal: `.pending` + journal simultâneos e `RUN.lock` em árvore concluída

## Pendência herdada

O V003 manteve `ROOT_CAUSE_NOT_PROVEN` e `RECOVERY=BLOCKED`: o caso `suite_final/fault_during_pending` preservado contém, ao mesmo tempo, o journal ativo do run 199, a cópia `RECOVERED_REQUEUE` desse mesmo journal (bytes idênticos), `sessions/2000-01-06.pending/trades.jsonl.gz` e o `RUN.lock` do run 222. Faltavam trilhas de operação; o probe instrumentado nunca foi executado.

## Prova executada nesta missão

Probe `pending_causal_probe_v008.py`, Python 3.12.3 + numpy 2.4.6 (wheel do próprio payload, hash do lock conferido), V003 byte-idêntico, fixtures sintéticas, root novo. Audit hook herdado pelos workers registra `rename/remove/rmdir/rmtree/mkdir/open` de escrita com PID; inventários com `(st_dev, st_ino, bytes, sha256)` após cada fase.

| Fase | Estado medido |
|---|---|
| Fault `during_pending` (pid 554) | journal ativo + `.pending/trades.jsonl.gz`; 65 arquivos de scratch (3 `.sealed`, sem `trades`); `RUN.lock` removido no `__exit__` |
| Retomada (pid 577) | criação do `RUN.lock` → `rmtree .pending` → `rmtree _scratch/554` → `os.rename` do journal para `RECOVERED_REQUEUE` → 2 commits → status final → `os.remove RUN.lock` |
| Estado final | 0 `.pending`, 0 journal ativo, sem `RUN.lock`, bytes econômicos iguais à referência |

A cadeia completa do V003 (`tests/qualify.py`) rodou nos mesmos bytes: **19/19 PASS**, inclusive `RECOVERY_during_pending`.

## Conclusão

1. O arquivo `RECOVERED_REQUEUE` só nasce do `os.rename` atômico do journal ativo; os dois nomes têm intervalos de existência disjuntos. Nenhum instante do runtime contém ambos.
2. O subconjunto histórico contém artefatos de **dois instantes**: A (pós-fault: scratch 199 com 3 `.sealed`, journal ativo, `.pending`) e B (janela entre o archive do último commit e o `rmtree` do scratch/`unlink` do lock: scratch 222/2000-01-11, journal `COMMITTED` 2000-01-11, `RECOVERED_REQUEUE`, `RUN.lock` 222).
3. Logo, o estado foi materializado por uma operação **externa ao runtime** que combinou ≥2 instantes (cópia não atômica ou restauração de superfície). O ator histórico exato não é identificável pelos bytes preservados; está provado que **não** é `commit`, `recover`, `archive_journal` nem `RunLock`. Entregue ao `recover`, esse estado falharia fechado (`BOTH_FINAL_AND_PENDING`).
4. O `RUN.lock` em árvore "concluída" decorre de o status 100%/`PROCESS_TREE_CLEAN` ser gravado antes do `__exit__`; qualquer captura guiada pelo status pode incluir o lock.

## Correção aplicada (somente onde há defeito real)

- Runtime: **nenhum patch** (sem defeito).
- Supervisor V008: `completion_verdict` só declara COMPLETED — e só permite captura de evidência — após exit observado, árvore vazia, `RUN.lock` ausente e dois inventários idênticos. Testado (Q09 e mutantes `completion_ignore_lock`, `completion_ignore_unstable_inventory`).
- Recovery do runtime: desbloqueado tecnicamente para qualificação; a qualificação nativa Windows segue na campanha única.
