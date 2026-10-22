# PEGASUS FULL 2026 — ENGENHARIA FINAL V008R1 — campanha única no Windows do titular

Revisão corretiva da V008: fecha o caminho executável supervisionado de `cmd_run` (achado da origem). Substitui a V008 (`31713EBF…`).

**Base:** Codex V003 físico (`CC37261C…`), byte-idêntico. **Pacote:** `PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R1_20261022.zip` — SHA-256 `912A7A1DE17F82A644829FB531B91C88621884E1912DF4FC77E41FF68B51BEB5` (87.350.085 bytes, 2.938 membros). **Bootstrap:** `BOOTSTRAP_PEGASUS_FULL_2026_V008R1_PS51.ps1` — SHA-256 `93B535336F9168BF69E014A8402C863E4B14CC690E2F683E4594C574F1B0D83C`. **Manifesto interno:** `A47F76466EE96959DC3E1EAFDF95C3540F94E04CE34CBB903795CA8F419AD762`.

Fronteiras: `G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO`.

## O que mudou na R1

`cmd_run` (modos `run-b/-c/-full`) agora é **admissão → plano → execução supervisionada**: a admissão é a única porta; concedida, o caminho percorre W04 armado antes do filho, Job, SAFE_STOP cooperativo, retomada e porta de conclusão. Em produção a admissão padrão delega ao `release_admission` selado do V003 e bloqueia (causa G00), sem efeito. O econômico fica triplamente travado (admissão default bloqueia; plano econômico recusado sem prova externa; executor econômico revalida por dentro).

## Passos (a partir de `PS C:\Users\silvi>`, sem `cd`, arquivos em `C:\Users\silvi\Downloads`)

```powershell
(Get-FileHash -LiteralPath C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R1_PS51.ps1 -Algorithm SHA256).Hash -ceq '93B535336F9168BF69E014A8402C863E4B14CC690E2F683E4594C574F1B0D83C'
(Get-FileHash -LiteralPath C:\Users\silvi\Downloads\PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R1_20261022.zip -Algorithm SHA256).Hash -ceq '912A7A1DE17F82A644829FB531B91C88621884E1912DF4FC77E41FF68B51BEB5'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R1_PS51.ps1 -Mode Verify
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R1_PS51.ps1 -Mode QualifyNative
```

`QualifyNative` (pede UAC uma vez) instala numpy 2.4.6 offline pela wheel do pacote e roda, sob Job e W04 reais, Q01–Q09 (A/B, SAFE_STOP com Ctrl+C real, retomada, duas lacunas, journal duplicado, porta de evidência), **Q12/Q12b** (o caminho `cmd_run` supervisionado e o SAFE_STOP+retomada por ele), **Q13a–c** (econômico bloqueado) e os negativos nativos Q10a–f/Q11.

Log sempre em `C:\Users\silvi\Downloads\PEGASUS_FULL_2026_RUNS\<MODO>_<yyyyMMdd_HHmmss_fff>_<PID>\RUN_LOG.txt`; resultado em `..._RESULT.zip`. Em falha, não repita automaticamente.

Devolva os `..._RESULT.zip` de `Verify` e `QualifyNative` ao ChatGPT, no projeto 'Pegasus Original', conversa 'Implementação Runner Paralelo 14'.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
