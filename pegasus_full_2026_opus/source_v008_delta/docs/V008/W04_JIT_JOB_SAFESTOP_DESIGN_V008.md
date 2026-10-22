# Decisões de projeto: W04, JIT/Job, SAFE_STOP, observabilidade

## W04 — proteção contínua do conjunto de entrada

**Prevenção (kernel).** Antes de criar o filho, o supervisor abre cada arquivo protegido e cada stream nomeado existente com `GENERIC_READ` e compartilhamento somente-leitura (nega escrita e remoção). A abertura falha com `ERROR_SHARING_VIOLATION` se existir qualquer handle com acesso de escrita/remoção ou seção mapeada gravável sobre o arquivo — em qualquer processo, inclusive protegido, e independentemente do tipo que o census reporte. Mantidos os handles, nenhuma escrita, remoção ou renomeação é admitida. Como o compartilhamento é avaliado por arquivo, cobre aliases (hardlinks, nomes 8.3, `\\?\`, subst). Diretórios são abertos sem `FILE_SHARE_DELETE` (impede renomear/remover a árvore).

**Detecção (filesystem).** Marco USN antes do filho; no fim, leitura do diário do marco até o fim, exigindo mesmo `UsnJournalID`, ausência de expurgo (`FirstUsn ≤ marco`) e zero registros sobre os FRN protegidos ou com pai em diretório protegido — cobre novos nomes, streams alternados, hardlinks novos, atributos e segurança. Sem diário ativo, bloqueia (não cria diário).

**Census (corroboração).** Backend R14R3 inalterado. Escritor externo resolvido sob o alvo bloqueia. Handles não resolvidos (incluindo `FILE_TYPE_UNKNOWN`) são reportados com a semântica `NOT_ABSENCE_PROOF;COVERED_BY_KERNEL_SHARE_ACCESS_LEASE` — nunca convertidos em ausência; o veredito não depende de nomeá-los porque a prova primária é de kernel.

**Resíduos declarados.** Gravação bruta em volume (handle de volume com privilégio administrativo) contorna o filesystem; não é coberta por USN nem por compartilhamento. Componentes de kernel com `IO_IGNORE_SHARE_ACCESS_CHECK` contornam a prevenção, mas não a detecção USN.

**Escopo D:.** Nenhuma ACL de D: é alterada. A lease é uma abertura somente-leitura temporária, desfeita ao fim.

## JIT e Job

Ordem provada por sequência de marcos: `W04_ARM → CHILD_CREATED → CHILD_RESUMED → TREE_EMPTY → W04_DISARM`. O filho nasce `CREATE_SUSPENDED` com console próprio oculto, é associado a um Job anônimo (sem `BREAKAWAY_OK`) e só então retomado. Linhagem: porta de conclusão (`NEW_PROCESS`/`EXIT`/`ACTIVE_PROCESS_ZERO`) + varredura da lista do Job; exige `TotalProcesses` = identidades `(PID, creation_time)` distintas e `ActiveProcesses = 0`. `KILL_ON_JOB_CLOSE` é apenas fail-safe de queda do supervisor: sem supervisor não há lease W04, e a retomada é transacional (faults provados).

## SAFE_STOP

Ctrl+C no supervisor → pedido único ao coordenador, entregue somente no console privado dele pelo helper `CODE/r1r11_signal.py` do V003. O coordenador fecha a admissão na fronteira de commit; workers ignoram SIGINT; segundo Ctrl+C espera, sem kill. **Confirmação pelo supervisor:** exit 130, Job drenado, STATUS `SAFE_STOP=YES`/`PROCESS_TREE_CLEAN=YES`, checkpoint autoverificado, `RUN.lock` ausente, W04 contínuo.

## Observabilidade

Heartbeat do supervisor a cada ≤10 s com `committed/total` e ETA por unidades COMMITTED (`UNKNOWN` justificado antes do primeiro commit). Watchdog de produção: heartbeat do STATUS do coordenador parado por mais de 120 s → SAFE_STOP cooperativo. AUTOCPU/backpressure/telemetria são os do runtime V003 (`grant_workers` 1–24 por CPU/RAM/IO/grupos causais; decisão de backpressure de I/O por sessão).
