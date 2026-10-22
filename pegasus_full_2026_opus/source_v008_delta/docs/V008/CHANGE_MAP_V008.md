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
