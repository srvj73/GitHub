# Auditoria interna adversarial — convergência integrada V008R15

**Base auditada:** predecessor congelado V008R14 (ZIP `012D4347…D7CF`; supervisor `E724B221…F55D`; camada Windows `97A9543C…89D9`). **Método:** leitura integral dos módulos `supervisor/*.py`, do contrato terminal do runtime V003 (`r1r11_coordinator.py`, `r1r11_runtime_status.py`, `r1r11_resources.py`, `tests/synthetic_chain.py`) e do bootstrap; para cada fronteira, os cinco desfechos: sucesso, falha antes do efeito, falha após efeito parcial, dado incompleto e exceção inesperada. Provas POSIX não equivalem a Win32; o que depende do Windows real fica no protocolo dirigido (`WINDOWS_DIRECTED_QUALIFICATION_PROTOCOL_R15.md`).

## 1. Diagnóstico de método

R10–R14 endureceram decisões puras, mas o ciclo de vida não tinha um invariante de saída: qualquer exceção levantada entre as decisões (helper de SAFE_STOP, conversões de telemetria, consulta do Job, revalidação W04, escrita de recibo, desarme, linhagem) atravessava o `finally: cust.close()` e encerrava o processo custodiante com a árvore possivelmente viva. A correção não é capturar casos isolados: é tornar a supervisão pós-spawn uma máquina de estados cujas transições não levantam, com uma única saída de custódia (árvore vazia verificada) e uma disposição explícita para os demais desfechos.

## 2. Máquina de estados (R15)

`PRESPAWN → SPAWNED_SUSPENDED → ASSIGNED → RUNNING → STOP_REQUESTED → DRAINING → (LIVE_TREE_BLOCKED) → TREE_EMPTY → W04_DISARMED → CUSTODIAN_CLOSED → RESULT_PERSISTED`

Saídas permitidas da custódia:
1. `TREE_EMPTY` verificado por duas observações consecutivas bem-sucedidas (`observe_tree() == EMPTY`); uma observação que falha é `UNKNOWN` e nunca vazio.
2. Nenhum filho criado (falha em `PRESPAWN`): limpeza idempotente de Job/IOCP/lease, recibo `BLOCKED_PRESPAWN_NO_EFFECT`, exit 2.
3. Disposição explícita do titular `RELEASE_CUSTODY_LEAVE_TREE_RUNNING` (arquivo de disposição com confirmação de rótulo e PID): só é aplicada se `KILL_ON_JOB_CLOSE` puder ser removido antes; caso contrário é recusada e o hold continua. Exit 3, W04 `BLOCKED`.
4. Falha externa irrecuperável (término forçado do próprio supervisor, perda de energia): fora do controle do software; ver §6.

O supervisor nunca termina processo, exceto o rollback do próprio filho comprovadamente ainda suspenso e que nunca executou código (falha de `Assign` ou de `Resume` com zero threads retomadas).

## 3. Matriz de fronteiras

