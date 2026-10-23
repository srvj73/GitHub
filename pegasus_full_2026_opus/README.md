# PEGASUS FULL 2026 — Engenharia Final V008R9

- `delivery/` — release imutável: `PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R9_20261022.zip` (SHA-256 `2C3F39EB…`, 2.946 membros, manifesto `93D56AC7…`), bootstrap PS 5.1 com pins (`EFB77938…`), recibos externos e `00_START_HERE_PEGASUS_V008R9.md`. Texto de retorno: `RESPOSTA_CHATGPT_RUNNER_PARALELO_14_V008R9.md`.
- `source_v008_delta/` — delta V008 sobre o payload V003 (`supervisor/`, `docs/V008/`, `receipts/V008/` incl. `offline_final/native_campaign_r8/`, `00_START_HERE_V008.md`).
- `build/` — `build_v008.py`, `make_delivery_receipts_v008r9.py`, `ps_parse_check.ps1`.
- `probes/` — `pending_causal_probe_v008.py`.

## Convergência das campanhas nativas (R2 → R9)

Cada campanha no Windows do titular, com a fronteira de exit honesta, revelou o próximo defeito físico real — não reproduzível offline — e foi corrigida:

- **R2** fronteira de exit validada nativa (S00/S03 MATCH).
- **R3** ciclo de vida do handle do Job: Q01/Q02 PASS nativos.
- **R4** SAFE_STOP por plataforma: Q01–Q09 e Q12 PASS; parou em Q12b.
- **R5** diagnóstico: reentrega do Ctrl+C não recupera o encrave.
- **R6** janela segura de entrega (ACTIVE>0): **22/23 casos nativos PASS** (Q01–Q15 + W04 Q10a–f, incl. Q03/Q04 SAFE_STOP/retomada e Q12b). Resíduo: Q11 breakaway.
- **R7** contenção de breakaway: o proxy do `CreateProcess` é incorreto no Win8+ (jobs aninhados). Q11 passa a verificar a **contenção real** (o PID do neto permanece em `job_pids`). `Supervision.run` expõe `job_pids`.
- **R8** census de corroboração com até 3 tentativas: na R7, Q10a ficou `BLOCKED` por `CENSUS_TRUNCATED` intermitente, com a prova do kernel íntegra.
- **R9 (esta entrega)** negativos nativos em processo próprio: na R8, Q10a voltou a ficar `BLOCKED` por `CENSUS_TRUNCATED` **apesar** das 3 tentativas. Causa: o backend de census pinado abandona threads que seguram handles em consultas de nome travadas e varre o próprio processo; num processo de qualificação longevo (que já rodou Q01–Q15) esses handles acumulam e cruzam o limite de truncamento — por isso Q12 (subprocesso próprio) passava e Q10a (processo longevo) truncava na mesma execução. Os negativos nativos (Q10a–f, Q11) passam a rodar num **subprocesso novo** (`--native-negatives`), que parte de um census limpo; o pai reencena os casos no recibo (fail-closed se faltar JSON, caso ou conclusão). O `w04_verdict` passa a persistir `census_attempts` e `census_abandoned_name_workers`. A regra fail-closed do W04 continua inalterada.

**tested=packaged=delivered:** M1 (`7B85DA44…`) → M2 (`93D56AC7…`) difere só por 14 arquivos de evidência sob `receipts/V008/offline_final/`; código e docs byte-idênticos. O extrato reconfere 2.945/2.945 arquivos; verify e 75/75 unit sobre os bytes entregues. Offline: mutantes do supervisor 24/24, fronteira do bootstrap 20/20 + 8/8, cadeia V003 19/19, qualificação 16/16 PASS + 2 SKIPPED_NON_NATIVE.

Supersede o V008R8 (`17A9FB12…`). O payload V003 completo (2.867 arquivos byte-idênticos) está dentro do ZIP.

## Campanha nativa R9 — PASS (23/23 numa execução)

No PC do titular (PS 5.1, build 10.0.26200, 24 CPUs, elevado), sobre os bytes entregues (ZIP `2C3F39EB…`, manifesto `93D56AC7…`, Python 3.14.7 `4942B86A…`): `QualifyNative` exit 0, **23/23 casos PASS**, `native_completeness_evaluation=MET` (`unmet=[]`; W04 nativo PASS=5, GAPLESS_NATIVE_JOB=4). A correção R9 confirmou-se: **Q10a passou** com census `attempts=[1,1]`, `abandoned_name_workers=[0,0]` — no subprocesso novo o census não trunca. Atestação externa (vinculada aos SHAs entregues) em `delivery/NATIVE_QUALIFICATION_ACHIEVED_V008R9.json` e `delivery/native_result_r9/`. O candidato **não** foi reempacotado.

`G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO`

`native_completeness_evaluation=MET` sobre os bytes finais. A selagem formal de `CANDIDATE_COMPLETENESS` e o passo opcional `-Mode Install` são do titular/origem (`INDEPENDENT_AUDIT=NOT_STARTED`).

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
