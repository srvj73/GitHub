# PEGASUS FULL 2026 — Engenharia Final V008R16

- `delivery/` — release imutável: `PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R16_20261024.zip` (SHA-256 `CE1E923D9403774496906A51F849AB2E896277469E5FEDD412BACCD52DA656FD`, 2.969 membros, manifesto `6332DCAD…`), bootstrap PS 5.1 com pins (`B1983D67…`), recibos externos, `00_START_HERE_PEGASUS_V008R16.md` e a atestação nativa R9 preservada. Texto de retorno: `RESPOSTA_CHATGPT_RUNNER_PARALELO_14_V008R16.md`.
- `source_v008_delta/` — delta V008 sobre o payload V003 (`supervisor/`, `docs/V008/` incl. `INTERNAL_AUDIT_R16.md` e `WINDOWS_DIRECTED_QUALIFICATION_PROTOCOL_R16.md`; `receipts/V008/` incl. `offline_final/native_campaign_r9/`, `r10_boundary_fix/` … `r15_origin_fixes/`, `r16_origin_fixes/`, `00_START_HERE_V008.md`).
- `build/` — `build_v008.py`, `make_delivery_receipts_v008r16.py`, `ps_parse_check.ps1`.

## V008R16 — fechamento sistêmico do parecer físico da origem sobre a R15

A origem reproduziu fisicamente três inconsistências sobre a R15 (`PACKAGE_INTEGRITY_R15=PASS`; `MANIFEST=2962/2962`) que convergem para **uma família causal única**: a ausência de um contrato exaustivo entre fase real do filho, efeitos já possíveis, custódia/handles realmente retidos ou liberados, resultado terminal e recibo/exit final. A R16 fecha a classe como sistema, num único candidato, preservando todos os PASS válidos (R9 23/23 `MET`; F01–F04; R11/R12/R13-ORIGIN; A01–A04/INT da R15):

- **N1** `start_failure_effect_class` — retomada de thread ≥1 EXECUTOU ⇒ efeitos possíveis (nunca "sem efeito"/exit 2); `_run_spawned` só sai BLOCKED sem efeito quando provado.
- **N2** `close()` com prova estruturada + `_finalize` reconferindo a contabilidade final; `CUSTODIAN_CLOSED` só via `custody_close_confirmed`; senão hold observável (W04+Job retidos, NO_KILL).
- **N3** `supervised_final_outcome` — recibo canônico ausente nunca é sucesso; `result`/`exit_code`/fase/banner coerentes; emissão do resumo à prova de falha.

Fechamento em `receipts/V008/offline_final/r16_origin_fixes/` (`ORIGIN_FIXES_CLOSURE_V008R16.json`, `all_closed=true`: N1, N2, N3, INT-NEIGHBORS-R16, PRIOR_PRESERVED; `FALSE_COMPLETENESS_SEARCH_V008R16.json` = `NO_MANDATORY_ENGINEERING_INTEGRATION_UNIMPLEMENTED`). `r15_origin_fixes/` preservado. Regressões `R16EffectClassPure/CloseProofPure/OutcomeCoherencePure/Integration` falham na R15 congelada e PASS nos bytes R16; probe de convergência N1/N2/N3 `all_safe` em R16 e UNSAFE reproduzido na R15.

**tested=packaged=delivered:** M1 (`776A54F3…`) → M2 (`6332DCAD…`) difere só por 18 arquivos de evidência sob `receipts/V008/offline_final/`; código e docs byte-idênticos. Extrato reconfere 2.968/2.968; verify e **173/173** unit sobre os bytes entregues; mutantes do supervisor **48/48**; fronteira do bootstrap 20/20 + 8/8; cadeia V003 19/19; qualificação **18 PASS** (incl. Q16, Q17) + 2 SKIPPED_NON_NATIVE.

Supersede o V008R15 (`75EE96E7…`). O payload V003 completo está dentro do ZIP. A efetividade Win32 das rotas modificadas fica na qualificação dirigida (processos sintéticos; **D4 não autorizado**): enquanto pendente, `TARGET_RUNTIME_PENDING` — sem declarar READY.

`G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO`
