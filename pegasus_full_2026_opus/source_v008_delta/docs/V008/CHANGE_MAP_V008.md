# Mapa diferencial V008 contra os parents

## Base e parents (identidade por SHA-256, sem seleção por data ou nome)

| Parent | Identidade | Uso no V008 |
|---|---|---|
| Codex FULL V003 consolidado | ZIP `CC37261C…`; payload `73EF2833…`; manifesto `701DF5EC…` | Base única. 2.867 arquivos byte-idênticos; somente `MANIFEST_SHA256.json` da raiz é regenerado |
| G4 original congelado | `61330A93…` | Não alterado. O núcleo econômico `minotauro_*` do V003 é idêntico ao do G4; os 7 módulos `r1r11_*` divergentes já eram delta do Codex (V002/V003) |
| `pegasus_entry.py` (V003) | `F77B5266…` | Não alterado; a suíte final do V003 rodou agora sobre esses bytes empacotados |
| `r1r11_resources.py` (V003) | `719988E1…` | Não alterado (correção de `RunLock.__enter__` do Codex preservada) |
| Backend W04 R14R3 | `native_handle_backend_v001.py` `8FEF1313…` | Copiado byte-idêntico para `supervisor/`; usado como census de corroboração |
| SAFE_STOP V006 | `pegasus_qs4_stop_bridge_v006.py` `178CEBBC…` | Copiado byte-idêntico; `DurableStopAdapter` ligado ao `Orchestrator` pelo binding QS4 |
| QS4 V002 R001 | candidato `0680FE65…`; harness `E52AF782…` | `QS4_HARNESS_R001/` byte-idêntico (28 arquivos) |
| V007 parent controlado | `2137D303…` | Mantido como prova histórica de identidade; substituído funcionalmente pelo supervisor V008 |

## Arquivos novos (todo o código novo está fora de `CODE/`)

| Arquivo | Função |
|---|---|
| `supervisor/pegasus_supervisor_v008.py` | Pai executado: verify, admissão B/C antes de efeitos, W04 JIT, custódia, SAFE_STOP confirmado, porta de conclusão, watchdog por heartbeat, CLI |
| `supervisor/pegasus_win_native_v008.py` | Camada Windows: Job (suspenso → assign → resume, IOCP, contabilidade), lease, diretórios, USN, identidade, census |
| `supervisor/pegasus_qs4_binding_v008.py` | Regra de binding QS4 por bytes; instalação do `DurableStopAdapter`; filho QS4 bloqueado até admissão |
| `supervisor/pegasus_qualify_v008.py` | Qualificação integrada não econômica sobre o runtime real (Q01–Q09; Q10–Q11 nativos) |
| `supervisor/tests/test_supervisor_v008.py`, `mutation_supervisor_v008.py` | Testes unitários e controles negativos por mutação |
| `supervisor/launcher/BOOTSTRAP_PEGASUS_FULL_2026_V008_PS51.template.ps1` | Bootstrap PS 5.1 (Verify/QualifyNative/Install/Rollback) |

**Por que nada entrou em `CODE/`:** `r1r11_full_2026.verify_package()` exige que `CODE/SHA256SUMS.txt` liste exatamente os arquivos de `CODE/`; acrescentar um módulo ali quebraria o caminho FULL.

## Testes reaproveitados e não repetidos

- Não repetidos (bytes inalterados): 80/80 QS4 R001 Linux, retirement V002, identidade V007, causa R14R2, smoke R14R3, 8 controles do delta `RunLock` V003, suítes históricas do G4.
- Executados agora porque **nunca haviam rodado nos bytes finais**: a cadeia `tests/qualify.py` do V003 havia parado em `during_pending` (3º de 8 faults). Rodou integralmente: 19/19 PASS.
- Executado pela primeira vez: probe instrumentado `during_pending` (o V003 registrava `directed_instrumented_probe=NOT_EXECUTED`).
- Novos: 46 testes unitários do supervisor, 14 mutantes, qualificação supervisionada Q01–Q09.

## Custos e efeitos

Nenhum crédito pago; nenhuma execução econômica; nenhuma escrita em D:, ACL produtiva, serviço ou tarefa. Downloads de terceiros no ambiente de build: apenas o PowerShell 7.4.6 oficial (hash da release conferido), usado só para análise sintática.


## Fecho estrutural V008R1 (achado da origem)

A origem apontou que `cmd_run()` terminava em `RELEASE_ADMISSION_RETURNED_WITHOUT_EXTERNAL_MODULE` — o caminho executável supervisionado não era percorrido após admissão válida. Fechado:

