# Retorno — PEGASUS FULL 2026 — Engenharia Final V008R1 (Claude Opus, 22/10/2026)

**MISSION_ID:** PEGASUS_ORIGINAL_FULL_ENGENHARIA_FINAL_INTEGRADA_OPUS_20261022 · Papel: implementador integrado. Revisão corretiva da V008.

## 1. Achado da origem — resolvido

`supervisor/pegasus_supervisor_v008.py::cmd_run()` terminava incondicionalmente em `RELEASE_ADMISSION_RETURNED_WITHOUT_EXTERNAL_MODULE`: o caminho executável supervisionado não era percorrido após admissão válida. **Fechado:**

- `cmd_run` é agora **admissão → plano → `_run_supervised`**. A admissão é a porta única; concedida, o fluxo percorre W04 armado antes do filho → Job → SAFE_STOP cooperativo → retomada → porta de conclusão/evidência (o mesmo `Supervision` já qualificado).
- `DefaultReleaseAdmission` (padrão de `run-b/-c/-full`) delega ao `release_admission` selado do V003 → sempre `entry.Blocked` (G00), efeito NONE.
- `supervisor/tests/pegasus_synthetic_admission_v008.py`: admissão sintética isolada, não econômica, usável só via `--admission`, que exercita o caminho com o `synthetic_chain.py` (via real de worker/commit/journal/lease, recusa dados reais).
- Econômico travado em profundidade: (1) admissão default bloqueia; (2) `make_run_plan`/`_run_supervised` recusam plano econômico sem prova de autorização externa; (3) o executor econômico real revalida `release_admission` por dentro.
- Corrigido um duplo-import que daria identidade dupla de classe ao injetar a admissão (registro do módulo sob o nome canônico + captura fail-closed por nome).

## 2. Entrega (substitui a V008 `31713EBF…`)

| Artefato | SHA-256 |
|---|---|
| `PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R1_20261022.zip` (87.350.085 bytes, 2.938 membros) | `912A7A1DE17F82A644829FB531B91C88621884E1912DF4FC77E41FF68B51BEB5` |
| Manifesto interno (2.937 entradas) | `A47F76466EE96959DC3E1EAFDF95C3540F94E04CE34CBB903795CA8F419AD762` |
| `BOOTSTRAP_PEGASUS_FULL_2026_V008R1_PS51.ps1` (fora do ZIP) | `93B535336F9168BF69E014A8402C863E4B14CC690E2F683E4594C574F1B0D83C` |

Preservados: payload V003 byte-idêntico; G4 congelado; entrypoint `F77B5266…`; integridade da V008 anterior registrada como superseded.

## 3. Qualificação nos bytes finais

| Bateria | Resultado |
|---|---|
| Qualificação supervisionada V008R1 (runtime real, sintético) | **16/16 PASS** — Q01–Q09 + **Q12** (`cmd_run` percorre o caminho supervisionado até COMPLETED, bytes = referência) + **Q12b** (SAFE_STOP via `cmd_run` + retomada exactly-once) + **Q13a** (admissão default bloqueia os 3 modos, G00, efeito NONE) + **Q13b** (plano econômico recusado) + **Q13c** (argv ao executor econômico recusado, sem saída). Q10/Q11 nativos `SKIPPED_NON_NATIVE` |
| Cadeia completa do V003 (`tests/qualify.py`) | 19/19 (runtime inalterado; reaproveitada) |
| Testes unitários do supervisor | **52/52 PASS** (6 novos de wiring), inclusive sobre a cópia extraída do ZIP |
| Mutantes das invariantes | **17/17 mortos** (3 novos: plano econômico permitido, guarda econômico removido, admissão default retornando plano) |
| Testado = empacotado = entregue | **PASS offline** (nenhum dos 2.912 testados mudou; só recibos acrescentados; ZIP extraído verifica `A47F7646…`) |
| QS4 binding (harness R001 empacotado) | BLOCKED provado (pin `05A0CF3D` vs adaptador G4 `EC96FE9A`) |
| Parse PowerShell | PASS no pwsh 7.4.6 (limitado; PS 5.1 nativo pendente) |

## 4. Estado honesto

`G1=PASS (caminho supervisionado fechado; QS4 binding BLOCKED provado)` · `G2/G3=IMPLEMENTADOS, OFFLINE QUALIFICADOS, NATIVO PENDENTE` · `G4=OFFLINE PASS NO RUNTIME REAL, NATIVO PENDENTE` · `G5=CAMPANHA PRONTA` · `G6 CANDIDATE_COMPLETENESS=NOT_PASS`.

Toda engenharia internamente implementável — inclusive o caminho executável supervisionado — está implementada, conectada e qualificada offline. `ENGINEERING_COMPLETE`/`CANDIDATE_COMPLETENESS` não são declarados PASS: falta só a execução nativa Windows, fisicamente indisponível ao implementador. **Requisição única:** rodar no PC do titular `-Mode Verify` e depois `-Mode QualifyNative` do bootstrap `93B53533…` e devolver os dois `..._RESULT.zip`; com isso a mesma missão reconcilia G2/G3/G5 e emite (ou nega, com causa) `CANDIDATE_COMPLETENESS`.

`G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO` · créditos: não usados · auditoria independente: não iniciada.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
