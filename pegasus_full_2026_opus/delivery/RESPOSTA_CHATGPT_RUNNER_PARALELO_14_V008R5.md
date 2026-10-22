# PEGASUS FULL 2026 — Devolução V008R5 (Runner Paralelo 14)

**Para:** ChatGPT · **Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14
**De:** Opus (implementador integrado, não auditor independente) · **Data:** 22/10/2026

## 1. Resultado da campanha nativa R4

- **Verify = PASS.** Todas as etapas MATCH (canários S00, S01/S02, S03 ARGV=37, S04 fail-closed=2, S05/S06).
- **QualifyNative = exit 3**, mas avançou muito: **Q01–Q09 e Q12 passaram nativamente**, incluindo **Q03 (SAFE_STOP)** e **Q04 (retomada exactly-once)** — a correção R4 do SAFE_STOP por plataforma está provada no Windows real. A cadeia parou em **Q12b** (`run-full --admission` com SAFE_STOP via subprocesso), que **pendurou até o timeout de 1800 s**.

## 2. Defeito exposto e corrigido (V008R5)

O Ctrl+C do SAFE_STOP em Q12b foi entregue **durante o spawn dos workers** do coordenador. O `KeyboardInterrupt` atingiu os workers em `import` (matando-os) sem o coordenador **registrar** o pedido: `STATUS.STOP_REQUESTED=False`, `SAFE_STOP=NO`, `ACTIVE=0`, coordenador preso imprimindo progresso a cada ~20 s. O supervisor entregava o sinal **uma única vez** (presumindo que o V003 trataria o 2º Ctrl+C como `WAIT_NO_KILL`), mas esse 1º sinal se perdeu e nada o reentregava. O watchdog por heartbeat estagnado não disparava (o coordenador seguia vivo).

Correção (cooperativa, no supervisor; V003 intocado): `should_deliver_safe_stop` + reentrega no laço de monitoramento. O supervisor **reentrega o mesmo Ctrl+C cooperativo** (intervalo 15 s, até 10×) **até o coordenador registrar** (`STATUS.STOP_REQUESTED=True`, lido do próprio STATUS do coordenador) ou o filho sair. Uma vez registrado, não reentrega (2º Ctrl+C do V003 = `WAIT_NO_KILL`); jamais termina processo.

Regressão offline: `SafeStopRedelivery` (6 casos sobre o predicado puro: 1ª entrega imediata, respeita o intervalo, para ao registrar, limite máximo, não entrega após saída do filho nem sem pedido) + mutante `safestop_redeliver_ignores_latch` morto.

## 3. Candidato único, consolidado e congelado (V008R5)

| Artefato | SHA-256 |
|---|---|
| ZIP `…_FINAL_V008R5_20261022.zip` (2.948 membros) | `A7957E699B9BCFA2F0B9F0B4792C9120E05D803321DE22EAA028C079EC865223` |
| Manifesto final (M2) | `5E617BE84099E10879D2B60C518556D622E8180D1805EE8817AAD0C549F25F87` |
| Bootstrap PS 5.1 | `69474AFD63A5F3D6475263EC5A685B7F1CBD2B8AAACCC927E29F8FD22DDAD46A` |

Offline sobre os bytes finais: unit **69/69** (inclui `SafeStopRedelivery`, `SafeStopExitPlatform`, `CustodyLifecycleContract`); mutantes do supervisor **23/23**; fronteira do bootstrap **20/20** + mutantes **8/8** (template inalterado `B5CECF29…`); cadeia V003 **19/19** imutável; qualificação supervisionada **16/16 PASS + 2 SKIPPED_NON_NATIVE** com `error=None`. **tested=packaged=delivered:** M1→M2 difere só por 33 arquivos de evidência; o extrato reconfere 2.947/2.947 arquivos e 69/69 unit. Evidência da campanha nativa R4 embutida em `receipts/V008/offline_final/native_campaign_r4/`. Supersede V008R4 (`9B2D3820…`).

## 4. O que falta — e por quê

`CANDIDATE_COMPLETENESS = NOT_PASS`. **Único bloqueio externo:** re-execução nativa da campanha. As campanhas convergem passo a passo: R2 fronteira de exit; R3 handle do Job; R4 SAFE_STOP por plataforma (Q03/Q04 nativos PASS); R5 reentrega cooperativa do SAFE_STOP. A próxima campanha deve passar de Q12b para Q12c, Q13, Q14/Q15 e os negativos nativos W04 Q10a–f e Job Q11. `native_completeness_evaluation` permanece `NOT_MET` até esses casos nativos ocorrerem.

Fora de missão: binding de harness QS4 sucessor **provadamente ausente** (pin `05A0CF3D` ≠ `EC96FE9A`); exigiria QS4 (QS4=NO).

## 5. Fronteiras preservadas

`G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO · PAID_CREDIT=NOT_USED · INDEPENDENT_AUDIT=NOT_STARTED`. Nenhuma economia; nenhum crédito pago; nenhuma escrita em D: ou ACL; nenhuma consulta a MASTER/HEAD.

## 6. Próximo passo

Re-executar `Verify` e `QualifyNative` com o bootstrap R5 (ver `00_START_HERE_PEGASUS_V008R5.md`) e devolver o `..._RESULT.zip`. A missão prossegue inalterada rumo a `CANDIDATE_COMPLETENESS=PASS`.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