- `cmd_run` agora é **admissão → plano → `_run_supervised`**. A admissão é a única porta; `make_run_plan` recusa plano econômico sem prova de autorização externa; `_run_supervised` executa o argv admitido sob W04/Job/SAFE_STOP/retomada/porta de conclusão.
- `DefaultReleaseAdmission` (produção, default de `run-b/-c/-full`) delega ao `release_admission` selado do V003 → sempre `entry.Blocked` (causa G00), sem efeito.
- `supervisor/tests/pegasus_synthetic_admission_v008.py`: admissão sintética isolada (não econômica) usada só via `--admission`, para exercitar o caminho com o `synthetic_chain.py`.
- Barreiras econômicas em profundidade: (1) admissão default bloqueia; (2) `make_run_plan`/`_run_supervised` recusam plano econômico sem prova externa; (3) o executor econômico real revalida `release_admission` por dentro.

Qualificação acrescida: **Q12** (`cmd_run` percorre o caminho supervisionado até COMPLETED, bytes iguais à referência), **Q12b** (SAFE_STOP via `cmd_run` + retomada exactly-once), **Q13a** (admissão default bloqueia os 3 modos, causa G00, efeito NONE), **Q13b** (plano econômico recusado), **Q13c** (argv ao executor econômico real recusado, sem criar saída). Testes unitários 52/52; mutantes 17/17; parse PS 5.1-safe pelo pwsh 7.4.6.


## Fecho da fronteira de exit codes V008R2 (achado da campanha nativa R1)

A campanha nativa R1 do titular terminou `EXIT=3` com `ARGV_EXIT_PROPAGATION_PROBE_FAILED`, embora S03 tenha gravado `ARGV_PROBE.json` com `pass=true` (fonte sai 37) e o bootstrap registrasse `NATIVE_EXIT code=0`. Causa-raiz: no PowerShell 5.1, `Start-Process -PassThru` não retém o handle do processo; um filho de saída rápida devolve `ExitCode` `$null`, e `[int]$null` vira **0** — um vetor de **falso PASS** em toda etapa que espera 0, inclusive no relé do UAC. Não é um defeito isolado de S03; é a fronteira inteira de execução/propagação de exit e stdio.

Correção integral (não um remendo pontual):

- **Bootstrap reescrito** (`BOOTSTRAP_…_V008_PS51.template.ps1`): captura nativa por `System.Diagnostics.Process.Start()` com `$null = $Child.Handle` antes de `WaitForExit`; `Get-PegasusExitCode` é **fail-closed** (lança `NATIVE_PROCESS_OBJECT_NULL`, `NATIVE_EXIT_READ_BEFORE_EXIT`, `NATIVE_EXIT_NULL` — exit ausente/não encerrado nunca vira 0); dreno assíncrono de stdout/stderr por `ReadToEndAsync` (sem deadlock em fluxos grandes, bytes íntegros); higiene de ambiente (`PYTHONPATH`/`PYTHONHOME` removidos, flags fixas); watchdog por prazo que **não mata** o filho, grava `TIMEOUT_RECONCILE_<label>.json` (`kill_performed=false`) e lança; relé do UAC (`Resolve-PegasusRelayExit`) confronta o exit do processo elevado com o exit gravado pelo elevado — divergência ou nulo ⇒ 3. Recibo por etapa `{expected, observed, classification MATCH/MISMATCH/…, pid, creation_time_utc, stdout_bytes, stderr_bytes}`.
- **Supervisor** (`pegasus_supervisor_v008.py`): `classify_exit` e `EXIT_CLASSES` — 0 PASS; 2 BLOCKED (fail-closed, sem efeito); 3 FAIL técnico após início de efeito; 130 SAFE_STOP confirmado e retomável; ausente/não-inteiro ⇒ `EXIT_UNKNOWN_FAIL_CLOSED` (jamais PASS). `_run_supervised` classifica COMPLETED/STOPPED/FAIL e grava `exit_code`/`exit_class` no recibo; `main()` converte exceção técnica em exit 3 (`PEGASUS_SUPERVISOR=FAIL_TECHNICAL`), nunca 0/1.

Qualificação acrescida (sobre os bytes finais): **Q14** (matriz de propagação de exit por subprocesso sob a custódia: 0,1,2,3,7,19,37,130 observados exatamente), **Q15** (classificação técnica: exceção na admissão ⇒ 3; filho falho ⇒ 3 com `exit_class=FAIL_TECHNICAL_AFTER_EFFECT_START`). Nova avaliação objetiva embutida no recibo de qualificação: `native_completeness_evaluation` (partes 3–4 do CANDIDATE_COMPLETENESS; veredito `MET`/`NOT_MET` sobre o próprio run — `NOT_MET` fora do Windows nativo).

