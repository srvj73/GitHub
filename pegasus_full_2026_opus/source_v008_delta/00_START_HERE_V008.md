# PEGASUS FULL 2026 — ENGENHARIA FINAL V008 (Opus, 22/10/2026)

**Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14 · **Papel:** implementador integrado (não auditor independente).

## O que é este pacote

Um único release imutável construído **sobre o Codex V003 físico** (`CC37261C…`, payload `73EF2833…`): os 2.867 arquivos do payload V003 permanecem **byte-idênticos** (manifesto parent `701DF5EC…` preservado em `receipts/V008/PARENT_V003_MANIFEST_SHA256.json`). O V008 acrescenta, sem tocar em `CODE/` nem no G4:

- `supervisor/` — o pai realmente executado: W04 nativo JIT (lease deny-write/deny-delete + diretórios + USN + census), custódia Job (suspenso → Job → resume, linhagem `(PID, creation_time)` sem lacunas), SAFE_STOP cooperativo confirmado por evidência própria, porta de conclusão/evidência anti captura multi-instante, watchdog por estagnação de heartbeat, binding QS4 por bytes e ligação do `DurableStopAdapter` V006;
- `supervisor/launcher/` — template do bootstrap PowerShell 5.1 (modos `Verify`, `QualifyNative`, `Install`, `Rollback`);
- `QS4_HARNESS_R001/` — harness QS4 V002 R001 corrigido, byte-idêntico ao candidato `0680FE65…`;
- `docs/V008/` e `receipts/V008/` — mapa diferencial, atribuição causal, decisões de projeto, ledger e recibos offline.

## Fronteiras (inalteradas)

`G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO`. `run-b`, `run-c` e `run-full` passam primeiro pelo `release_admission` do V003 e bloqueiam antes de qualquer efeito. O modo de qualificação usa somente fixtures sintéticas do próprio pacote.

## Execução no Windows do titular

O bootstrap renderizado (com SHA do ZIP e do manifesto fixados) é entregue **fora** do ZIP. A partir de `PS C:\Users\silvi>`, sem `cd`, com o ZIP e o bootstrap em `C:\Users\silvi\Downloads`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008_PS51.ps1 -Mode Verify
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008_PS51.ps1 -Mode QualifyNative
```

Log sempre em `C:\Users\silvi\Downloads\PEGASUS_FULL_2026_RUNS\<MODO>_<yyyyMMdd_HHmmss_fff>_<PID>\RUN_LOG.txt`, independentemente da pasta atual; a instância elevada (UAC) usa a mesma pasta. O resultado é um `..._RESULT.zip` ao lado da pasta da execução.

## Estado honesto dos gates

Ver `receipts/V008/GATE_LEDGER_V008.json`. Em resumo: implementação integral e qualificação offline sobre os bytes finais concluídas; a prova nativa Windows de W04/Job/SAFE_STOP (G2, G3, G5) depende da campanha única `QualifyNative`; o binding de um harness QS4 sucessor ao adaptador G4 do V003 está provadamente ausente e exige qualificação QS4 própria, vedada nesta missão. Nenhum PASS foi declarado sem execução efetiva.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
