# PEGASUS FULL 2026 — Engenharia Final V008R6

- `delivery/` — release imutável: `PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R6_20261022.zip` (SHA-256 `4B8DF8B9…`, 2.949 membros, manifesto `186E8A0F…`), bootstrap PS 5.1 com pins (`B90A86FA…`), recibos externos e `00_START_HERE_PEGASUS_V008R6.md`. Texto de retorno: `RESPOSTA_CHATGPT_RUNNER_PARALELO_14_V008R6.md`.
- `source_v008_delta/` — cópia byte-idêntica, para revisão, do delta V008 sobre o payload V003 (`supervisor/`, `docs/V008/`, `receipts/V008/` incl. `offline_final/native_campaign_r5/`, `00_START_HERE_V008.md`).
- `build/` — `build_v008.py`, `make_delivery_receipts_v008r6.py`, `ps_parse_check.ps1`.
- `probes/` — `pending_causal_probe_v008.py`.

## Convergência das campanhas nativas (R2 → R6)

Cada campanha no Windows do titular, com a fronteira de exit honesta (sem falso PASS), revelou o próximo defeito físico real — não reproduzível offline — e foi corrigida:

- **R2** validou a fronteira de exit no Windows real (canários S00, S03 ARGV=37 MATCH).
- **R3** fechou o ciclo de vida do handle do Job: Q01/Q02 PASS nativos.
- **R4** fechou o SAFE_STOP por plataforma: Q01–Q09 e Q12 PASS nativos (incl. Q03/Q04). Parou em Q12b.
- **R5** fechou (tentativa) a reentrega cooperativa; a campanha mostrou que reentregar **não** recupera o encrave — Q03 preso em `ACTIVE=0`.
- **R6 (esta entrega)** fecha a **janela segura de entrega**: o Ctrl+C vai ao grupo do console; entregue com `ACTIVE=0` (spawn/`import` dos workers) ele mata workers em import e encrava o coordenador. No Windows, o supervisor passa a entregar o SAFE_STOP só com `ACTIVE>0` (workers em execução, que ignoram o SIGINT por design); no POSIX entrega direto ao coordenador (`os.kill`). Encrave vira falha-fechada em 180 s (`SAFE_STOP_NOT_HONORED`), sem pendurar.

**tested=packaged=delivered:** M1 (`EA3AF7FB…`) → M2 (`186E8A0F…`) difere só por 34 arquivos de evidência sob `receipts/V008/offline_final/`; código e docs byte-idênticos. O extrato do ZIP reconfere 2.948/2.948 arquivos e roda 71/71 unit. Qualificação offline: unit 71/71 (inclui `SafeStopRedelivery` com janela segura, `SafeStopExitPlatform`, `CustodyLifecycleContract`), mutantes do supervisor 24/24, fronteira do bootstrap 20/20 + mutantes 8/8 (template inalterado `B5CECF29…`), cadeia V003 19/19 imutável, qualificação supervisionada 16/16 PASS + 2 SKIPPED_NON_NATIVE.

Supersede o V008R5 (`A7957E69…`). O payload V003 completo (2.867 arquivos byte-idênticos) está dentro do ZIP.

`G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO`

`CANDIDATE_COMPLETENESS=NOT_PASS` — único bloqueio externo: re-execução nativa da campanha única (`Verify` → `QualifyNative`) no Windows do titular.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