Controles negativos específicos da fronteira (sobre os **bytes reais** do template, extraídos por AST): `test_bootstrap_exit_boundary_v008.ps1` (20/20) e `mutation_bootstrap_exit_boundary_v008.py` (8/8 mutantes mortos: `null_exit_coerced_to_zero`, `exit_read_before_exit_allowed`, `relay_trusts_process_on_mismatch`, `relay_null_becomes_zero`, `expected_ignored`, `pythonpath_leaks`, `watchdog_kills_child`, `stderr_not_drained`). Testes unitários do supervisor 55/55; mutantes do supervisor 20/20. Nenhum PASS comprovado foi reexecutado sem impacto material; a cadeia V003 (19/19) permanece imutável e reaproveitada.


## Fecho do ciclo de vida do handle do Job V008R3 (achado da campanha nativa R2)

A campanha nativa R2 **validou a fronteira de exit no Windows real** (PS 5.1 build 26100): canários S00 (0,2,3,7,19,37,130 e fluxos 2 MB+2 MB → 5) todos MATCH; **S03 ARGV probe = 37 MATCH** (a R1 lia 0 — falso PASS eliminado); S01/S02/S04/S05/S06 MATCH. Sem a correção R2, o defeito abaixo teria sido mascarado como falso PASS.

A fronteira correta **expôs um defeito real** em S07 (`SUPERVISED_NATIVE_QUALIFICATION`, exit 3): `RuntimeError('JOB_ACCOUNTING_FAILED winerror=6')` (`ERROR_INVALID_HANDLE`). Causa-raiz: em `_run_supervised`, `cust.close()` fecha o handle do Job (o `KILL_ON_JOB_CLOSE` é apenas o fail-safe de queda do supervisor) e, **logo em seguida**, `lineage_verdict`/`completion_verdict` consultavam `cust.accounting()`/`cust.tree_empty()` sobre o handle já fechado. No POSIX esse `close()` era no-op e `accounting()` lia `/proc`, então a ordenação inválida passava silenciosamente — invisível offline.

Correção (três frentes):

- **Supervisor**: a evidência terminal (`accounting`, `tree_empty`, `new_process_events`, `marks`, `native_job`, `breakaway_allowed`) é capturada em variáveis locais **antes** do `finally: cust.close()`; `lineage`/`completion`/`safe_stop` passam a usar essas locais. Nenhuma consulta ao custodiante ocorre após `close()`.
- **Custodiantes (Windows e POSIX)**: passam a **recusar** `accounting()/tree_empty()/new_process_events()` após `close()` (`RuntimeError('CUSTODY_QUERIED_AFTER_CLOSE')`). Isso faz o caminho POSIX **reproduzir offline** a mesma classe de erro de ordenação que no nativo seria `ERROR_INVALID_HANDLE`; o Windows avalia a vacuidade pelo acessor cru antes de marcar fechado e então fecha os handles.
- **Teste de regressão** (`CustodyLifecycleContract`): prova que a evidência terminal é capturável enquanto aberto e recusada após `close()`.

Validação offline: unit do supervisor **56/56** (inclui o novo contrato); mutantes do supervisor 20/20; a qualificação supervisionada **16/16 PASS + 2 SKIPPED_NON_NATIVE** com `error=None` — o guarda POSIX **não** dispara, provando que o supervisor honra o contrato (se a reordenação estivesse incompleta, Q01 falharia com `CUSTODY_QUERIED_AFTER_CLOSE`). Bootstrap inalterado (template `B5CECF29…`): fronteira de exit 20/20 e mutantes 8/8 reaproveitados (bytes idênticos; já provados nativamente pelos canários S00 e pelo S03). Cadeia V003 19/19 imutável.


## Confirmação de SAFE_STOP por plataforma V008R4 (achado da campanha nativa R3)

A campanha nativa R3 **confirmou a correção do handle do Job** (R3): no Windows real, **Q01 e Q02 passaram nativamente** (W04 armou por caso — 43 arquivos, 0 violações, `usn_hits=0`; contabilidade do Job lida sem `ERROR_INVALID_HANDLE`). A cadeia avançou e parou em **Q03 (SAFE_STOP)**: `safestop_verdict` exigia `child_exit == 130`, mas o Ctrl+C cooperativo honrado pelo coordenador saiu **1** no Windows.

