# PEGASUS FULL 2026 — Engenharia Final V008R5

- `delivery/` — release imutável: `PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R5_20261022.zip` (SHA-256 `A7957E69…`, 2.948 membros, manifesto `5E617BE8…`), bootstrap PS 5.1 com pins (`69474AFD…`), recibos externos e `00_START_HERE_PEGASUS_V008R5.md`. Texto de retorno: `RESPOSTA_CHATGPT_RUNNER_PARALELO_14_V008R5.md`.
- `source_v008_delta/` — cópia byte-idêntica, para revisão, de tudo que o V008 acrescentou ao payload V003 (`supervisor/`, `docs/V008/`, `receipts/V008/` incl. `offline_final/native_campaign_r4/`, `00_START_HERE_V008.md`).
- `build/` — `build_v008.py`, `make_delivery_receipts_v008r5.py`, `ps_parse_check.ps1`.
- `probes/` — `pending_causal_probe_v008.py`.

## Convergência das campanhas nativas (R2 → R3 → R4 → R5)

Cada campanha no Windows do titular, com a fronteira de exit honesta (sem falso PASS), revelou o próximo defeito físico real — não reproduzível offline — e foi corrigida:

- **R2** validou a fronteira de exit no Windows real (canários S00, S03 ARGV=37 MATCH).
- **R3** confirmou a correção do ciclo de vida do handle do Job: Q01/Q02 PASS nativos.
- **R4** confirmou o SAFE_STOP por plataforma: **Q01–Q09 e Q12 PASS nativos**, incl. **Q03 (SAFE_STOP) e Q04 (retomada exactly-once)**. Parou em **Q12b** (SAFE_STOP via `run-full` em subprocesso), que pendurou 1800 s.
- **R5 (esta entrega)** fecha a reentrega cooperativa do SAFE_STOP: o Ctrl+C entregue na janela de spawn de workers os matava em `import` sem o coordenador registrar o pedido (`STATUS.STOP_REQUESTED=False`). O supervisor passa a **reentregar** o Ctrl+C cooperativo (15 s, até 10×) até o coordenador registrar (`STATUS.STOP_REQUESTED=True`) ou o filho sair; nunca mata; uma vez registrado, não reentrega.

**tested=packaged=delivered:** M1 (`4D3CF6AC…`) → M2 (`5E617BE8…`) difere só por 33 arquivos de evidência sob `receipts/V008/offline_final/`; código e docs byte-idênticos. O extrato do ZIP reconfere 2.947/2.947 arquivos e roda 69/69 unit. Qualificação offline: unit 69/69 (inclui `SafeStopRedelivery`, `SafeStopExitPlatform`, `CustodyLifecycleContract`), mutantes do supervisor 23/23, fronteira do bootstrap 20/20 + mutantes 8/8 (template inalterado `B5CECF29…`), cadeia V003 19/19 imutável, qualificação supervisionada 16/16 PASS + 2 SKIPPED_NON_NATIVE.

Supersede o V008R4 (`9B2D3820…`). O payload V003 completo (2.867 arquivos byte-idênticos) está dentro do ZIP.

`G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO`

`CANDIDATE_COMPLETENESS=NOT_PASS` — único bloqueio externo: re-execução nativa da campanha única (`Verify` → `QualifyNative`) no Windows do titular.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