| Fronteira | Sucesso | Falha antes do efeito | Falha após efeito parcial | Dado incompleto | Exceção inesperada | Disposição R15 |
|---|---|---|---|---|---|---|
| Admissão (`_load_admission`, `admit`) | plano | `Blocked` → 2 | n/a | plano inválido → 2 | exceção → 3 técnico | `--admission` só aceita o módulo sintético selado (caminho + SHA do manifesto); argv do plano validado contra entrypoints econômicos e saída dentro do pacote |
| `make_custody` / `WindowsJobCustody.__init__` | Job+IOCP+pump | handles parciais fechados, `PrespawnBlocked` → 2 | n/a | n/a | idem | limpeza idempotente (INT-09) |
| `W04Guard.arm` / pré-spawn | lease completa | `BLOCKED_NO_SPAWN` → 2 | n/a | violação/erro/reparse → 2 | handles parciais liberados → 2 | `release()` em todo caminho pré-spawn (INT-08) |
| `start` (suspenso → assign → resume) | RUNNING | Popen falhou: sem filho → 2 | assign falhou: rollback do suspenso; resume falhou com 0 threads: rollback; ≥1 thread: RUNNING sob custódia | n/a | estado do filho registrado; se vivo → hold | decisão pura `start_failure_disposition` (INT-10, INT-17) |
| `poll` / `sample` / IOCP / `accounting` / `observe_tree` | observação | n/a | n/a | `UNKNOWN` | contida, registrada | falha nunca é vazio; eventos do Job protegidos por lock (INT-20) |
| `_status` / telemetria | STATUS válido | ausente | stale (watchdog) | corrupto / esquema / inconsistente | contida | leitura tipada com estado; ETA e janelas nunca derrubam a custódia (INT-01, INT-02) |
| `request_stop` / helper Ctrl+C | entregue | spawn do helper falhou | n/a | nonzero / timeout | contida | resultado estruturado, contagem limitada, erro persistido (A01, INT-11) |
| `revalidate` (loop) | identidade estável | n/a | n/a | falha por arquivo → `revalidation_failures` | contida → W04 `BLOCKED` | INT-04 |
| hold / reservada | árvore drena | n/a | prazo esgotado: reporta 1x e mantém | observação `UNKNOWN` persistente: mantém | escrita de recibo/log falha: contada | `CUSTODY_STATE` persistente a cada heartbeat; disposição explícita do titular; nenhum `except: pass` mudo (INT-12, INT-19) |
| `disarm` (W04) | veredito | n/a | n/a | USN incompleto → `BLOCKED` | consulta/census/USN falhou → `BLOCKED` com causa | `disarm` não levanta (INT-05, INT-22) |
| USN (`_read_usn`) | cobertura até `end_usn` | IOCTL falhou | EOF antes do fim | cursor não progressivo, registro malformado/truncado/versão, FRN 128 bits | contida | `usn_scan_coverage` pura com prova de cobertura; `w04_verdict` exige a prova (A02, INT-21) |
| `close` | só com árvore vazia | n/a | n/a | n/a | contida | nunca chamado com árvore viva em caminho controlável |
| linhagem / JIT | `GAPLESS` | n/a | n/a | identidade não resolvida → bloqueio | contida → dado | veredito como dado; conclusão exige (INT-06, INT-18) |
| conclusão / SAFE_STOP | evidência terminal completa | n/a | n/a | STATUS ausente/stale/de outro produtor, checkpoint inválido → não concluído | contida | `terminal_evidence_verdict` vinculada à tentativa (A03, INT-14) |
| inventário | estável | n/a | n/a | mudança entre passadas | race → lacuna | INT-15 |
| recibo / CLI / exit | 0 / 130 só com recibo persistido | 2 sem efeito | 3 com causa primária | n/a | 3 com recibo técnico | A04, INT-07 |

## 4. Achados

**Da origem, confirmados por leitura dos bytes R14:** A01 (exceção do helper de SAFE_STOP encerra a custódia com árvore viva — `pegasus_win_native_v008.py:315–326`, `pegasus_supervisor_v008.py:750–762, 807–813, 852–862`); A02 (`_read_usn` declara cobertura completa com cursor não progressivo `:474–476` e com `ERROR_HANDLE_EOF` antes do fim `:443–445`; `w04_verdict` valida apenas o booleano); A03 (`completion_verdict` não recebe STATUS/checkpoint; `_status` engole erros); A04 (`_run_supervised` só intercepta `SupervisorBlocked`).

**Internos (novos):**

