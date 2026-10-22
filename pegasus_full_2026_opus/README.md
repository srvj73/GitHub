# PEGASUS FULL 2026 — Engenharia Final V008R3

- `delivery/` — release imutável: `PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R3_20261022.zip` (SHA-256 `46E4D331…`, 2.948 membros, manifesto `3199509D…`), bootstrap PS 5.1 com pins (`4185F66D…`), recibos externos e `00_START_HERE_PEGASUS_V008R3.md` (campanha do titular). Texto de retorno: `RESPOSTA_CHATGPT_RUNNER_PARALELO_14_V008R3.md`.
- `source_v008_delta/` — cópia byte-idêntica, para revisão, de tudo que o V008 acrescentou ao payload V003 (`supervisor/` incl. `launcher/` e `tests/`, `docs/V008/`, `receipts/V008/` incl. `offline_final/native_campaign_r2/`, `00_START_HERE_V008.md`).
- `build/` — `build_v008.py` (manifesto/ZIP determinísticos), `make_delivery_receipts_v008r3.py` (recibos externos R3) e `ps_parse_check.ps1`.
- `probes/` — `pending_causal_probe_v008.py`.

## V008R3 — ciclo de vida do handle do Job fechado

A campanha nativa R2 **validou a fronteira de exit no Windows real** (canários S00 e o probe S03 ARGV=37 todos MATCH; sem falso PASS) e, por não mais mascarar erros, **expôs** um defeito real em S07: `JOB_ACCOUNTING_FAILED winerror=6` (`ERROR_INVALID_HANDLE`). Causa: o supervisor consultava a contabilidade do Job Object **depois** de `cust.close()` fechar o handle.

Correção:
- **Supervisor**: evidência terminal capturada em locais **antes** de `cust.close()`; nenhuma consulta ao custodiante após `close()`.
- **Custodiantes (Windows e POSIX)**: **recusam** consultas após `close()` (`CUSTODY_QUERIED_AFTER_CLOSE`), fazendo o POSIX reproduzir offline a classe de erro que no nativo era `ERROR_INVALID_HANDLE`.
- **Regressão**: `CustodyLifecycleContract` (unit 56/56).

**tested=packaged=delivered:** M1 (`559B1D6F…`) → M2 (`3199509D…`) difere só por 33 arquivos de evidência sob `receipts/V008/offline_final/`; código e docs byte-idênticos. O extrato do ZIP reconfere 2.947/2.947 arquivos e roda 56/56 testes unitários. Qualificação offline: unit 56/56, mutantes do supervisor 20/20, fronteira do bootstrap 20/20 + mutantes 8/8 (template inalterado `B5CECF29…`, provado nativo na R2), cadeia V003 19/19 imutável, qualificação supervisionada 16/16 PASS + 2 SKIPPED_NON_NATIVE.

Supersede o V008R2 (`4A167681…`). O payload V003 completo (2.867 arquivos byte-idênticos) está dentro do ZIP.

`G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO`

`CANDIDATE_COMPLETENESS=NOT_PASS` — único bloqueio externo: re-execução nativa da campanha única (`Verify` → `QualifyNative`) no Windows do titular.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