Causa-raiz: o `130` é um **artefato POSIX** — o CPython restaura o SIGINT ao default e o re-ergue, e o processo morre por SIGINT (128+2). O Windows não tem essa semântica: o `CTRL_C_EVENT` vira `KeyboardInterrupt` e, ao desenrolar o processo (aqui `InterruptedError` no `multiprocessing`), sai 1; quando o handler de console do Windows encerra o processo, sai `0xC000013A` (STATUS_CONTROL_C_EXIT). O STATUS do próprio filho já reportava `SAFE_STOP=YES`, `PROCESS_TREE_CLEAN=YES`, `COMMITTED=1/3`, checkpoint válido e sem `RUN.lock` — parada cooperativa limpa e retomável; o único descompasso era o código literal.

Correção (sem enfraquecer a garantia):

- `is_cooperative_stop_exit(code)`: aceita o código de interrupção **da plataforma** — `130` no POSIX; `1` ou `EXIT_CTRL_C_WINDOWS` (`0xC000013A`) no Windows. `safestop_verdict` passa a usá-lo no lugar de `child_exit != EXIT_SAFE_STOP`. O código de saída é **corroboração**: a confirmação do SAFE_STOP continua exigindo a evidência independente (STATUS `SAFE_STOP=YES` + árvore drenada sem kill + checkpoint válido + `RUN.lock` ausente + continuidade W04), e o **Q04** prova a retomada exactly-once. Exit 0 (completou) e códigos de crash (ex.: 87) permanecem recusados — inclusive no Windows.

Regressão offline: `SafeStopExitPlatform` (7 casos, `os.name` mockado para `nt`/`posix`) prova que exit 1/`0xC000013A` confirmam no Windows mas não no POSIX, que exit 0 nunca confirma, que crash 87 não confirma, e que um código de interrupção **sozinho** (sem STATUS `SAFE_STOP=YES`) continua `NOT_CONFIRMED`. Mutantes do supervisor **22/22** (novos `safestop_windows_accepts_any_code` e `custody_guard_after_close_disabled`); unit **63/63**. Fronteira do bootstrap inalterada (20/20 + 8/8). Cadeia V003 19/19 imutável.


## Reentrega cooperativa do SAFE_STOP V008R5 (achado da campanha nativa R4)

A campanha nativa R4 provou a correção do SAFE_STOP por plataforma (R4): no Windows real, **Q01–Q09 e Q12 passaram nativamente** — incluindo **Q03 (SAFE_STOP) e Q04 (retomada exactly-once)**. A cadeia avançou e parou em **Q12b** (`run-full --admission` com SAFE_STOP via subprocesso), que **pendurou até o timeout de 1800 s**.

Causa-raiz: o Ctrl+C do SAFE_STOP foi entregue **durante o spawn dos workers** do coordenador. Na janela de spawn, o `KeyboardInterrupt` atingiu os processos worker em `import` (matando-os) sem que o coordenador **registrasse** o pedido — `STATUS.STOP_REQUESTED` permaneceu `False`, `SAFE_STOP=NO`, `ACTIVE=0`, com o coordenador preso imprimindo progresso a cada ~20 s. O supervisor entregava o sinal **uma única vez** (assumindo que o V003 trata o 2º Ctrl+C como `WAIT_NO_KILL`), mas esse 1º sinal se perdeu, então nada o reentregava.

Correção (cooperativa, no supervisor; V003 intocado): `should_deliver_safe_stop` + reentrega no laço de monitoramento. O supervisor **reentrega o mesmo Ctrl+C cooperativo** (intervalo `SAFE_STOP_REDELIVER_S=15 s`, até `SAFE_STOP_MAX_DELIVERIES=10`) **até o coordenador LATCH-ar o pedido** (`STATUS.STOP_REQUESTED=True`) ou o filho sair. Uma vez registrado, não reentrega (o 2º Ctrl+C do V003 é `WAIT_NO_KILL`); jamais termina processo. O latch é lido do próprio STATUS do coordenador (`STOP_REQUESTED`), que fica `True` quando ele honra o pedido (visto em Q03). O watchdog por heartbeat estagnado não cobria este caso porque o coordenador seguia vivo e atualizando o STATUS.

Regressão offline: `SafeStopRedelivery` (6 casos sobre o predicado puro: 1ª entrega imediata, respeita o intervalo, para ao LATCH-ar, limite máximo, não entrega após saída do filho nem sem pedido) + mutante `safestop_redeliver_ignores_latch`. Unit do supervisor **69/69**; mutantes do supervisor **23/23**; fronteira do bootstrap 20/20 + 8/8 (template inalterado); cadeia V003 19/19 imutável; qualificação supervisionada 16/16 PASS + 2 SKIPPED_NON_NATIVE.