| ID | Achado | Evidência (R14) |
|---|---|---|
| INT-01 | `eta_status` levanta `SupervisorBlocked` com `COMMITTED>TOTAL` dentro do loop vivo | `pegasus_supervisor_v008.py:470–474, 771–778` |
| INT-02 | `int()` sobre campos de STATUS corrompidos levanta `ValueError` no loop vivo | `:736, 744, 751` |
| INT-03 | `tree_empty()`/`accounting()` levantam em falha de consulta do Job no loop de drenagem | `:798`; nativo `:298–313` |
| INT-04 | exceção de `guard.revalidate()` não contida no loop | `:772, 814` |
| INT-05 | `disarm` pode levantar (consulta USN, leitura USN, census) após árvore vazia → sem recibo estruturado | nativo `:446, 591–597`; `:840` |
| INT-06 | linhagem/JIT levantam após `close` → recibo perde W04/linhagem/evidência | `:878–881` |
| INT-07 | bloqueio pré-spawn classificado como falha após efeito (exit 3) | `:1014–1022` |
| INT-08 | exceção no meio de `W04Guard.arm` não libera a lease parcial | `:703–715` |
| INT-09 | falha parcial em `WindowsJobCustody.__init__` vaza Job/IOCP | nativo `:196–210` |
| INT-10 | falha de `Resume` deixa filho suspenso no Job sem decisão de rollback | nativo `:272–273` |
| INT-11 | `PosixCustody.request_stop` levanta `ProcessLookupError` em corrida | `:579–581` |
| INT-12 | escrita do recibo da reservada falha em silêncio (`except Exception: pass`) | `:825–835, 872–875` |
| INT-13 | `--admission` executa qualquer `.py`; isolamento só documentado | `:969–988` |
| INT-14 | `safestop_verdict` aceita STATUS não vinculado à tentativa (stale) | `:417–440` |
| INT-15 | exceção de `inventory()` (corrida) escapa do cálculo do resultado | `:490–507, 883–884` |
| INT-16 | `checkpoint_valid` insere `CODE/` em `sys.path` a cada chamada | `:510–520` |
| INT-17 | `start` registra `CHILD_CREATED` antes do Popen e vaza o handle de stdout se o Popen falhar | `:551–559`; nativo `:253–266` |
| INT-18 | conclusão não consome linhagem/JIT como dados | `:443–467` |
| INT-19 | hold da reservada sem heartbeat persistente (hold mudo) | `:815–838` |
| INT-20 | dicionário `events` mutado pela thread IOCP enquanto o thread principal itera | nativo `:215–227, 284–290, 328–329` |
| INT-21 | leitor USN ignora `RecordLength=0`, bytes residuais, versões desconhecidas e bits altos de FRN 128 | nativo `:450–473` |
| INT-22 | `_query_usn` no desarme levanta sem disposição | nativo `:428–433, 593` |

Todos os achados acima são corrigidos na R15; cada um tem teste negativo e, onde há guarda decisiva, mutante (ver `INVARIANTS_AND_EXCEPTIONS_MATRIX_R15.md`).

## 5. Contrato terminal V003 (A03)

A cadeia V003 grava `TELEMETRY/R1R11_STATUS.json` (esquema `MINOTAURO_R1R11_RUNTIME_STATUS_V001`, campos obrigatórios em `r1r11_runtime_status.REQUIRED`), com `run_instance = "<pid>_<ns>"` do processo dono do `RunLock`. A `synthetic_chain` só retorna 0 após `status('SYNTHETIC_COMMITTED', COMMITTED=len(done), TOTAL=...)` e `rt.close()` (`PROCESS_TREE_CLEAN=YES`, `ACTIVE=0`). Esse contrato vincula a cadeia, mas não o supervisor: um argv admitido qualquer pode sair 0 sem STATUS, e uma raiz de saída reutilizada pode conter STATUS de execução anterior. Por isso a R15 adiciona `terminal_evidence_verdict` (simétrica ao que `safestop_verdict` já exigia): STATUS legível e com esquema, `out_root` igual, `run_instance` diferente do anterior à tentativa e com PID produtor pertencente à árvore supervisionada, `PROCESS_TREE_CLEAN=YES`, `ACTIVE=0`, `TOTAL>0`, `COMMITTED==TOTAL`, sem pedido de parada, e `CHECKPOINT.json` autoverificável com contagem igual a `COMMITTED`. Não é gate redundante: é a confirmação independente do supervisor.

## 6. Limites físicos (não prometidos)

- **Término forçado do supervisor** (taskkill /F, perda de energia, falha do SO): o processo custodiante deixa de existir e seus handles são fechados pelo kernel. Com o fail-safe `KILL_ON_JOB_CLOSE` (mantido desde R3 e qualificado nativamente em R9), o kernel encerra a árvore; o estado V003 é consistente a falhas (Q05–Q07 provam a recuperação), nunca há PASS e a próxima execução reconcilia via `RUN.lock` + journal. Não existe forma física de preservar simultaneamente NO_KILL e W04 sem um custodiante vivo.
- **Efetividade Win32** das correções na camada nativa: dependente do Windows real; protocolo dirigido com processos sintéticos.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
