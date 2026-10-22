# PEGASUS FULL 2026 — Devolução V008R2 (Runner Paralelo 14)

**Para:** ChatGPT · **Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14
**De:** Opus (implementador integrado, não auditor independente) · **Data:** 22/10/2026

## 1. Causa-raiz do `EXIT=3` da campanha nativa R1

O resultado `QUALIFYNATIVE_20261022_095448_726_23044_RESULT.zip` (SHA `105AFF88…`) terminou `EXIT=3` com `ARGV_EXIT_PROPAGATION_PROBE_FAILED`, embora o S03 tenha gravado `ARGV_PROBE.json` com `pass=true` (a fonte sai 37) e o bootstrap registrasse `NATIVE_EXIT code=0`.

**A causa não foi o probe S03.** Foi a fronteira de captura de exit do bootstrap sob **PowerShell 5.1**: `Start-Process -PassThru` não retém o handle do processo, de modo que um filho de saída rápida devolve `ExitCode = $null`; `[int]$null` é **0**. O probe comparou o exit esperado (37) com o `0` fabricado, divergiu e falhou — corretamente, mas por um valor falso. O mesmo vetor de **falso PASS** afetava toda etapa que espera 0 e o relé do UAC.

**Consequência para a evidência daquele run:** o conteúdo de stdout de S01/S02 é válido, mas **os exit codes daquele run não são evidência válida** e foram descartados.

## 2. Correção integral (não um remendo pontual)

**Bootstrap** (`BOOTSTRAP_PEGASUS_FULL_2026_V008R2_PS51.ps1`, SHA `DF1DF8C3…`):
- Captura nativa por `System.Diagnostics.Process.Start()` com `$null = $Child.Handle` **antes** de `WaitForExit` (retém o handle que o PS 5.1 descartaria).
- `Get-PegasusExitCode` **fail-closed**: lança `NATIVE_PROCESS_OBJECT_NULL`, `NATIVE_EXIT_READ_BEFORE_EXIT`, `NATIVE_EXIT_NULL`. Exit ausente/não encerrado **nunca** vira 0.
- Dreno assíncrono de stdout/stderr (`ReadToEndAsync`): sem deadlock em fluxos grandes (provado com 2 MB + 2 MB), bytes íntegros, contados por etapa.
- Higiene de ambiente (`PYTHONPATH`/`PYTHONHOME` removidos; `PYTHONNOUSERSITE`/`PYTHONDONTWRITEBYTECODE`/`PYTHONIOENCODING=utf-8` fixos).
- Watchdog por prazo que **não mata** o filho: grava `TIMEOUT_RECONCILE_<label>.json` (`kill_performed=false`) e lança.
- Relé do UAC (`Resolve-PegasusRelayExit`): confronta o exit do **processo elevado** com o exit **gravado** pelo elevado em `CAMPAIGN_RESULT.json`; divergência ou nulo ⇒ 3.
- Recibo por etapa `{expected, observed, classification MATCH/MISMATCH/…, pid, creation_time_utc, seconds, stdout_bytes, stderr_bytes}`.

**Supervisor** (`pegasus_supervisor_v008.py`):
- `classify_exit`/`EXIT_CLASSES`: **0** PASS; **2** BLOCKED (fail-closed, sem efeito, inclui UAC recusado); **3** FAIL técnico após início de efeito; **130** SAFE_STOP confirmado e retomável; ausente/não-inteiro ⇒ `EXIT_UNKNOWN_FAIL_CLOSED` (jamais PASS).
- `_run_supervised` grava `exit_code`/`exit_class` no recibo; `main()` converte exceção técnica em exit 3 (`PEGASUS_SUPERVISOR=FAIL_TECHNICAL`), nunca 0/1.

## 3. Qualificação interna dos cinco regimes (sem falso PASS)