## Janela segura de entrega do SAFE_STOP V008R6 (achado da campanha nativa R5)

A campanha nativa R5 mostrou que a reentrega cooperativa (R5) **não** resolve a corrida: em Q03, as 8+ reentregas do Ctrl+C mantiveram `STATUS.STOP_REQUESTED=False`, `COMMITTED=1/3`, `ACTIVE=0`, até o timeout. O Q03 havia passado na R4 apenas por sorte de timing.

Causa-raiz precisa: o Ctrl+C vai ao **grupo do console**. Entregue no instante `ACTIVE=0` (logo após um `SESSION_COMMIT`, durante o spawn/`import` dos workers da próxima sessão), ele mata os workers em `import` — que ainda não instalaram o ignore-SIGINT do design V003 — e **encrava** o coordenador num estado `ACTIVE=0` do qual nenhum Ctrl+C posterior recupera. Com os workers já em execução (`ACTIVE>0`), eles ignoram o SIGINT e só o coordenador reage, registrando o pedido e fechando a admissão no próximo `SESSION_COMMIT`.

Correção (no supervisor; V003 intocado):

- **Janela segura**: `should_deliver_safe_stop` ganha `require_active_window`. No Windows (`os.name=='nt'`) a entrega só ocorre com `STATUS.ACTIVE>0` (workers em execução), nunca na janela de `import`/spawn. No POSIX o sinal vai só ao coordenador (`os.kill`), sem a corrida de console, então o gate não se aplica (preserva o Q03 offline).
- **Falha-fechada rápida**: `SAFE_STOP_HONOR_DEADLINE_S=180 s`. Se o pedido for feito mas o coordenador nunca registrar (encrave), o supervisor levanta `SAFE_STOP_NOT_HONORED_NO_LATCH_RECONCILE_REQUIRED` — diagnóstico claro em ~180 s em vez de pendurar até o timeout total. Jamais termina processo.

Regressão offline: `SafeStopRedelivery` passa a cobrir a janela segura (entrega imediata com `ACTIVE>0`; recusa em `ACTIVE=0` no Windows; POSIX entrega independente de `ACTIVE`) + mutante `safestop_delivers_in_spawn_window`. Unit do supervisor **70/70**; mutantes do supervisor **24/24**; fronteira do bootstrap 20/20 + 8/8 (template inalterado); cadeia V003 19/19 imutável; qualificação supervisionada 16/16 PASS + 2 SKIPPED_NON_NATIVE.


## Contenção de breakaway do Job V008R7 (achado da campanha nativa R6)

A campanha nativa R6 provou **22 de 23 casos nativos** (Q01–Q15 e os negativos W04 Q10a–f, incl. Q03 SAFE_STOP, Q04 retomada e Q12b — o que pendurava na R5). Único resíduo: **Q11** (linhagem Job + breakaway). Linhagem OK (`GAPLESS_NATIVE_JOB`, 15 processos); o neto imprimiu `BREAKAWAY_SUCCEEDED` — ou seja, `CreateProcess` com `CREATE_BREAKAWAY_FROM_JOB` **não lançou**.

Causa: no Windows 8+ (jobs aninhados) o `CreateProcess` com esse flag pode **não lançar** e, ainda assim, o SO manter o processo no Job. O proxy antigo do teste (“lançou ⇒ negado; não lançou ⇒ escapou”) é **incorreto** nesse regime: ele não mede a propriedade de segurança real, que é a **contenção** (o processo não sai da contabilidade do Job, de onde valem o gate de árvore-vazia e o fail-safe `KILL_ON_JOB_CLOSE`).

Correção (no teste de qualificação e no resultado do supervisor; V003 intocado):

- `_JOB_CHILD` mantém o neto de breakaway vivo ~3 s e reporta seu PID.
- `Supervision.run` passa a expor `job_pids` (o conjunto de PIDs que o kernel registrou no Job via NEW_PROCESS/IOCP + amostragem).
- **Q11 verifica contenção real**: PASS se o SO negou o flag (`BREAKAWAY_DENIED`) **ou** se, apesar de o `CreateProcess` não lançar, o PID do neto permaneceu em `job_pids` (contido pelo kernel). FAIL só no escape real (CreateProcess OK e PID **fora** do Job). Isso é um critério **mais rigoroso** que o proxy anterior — mede o escape de custódia de fato, não o valor de retorno do `CreateProcess`.

