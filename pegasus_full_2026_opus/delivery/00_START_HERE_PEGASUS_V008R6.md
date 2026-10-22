# PEGASUS FULL 2026 — ENTREGA DE ENGENHARIA V008R6 (Opus, 22/10/2026)

**Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14 · **Papel:** implementador integrado (não auditor independente).

## O que mudou da R5 para a R6

A campanha nativa R5 mostrou que **reentregar** o Ctrl+C (R5) não resolve a corrida: em **Q03**, as 8+ reentregas mantiveram `STATUS.STOP_REQUESTED=False`, `COMMITTED=1/3`, `ACTIVE=0`, até o timeout. (O Q03 havia passado na R4 só por sorte de timing.)

Causa-raiz precisa: o Ctrl+C vai ao **grupo do console**. Entregue no instante `ACTIVE=0` (logo após um `SESSION_COMMIT`, durante o spawn/`import` dos workers da próxima sessão), ele mata os workers em `import` — que ainda não instalaram o ignore-SIGINT do design V003 — e **encrava** o coordenador num estado `ACTIVE=0` do qual nenhum Ctrl+C posterior recupera. Com workers já em execução (`ACTIVE>0`), eles ignoram o SIGINT e só o coordenador reage, registrando o pedido e fechando a admissão no próximo `SESSION_COMMIT`.

Correção R6 (no supervisor; V003 intocado):

- **Janela segura:** no Windows, o supervisor só entrega o SAFE_STOP com `STATUS.ACTIVE>0` (workers em execução), nunca na janela de `import`/spawn. No POSIX o sinal vai só ao coordenador (`os.kill`), sem a corrida de console, então o gate não se aplica (preserva o Q03 offline).
- **Falha-fechada rápida:** se o pedido for feito mas o coordenador nunca registrar em 180 s (encrave), o supervisor levanta `SAFE_STOP_NOT_HONORED_NO_LATCH_RECONCILE_REQUIRED` — diagnóstico claro em vez de pendurar até o timeout total. Jamais termina processo.

### Bytes finais (fora do ZIP)

| Artefato | SHA-256 | Tamanho |
|---|---|---|
| ZIP `…_FINAL_V008R6_20261022.zip` | `4B8DF8B9C178B4DD19565992BF0B0DC5D90FB8B1E4E10C816AF724F7ED1E8360` | 2.949 membros |
| Manifesto final (M2) | `186E8A0F9F3E46290F64D20CC713DF63043D5DB4120AA21097128443C0D9963D` | 2.948 arquivos |
| Manifesto testado (M1) | `EA3AF7FB29F96D035F48066A8BF9244A56F08B95185AFB0EA16FF4EB8A215E9A` | 2.914 arquivos |
| Bootstrap `BOOTSTRAP_…_V008R6_PS51.ps1` | `B90A86FA37538C07669C469EC29D483256D72378333798D7A4BD13C73AC8D89F` | 22.858 B |
| Entry `CODE/pegasus_entry.py` | `F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB` | — |

**tested=packaged=delivered:** M1→M2 difere só por 34 arquivos de evidência sob `receipts/V008/offline_final/` (0 removidos, 0 alterados); código e docs byte-idênticos. O extrato reconfere 2.948/2.948 arquivos e roda 71/71 unit. Supersede V008R5 (`A7957E69…`). Template do bootstrap inalterado (`B5CECF29…`).

## Re-execução — a mesma campanha única (bootstrap R6)

A partir de `PS C:\Users\silvi>`, com o ZIP e o bootstrap R6 em `C:\Users\silvi\Downloads`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R6_PS51.ps1 -Mode Verify
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R6_PS51.ps1 -Mode QualifyNative
```

Agora a `QualifyNative` deve passar de Q03 (SAFE_STOP) para Q04 (retomada), Q05–Q09, Q12/Q12b/Q12c, Q13, Q14/Q15 e os negativos nativos W04 Q10a–f e Job Q11. Log sempre em `C:\Users\silvi\Downloads\PEGASUS_FULL_2026_RUNS\<MODO>_<timestamp>_<PID>\RUN_LOG.txt`. Se algum SAFE_STOP não for honrado, agora o resultado chega em ~180 s com diagnóstico claro, não mais com longos travamentos. Devolva o `..._RESULT.zip`.

## Estado honesto dos gates

| Gate | Estado |
|---|---|
| G1 | PASS (supervisionado + fronteira de exit + handle do Job + SAFE_STOP por plataforma + janela segura de entrega fechados; QS4 BLOQUEADO provado) |
| G2 W04 full | W04 armou nativamente (R2–R5); negativos Q10a–f pendentes de re-run |
| G3 W04 JIT/Job | Q01/Q02 nativos PASS (R5); demais pendentes de re-run |
| G4 SAFE_STOP/retomada | Entrega em janela segura fechada (R6); Q03/Q04 nativos pendentes de re-run |
| G5 Windows nativo | Fronteira de exit validada nativa; campanha completa pendente de re-run |
| G6 CANDIDATE_COMPLETENESS | **NOT_PASS** — único bloqueio externo: re-execução nativa da campanha |

Nenhum PASS declarado sem execução efetiva.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
