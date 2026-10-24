# Auditoria interna adversarial e convergência sistêmica — V008R16

Resposta ao parecer físico da origem sobre a R15 (três negativos N1/N2/N3 reproduzidos em simulação).
A revisão tratou a implementação **como um sistema completo** e fechou a **família causal única** que os
três negativos expõem, não cada sintoma em separado. Nenhum núcleo econômico V003, census ou G4 foi tocado.

## 1. Família causal

Falta de um **contrato único e exaustivo** entre cinco eixos do desfecho de uma tentativa supervisionada:

1. **fase real do filho** (criado? atribuído? retomou thread? vivo? morto rápido?);
2. **efeitos já possíveis** (uma thread retomada EXECUTOU código — efeitos são possíveis mesmo que o filho
   esteja morto na consulta posterior);
3. **custódia/handles realmente mantidos ou liberados** (o `close()` pode ter RECUSADO fechar);
4. **resultado terminal** (concluído, SAFE_STOP, FAIL, ou hold);
5. **recibo/exit final** (o recibo canônico foi persistido? o exit reflete isso?).

O R16 introduz funções puras de decisão que amarram esses eixos e as integra nas três fronteiras reais.

## 2. Os três negativos, fechados por fato (não por sintoma)

| # | Fronteira | Defeito R15 | Correção R16 |
|---|---|---|---|
| **N1** | `Supervision._run_spawned` → `cust.start` levanta → `child_state()` | `child_alive=False` ⇒ `PrespawnBlocked`/sem efeito (exit 2), mesmo com `resumed_threads=1` | `start_failure_effect_class(created,assigned,resumed,alive,rollback)`: retomada ≥1 ⇒ `EFFECTS_POSSIBLE_CHILD_EXECUTED`; só é "sem efeito" quando PROVADO (sem filho; ou suspenso revertido que nunca retomou). `_run_spawned` só sai BLOCKED sem efeito por `start_failure_is_no_effect`; efeitos possíveis/incerteza ⇒ `effects_started=True` e FAIL exit 3 / hold. |
| **N2** | `Supervision._finalize` → `cust.close()` | `custody_closed=True` + fase `CUSTODIAN_CLOSED` mesmo com fechamento recusado (`ActiveProcesses>0`, retorno `None`) | `close()` devolve **prova estruturada** (`closed`, `active_processes`, `handles_closed`). `_finalize` reconfere a contabilidade final ANTES de disarm/close; só declara `CUSTODIAN_CLOSED` via `custody_close_confirmed` (closed=True ∧ ativo=0 ∧ árvore verificada vazia). Contradição/recusa/UNKNOWN ⇒ hold observável com W04+Job retidos, **NO_KILL**. |
| **N3** | `_run_supervised` recibo/exit | `result="PASS_SUPERVISED_RUN"` com `exit_code=3` quando `persist_run_receipt` falha | `supervised_final_outcome(completed,stopped,receipt_persisted)` centraliza o desfecho: recibo não persistido ⇒ **FAIL** (nunca 0/130). `result`/`exit_code`/`exit_class`/`supervision.phase`/banner derivam do mesmo desfecho. Gate `custody_resolved` (custódia provada fechada ou liberada pelo titular) e emissão do resumo **à prova de falha** (uma falha ao imprimir não altera o código nem derruba). |

## 3. Matriz invariante × classe de falha (vizinhos revisados)

| Classe de falha | Invariante exigido | Onde é provado |
|---|---|---|
| pré-spawn (lease incompleta) | sem spawn, sem efeito, exit 2 | `w04_prespawn_verdict` + gate F02 (preservado) |
| pós-resume + saída rápida | efeitos possíveis ⇒ nunca "sem efeito"; FAIL exit 3 / hold | **N1** `start_failure_effect_class`, `R16Integration.test_n1_*` |
| filho vivo / estado incerto | custódia assume e segura | **N1** classe `EFFECTS_UNCERTAIN_FAIL_CLOSED`/`CHILD_ALIVE_*` |
| rollback do suspenso que nunca executou | único término admitido (não é kill) | `start_failure_disposition` (preservado) |
| close recusado / `ActiveProcesses>0` | hold observável; nunca `CUSTODIAN_CLOSED` | **N2** `custody_close_confirmed`, `_finalize` gate |
| observação final ≠ TREE_EMPTY | não disarma W04, não fecha; hold | **N2** gate de contabilidade final em `_finalize` |
| Job/consulta UNKNOWN | UNKNOWN nunca libera | `observe_tree` tri-estado (preservado) |
| SAFE_STOP helper falho | erro persistido; custódia viva | `request_stop` estruturado (preservado) |
| USN/W04 incompleto | W04 BLOCKED | `usn_scan_coverage`/`w04_verdict` (A02, preservado) |
| evidência terminal ausente | conclusão bloqueada | `terminal_evidence_verdict` (A03, preservado) |
| recibo canônico falha | FAIL coerente (nunca sucesso) | **N3** `supervised_final_outcome` |
| falha ao emitir o resumo | desfecho e exit preservados; sem crash | **N3** `try/except` no banner |
| loop de hold / `close`/`finally` falho | nada é liberado sem árvore verificada vazia | `_emergency_hold_and_result` (prova de fechamento, N2) |

## 4. Prova (controles negativos) e limites honestos

- Regressões dos módulos reais: `R16EffectClassPure`, `R16CloseProofPure`, `R16OutcomeCoherencePure`,
  `R16Integration` — cada uma **falha na R15 congelada** (símbolo ausente ou conduta contraditória) e **PASS
  nos bytes R16**. Mutantes: `n1_*`, `n2_*`, `n3_*` (7), todos MORTOS pelo subconjunto.
- Probe de convergência N1/N2/N3 (`converge_probe_r16.py`): `all_safe` nos bytes R16; **UNSAFE reproduzido**
  nos bytes R15 congelados.
- **Fixtures sintéticas NÃO contam como prova Win32.** A efetividade nativa das rotas modificadas (Job/USN/W04)
  fica para a qualificação dirigida (processos sintéticos, hash-bound). **D4 (término forçado do supervisor) não
  está autorizado.** A campanha R9 (23/23 MET, somente bytes R9) é preservada, não repetida por rotina.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
