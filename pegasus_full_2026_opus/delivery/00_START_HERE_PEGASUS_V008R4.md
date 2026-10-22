# PEGASUS FULL 2026 — ENTREGA DE ENGENHARIA V008R4 (Opus, 22/10/2026)

**Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14 · **Papel:** implementador integrado (não auditor independente).

## O que mudou da R3 para a R4

A campanha nativa R3 **confirmou a correção do handle do Job** (R3): no Windows real, **Q01 e Q02 passaram nativamente** (W04 armou por caso — 43 arquivos, 0 violações, `usn_hits=0` — e a contabilidade do Job foi lida sem `ERROR_INVALID_HANDLE`). A cadeia avançou e parou em **Q03 (SAFE_STOP)**: o supervisor exigia `child_exit == 130`, mas o Ctrl+C cooperativo honrado pelo coordenador saiu **1** no Windows (o `130` é um artefato POSIX: o CPython re-ergue o SIGINT; o Windows não tem essa semântica — o `KeyboardInterrupt` desenrola o processo com exit 1, ou o handler de console encerra com `0xC000013A`/STATUS_CONTROL_C_EXIT).

O próprio STATUS do filho reportou `SAFE_STOP=YES`, `PROCESS_TREE_CLEAN=YES`, `COMMITTED=1/3`, checkpoint válido e sem `RUN.lock` — ou seja, uma **parada cooperativa limpa e retomável**; o único descompasso era o código literal. Correção R4 (sem enfraquecer a garantia):

- **`safestop_verdict`** passa a aceitar o código de interrupção **da plataforma** (`130` POSIX; `1` ou `0xC000013A` Windows) via `is_cooperative_stop_exit`. O código de saída é **corroboração**: a confirmação continua exigindo a evidência independente (STATUS `SAFE_STOP=YES` + árvore drenada sem kill + checkpoint válido + `RUN.lock` ausente + continuidade W04), e o **Q04** prova a retomada exactly-once. Crash (ex.: 87) e exit 0 (completou) continuam recusados.
- **Regressão**: `SafeStopExitPlatform` (7 casos) + mutantes `safestop_windows_accepts_any_code` e `custody_guard_after_close_disabled`.

### Bytes finais (fora do ZIP)

| Artefato | SHA-256 | Tamanho |
|---|---|---|
| ZIP `…_FINAL_V008R4_20261022.zip` | `9B2D3820F36174FB1050F6C4AE03E70DF644FB9C41FCCB7184028E5E57358C61` | 87.386.885 B · 2.949 membros |
| Manifesto final (M2) | `7F7ADC5784F56C93AD8A1D7587D400D5FB579CA846FF0B1B18F631498CCAF9AF` | 2.948 arquivos |
| Manifesto testado (M1) | `E0B2119B7A81F1BF2466B91C23CA1B2CD84D9FA5CDE17A31A3BD53B2D8162DA4` | 2.914 arquivos |
| Bootstrap `BOOTSTRAP_…_V008R4_PS51.ps1` | `E5D5803D07EC756E56597101D8B1E446F14A1737DAFE2DE0A25ADFBE044DE97D` | 22.858 B |
| Entry `CODE/pegasus_entry.py` | `F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB` | — |

**tested=packaged=delivered:** M1→M2 difere só por 34 arquivos de evidência sob `receipts/V008/offline_final/` (0 removidos, 0 alterados); código e docs byte-idênticos. O extrato reconfere 2.948/2.948 arquivos e roda 63/63 unit. Supersede V008R3 (`46E4D331…`). Template do bootstrap inalterado (`B5CECF29…`), fronteira de exit já provada nativa.

## Re-execução — a mesma campanha única (bootstrap R4)

A partir de `PS C:\Users\silvi>`, com o ZIP e o bootstrap R4 em `C:\Users\silvi\Downloads`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R4_PS51.ps1 -Mode Verify
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R4_PS51.ps1 -Mode QualifyNative
```

Agora a `QualifyNative` deve avançar além de Q03: Q04 (retomada exactly-once), Q05–Q09, W04 Q10a–f, Job Q11, e a matriz de exit Q14/Q15. Log sempre em `C:\Users\silvi\Downloads\PEGASUS_FULL_2026_RUNS\<MODO>_<timestamp>_<PID>\RUN_LOG.txt`, independentemente da pasta atual; a instância elevada usa a mesma pasta. Devolva o `..._RESULT.zip`.

## Estado honesto dos gates

| Gate | Estado |
|---|---|
| G1 | PASS (caminho supervisionado + fronteira de exit + handle do Job + SAFE_STOP por plataforma fechados; QS4 BLOQUEADO provado) |
| G2 W04 full | W04 **armou nativamente** (R2/R3); qualificação nativa completa pendente de re-run |
| G3 W04 JIT/Job | Q01/Q02 **nativos PASS** na R3; Q11 netos/breakaway pendente de re-run |
| G4 SAFE_STOP/retomada | Confirmação por plataforma fechada (R4); Q03/Q04 nativos pendentes de re-run |
| G5 Windows nativo | Fronteira de exit validada nativa; campanha completa pendente de re-run |
| G6 CANDIDATE_COMPLETENESS | **NOT_PASS** — único bloqueio externo: re-execução nativa da campanha |

Nenhum PASS declarado sem execução efetiva.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
