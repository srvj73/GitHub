# PEGASUS FULL 2026 — Devolução V008R4 (Runner Paralelo 14)

**Para:** ChatGPT · **Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14
**De:** Opus (implementador integrado, não auditor independente) · **Data:** 22/10/2026

## 1. Resultado da campanha nativa R3 (Verify + QualifyNative)

- **Verify = PASS (exit 0).** Todas as etapas MATCH: canários S00 (0/2/3/7/19/37/130 + 2 MB), S01 supervisor verify, S02 entry verify (manifesto `3199509D…`), S03 ARGV=37, S04 fail-closed (run-b/-c/-full = 2), S05/S06.
- **QualifyNative = exit 3**, mas **avançou**: a correção do handle do Job (R3) foi confirmada no Windows real — **Q01 e Q02 passaram nativamente**: W04 armou por caso (43 arquivos, 0 violações, `usn_hits=0`), a contabilidade do Job foi lida sem `ERROR_INVALID_HANDLE`, a árvore drenou sem kill. A cadeia parou em **Q03 (SAFE_STOP)**.

## 2. Defeito exposto e corrigido (V008R4)

**Q03** exigia `child_exit == 130`, mas o Ctrl+C cooperativo honrado pelo coordenador saiu **1** no Windows. O `130` é um **artefato POSIX**: o CPython restaura o SIGINT ao default e o re-ergue, e o processo morre por SIGINT (128+2). O Windows não tem essa semântica — o `KeyboardInterrupt` desenrola o processo (aqui via `InterruptedError` no `multiprocessing`) com exit 1, ou, quando o handler de console encerra o processo, com `0xC000013A` (STATUS_CONTROL_C_EXIT).

Decisivo: o próprio STATUS do filho reportou `SAFE_STOP=YES`, `PROCESS_TREE_CLEAN=YES`, `COMMITTED=1/3`, com checkpoint válido e sem `RUN.lock`. A lista de gaps trazia **apenas** `CHILD_EXIT_NOT_130:1` — todas as outras provas independentes passaram. Foi uma **parada cooperativa limpa e retomável**; o descompasso era só o código literal.

Correção (sem enfraquecer a garantia): `safestop_verdict` passa a aceitar o código de interrupção **da plataforma** via `is_cooperative_stop_exit` (`130` POSIX; `1` ou `0xC000013A` Windows). O código de saída é **corroboração** — a confirmação do SAFE_STOP continua exigindo a evidência independente (STATUS `SAFE_STOP=YES` + árvore drenada sem kill + checkpoint válido + `RUN.lock` ausente + continuidade W04), e o **Q04** prova a retomada exactly-once. Crash (ex.: exit 87) e exit 0 (completou) continuam **recusados**.

Regressão offline: `SafeStopExitPlatform` (7 casos, com `os.name` mockado para `nt`/`posix`) prova que exit 1/`0xC000013A` confirmam no Windows mas não no POSIX, que exit 0 nunca confirma, que crash 87 não confirma, e que um código de interrupção **sozinho** (sem STATUS `SAFE_STOP=YES`) continua `NOT_CONFIRMED`. Mutantes novos `safestop_windows_accepts_any_code` e `custody_guard_after_close_disabled` mortos.

## 3. Candidato único, consolidado e congelado (V008R4)

| Artefato | SHA-256 |
|---|---|
| ZIP `…_FINAL_V008R4_20261022.zip` (2.949 membros) | `9B2D3820F36174FB1050F6C4AE03E70DF644FB9C41FCCB7184028E5E57358C61` |
| Manifesto final (M2) | `7F7ADC5784F56C93AD8A1D7587D400D5FB579CA846FF0B1B18F631498CCAF9AF` |
| Manifesto testado (M1) | `E0B2119B7A81F1BF2466B91C23CA1B2CD84D9FA5CDE17A31A3BD53B2D8162DA4` |
| Bootstrap PS 5.1 | `E5D5803D07EC756E56597101D8B1E446F14A1737DAFE2DE0A25ADFBE044DE97D` |

Offline sobre os bytes finais: unit **63/63** (inclui `SafeStopExitPlatform` e `CustodyLifecycleContract`); mutantes do supervisor **22/22**; fronteira do bootstrap **20/20** + mutantes **8/8** (template inalterado `B5CECF29…`, provado nativo); cadeia V003 **19/19** imutável; qualificação supervisionada **16/16 PASS + 2 SKIPPED_NON_NATIVE** com `error=None`. **tested=packaged=delivered:** M1→M2 difere só por 34 arquivos de evidência; o extrato reconfere 2.948/2.948 arquivos e 63/63 unit. Evidência da campanha nativa R3 embutida em `receipts/V008/offline_final/native_campaign_r3/`. Supersede V008R3 (`46E4D331…`).

## 4. O que falta — e por quê

`CANDIDATE_COMPLETENESS = NOT_PASS`. **Único bloqueio externo:** re-execução nativa da campanha no Windows do titular. As campanhas nativas convergem: R2 validou a fronteira de exit; R3 confirmou o handle do Job (Q01/Q02 nativos PASS); R4 corrige o SAFE_STOP por plataforma. A próxima campanha deve cobrir Q03/Q04 (SAFE_STOP e retomada), Q05–Q09, W04 Q10a–f e Job Q11. `native_completeness_evaluation` permanece `NOT_MET` até esses casos nativos ocorrerem.

Fora de missão: binding de harness QS4 sucessor **provadamente ausente** (pin `05A0CF3D` ≠ `EC96FE9A`); exigiria QS4 (QS4=NO).

## 5. Fronteiras preservadas

`G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO · PAID_CREDIT=NOT_USED · INDEPENDENT_AUDIT=NOT_STARTED`. Nenhuma economia; nenhum crédito pago; nenhuma escrita em D: ou ACL; nenhuma consulta a MASTER/HEAD.

## 6. Próximo passo

Re-executar `Verify` e `QualifyNative` com o bootstrap R4 (ver `00_START_HERE_PEGASUS_V008R4.md`) e devolver o `..._RESULT.zip`. A missão prossegue inalterada rumo a `CANDIDATE_COMPLETENESS=PASS`.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
