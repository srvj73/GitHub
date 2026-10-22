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

## Revisão V008R2 — fronteira de exit codes fechada

A campanha nativa R1 terminou `EXIT=3` por um defeito do PowerShell 5.1: `Start-Process -PassThru` não retém o handle, e o `ExitCode` `$null` de um filho rápido era coagido a `0` — falso PASS. O bootstrap foi reescrito para capturar o processo nativo com handle retido, exit **fail-closed** (ausente/não encerrado nunca vira 0), dreno assíncrono de stdout/stderr, watchdog que não mata o filho (grava recibo de reconciliação) e relé do UAC que confronta o exit do processo elevado com o exit gravado. O supervisor classifica exit de forma exata (0/2/3/130; desconhecido ⇒ fail-closed). Controles: `test_bootstrap_exit_boundary_v008.ps1` 20/20 e `mutation_bootstrap_exit_boundary_v008.py` 8/8 sobre os bytes reais do template; unit 55/55; mutantes do supervisor 20/20; qualificação acrescida de Q14/Q15. O recibo de qualificação passa a embutir `native_completeness_evaluation` (NOT_MET fora do Windows nativo).

## Revisão V008R3 — ciclo de vida do handle do Job fechado

A campanha nativa R2 **validou a fronteira de exit no Windows real** (canários S00 e o probe S03 ARGV=37 todos MATCH; sem falso PASS) e, por isso, **expôs** um defeito real em S07: `JOB_ACCOUNTING_FAILED winerror=6` (`ERROR_INVALID_HANDLE`). Causa: o supervisor consultava a contabilidade do Job **depois** de `cust.close()` fechar o handle. Corrigido em V008R3: a evidência terminal é capturada antes de `close()`, e os custodiantes (Windows e POSIX) passam a **recusar** consultas pós-close — o que torna o erro reproduzível offline no POSIX. Regressão `CustodyLifecycleContract`; unit 56/56; qualificação 16/16 PASS + 2 SKIP com `error=None`. Bootstrap inalterado (template `B5CECF29…`), já provado nativo.

## Revisão V008R4 — SAFE_STOP correto por plataforma

A campanha nativa R3 confirmou o fix do handle do Job (Q01/Q02 PASS nativos) e parou em Q03: `safestop_verdict` exigia `child_exit == 130`, um artefato POSIX. No Windows o Ctrl+C cooperativo honrado sai 1 (ou `0xC000013A`). Corrigido em V008R4: `is_cooperative_stop_exit` aceita o código de interrupção da plataforma, com a confirmação do SAFE_STOP ancorada na evidência independente (STATUS `SAFE_STOP=YES` + árvore drenada + checkpoint válido + sem `RUN.lock` + W04) e no Q04 (retomada exactly-once). Regressão `SafeStopExitPlatform`; unit 63/63; mutantes do supervisor 22/22.

## Revisão V008R5 — reentrega cooperativa do SAFE_STOP

A campanha nativa R4 confirmou o SAFE_STOP por plataforma: **Q01–Q09 e Q12 passaram nativamente** (incl. Q03 e Q04). Parou em **Q12b** (SAFE_STOP via `run-full` em subprocesso), que pendurou 1800 s: o Ctrl+C foi entregue na janela de spawn de workers, matou-os em import e o coordenador não registrou o pedido (`STATUS.STOP_REQUESTED=False`). Corrigido em V008R5: o supervisor **reentrega** o Ctrl+C cooperativo (a cada 15 s, até 10×) até o coordenador registrar (`STATUS.STOP_REQUESTED=True`) ou o filho sair; nunca mata; uma vez registrado, não reentrega. Regressão `SafeStopRedelivery`; unit 69/69; mutantes do supervisor 23/23.

## Revisão V008R6 — SAFE_STOP entregue só em janela segura

A campanha nativa R5 mostrou que reentregar o Ctrl+C (R5) nao resolve: em Q03 as reentregas mantiveram `STATUS.STOP_REQUESTED=False` ate o timeout. Causa: o Ctrl+C vai ao grupo do console; entregue com `ACTIVE=0` (spawn/import dos workers) ele mata os workers em import e encrava o coordenador. Corrigido em V008R6: no Windows o supervisor so entrega o SAFE_STOP com workers em execucao (`ACTIVE>0`), fora da janela de import; no POSIX entrega direto ao coordenador (os.kill). Encrave vira falha-fechada em 180 s (`SAFE_STOP_NOT_HONORED`), sem pendurar. Regressao `SafeStopRedelivery` (janela segura); unit 70/70; mutantes 24/24.

## Revisão V008R7 — contenção de breakaway do Job

A campanha nativa R6 provou **22 de 23 casos nativos** (Q01–Q15 + W04 Q10a–f, incl. Q03/Q04 SAFE_STOP/retomada e Q12b). Resta Q11: o neto imprimiu `BREAKAWAY_SUCCEEDED` porque o `CreateProcess` com `CREATE_BREAKAWAY_FROM_JOB` nao lancou — proxy incorreto no Win8+ (jobs aninhados), onde o SO pode nao lancar e ainda assim manter o processo no Job. Corrigido em V008R7: Q11 verifica **contencao real** (o PID do neto permanece em `job_pids` registrado pelo kernel) em vez do proxy; escape real = FAIL. `Supervision.run` passa a expor `job_pids`. Unit 71/71; mutantes 24/24.

## Estado honesto dos gates

Ver `receipts/V008/GATE_LEDGER_V008.json`. Em resumo: implementação integral e qualificação offline sobre os bytes finais concluídas; a prova nativa Windows de W04/Job/SAFE_STOP (G2, G3, G5) depende da campanha única `QualifyNative`; o binding de um harness QS4 sucessor ao adaptador G4 do V003 está provadamente ausente e exige qualificação QS4 própria, vedada nesta missão. Nenhum PASS foi declarado sem execução efetiva.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