- **Sucesso**: Q01/Q02/Q12 (COMPLETED, bytes iguais à referência, exit 0).
- **Bloqueio**: Q13a (admissão default bloqueia os 3 modos, causa G00, efeito NONE, exit 2).
- **Falha técnica**: Q15a (exceção na admissão ⇒ 3), Q15b (filho falho ⇒ 3, `exit_class=FAIL_TECHNICAL_AFTER_EFFECT_START`).
- **SAFE_STOP**: Q03/Q12b (130 confirmado pelo supervisor) + retomada exactly-once (Q04/Q12c).
- **Erro de subprocesso**: Q14 (matriz 0,1,2,3,7,19,37,130 observada exatamente sob a custódia).

Controles negativos específicos da fronteira, sobre os **bytes reais** do template (extração por AST):
- `test_bootstrap_exit_boundary_v008.ps1`: **20/20 PASS** (pwsh 7.4.6) — inclui null-exit fail-closed, MISMATCH nunca vira PASS, exceção do filho (exit 1 + stderr), 2 MB + 2 MB sem deadlock, watchdog sem matar, argv preservado (exit 37), higiene de ambiente, regras do relé UAC.
- `mutation_bootstrap_exit_boundary_v008.py`: **8/8 mutantes mortos** (`null_exit_coerced_to_zero`, `exit_read_before_exit_allowed`, `relay_trusts_process_on_mismatch`, `relay_null_becomes_zero`, `expected_ignored`, `pythonpath_leaks`, `watchdog_kills_child`, `stderr_not_drained`).

Testes unitários do supervisor **55/55**; mutantes do supervisor **20/20**. Cadeia V003 **19/19** imutável e reaproveitada (nenhum PASS reexecutado sem impacto material).

## 4. Candidato único, consolidado e congelado

| Artefato | SHA-256 |
|---|---|
| ZIP `…_FINAL_V008R2_20261022.zip` (2.944 membros) | `4A1676816C81DB5CA343261712238DCCBEA1F9C6ECBDE1AA8013307D8514EFE2` |
| Manifesto final (M2) | `9FA39FC91CD3B46A263E62628BF005CBDB4F1871BDA3B77B991616DA9A5C7C02` |
| Manifesto testado (M1) | `165BE55F17160ECB260F0DA5AC74F6092C78E00D99B45F5350ED67BA7B780A25` |
| Bootstrap PS 5.1 | `DF1DF8C3145378E58E4A1779E97B1658A00CF3C5DD3A069C1240B2B26A1C901E` |

**tested=packaged=delivered:** M1→M2 difere só por 29 arquivos de evidência (0 removidos, 0 alterados); código e docs byte-idênticos; o extrato reconfere 2.943/2.943 arquivos e 55/55 unit sobre os bytes entregues. Sucede o V008R1 (ZIP `912A7A1D…`).

## 5. O que falta — e por quê

`CANDIDATE_COMPLETENESS = NOT_PASS`. **Único bloqueio externo:** a execução nativa da campanha única no Windows do titular (efeito físico de W04/Job/USN/UAC indisponível ao implementador). A avaliação objetiva `native_completeness_evaluation` já está embutida no recibo de qualificação e reporta `NOT_MET` fora do Windows; só vira `MET` quando os casos nativos ocorrerem (W04 Q10a–f, Job Q11, ≥4 `PASS_NATIVE_SAME_ATTEMPT`, ≥3 `GAPLESS_NATIVE_JOB`).

Fora de missão: o binding de um harness QS4 sucessor ao adaptador G4 do V003 está **provadamente ausente** (pin `05A0CF3D` ≠ adaptador `EC96FE9A`) e exigiria qualificação QS4 própria — vedada (QS4=NO).

## 6. Fronteiras preservadas

`G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO · PAID_CREDIT=NOT_USED · INDEPENDENT_AUDIT=NOT_STARTED`. Nenhuma economia executada; nenhum crédito pago; nenhuma escrita em D: ou mudança de ACL; nenhuma consulta/validação de MASTER/HEAD ou captura de política.

## 7. Próximo passo (uma campanha, dois modos)

Rodar `Verify` e depois `QualifyNative` conforme o `00_START_HERE_PEGASUS_V008R2.md`, e devolver o `..._RESULT.zip` a esta conversa. Com o resultado nativo, a missão prossegue inalterada rumo a `CANDIDATE_COMPLETENESS=PASS`.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
