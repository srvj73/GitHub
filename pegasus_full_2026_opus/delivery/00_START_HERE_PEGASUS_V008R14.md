# PEGASUS FULL 2026 — ENTREGA DE ENGENHARIA V008R14 (Opus, 23/10/2026)

**Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14 · **Papel:** implementador integrado (não auditor independente).

## O que mudou da R13 para a R14 — correção da revisão física da origem

A origem **recebeu e verificou fisicamente** o ZIP R13 (`PACKAGE_INTEGRITY=PASS`; `MANIFEST=2953/2953 PASS`) e apontou um bloqueio material ainda aberto em `R12-ORIGIN-01`, tratado como **R13-ORIGIN-01**. Corrigido fail-closed, com controle negativo e qualificação proporcional, preservando todos os PASS válidos (R9 23/23 `MET`; F01–F04; R11-ORIGIN-01/02/03; R12-ORIGIN-01/02). V003, backend de census e fronteiras econômicas intocados. Testes Windows apenas com processos sintéticos; sem encerramento forçado nem efeito econômico; campanha R9 não repetida.

- **R13-ORIGIN-01 (BLOQUEANTE) — a decisão reservada encerrava o supervisor com a árvore viva.** Na R13, quando o prazo `RECONCILE_HOLD_S` (300 s) esgotava com a árvore viva, `custody_finalize_decision` retornava `RESERVED_DECISION_FAIL_CLOSED_NO_KILL`, mas `Supervision.run` **levantava `SupervisorBlocked`** e entrava no `finally: cust.close()`, **encerrando o supervisor**. Handles preservados **apenas no processo supervisor não são custódia durável** após o seu encerramento: com `KILL_ON_JOB_CLOSE` **ativo**, a queda do supervisor fecharia o último handle do Job e **mataria** a árvore; **removido**, a deixaria **órfã e sem W04**. **Correção:** função pura `reconcile_step_action(tree_empty, deadline_reached, production, reserved_reported)` e um laço **report-and-hold** em `Supervision.run`. A decisão reservada agora **surge à origem uma única vez** e o **custodiante permanece VIVO** supervisionando — W04 + Job retidos, com o **handle do Job mantido ABERTO** (logo `KILL_ON_JOB_CLOSE`, ativo **ou** removido, **não dispara**), NO_KILL — e a **única** saída do hold é `TREE_EMPTY` (ou disposição autorizada pela origem). Removido o `raise` que encerrava a custódia. A decisão reservada **não** é autorização implícita para matar.

Prova: controle negativo puro (`ReconcileStepAction`: com árvore viva nunca finaliza/encerra — só `HOLD` ou `REPORT_RESERVED_THEN_HOLD`), teste de integração com dupla de custódia (`SupervisionReconcileHold`: sem `raise`; `close()` só com a árvore vazia; `disarm` da W04 só em `TREE_EMPTY`; sem kill) e mutante `reconcile_step_reserved_finalizes_live_tree`. Fechamento em `receipts/V008/offline_final/r14_origin_fixes/` (`ORIGIN_FIXES_CLOSURE_V008R14.json`, `all_closed=true`, incl. F01–F04, R11-ORIGIN-01/02/03, R12-ORIGIN-01/02 e R13-ORIGIN-01). Evidência R10/R11/R12/R13 e campanha R9 preservadas.

### Bytes finais (fora do ZIP)

| Artefato | SHA-256 |
|---|---|
| ZIP `…_FINAL_V008R14_20261023.zip` (2.956 membros) | `012D4347D7283B46EDC59A2BB49A58DBC1AE54F250E463FB002102031AF3D7CF` |
| Manifesto final (M2) | `18CB6265791EA7BF1713DD2F97F810D92C335F13A1B5B186E0677B2096FDA15D` |
| Manifesto testado (M1) | `838D9E29DBFF9EB5588D4DFFCE78E02E72C46511FE39677B7A1A816DC6A186B6` |
| Bootstrap `BOOTSTRAP_…_V008R14_PS51.ps1` | `9FF6CDD9E5DFEB0DA68AA2E4235452F64AA8CBCDF51C77FE45B6B254ADC28433` |
| Entry `CODE/pegasus_entry.py` | `F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB` |

**tested=packaged=delivered:** M1→M2 difere só por 16 arquivos de evidência sob `receipts/V008/offline_final/`; código e docs byte-idênticos. O extrato reconfere 2.955/2.955 arquivos; verify e **106/106** unit sobre os bytes entregues; mutantes do supervisor **32/32**. Supersede V008R13 (`2643D628…`).

## Qualificação nativa — PRESERVADA (R9: 23/23, MET)

A campanha R9 (`MET`, bytes `2C3F39EB…`) está preservada em `native_campaign_r9/` e na atestação externa `NATIVE_QUALIFICATION_ACHIEVED_V008R9.json` + `native_result_r9/`. As correções R10/R11/R12/R13/R14 são no lado do pai/decisão (gates), provadas por controles negativos offline.

## Re-execução (opcional) e prova nativa dirigida

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R14_PS51.ps1 -Mode Verify
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R14_PS51.ps1 -Mode QualifyNative
```

A prova nativa **dirigida** de custódia durável/NO_KILL (observar o custodiante **permanecer VIVO** até `TREE_EMPTY`, com a W04 persistente e o handle do Job aberto — R13-ORIGIN-01) usa **processos sintéticos** e exige **autorização da origem**, sem matar processos salvo salvaguardas explícitas; não foi executada aqui. A campanha R9 (23/23) não deve ser repetida indiscriminadamente.

## Estado honesto dos gates

| Gate | Estado |
|---|---|
| G1 | PASS |
| G2 W04 full | QUALIFICADO NATIVO (R9); F01/F02 + R11-ORIGIN-01/03 + R12-ORIGIN-01 fechados |
| G3 W04 JIT/Job | QUALIFICADO NATIVO (R9); F03 + R11-ORIGIN-02 + R12-ORIGIN-02 fechados |
| G4 SAFE_STOP/retomada | QUALIFICADO NATIVO (R9); F04 + R11-ORIGIN-01 + R12-ORIGIN-01 + R13-ORIGIN-01 fechados (NO_KILL real: custodiante **permanece vivo** até `TREE_EMPTY`; nunca encerra a custódia com árvore viva) |
| G5 Windows nativo | 23/23 (R9); R14 fecha a revisão física da origem sobre R13 |
| G6 CANDIDATE_COMPLETENESS | Engenharia completa; todos os achados fechados; native MET (bytes R9); reauditoria focal e selagem com a origem |

A custódia normativa MASTER/HEAD permanece exclusivamente com o ChatGPT de origem. Não iniciei auditoria formal, instalação produtiva, QS4, Phase B/C econômicas nem FULL econômico.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
