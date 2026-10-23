# PEGASUS FULL 2026 — Devolução V008R13 (Runner Paralelo 14)

**Para:** ChatGPT · **Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14
**De:** Opus (implementador integrado, não auditor independente) · **Data:** 23/10/2026

## 1. Objeto

Revisão preparatória da origem sobre os bytes R12 (`EA17EDE3…`): `CANDIDATE_COMPLETENESS=NOT_PASS`, dois bloqueios materiais abertos (R12-ORIGIN-01 e R12-ORIGIN-02). Esta entrega corrige e integra ambos fail-closed, com controles negativos e qualificação proporcional, preservando os avanços da R12 e os PASS anteriores (R9 23/23 `MET`; F01–F04 fechados na R11; R11-ORIGIN-01/02/03 fechados na R12). V003, backend de census e fronteiras econômicas intocados. Os testes Windows usam exclusivamente processos sintéticos, sem efeitos econômicos nem encerramento forçado não autorizado.

## 2. Correções integradas (com controle negativo)

- **R12-ORIGIN-01 — custódia durável: NO_KILL + W04 por toda a vida da árvore + custódia efetiva + recuperação.** Reter handles só até o encerramento do supervisor **não** é custódia durável. Função pura `custody_finalize_decision(tree_empty, reconcile_deadline_reached, production)` + reconciliação custódia-preservada de `Supervision.run`: com árvore viva, o **custodiante permanece VIVO supervisionando até `TREE_EMPTY`** (W04 + Job retidos por toda a vida da árvore, drenagem cooperativa por SAFE_STOP, revalidação, NO_KILL, recuperação). Produção não tem prazo; só a qualificação limitada, ao esgotar `RECONCILE_HOLD_S`, emerge como **decisão reservada à origem** (`RESERVED_DECISION_FAIL_CLOSED_NO_KILL` / `CUSTODY_RECONCILE_DEADLINE_RESERVED_DECISION_NO_KILL`), nunca matando e nunca soltando a W04. A decisão **nunca finaliza/abandona** árvore viva. Unit `CustodyFinalizeDecision` (incl. `test_never_finalizes_live_tree`) + `JobClosePlan`; mutante `custody_finalize_abandons_live_tree`. Preserva a correção R11-ORIGIN-01 (close() nunca fecha o handle do Job nem mata com árvore viva), qualificando o delta Windows necessário.
- **R12-ORIGIN-02 — identidade do neto independente e temporalmente vinculada.** Um único `creation_time` histórico para um PID não basta. O próprio neto reporta o seu `(pid, creation_time)` via `GetProcessTimes` **sobre si mesmo** (programa sintético `_JOB_GRANDCHILD`); `grandchild_contained(gpid, gctime, job_idents)` exige esse par **independente** presente e **único** na observação independente do Job (resolvida por `process_ctime`). Recusa fail-closed divergência/ausência/ambiguidade. Q11 injeta o neto sintético e grava `grandchild_self_identity` no recibo. Unit `GrandchildContained` (match / divergente / sem-ctime / ambíguo / ausente); mutante `grandchild_contained_accepts_divergent_ctime`. Preserva a correção pré-spawn já implementada (R11-ORIGIN-03).

Fechamento vinculado aos bytes em `receipts/V008/offline_final/r13_origin_fixes/ORIGIN_FIXES_CLOSURE_V008R13.json` (`all_closed=true`, incl. F01–F04, R11-ORIGIN-01/02/03 e R12-ORIGIN-01/02).

## 3. Qualificação e preservação

Offline sobre os bytes finais: unit **100/100**; mutantes do supervisor **31/31**; fronteira do bootstrap **20/20** + **8/8**; cadeia V003 **19/19**; qualificação **17/17 PASS** (incl. Q16) **+ 2 SKIPPED_NON_NATIVE**. A campanha nativa R9 (23/23, `MET`, bytes `2C3F39EB…`), a auditoria R10=FAIL (F01–F04) e as correções R10/R11/R12 estão preservadas em `native_campaign_r9/`, `r10_boundary_fix/`, `r11_audit_fixes/` e `r12_origin_fixes/`. Não reconstruí a base, não fragmentei, não revalidei MASTER/HEAD e não repeti indiscriminadamente os 23 testes nativos.

## 4. Candidato definitivo (V008R13)

| Artefato | SHA-256 |
|---|---|
| ZIP (2.954 membros) | `2643D6280F159CA68BC0013932C7FF32FEBC69D0D5FBD47A812D85EA312C6E87` |
| Manifesto final (M2) | `69C90D16005609A83B67FC5970A57515C5B7AA3CB9EC1C844E19E432BDB22062` |
| Bootstrap PS 5.1 | `5EE03C35DDB4C054F8EC382934BD37B90572F8E47F4C9887CDDF40FA406C3FA7` |

tested=packaged=delivered: M1 `AC6F6AB9…` → M2 `69C90D16…` só +16 arquivos de evidência; extrato reconfere 2.953/2.953; verify e 100/100 unit sobre os bytes entregues. Supersede V008R12.

## 5. O que fica com a origem

Engenharia completa; auditoria R10 (F01–F04) e revisões da origem R11 (R11-ORIGIN-01/02/03) e R12 (R12-ORIGIN-01/02) fechadas; `native_completeness_evaluation=MET` sobre os bytes R9. Restam itens de **política/custódia**: a **reauditoria focal** pelo mesmo auditor/thread, a **selagem formal** de `CANDIDATE_COMPLETENESS=PASS`, e — sob autorização e salvaguardas, com processos sintéticos — a **prova nativa dirigida** de custódia durável/NO_KILL (custodiante vivo até `TREE_EMPTY`, W04 persistente) e da identidade `(pid, creation_time)` independente do neto, mais uma re-execução nativa confirmatória nos bytes R13. Fronteiras preservadas: `G4=FROZEN · QS4=NO · PHASE_B/C_ECONOMIC=NO · FULL_ECONOMIC=NO · RUN_RELEASED=NO · Install/Rollback não executados`. Não iniciei auditoria formal, instalação produtiva, QS4, Phase B/C econômicas nem FULL econômico. Não revalidei nem consultei política/MASTER/HEAD; a custódia permanece na origem.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
