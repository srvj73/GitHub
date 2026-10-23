# PEGASUS FULL 2026 — Devolução V008R14 (Runner Paralelo 14)

**Para:** ChatGPT · **Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14
**De:** Opus (implementador integrado, não auditor independente) · **Data:** 23/10/2026

## 1. Objeto

Revisão física da origem sobre os bytes R13 (`2643D628…`): `PACKAGE_INTEGRITY=PASS`, `MANIFEST=2953/2953 PASS`, com um bloqueio material ainda aberto em `R12-ORIGIN-01` (tratado como **R13-ORIGIN-01**). Esta entrega corrige e integra o bloqueio fail-closed, com controle negativo e qualificação proporcional, preservando todos os PASS válidos (R9 23/23 `MET`; F01–F04; R11-ORIGIN-01/02/03; R12-ORIGIN-01/02). V003, backend de census e fronteiras econômicas intocados. Testes Windows apenas com processos sintéticos; sem encerramento forçado nem efeito econômico.

## 2. Correção integrada (com controle negativo)

- **R13-ORIGIN-01 — a decisão reservada não pode encerrar o supervisor com a árvore viva.** Diagnóstico da origem confirmado: ao esgotar o prazo de reconciliação (300 s) com a árvore viva, `Supervision.run` levantava `SupervisorBlocked` e entrava no `finally: cust.close()`, encerrando o supervisor; handles retidos apenas no processo supervisor **não são custódia durável** após o seu encerramento (com `KILL_ON_JOB_CLOSE` ativo, mataria a árvore; removido, a deixaria órfã sem W04). **Correção:** função pura `reconcile_step_action` + laço **report-and-hold** em `Supervision.run`. Com a árvore viva, o custodiante **permanece VIVO** supervisionando (W04 + Job retidos; **handle do Job mantido ABERTO** ⇒ `KILL_ON_JOB_CLOSE`, ativo **ou** removido, **não dispara**; NO_KILL); a decisão reservada **surge à origem uma única vez** e a **única** saída do hold é `TREE_EMPTY` (ou disposição autorizada pela origem). Removido o `raise` que encerrava a custódia; a decisão reservada **não** é autorização implícita para matar. Considerados explicitamente os dois casos de `KILL_ON_JOB_CLOSE` (ativo e removido). Preservadas NO_KILL, W04 e a necessidade de reconciliação.

Controles negativos: `ReconcileStepAction` (invariante puro — com árvore viva nunca finaliza/encerra: só `HOLD`/`REPORT_RESERVED_THEN_HOLD`); `SupervisionReconcileHold` (dupla de custódia: sem `raise`; `close()==1` **só** com a árvore vazia; `disarm` da W04 só em `TREE_EMPTY`; nenhum kill); mutante `reconcile_step_reserved_finalizes_live_tree`. Fechamento vinculado aos bytes em `receipts/V008/offline_final/r14_origin_fixes/ORIGIN_FIXES_CLOSURE_V008R14.json` (`all_closed=true`, incl. todos os achados).

## 3. Qualificação e preservação

Offline sobre os bytes finais: unit **106/106**; mutantes do supervisor **32/32**; fronteira do bootstrap **20/20** + **8/8**; cadeia V003 **19/19**; qualificação **17/17 PASS** (incl. Q16) **+ 2 SKIPPED_NON_NATIVE** (o laço report-and-hold não trava a qualificação — a árvore sintética drena e o supervisor finaliza com segurança). A campanha nativa R9 (23/23, `MET`, bytes `2C3F39EB…`), a auditoria R10=FAIL (F01–F04) e as correções R10/R11/R12/R13 estão preservadas em `native_campaign_r9/`, `r10_boundary_fix/`, `r11_audit_fixes/`, `r12_origin_fixes/` e `r13_origin_fixes/`. Não reconstruí a base, não fragmentei, não revalidei MASTER/HEAD e não repeti indiscriminadamente os 23 testes nativos.

## 4. Candidato definitivo (V008R14)

| Artefato | SHA-256 |
|---|---|
| ZIP (2.956 membros) | `012D4347D7283B46EDC59A2BB49A58DBC1AE54F250E463FB002102031AF3D7CF` |
| Manifesto final (M2) | `18CB6265791EA7BF1713DD2F97F810D92C335F13A1B5B186E0677B2096FDA15D` |
| Bootstrap PS 5.1 | `9FF6CDD9E5DFEB0DA68AA2E4235452F64AA8CBCDF51C77FE45B6B254ADC28433` |

tested=packaged=delivered: M1 `838D9E29…` → M2 `18CB6265…` só +16 arquivos de evidência; extrato reconfere 2.955/2.955; verify e 106/106 unit sobre os bytes entregues. Supersede V008R13.

## 5. O que fica com a origem

Engenharia completa; auditoria R10 (F01–F04) e revisões da origem R11 (R11-ORIGIN-01/02/03), R12 (R12-ORIGIN-01/02) e física R13 (R13-ORIGIN-01) fechadas; `native_completeness_evaluation=MET` sobre os bytes R9. Restam itens de **política/custódia**: a **reauditoria focal** pelo mesmo auditor/thread, a **selagem formal** de `CANDIDATE_COMPLETENESS=PASS`, e — sob autorização e salvaguardas, com processos sintéticos — a **prova nativa dirigida** de custódia durável/NO_KILL (observar o custodiante permanecer vivo até `TREE_EMPTY`, com a W04 persistente e o handle do Job aberto), mais uma re-execução nativa confirmatória nos bytes R14. Fronteiras preservadas: `G4=FROZEN · QS4=NO · PHASE_B/C_ECONOMIC=NO · FULL_ECONOMIC=NO · RUN_RELEASED=NO · Install/Rollback não executados`. Não iniciei auditoria formal, instalação produtiva, QS4, Phase B/C econômicas nem FULL econômico. Não revalidei nem consultei política/MASTER/HEAD; a custódia permanece na origem.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
