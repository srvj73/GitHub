# PEGASUS FULL 2026 — ENTREGA DE ENGENHARIA V008R5 (Opus, 22/10/2026)

**Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14 · **Papel:** implementador integrado (não auditor independente).

## O que mudou da R4 para a R5

A campanha nativa R4 provou a correção do SAFE_STOP por plataforma: no Windows real, **Q01–Q09 e Q12 passaram nativamente** — incluindo **Q03 (SAFE_STOP) e Q04 (retomada exactly-once)**. A cadeia parou em **Q12b** (`run-full --admission` com SAFE_STOP via subprocesso), que **pendurou até o timeout de 1800 s**.

Causa-raiz: o Ctrl+C do SAFE_STOP foi entregue **durante o spawn dos workers** do coordenador. Nessa janela, o `KeyboardInterrupt` atingiu os workers em `import` (matando-os) sem que o coordenador **registrasse** o pedido: `STATUS.STOP_REQUESTED` ficou `False`, `SAFE_STOP=NO`, `ACTIVE=0`, com o coordenador preso imprimindo progresso a cada ~20 s. O supervisor entregava o sinal **uma única vez** (assumindo que o V003 trata o 2º Ctrl+C como `WAIT_NO_KILL`), mas esse 1º sinal se perdeu — e nada o reentregava. O watchdog por heartbeat estagnado não cobria o caso (o coordenador seguia vivo e atualizando o STATUS).

Correção R5 (cooperativa, no supervisor; V003 intocado): o supervisor **reentrega o mesmo Ctrl+C cooperativo** (a cada `SAFE_STOP_REDELIVER_S=15 s`, até `SAFE_STOP_MAX_DELIVERIES=10`) **até o coordenador registrar o pedido** (`STATUS.STOP_REQUESTED=True`) ou o filho sair. Uma vez registrado, não reentrega (o 2º Ctrl+C do V003 é `WAIT_NO_KILL`); jamais termina processo. Regressão `SafeStopRedelivery` (6 casos sobre o predicado puro) + mutante `safestop_redeliver_ignores_latch`.

### Bytes finais (fora do ZIP)

| Artefato | SHA-256 | Tamanho |
|---|---|---|
| ZIP `…_FINAL_V008R5_20261022.zip` | `A7957E699B9BCFA2F0B9F0B4792C9120E05D803321DE22EAA028C079EC865223` | 2.948 membros |
| Manifesto final (M2) | `5E617BE84099E10879D2B60C518556D622E8180D1805EE8817AAD0C549F25F87` | 2.947 arquivos |
| Manifesto testado (M1) | `4D3CF6ACCE4E118DF985B687C4497CAEBC0649F7692AC70614A16E37B87D1D03` | 2.914 arquivos |
| Bootstrap `BOOTSTRAP_…_V008R5_PS51.ps1` | `69474AFD63A5F3D6475263EC5A685B7F1CBD2B8AAACCC927E29F8FD22DDAD46A` | 22.858 B |
| Entry `CODE/pegasus_entry.py` | `F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB` | — |

**tested=packaged=delivered:** M1→M2 difere só por 33 arquivos de evidência sob `receipts/V008/offline_final/` (0 removidos, 0 alterados); código e docs byte-idênticos. O extrato reconfere 2.947/2.947 arquivos e roda 69/69 unit. Supersede V008R4 (`9B2D3820…`). Template do bootstrap inalterado (`B5CECF29…`), fronteira de exit já provada nativa.

## Re-execução — a mesma campanha única (bootstrap R5)

A partir de `PS C:\Users\silvi>`, com o ZIP e o bootstrap R5 em `C:\Users\silvi\Downloads`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R5_PS51.ps1 -Mode Verify
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R5_PS51.ps1 -Mode QualifyNative
```

Agora a `QualifyNative` deve passar de Q12b (SAFE_STOP via subprocesso) para Q12c (retomada), Q13 (bloqueios econômicos), Q14/Q15 (matriz de exit) e os negativos nativos W04 Q10a–f e Job Q11. Log sempre em `C:\Users\silvi\Downloads\PEGASUS_FULL_2026_RUNS\<MODO>_<timestamp>_<PID>\RUN_LOG.txt`, independentemente da pasta atual; a instância elevada usa a mesma pasta. Devolva o `..._RESULT.zip`.

## Estado honesto dos gates

| Gate | Estado |
|---|---|
| G1 | PASS (supervisionado + fronteira de exit + handle do Job + SAFE_STOP por plataforma + reentrega cooperativa fechados; QS4 BLOQUEADO provado) |
| G2 W04 full | W04 armou nativamente (R2/R3/R4); negativos Q10a–f pendentes de re-run |
| G3 W04 JIT/Job | Q01–Q09 e Q12 **nativos PASS** (R4); Q11 netos/breakaway pendente de re-run |
| G4 SAFE_STOP/retomada | Q03 SAFE_STOP e Q04 retomada **nativos PASS** (R4); reentrega cooperativa fechada (R5) |
| G5 Windows nativo | Fronteira de exit validada nativa; campanha completa (Q12b→fim) pendente de re-run |
| G6 CANDIDATE_COMPLETENESS | **NOT_PASS** — único bloqueio externo: re-execução nativa da campanha |

Nenhum PASS declarado sem execução efetiva.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
