# PEGASUS FULL 2026 — ENTREGA DE ENGENHARIA V008R7 (Opus, 22/10/2026)

**Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14 · **Papel:** implementador integrado (não auditor independente).

## O que mudou da R6 para a R7

A campanha nativa R6 provou **22 de 23 casos nativos** no Windows real — Q01–Q15 **e** os negativos W04 Q10a–f, incluindo **Q03 (SAFE_STOP)**, **Q04 (retomada exactly-once)** e **Q12b** (que pendurava na R5). Único resíduo: **Q11** (linhagem Job + breakaway). A linhagem passou (`GAPLESS_NATIVE_JOB`, 15 processos); o neto imprimiu `BREAKAWAY_SUCCEEDED` — ou seja, `CreateProcess` com `CREATE_BREAKAWAY_FROM_JOB` **não lançou**.

Causa: no Windows 8+ (jobs aninhados), esse `CreateProcess` pode **não lançar** e, mesmo assim, o SO manter o processo no Job. O proxy antigo do teste (“não lançou ⇒ escapou”) é **incorreto** nesse regime — ele não mede a propriedade de segurança real, que é a **contenção**: o processo não sai da contabilidade do Job (de onde valem o gate de árvore-vazia e o fail-safe `KILL_ON_JOB_CLOSE`).

Correção R7 (no teste e no resultado do supervisor; V003 intocado):

- `_JOB_CHILD` mantém o neto de breakaway vivo ~3 s e reporta seu PID.
- `Supervision.run` expõe `job_pids` (PIDs que o kernel registrou no Job via NEW_PROCESS/IOCP + amostragem).
- **Q11 verifica contenção real**: PASS se o SO negou o flag (`BREAKAWAY_DENIED`) **ou** se, apesar de o `CreateProcess` não lançar, o PID do neto permaneceu em `job_pids` (contido pelo kernel). FAIL **só** no escape real (CreateProcess OK e PID **fora** do Job). Critério mais rigoroso que o proxy — mede o escape de custódia de fato.

### Bytes finais (fora do ZIP)

| Artefato | SHA-256 | Tamanho |
|---|---|---|
| ZIP `…_FINAL_V008R7_20261022.zip` | `FDFCEDB59BB361C05B9900FFE4697B5C9496159C546CB379C10E82ECB1002F7F` | 2.947 membros |
| Manifesto final (M2) | `055A9276EEDAD7931A95C65EA6173BA271B29C6E455D8D8939F94DE7627232C3` | 2.946 arquivos |
| Manifesto testado (M1) | `1F8415010BC31A525244B38EE7F8D9FABF92520088483FD9A8B230E3E3A5E26C` | 2.914 arquivos |
| Bootstrap `BOOTSTRAP_…_V008R7_PS51.ps1` | `D90799137B56AFDAAA88B16A196804DD325595944E016B4C216FA8C1B6E0D324` | 22.858 B |
| Entry `CODE/pegasus_entry.py` | `F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB` | — |

**tested=packaged=delivered:** M1→M2 difere só por 32 arquivos de evidência sob `receipts/V008/offline_final/` (0 removidos, 0 alterados); código e docs byte-idênticos. O extrato reconfere 2.946/2.946 arquivos e roda 71/71 unit. Supersede V008R6 (`4B8DF8B9…`). Template do bootstrap inalterado (`B5CECF29…`).

## Re-execução — a mesma campanha única (bootstrap R7)

A partir de `PS C:\Users\silvi>`, com o ZIP e o bootstrap R7 em `C:\Users\silvi\Downloads`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R7_PS51.ps1 -Mode Verify
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R7_PS51.ps1 -Mode QualifyNative
```

Esta é a campanha que pode fechar **23/23 nativos**. Se Q11 passar (neto contido no Job), a qualificação nativa termina com exit 0 e `native_completeness_evaluation=MET`; se o neto realmente escapar, o resultado dirá `BREAKAWAY_CREATEPROCESS=OK pid=... in_job=False` — um escape real, que eu trataria em seguida. Devolva o `..._RESULT.zip`.

## Estado honesto dos gates

| Gate | Estado |
|---|---|
| G1 | PASS |
| G2 W04 full | W04 nativo + negativos Q10a–f PASS (R6); completo |
| G3 W04 JIT/Job | 22/23 nativos PASS (R6); Q11 breakaway com contenção corrigida (R7), pendente de re-run |
| G4 SAFE_STOP/retomada | Q03/Q04 nativos PASS (R6) |
| G5 Windows nativo | 22/23 nativos PASS; re-run para confirmar 23/23 |
| G6 CANDIDATE_COMPLETENESS | **NOT_PASS** — único bloqueio externo: re-execução nativa (confirmar Q11 → 23/23) |

Nenhum PASS declarado sem execução efetiva.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