Observação de validação: Q11 é nativo (offline `SKIPPED_NON_NATIVE`), então esta lógica é exercida apenas na campanha do titular; o campo `job_pids` é exercido também no POSIX pelos casos Q01–Q12 da qualificação offline. Unit do supervisor 71/71; mutantes 24/24; fronteira do bootstrap 20/20 + 8/8 (template inalterado); cadeia V003 19/19 imutável.


## Robustez do census de corroboração V008R8 (achado da campanha nativa R7)

Na campanha nativa R7 a cadeia parou em **Q10a**, caso que havia **passado na R6**. A prova primária do kernel funcionou (escritor externo negado; rename negado com `winerror=32`), mas o veredito W04 ficou `BLOCKED` por `CENSUS_TRUNCATED`: o census de handles do sistema (R14R3, apenas corroboração) veio incompleto. O backend pinado (`8FEF1313…`, não alterável) declara a enumeração truncada quando mais de 8 consultas de nome travam numa mesma chamada — condição intermitente, dependente da carga de handles do Windows no momento. O contador é por chamada.

Correção (em `pegasus_win_native_v008._census`; backend e V003 intocados): **nova tentativa limitada** do census (`CENSUS_MAX_ATTEMPTS=3`). Retorna a primeira enumeração completa; se **todas** truncarem, o resultado segue truncado e o W04 continua **bloqueando** — a regra fail-closed não foi afrouxada. As tentativas ficam registradas na evidência (`census.attempts`).

Validação: código nativo (o módulo só carrega no Windows); exercido pela campanha do titular. Offline: unit 71/71; mutantes 24/24; fronteira do bootstrap 20/20 + 8/8; V003 19/19; qualificação 16/16 PASS + 2 SKIPPED_NON_NATIVE. A correção de Q11 da R7 (contenção real) segue pendente de execução nativa (a R7 parou antes de Q11).


## Negativos nativos em processo próprio V008R9 (achado da campanha nativa R8)

A campanha nativa R8 avançou **16 casos** (Q01–Q09 e Q12–Q15, todos PASS) e parou de novo em **Q10a**, com a mesma assinatura da R7: prova primária do kernel íntegra (`WRITE_DENIED`; `RENAME_DENIED winerror=32`) mas veredito W04 `BLOCKED` por `CENSUS_TRUNCATED` — agora **apesar** das 3 tentativas da R8. A nova tentativa limitada não bastou.

Causa-raiz precisa (sem alterar o backend pinado `8FEF1313…`): o backend de census enumera **todos** os processos, inclusive o próprio, e, quando uma consulta de nome trava, **abandona a thread segurando o handle** (não fecha, não faz join). Num **processo de qualificação longevo** — que já rodou Q01–Q15, incluindo os subprocessos supervisionados Q12–Q15 — os handles duplicados retidos por threads abandonadas **acumulam** entre chamadas; a cada novo census há mais o que varrer e mais o que travar, até cruzar o limite de 8 workers abandonados e declarar `enumeration_truncated`. Por isso Q12 (em subprocesso próprio) passava e Q10a (no processo longevo) truncava **na mesma execução**.

Correção (mais fiel à produção, onde cada execução supervisionada é um processo próprio; backend e V003 intocados):

- **Negativos nativos em subprocesso novo**: `_native_negatives_in_fresh_process` lança os casos Q10a–f e Q11 num processo `-I -B` recém-criado (`pegasus_qualify_v008.py --native-negatives`). O processo filho começa sem o acúmulo de handles do backend, então o census parte de um estado limpo. O filho **coleta** os casos sem levantar e grava `NATIVE_NEGATIVES_RESULT.json`; o pai **reencena** (`_replay_case_records`) cada caso no recibo, levantando na primeira falha. Fail-closed reforçado: se o filho não entregar o JSON, ou faltar qualquer caso nativo esperado, ou não concluir, o pai levanta (nunca PASS silencioso).
- **Observabilidade do census**: `w04_verdict` passa a registrar, em **ambos** os veredictos (PASS e BLOCKED), `census_attempts` e `census_abandoned_name_workers` (início/fim). O truncamento deixa de ser opaco — a evidência mostra quantas threads de nome foram abandonadas, o indício direto do acúmulo.

A regra fail-closed do W04 **não** foi afrouxada: um census que trunque mesmo num processo novo continua **bloqueando** o W04. Se isso ainda ocorrer, aceitar corroboração degradada com a prova de kernel completa é **decisão de política do titular/origem**, não do implementador.

