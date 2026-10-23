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

## Revisão V008R8 — census de corroboração com nova tentativa

Na campanha R7, Q10a (que passara na R6) ficou `BLOCKED` por `CENSUS_TRUNCATED` — census de handles (só corroboração) incompleto de forma intermitente; a prova primária do kernel funcionou. Corrigido em V008R8: até 3 tentativas do census; se todas truncarem, o W04 continua bloqueando (fail-closed inalterado).

## Revisão V008R9 — negativos nativos em processo próprio

A campanha nativa R8 avançou 16 casos (Q01–Q09, Q12–Q15) e parou de novo em **Q10a**: prova do kernel íntegra (`WRITE_DENIED`; `RENAME_DENIED winerror=32`) mas W04 `BLOCKED` por `CENSUS_TRUNCATED`, **apesar** das 3 tentativas da R8. Causa: o backend de census pinado abandona threads que seguram handles quando uma consulta de nome trava e varre o próprio processo; num processo de qualificação longevo (que já rodou Q01–Q15) esses handles **acumulam** e cruzam o limite de truncamento — por isso Q12 (subprocesso próprio) passava e Q10a (processo longevo) truncava na mesma execução. Corrigido em V008R9: os negativos nativos (Q10a–f, Q11) rodam num **subprocesso novo** (`--native-negatives`), que parte de um census limpo; o pai reencena os casos no recibo (fail-closed se faltar JSON, caso ou conclusão). `w04_verdict` passa a registrar `census_attempts` e `census_abandoned_name_workers` em ambos os veredictos. A regra fail-closed do W04 não mudou: truncar mesmo em processo novo continua bloqueando — e aceitar corroboração degradada com a prova de kernel completa seria decisão de política do titular/origem. Regressão `NativeNegativesReplay`; unit 75/75; mutantes 24/24.

## Revisão V008R10 — fronteira fail-closed do rc do subprocesso + reconciliação de completude

A revisão da origem encontrou um defeito material: em `_native_negatives_in_fresh_process`, o `rc` do subprocesso dos negativos nativos era só registrado, não exigido `== 0`; um filho que gravasse um JSON completo e depois saísse com código não zero seria aceito (falsa completude). Corrigido em V008R10: o pai exige `rc == 0` antes de aceitar qualquer caso (`NATIVE_NEGATIVES_CHILD_NONZERO_EXIT` caso contrário). Controle negativo prova a reprodução (pré-correção ACEITA; corrigido REJEITA) em `receipts/V008/offline_final/r10_boundary_fix/`. A campanha nativa R9 (23/23, `MET`) é preservada e já satisfazia a fronteira (saiu `rc=0`). Busca adversarial de falsa completude consolidada: bloqueio econômico terminal e triplo (`make_run_plan` + `DefaultReleaseAdmission` + `_run_supervised`), nenhuma integração obrigatória por implementar. Unit 78/78; mutantes 24/24.

## Revisão V008R11 — correção dos achados da auditoria independente (Work Astra, FAIL sobre a R10)

A auditoria independente reprovou os bytes R10 com quatro achados reais, todos corrigidos fail-closed, com controle negativo, preservando os PASS anteriores (R9 23/23 MET; R10 rc-gate):

- **F01** W04 BLOCKED era promovido a sucesso/exit 0 → `completion_verdict` passa a **exigir** W04 atestado; `native_completeness` por caso obrigatório; negativo integrado Q16.
- **F02** armamento W04 incompleto não impedia o spawn → gate **pré-spawn** fail-closed (`W04_ARM_INCOMPLETE_NO_SPAWN_NO_PROTECTED_EFFECTS`) com liberação de handles parciais.
- **F03** `ctime` não resolvido virava GAPLESS; Q11 só por PID histórico → `lineage_verdict` bloqueia `unresolved>0`; Q11 exige identidade temporal (pid+ctime) no Job.
- **F04** `KILL_ON_JOB_CLOSE` podia matar árvore viva num encerramento controlado → `close` limpa o flag com árvore viva (NO_KILL), reconciliação pela próxima execução; fail-closed se não conseguir.

Regressões: `CompletionW04`, `W04PrespawnGate`, `LineageUnresolvedIdentity`, `JobCloseNoKill`, caso integrado `Q16`. Unit 86/86; mutantes 28/28. Fechamento em `receipts/V008/offline_final/r11_audit_fixes/`.

## Revisão V008R12 — correção da revisão preparatória da origem sobre a R11

A origem inspecionou os bytes R11 e apontou três pontos ainda abertos; todos corrigidos fail-closed, com controle negativo, preservando os PASS anteriores (R9 23/23 MET; F01–F04 da R11):

- **R11-ORIGIN-01** `close()` fechava o handle do Job com árvore viva antes do `raise` (kill podia disparar) e liberava W04 com o filho vivo → função pura `job_close_plan`: com árvore viva o supervisor **nunca fecha o handle do Job nem mata**; retém Job + W04; `close()` não levanta; `Supervision.run` registra a decisão reservada à origem.
- **R11-ORIGIN-02** Q11 casava por PID histórico → `grandchild_contained` exige `(pid, creation_time)` único e resolvido.
- **R11-ORIGIN-03** `cust.close()` não garantido em pré-spawn falho → `arm`/pré-spawn/`start` movidos para dentro do `try`; `finally: cust.close()` roda exatamente uma vez.

