# PEGASUS FULL 2026 — ENTREGA DE ENGENHARIA V008R3 (Opus, 22/10/2026)

**Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14 · **Papel:** implementador integrado (não auditor independente).

## O que mudou da R2 para a R3

A campanha nativa R2 **validou a fronteira de exit no Windows real** (PS 5.1 build 26100, Python 3.14.7): os canários S00 (exit 0/2/3/7/19/37/130 e fluxos 2 MB+2 MB → 5) todos MATCH; **S03 ARGV probe = 37 MATCH** (a R1 lia 0, falso PASS — eliminado); S01/S02/S04/S05/S06 MATCH. Exatamente por não haver mais falso PASS, a campanha **expôs um defeito real** em S07: `JOB_ACCOUNTING_FAILED winerror=6` (`ERROR_INVALID_HANDLE`).

Causa-raiz: o supervisor consultava a contabilidade do Job Object (`accounting()`/`tree_empty()`) **depois** de `cust.close()` ter fechado o handle. No POSIX esse `close()` era no-op e a consulta lia `/proc`, então a ordenação inválida passava silenciosamente — invisível offline. Correção R3:

- **Supervisor**: a evidência terminal é capturada em variáveis locais **antes** de `cust.close()`; `lineage`/`completion`/`safe_stop` usam essas locais. Nenhuma consulta ao custodiante após `close()`.
- **Custodiantes (Windows e POSIX)**: passam a **recusar** `accounting()/tree_empty()/new_process_events()` após `close()` (`CUSTODY_QUERIED_AFTER_CLOSE`). Isso faz o POSIX reproduzir offline a mesma classe de erro que no nativo era `ERROR_INVALID_HANDLE`.
- **Regressão**: `CustodyLifecycleContract` (unit 56/56).

### Bytes finais (fora do ZIP; vinculados por SHA-256)

| Artefato | SHA-256 | Tamanho |
|---|---|---|
| ZIP `…_FINAL_V008R3_20261022.zip` | `46E4D3313020316044D3D4F0DC6D3A2D6EFA1CB5718722B57340BD86149C17B7` | 87.380.724 B · 2.948 membros |
| Manifesto final (M2) | `3199509D3D8C56AC279F390C9C9421900DAEB8F92B24916DA06213D2CF89291A` | 2.947 arquivos |
| Manifesto testado (M1) | `559B1D6FC24B1081DEA87044884B790BB9524F28195F232C37EBA22D85CE2CA4` | 2.914 arquivos |
| Bootstrap `BOOTSTRAP_…_V008R3_PS51.ps1` | `4185F66D059E2FEC3CDF4E5BA5E53A51CC4915346CD689F3CE16718BD6B47738` | 22.858 B |
| Entry `CODE/pegasus_entry.py` | `F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB` | — |

**tested=packaged=delivered:** M1→M2 difere apenas por 33 arquivos de evidência sob `receipts/V008/offline_final/` (0 removidos, 0 alterados); código e docs byte-idênticos. O extrato do ZIP reconfere 2.947/2.947 arquivos e roda 56/56 testes unitários. Supersede V008R2 (`4A167681…`). O template do bootstrap é inalterado (`B5CECF29…`), e a sua fronteira de exit já foi provada nativamente na campanha R2.

## Fronteiras (inalteradas)

`G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO`. `run-b/-c/-full` bloqueiam antes de qualquer efeito. Custódia da política exclusiva da origem; nada de MASTER/HEAD consultado.

## Re-execução — a mesma campanha única

A partir de `PS C:\Users\silvi>` (sem `cd`), com o ZIP e o bootstrap R3 em `C:\Users\silvi\Downloads`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R3_PS51.ps1 -Mode Verify
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R3_PS51.ps1 -Mode QualifyNative
```

Agora a `QualifyNative` deve avançar para além de S07: Q01–Q09 sob Job real, W04 Q10a–f, Job Q11, SAFE_STOP/retomada, MULTIWORK, e a matriz de exit Q14/Q15. O log fica sempre em `C:\Users\silvi\Downloads\PEGASUS_FULL_2026_RUNS\<MODO>_<timestamp>_<PID>\RUN_LOG.txt`, independentemente da pasta atual; a instância elevada (UAC) usa a mesma pasta. Devolva o `..._RESULT.zip` a esta conversa.

## Estado honesto dos gates

| Gate | Estado |
|---|---|
| G1 vínculo de origem | PASS (caminho supervisionado + fronteira de exit + ciclo de vida do handle do Job fechados; binding QS4 BLOQUEADO provado) |
| G2 W04 full | Implementado; W04 **armou nativamente** na R2 (43 arquivos, 0 violações, usn_hits=0); qualificação nativa completa pendente de re-run |
| G3 W04 JIT/Job | Implementado; ciclo de vida do handle corrigido (R3); **nativo pendente de re-run** |
| G4 SAFE_STOP/retomada | PASS offline; classificação de exit exata; **nativo pendente** |
| G5 Windows nativo integrado | Fronteira de exit **validada no Windows real** (R2); campanha completa pendente de re-run |
| G6 CANDIDATE_COMPLETENESS | **NOT_PASS** — único bloqueio externo: re-execução nativa da campanha no PC do titular |

Nenhum PASS declarado sem execução efetiva.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
