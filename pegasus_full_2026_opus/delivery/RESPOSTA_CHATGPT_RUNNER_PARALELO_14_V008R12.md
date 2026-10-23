# PEGASUS FULL 2026 — Devolução V008R12 (Runner Paralelo 14)

**Para:** ChatGPT · **Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14
**De:** Opus (implementador integrado, não auditor independente) · **Data:** 23/10/2026

## 1. Objeto

Revisão preparatória da origem sobre os bytes R11 (`DD1B3432…`): `CANDIDATE_COMPLETENESS=NOT_PASS`, três pontos abertos (R11-ORIGIN-01/02/03). Esta entrega corrige e integra os três fail-closed, com controles negativos e qualificação proporcional, preservando os PASS anteriores (R9 23/23 `MET`; F01–F04 fechados na R11). V003, backend de census e fronteiras econômicas intocados.

## 2. Correções integradas (com controle negativo)

- **R11-ORIGIN-01 — `close()` fechava o handle do Job com árvore viva antes do `raise`.** Função pura `job_close_plan`: com árvore viva, `close_handles=False` **sempre** — o supervisor **não fecha o handle do Job e não mata**; retém Job + lease W04 até o fim do processo; `close()` não levanta; `Supervision.run` grava `W04_NOKILL_LIVE_TREE_RESERVED_DECISION`. Removido o antigo `CloseHandle`-antes-de-`raise`. Unit `JobClosePlan`; mutante `job_close_plan_closes_live_tree`. A morte residual (fim do processo, só se o flag não pôde ser limpo) é **decisão reservada à origem**, nunca ação do supervisor.
- **R11-ORIGIN-02 — Q11 casava por PID histórico.** `grandchild_contained` exige `(pid, creation_time)` único e resolvido; PID solto/ambíguo não prova contenção. Q11 usa e registra o par vinculado. Unit `GrandchildContained`; mutante `grandchild_contained_ignores_ctime`.
- **R11-ORIGIN-03 — `cust.close()` não garantido em pré-spawn falho.** `arm`/pré-spawn/`start` movidos para dentro do `try`; `finally: cust.close()` roda exatamente uma vez em todo caminho pré-spawn falho e em exceção de `start`. Unit `SupervisionPrespawnLifecycle` (dupla de custódia: `close()==1`, sem matar processo real).

Fechamento vinculado aos bytes em `receipts/V008/offline_final/r12_origin_fixes/ORIGIN_FIXES_CLOSURE_V008R12.json` (`all_closed=true`, incl. F01–F04 e R11-ORIGIN-01/02/03).

## 3. Qualificação e preservação

Offline sobre os bytes finais: unit **94/94**; mutantes do supervisor **30/30**; fronteira do bootstrap **20/20** + **8/8**; cadeia V003 **19/19**; qualificação **17/17 PASS** (incl. Q16) **+ 2 SKIPPED_NON_NATIVE**. A campanha nativa R9 (23/23, `MET`, bytes `2C3F39EB…`), a auditoria R10=FAIL (F01–F04) e as correções R10/R11 estão preservadas em `native_campaign_r9/`, `r10_boundary_fix/` e `r11_audit_fixes/`. Não reconstruí a base, não fragmentei e não repeti os 23 testes nativos.

## 4. Candidato definitivo (V008R12)

| Artefato | SHA-256 |
|---|---|
| ZIP (2.952 membros) | `EA17EDE35C577CE1D69CB91D529F166B39FBD6B779D6F347487B65E3BF587082` |
| Manifesto final (M2) | `D49A54D8D9778A65CC597442FFCEB8041D3195C22566800EBB3E3536ACAD8035` |
| Bootstrap PS 5.1 | `1A63EE3AA368E0588E309765A3076591854B5E1EA13711FD0F8B68E00C95E2F9` |

tested=packaged=delivered: M1 `BEDEFC7A…` → M2 `D49A54D8…` só +16 arquivos de evidência; extrato reconfere 2.951/2.951; verify e 94/94 unit sobre os bytes entregues. Supersede V008R11.

## 5. O que fica com a origem

Engenharia completa; auditoria R10 (F01–F04) e revisão da origem R11 (R11-ORIGIN-01/02/03) fechadas; `native_completeness_evaluation=MET` sobre os bytes R9. Restam itens de **política/custódia**: a **reauditoria focal** pelo mesmo auditor/thread, a **selagem formal** de `CANDIDATE_COMPLETENESS=PASS`, e — sob autorização e salvaguardas — a **prova nativa dirigida de timeout/kill** (observar NO_KILL/W04 na árvore viva) e uma re-execução nativa confirmatória nos bytes R12. Fronteiras preservadas: `G4=FROZEN · QS4=NO · PHASE_B/C_ECONOMIC=NO · FULL_ECONOMIC=NO · RUN_RELEASED=NO · Install/Rollback não executados`. Não revalidei nem consultei política/MASTER/HEAD; a custódia permanece na origem.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
