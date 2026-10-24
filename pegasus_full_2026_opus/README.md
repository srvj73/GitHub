# PEGASUS FULL 2026 — Engenharia Final V008R17

- `delivery/` — release imutável: `PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R17_20261024.zip` (SHA-256 `67BFF721609866ADA51CF283DDF67CCA5DF66FEC6183B3714AB665A389D396EA`, 2.973 membros, manifesto `58EB5FFD…`), bootstrap PS 5.1 com pins (`DC45953F…`), recibos externos, `00_START_HERE_PEGASUS_V008R17.md` e a atestação nativa R9 preservada. Texto de retorno: `RESPOSTA_CHATGPT_RUNNER_PARALELO_15_V008R17.md`.
- `source_v008_delta/` — delta V008 sobre o payload V003 (`supervisor/`, `docs/V008/` incl. `INTERNAL_AUDIT_R17.md` e `WINDOWS_DIRECTED_QUALIFICATION_PROTOCOL_R17.md`; `receipts/V008/` incl. `offline_final/native_campaign_r9/`, `r10_boundary_fix/` … `r16_origin_fixes/`, `r17_origin_fixes/`, `00_START_HERE_V008.md`).
- `build/` — `build_v008.py`, `make_delivery_receipts_v008r17.py` (M2+pacote+verificação), `make_r17_convergence_closure.py`, `qualify_build_v008r17_m1.py` (M1+bateria), `ps_parse_check.ps1`.

## V008R17 — convergência integrada sobre a R16 (I-01/I-02/I-03)

A origem revisou o candidato R16 (`PACKAGE_INTEGRITY_R16=PASS`) e apontou **três resíduos materiais** de **uma mesma classe causal**: o contrato entre **retenção física da custódia**, **verdade terminal única** e **rota executável de autorização/encadeamento**. A R17 fecha a classe como sistema, num único candidato, preservando todos os PASS válidos (R9 23/23 `MET`; R16 N1/N2/N3; A01–A04/INT da R15; F01–F04; R11/R12/R13-ORIGIN):

- **I-01** `W04Guard.evaluate` / `W04NativeLease.disarm(release=False)` separam a **avaliação** do veredito W04 da **liberação física** da lease; `_finalize` e o hold de emergência só chamam `release()` **após** `custody_close_confirmed`. Close recusado/UNKNOWN ⇒ W04+Job fisicamente retidos (`w04_held_pending_close`, NO_KILL).
- **I-02** `terminal_for_prespawn_block` / `terminal_for_post_spawn_fail` unificam o desfecho de **todos** os ramos de `_run_supervised`: `BLOCKED`/exit 2 só com o recibo canônico persistido; sobre o fallback FAIL ⇒ FAIL/exit 3 coerente; `_emit_summary` à prova de falha.
- **I-03** `production_admission_verdict` + `ProductionReleaseAdmission` (pacote de autorização externo do titular, gates técnicos R01–R06/QS4/QS5-B06/PolicyRoot/qualificação Windows/fontes-por-hash/volume/runtime vinculados por SHA) + `cmd_run_full` encadeando **B→C→FULL**. Mesmo um pacote completo bloqueia no selo final `entry.release_admission` (RUN_RELEASED=NO). Nada fabricado; QS4/Phase B/C não antecipados; sem Owner Gate; política não lida.

Fechamento em `receipts/V008/offline_final/r17_origin_fixes/` (`ORIGIN_FIXES_CLOSURE_V008R17.json`, `all_closed=true`: I-01, I-02, I-03, PRIOR_PRESERVED; `FALSE_COMPLETENESS_SEARCH_V008R17.json` = `NO_MANDATORY_ENGINEERING_INTEGRATION_UNIMPLEMENTED`). Regressões `R17W04EvaluateVsRelease`, `R17TerminalCoherencePure/Integration`, `R17ProductionAdmissionPure/FailClosed` falham na R16 congelada e PASS nos bytes R17; probe de convergência I-01/I-02/I-03 `all_safe` em R17 e UNSAFE reproduzido na R16.

**tested=packaged=delivered:** M1 (`AB4260C7…`) → M2 (`58EB5FFD…`) difere só por 18 arquivos de evidência sob `receipts/V008/offline_final/`; **código e docs byte-idênticos** (0 alterados, 0 removidos). Os bytes **entregues** (ZIP extraído) verificam `supervisor verify=PASS_PACKAGE_VERIFIED` e `entry verify=PACKAGE_INTEGRITY=PASS` (2.973 arquivos). Unit **191/191**; mutantes do supervisor **48/48**; qualificação **18 PASS** (incl. Q16, Q17) + 2 SKIPPED_NON_NATIVE; cadeia V003 preservada; QS4 binding `BLOCKED` (pin). `pwsh` indisponível no sandbox (template PS5.1 byte-validado na R16).

Supersede o V008R16 (`CE1E923D…`). O payload V003 completo está dentro do ZIP. A efetividade Win32 das rotas modificadas fica na qualificação dirigida R17 (processos sintéticos; **D4 não autorizado**): enquanto pendente, `TARGET_RUNTIME_PENDING` — sem declarar READY.

`G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO`