Regressão offline: `NativeNegativesReplay` (4 casos sobre `_replay_case_records`: reencena todos os casos com detalhe preservado; levanta e para na primeira falha; é fail-closed contra caso ausente e contra filho incompleto). Unit do supervisor **75/75**; mutantes do supervisor **24/24** (âncoras inalteradas); fronteira do bootstrap 20/20 + 8/8 (template inalterado); cadeia V003 19/19 imutável; qualificação supervisionada 16/16 PASS + 2 SKIPPED_NON_NATIVE.


## Fronteira fail-closed do rc do subprocesso V008R10 (revisão da origem)

A revisão física da origem encontrou um defeito material na fronteira de resultados de `pegasus_qualify_v008._native_negatives_in_fresh_process`: o `p.returncode` do subprocesso dos negativos nativos era **apenas registrado**, não **exigido igual a zero** antes de aceitar os casos reencenados. Um filho que gravasse um `NATIVE_NEGATIVES_RESULT.json` completo (7 casos PASS, `completed=True`) e **depois** terminasse com código não zero (aborto do interpretador/SO, erro de flush no encerramento, exceção tardia) seria **aceito** pelo pai — uma porta de falsa completude.

Correção (fail-closed, V003 e backend intocados): antes de ler/aceitar qualquer caso, o pai passa a **exigir `rc == 0`**; um código não zero levanta `NATIVE_NEGATIVES_CHILD_NONZERO_EXIT` e nada é reencenado. No caminho projetado o filho sempre retorna 0 (até uma exceção interna vira caso negativo + `completed=False`, reencenado e levantado pelo pai), então a correção só rejeita o que já era falha fora desse caminho. É consistente com a campanha nativa R9, cujo filho saiu `rc=0` (log `NATIVE_NEGATIVES_FRESH_PROCESS_EXIT rc=0`): sob a fronteira endurecida, aquele run seria aceito de forma idêntica.

Controle negativo (reproduz o defeito): um filho que grava JSON completo e sai `rc=3` é **ACEITO** pelo código pré-correção (7 casos reencenados) e **REJEITADO** pelo corrigido (`NATIVE_NEGATIVES_CHILD_NONZERO_EXIT`). Evidência em `receipts/V008/offline_final/r10_boundary_fix/NEGATIVE_CONTROL_NONZERO_CHILD_EXIT.json`. Regressão offline `NativeNegativesFreshProcess` (3 casos: rc≠0 rejeitado mesmo com JSON completo; rc=0 + JSON completo aceito; rc=0 sem JSON rejeitado).

Reconciliação do contrato de completude FULL (busca adversarial de falsa completude): os bloqueios econômicos são **terminais e triplos** — (1) `make_run_plan` recusa qualquer plano econômico sem autorização externa comprovada (ausente neste artefato); (2) `DefaultReleaseAdmission.admit` sempre levanta `entry.Blocked` com causa `G00_RUN_RELEASE_DISABLED`; (3) `_run_supervised` revalida e reinvoca `release_admission`, bloqueando de novo (`ECONOMIC_EXECUTION_STILL_BLOCKED_BY_ENTRY_RELEASE_ADMISSION`). Provados por Q13a/b/c e pelos mutantes `run_plan_allows_economic`, `run_supervised_runs_economic`, `default_admission_returns_plan`. A matriz vinculada aos bytes finais está em `receipts/V008/offline_final/r10_boundary_fix/FALSE_COMPLETENESS_SEARCH_V008R10.json`: nenhuma integração obrigatória do marco de engenharia permanece por implementar; os únicos itens fora de PASS são fronteiras de política (QS4=NO, FULL_ECONOMIC=NO, auditoria formal) sob custódia da origem, não engenharia pendente.

Unit do supervisor **78/78** (inclui `NativeNegativesFreshProcess`); mutantes do supervisor **24/24** (âncoras inalteradas); fronteira do bootstrap 20/20 + 8/8; cadeia V003 19/19; qualificação supervisionada 16/16 PASS + 2 SKIPPED_NON_NATIVE. A evidência primária da campanha nativa R9 (23/23, `MET`) é preservada em `receipts/V008/offline_final/native_campaign_r9/`.


## Correção dos achados da auditoria independente V008R11 (Work Astra, AUDIT_VERDICT=FAIL sobre a R10)

A auditoria independente (Work Astra) sobre os bytes R10 reprovou o candidato com quatro achados reais. Todos foram corrigidos de forma fail-closed, com controle negativo e qualificação proporcional, preservando os PASS anteriores (campanha nativa R9 23/23 MET e a correção R10 da fronteira `rc` do subprocesso). V003, backend de census e fronteiras econômicas intocados.