Regressões: `JobClosePlan`, `GrandchildContained`, `SupervisionPrespawnLifecycle`. Unit 94/94; mutantes 30/30. Fechamento em `receipts/V008/offline_final/r12_origin_fixes/`. A prova nativa dirigida de timeout/kill e a identidade temporal real no Windows ficam para o titular/origem.

## Revisão V008R13 — correção da revisão preparatória da origem sobre a R12

A origem inspecionou os bytes R12 e apontou dois bloqueios materiais ainda abertos; ambos corrigidos fail-closed, com controle negativo e qualificação proporcional, preservando os avanços da R12 e os PASS anteriores (R9 23/23 MET; F01–F04 da R11; R11-ORIGIN-01/02/03 da R12). Testes Windows apenas com processos sintéticos; nenhum encerramento forçado nem efeito econômico:

- **R12-ORIGIN-01** (BLOQUEANTE) reter handles só até o encerramento do supervisor não é custódia durável → função pura `custody_finalize_decision` + reconciliação custódia-preservada de `Supervision.run`: com árvore viva o custodiante **permanece VIVO supervisionando até `TREE_EMPTY`** (W04 + Job retidos por TODA a vida da árvore, drenagem cooperativa, NO_KILL, recuperação); produção não tem prazo; só a qualificação limitada, ao esgotar `RECONCILE_HOLD_S`, emerge como **decisão reservada à origem** (nunca mata, nunca solta W04); nunca finaliza/abandona árvore viva.
- **R12-ORIGIN-02** (LACUNA DE PROVA) identidade do neto não era temporalmente vinculada (um único `creation_time` histórico não prova) → o próprio neto reporta o seu `(pid, creation_time)` via `GetProcessTimes` sobre si mesmo (programa sintético `_JOB_GRANDCHILD`); `grandchild_contained(gpid, gctime, job_idents)` exige esse par **independente** presente e **único** na observação independente do Job. Divergência/ausência/ambiguidade recusam a contenção.

Regressões: `CustodyFinalizeDecision` (inclui `test_never_finalizes_live_tree`), `GrandchildContained` reescrita (match/divergente/sem-ctime/ambíguo/ausente). Unit 100/100; mutantes 31/31 (adiciona `custody_finalize_abandons_live_tree` e `grandchild_contained_accepts_divergent_ctime`). Fechamento em `receipts/V008/offline_final/r13_origin_fixes/`. A prova nativa dirigida de timeout/kill e a identidade do neto em processo sintético no Windows ficam para o titular/origem.

## Revisão V008R14 — correção da revisão física da origem sobre a R13

A origem recebeu e verificou fisicamente o ZIP R13 (`PACKAGE_INTEGRITY=PASS`; `MANIFEST=2953/2953 PASS`) e apontou um bloqueio material ainda aberto em `R12-ORIGIN-01` (tratado como **R13-ORIGIN-01**); corrigido fail-closed, com controle negativo, preservando todos os PASS válidos (R9 23/23 MET; F01–F04; R11-ORIGIN-01/02/03; R12-ORIGIN-01/02):

- **R13-ORIGIN-01** quando o prazo de reconciliação (300 s) esgotava com a árvore viva, `custody_finalize_decision` retornava `RESERVED_DECISION_FAIL_CLOSED_NO_KILL`, mas `Supervision.run` **levantava `SupervisorBlocked`** e entrava no `finally: cust.close()`, encerrando o supervisor — e handles preservados só no processo supervisor **não são custódia durável** (com `KILL_ON_JOB_CLOSE` ativo a queda mata a árvore; removido, deixa-a órfã sem W04). Correção: função pura `reconcile_step_action` + laço **report-and-hold**: a decisão reservada **surge à origem uma vez** e o **custodiante permanece VIVO** (W04 + Job retidos, handle do Job **aberto** ⇒ `KILL_ON_JOB_CLOSE` ativo **ou** removido **não dispara**), NO_KILL; a **única** saída do hold é `TREE_EMPTY`. Removido o `raise` que encerrava a custódia; a decisão reservada não é autorização implícita para matar.

Regressões: `ReconcileStepAction` (nunca finaliza árvore viva) e `SupervisionReconcileHold` (dupla de custódia: sem `raise`; `close()` só com árvore vazia; `disarm` da W04 só em `TREE_EMPTY`; sem kill). Unit 106/106; mutantes 32/32 (adiciona `reconcile_step_reserved_finalizes_live_tree`). Fechamento em `receipts/V008/offline_final/r14_origin_fixes/`. A prova nativa dirigida (custódia durável/NO_KILL em processos sintéticos) fica para o titular/origem.

## Estado honesto dos gates

Ver `receipts/V008/GATE_LEDGER_V008.json`. Em resumo: implementação integral e qualificação offline sobre os bytes finais concluídas; a prova nativa Windows de W04/Job/SAFE_STOP (G2, G3, G5) depende da campanha única `QualifyNative`; o binding de um harness QS4 sucessor ao adaptador G4 do V003 está provadamente ausente e exige qualificação QS4 própria, vedada nesta missão. Nenhum PASS foi declarado sem execução efetiva.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
