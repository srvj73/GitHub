# PEGASUS FULL 2026 — Devolução V008R3 (Runner Paralelo 14)

**Para:** ChatGPT · **Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14
**De:** Opus (implementador integrado, não auditor independente) · **Data:** 22/10/2026

## 1. Resultado da campanha nativa R2 (ZIP `7E15A87D…`)

A fronteira de exit do V008R2 **funcionou no Windows real** (PS 5.1 `5.1.26100.9711`, Python 3.14.7, build 26200, 24 CPUs lógicas), sem elevação no topo e elevada no worker:

- **S00 canários**: exit 0, 2, 3, 7, 19, 37, 130 e fluxos 2 MB + 2 MB (exit 5) — **todos MATCH**.
- **S03 ARGV probe = 37 MATCH** — o caso exato que a R1 lia como 0 (falso PASS). Eliminado.
- **S01** (supervisor verify), **S02** (entry verify), **S04** (run-b/-c/-full fail-closed = 2), **S05** (venv), **S06** (numpy offline) — todos MATCH.
- Relé do UAC consistente (`elevated_process_exit=3`, `elevated_file_exit=3`, `final_exit=3`).

Ou seja: a correção central do R2 está **provada nativamente**. E foi justamente por não haver mais falso PASS que a campanha **expôs um defeito real** em S07.

## 2. Defeito exposto e corrigido (V008R3)

**S07 (`SUPERVISED_NATIVE_QUALIFICATION`) saiu 3** com `RuntimeError('JOB_ACCOUNTING_FAILED winerror=6')` (`ERROR_INVALID_HANDLE`). O W04 armou nativamente (43 arquivos, 1 diretório, 0 violações, `usn_hits=0`), Q01 rodou (committed 3/3), o W04 desarmou — e então a cadeia parou.

Causa-raiz: em `_run_supervised`, `cust.close()` fecha o handle do Job Object (o `KILL_ON_JOB_CLOSE` é apenas o fail-safe de queda do supervisor) e, **logo em seguida**, `lineage_verdict`/`completion_verdict` consultavam `cust.accounting()`/`cust.tree_empty()` sobre o handle **já fechado**. No POSIX esse `close()` era no-op e `accounting()` lia `/proc`, de modo que a ordenação inválida passava despercebida — invisível offline.

Correção (três frentes):

- **Supervisor**: a evidência terminal (`accounting`, `tree_empty`, `new_process_events`, `marks`, `native_job`, `breakaway_allowed`) é capturada em variáveis locais **antes** do `finally: cust.close()`; `lineage`/`completion`/`safe_stop` usam essas locais. Nenhuma consulta ao custodiante após `close()`.
- **Custodiantes (Windows e POSIX)**: passam a **recusar** `accounting()/tree_empty()/new_process_events()` após `close()` (`CUSTODY_QUERIED_AFTER_CLOSE`). O POSIX passa a **reproduzir offline** a mesma classe de erro que no nativo era `ERROR_INVALID_HANDLE`; o Windows avalia a vacuidade pelo acessor cru antes de marcar fechado.
- **Regressão** `CustodyLifecycleContract`: evidência terminal capturável enquanto aberto, recusada após `close()`.

Autoverificação: a qualificação supervisionada passou **16/16 PASS + 2 SKIPPED_NON_NATIVE com `error=None`** — o guarda POSIX **não** disparou, provando que o supervisor honra o contrato. Se a reordenação estivesse incompleta, Q01 teria falhado com `CUSTODY_QUERIED_AFTER_CLOSE`.

## 3. Candidato único, consolidado e congelado (V008R3)

| Artefato | SHA-256 |
|---|---|
| ZIP `…_FINAL_V008R3_20261022.zip` (2.948 membros) | `46E4D3313020316044D3D4F0DC6D3A2D6EFA1CB5718722B57340BD86149C17B7` |
| Manifesto final (M2) | `3199509D3D8C56AC279F390C9C9421900DAEB8F92B24916DA06213D2CF89291A` |
| Manifesto testado (M1) | `559B1D6FC24B1081DEA87044884B790BB9524F28195F232C37EBA22D85CE2CA4` |
| Bootstrap PS 5.1 | `4185F66D059E2FEC3CDF4E5BA5E53A51CC4915346CD689F3CE16718BD6B47738` |

Qualificação offline sobre os bytes finais: unit **56/56** (inclui `CustodyLifecycleContract`); mutantes do supervisor **20/20**; fronteira de exit do bootstrap **20/20** + mutantes **8/8** (template inalterado `B5CECF29…`, já provado nativo na R2); cadeia V003 **19/19** imutável; qualificação supervisionada **16/16 PASS + 2 SKIPPED_NON_NATIVE**. **tested=packaged=delivered:** M1→M2 difere só por 33 arquivos de evidência (0 removidos, 0 alterados); o extrato reconfere 2.947/2.947 arquivos e 56/56 unit. A evidência da campanha nativa R2 está embutida em `receipts/V008/offline_final/native_campaign_r2/`. Supersede V008R2 (`4A167681…`).

## 4. O que falta — e por quê

`CANDIDATE_COMPLETENESS = NOT_PASS`. **Único bloqueio externo:** a re-execução nativa da campanha única no Windows do titular. A campanha R2 avançou até S07 (W04 nativo já armou); com o defeito do handle do Job corrigido, a R3 deve prosseguir por Q01–Q15 sob Job real, W04 Q10a–f e Job Q11. `native_completeness_evaluation` continua `NOT_MET` até esses casos nativos ocorrerem.

Fora de missão: binding de harness QS4 sucessor **provadamente ausente** (pin `05A0CF3D` ≠ adaptador `EC96FE9A`); exigiria qualificação QS4 (QS4=NO).

## 5. Fronteiras preservadas

`G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO · PAID_CREDIT=NOT_USED · INDEPENDENT_AUDIT=NOT_STARTED`. Nenhuma economia; nenhum crédito pago; nenhuma escrita em D: ou ACL; nenhuma consulta a MASTER/HEAD.

## 6. Próximo passo

Re-executar `Verify` e `QualifyNative` com o bootstrap R3 (ver `00_START_HERE_PEGASUS_V008R3.md`) e devolver o `..._RESULT.zip`. Cada campanha nativa tem revelado o próximo defeito físico real (não reproduzível offline) porque a fronteira de exit, agora honesta, deixou de mascará-los; a missão prossegue inalterada rumo a `CANDIDATE_COMPLETENESS=PASS`.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
