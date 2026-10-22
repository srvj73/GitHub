# PEGASUS FULL 2026 — Engenharia Final V008R4

- `delivery/` — release imutável: `PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R4_20261022.zip` (SHA-256 `9B2D3820…`, 2.949 membros, manifesto `7F7ADC57…`), bootstrap PS 5.1 com pins (`E5D5803D…`), recibos externos e `00_START_HERE_PEGASUS_V008R4.md` (campanha do titular). Texto de retorno: `RESPOSTA_CHATGPT_RUNNER_PARALELO_14_V008R4.md`.
- `source_v008_delta/` — cópia byte-idêntica, para revisão, de tudo que o V008 acrescentou ao payload V003 (`supervisor/` incl. `launcher/` e `tests/`, `docs/V008/`, `receipts/V008/` incl. `offline_final/native_campaign_r3/`, `00_START_HERE_V008.md`).
- `build/` — `build_v008.py` (manifesto/ZIP determinísticos), `make_delivery_receipts_v008r4.py` (recibos externos R4) e `ps_parse_check.ps1`.
- `probes/` — `pending_causal_probe_v008.py`.

## Convergência das campanhas nativas (R2 → R3 → R4)

Cada campanha no Windows do titular, com a fronteira de exit agora honesta (sem falso PASS), revelou o próximo defeito físico real — não reproduzível offline — e foi corrigida:

- **R2** validou a fronteira de exit no Windows real (canários S00 e S03 ARGV=37 MATCH).
- **R3** confirmou a correção do ciclo de vida do handle do Job: **Q01/Q02 passaram nativamente** (W04 armou, contabilidade do Job sem `ERROR_INVALID_HANDLE`). Parou em **Q03 (SAFE_STOP)**.
- **R4 (esta entrega)** corrige a confirmação de SAFE_STOP: o `child_exit == 130` era um **artefato POSIX** (o CPython re-ergue o SIGINT). No Windows o Ctrl+C cooperativo honrado sai `1` ou `0xC000013A`. `is_cooperative_stop_exit` aceita o código de interrupção da plataforma; a confirmação continua ancorada na evidência independente (STATUS `SAFE_STOP=YES` + árvore drenada + checkpoint válido + sem `RUN.lock` + W04) e no Q04 (retomada exactly-once). Crash (87) e exit 0 permanecem recusados.

**tested=packaged=delivered:** M1 (`E0B2119B…`) → M2 (`7F7ADC57…`) difere só por 34 arquivos de evidência sob `receipts/V008/offline_final/`; código e docs byte-idênticos. O extrato do ZIP reconfere 2.948/2.948 arquivos e roda 63/63 testes unitários. Qualificação offline: unit 63/63 (inclui `SafeStopExitPlatform`, `CustodyLifecycleContract`), mutantes do supervisor 22/22, fronteira do bootstrap 20/20 + mutantes 8/8 (template inalterado `B5CECF29…`, provado nativo), cadeia V003 19/19 imutável, qualificação supervisionada 16/16 PASS + 2 SKIPPED_NON_NATIVE.

Supersede o V008R3 (`46E4D331…`). O payload V003 completo (2.867 arquivos byte-idênticos) está dentro do ZIP.

`G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO`

`CANDIDATE_COMPLETENESS=NOT_PASS` — único bloqueio externo: re-execução nativa da campanha única (`Verify` → `QualifyNative`) no Windows do titular.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