- **F01 (ALTA/BLOQUEANTE) — W04 BLOCKED era promovido a sucesso/exit 0.** `Supervision.run` obtinha o veredito W04 mas `completion_verdict` não o exigia; `_run_supervised` convertia `completed=true` em exit 0. Reproduzido pelo probe do auditor (filho que alterou o conjunto protegido: `w04_full=BLOCKED`, `hash_continuity=CHANGED`, mas `PASS_SUPERVISED_RUN`/exit 0). Correção: `completion_verdict` passa a **exigir** W04 atestado (`PASS_NATIVE_SAME_ATTEMPT` ou `NOT_ATTESTED_NON_NATIVE_PLATFORM`); qualquer outro valor insere o gap `W04_NOT_ATTESTED` e impede COMPLETED (logo exit 3). `native_completeness_evaluation` passa a exigir o W04 nativo **por caso obrigatório** (Q01/Q02/Q03/Q10a/Q12), sem compensação por contagem agregada; o predicado de Q12 passa a exigir W04 atestado. Controle negativo **integrado** Q16 (chega ao recibo): fora do Windows o filho altera o protegido → BLOCKED → não COMPLETED; no Windows a lease nega a escrita → protegido intacto → PASS.
- **F02 (ALTA/BLOQUEANTE) — armamento W04 incompleto não impedia o spawn.** `W04NativeLease.arm` acumulava sharing violations/erros/reparse mas retornava `armed` e o supervisor chamava `cust.start`. Correção: função pura `w04_prespawn_verdict` + `W04Guard.prespawn_verdict/release`; `Supervision.run` avalia o veredito pré-spawn **antes** de criar o filho e, se a lease não foi adquirida em todos os alvos, libera os handles parciais e levanta `W04_ARM_INCOMPLETE_NO_SPAWN_NO_PROTECTED_EFFECTS` (sem spawn, sem efeitos). `W04NativeLease.prespawn_state`/`release` adicionados.
- **F03 (MÉDIA/LACUNA DE PROVA) — identidade GAPLESS/Q11.** `lineage_verdict` aceitava `ctime=0` e ainda classificava `GAPLESS_NATIVE_JOB`; Q11 comparava o PID do neto só com o histórico `job_pids`. Correção: `lineage_verdict` **bloqueia** `unresolved>0` (`JOB_IDENTITY_UNRESOLVED_NO_GAPLESS`); `Supervision.run` expõe `job_idents` (pid, creation_time); Q11 passa a exigir que o neto permaneça no Job com **identidade temporal resolvida** (pid+ctime) e `identity_unresolved_short_lived==0`. Sem presumir escape (não demonstrado).
- **F04 (ALTA/BLOQUEANTE) — timeout/SAFE_STOP não honrado vs NO_KILL.** O Job é criado com `KILL_ON_JOB_CLOSE`; no encerramento controlado (timeout/SAFE_STOP não honrado → `SupervisorBlocked` → exit 3 → CLI encerra), fechar o handle mataria a árvore viva. Reter o handle até `sys.exit` não é reconciliação durável. Correção: função pura `job_close_disposition`; `WindowsJobCustody.close`, com a árvore ainda viva, **limpa `KILL_ON_JOB_CLOSE` antes de fechar** (NO_KILL honrado — a árvore sobrevive e é reconciliada pela próxima execução via RUN.lock/journal), e falha-fechada explícita se não conseguir limpar. O fail-safe de QUEDA do supervisor permanece durante a operação normal. A prova nativa dirigida de kill é do titular/origem; aqui a disposição é provada por função pura + fonte.

Regressões offline: `CompletionW04` (gate de W04 na conclusão), `W04PrespawnGate`, `LineageUnresolvedIdentity`, `JobCloseNoKill`, e o caso integrado `Q16`. Unit do supervisor **86/86**; mutantes do supervisor **28/28** (inclui `completion_ignores_w04`, `prespawn_accepts_sharing_violation`, `lineage_accepts_unresolved_identity`, `job_close_kills_live_tree`); fronteira do bootstrap 20/20 + 8/8; cadeia V003 19/19; qualificação **17/17 PASS** (16 + Q16) **+ 2 SKIPPED_NON_NATIVE**. Fechamento em `receipts/V008/offline_final/r11_audit_fixes/`; evidência R10 preservada em `r10_boundary_fix/` e a campanha R9 em `native_campaign_r9/`.
