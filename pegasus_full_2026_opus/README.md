# PEGASUS FULL 2026 — Engenharia Final V008R2

- `delivery/` — release imutável: `PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R2_20261022.zip` (SHA-256 `4A167681…`, 2.944 membros, manifesto `9FA39FC9…`), bootstrap PS 5.1 com pins (`DF1DF8C3…`), recibos externos e `00_START_HERE_PEGASUS_V008R2.md` (campanha do titular). Texto de retorno: `RESPOSTA_CHATGPT_RUNNER_PARALELO_14_V008R2.md`.
- `source_v008_delta/` — cópia byte-idêntica, para revisão, de tudo que o V008 acrescentou ao payload V003 (`supervisor/` incl. `launcher/` e `tests/`, `docs/V008/`, `receipts/V008/`, `00_START_HERE_V008.md`).
- `build/` — `build_v008.py` (manifesto/ZIP determinísticos), `make_delivery_receipts_v008r2.py` (recibos externos R2) e `ps_parse_check.ps1` (parse estático PS).
- `probes/` — `pending_causal_probe_v008.py` (probe instrumentado da pendência `.pending`/journal).

## V008R2 — fronteira de exit codes fechada

A campanha nativa R1 terminou `EXIT=3` por um defeito do PowerShell 5.1: `Start-Process -PassThru` não retém o handle do processo; o `ExitCode` `$null` de um filho rápido era coagido a `0` — falso PASS (inclusive no relé do UAC). O V008R2 reescreve a fronteira inteira:

- **Bootstrap**: captura nativa com handle retido (`Process.Start()` + `$null = $Child.Handle`), exit **fail-closed** (ausente/não encerrado nunca vira 0), dreno assíncrono de stdout/stderr, watchdog que não mata o filho (recibo de reconciliação), relé do UAC que confronta exit do processo com exit gravado.
- **Supervisor**: `classify_exit` exato (0 PASS · 2 BLOCKED · 3 FAIL técnico · 130 SAFE_STOP · desconhecido ⇒ fail-closed); `_run_supervised` grava `exit_code`/`exit_class`; exceção técnica ⇒ 3.

Controles sobre os **bytes reais** do template (extração por AST): `test_bootstrap_exit_boundary_v008.ps1` 20/20; `mutation_bootstrap_exit_boundary_v008.py` 8/8 mutantes mortos. Unit do supervisor 55/55; mutantes 20/20. Qualificação acrescida de Q14 (matriz de propagação de exit) e Q15 (classificação técnica); o recibo embute `native_completeness_evaluation` (`NOT_MET` fora do Windows nativo).

**tested=packaged=delivered:** M1 (`165BE55F…`) → M2 (`9FA39FC9…`) difere apenas por 29 arquivos de evidência sob `receipts/V008/offline_final/`; código e docs byte-idênticos. O extrato do ZIP reconfere 2.943/2.943 arquivos e roda 55/55 testes unitários.

Supersede o V008R1 (`912A7A1D…`). O payload V003 completo (2.867 arquivos byte-idênticos) está dentro do ZIP; não é duplicado aqui.

`G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO`

`CANDIDATE_COMPLETENESS=NOT_PASS` — único bloqueio externo: execução nativa da campanha única (`Verify` → `QualifyNative`) no Windows do titular.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
