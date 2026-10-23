# PEGASUS FULL 2026 — ENTREGA DE ENGENHARIA V008R12 (Opus, 23/10/2026)

**Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14 · **Papel:** implementador integrado (não auditor independente).

## O que mudou da R11 para a R12 — correção da revisão preparatória da origem

A origem inspecionou os bytes R11 e apontou três pontos ainda abertos; todos corrigidos fail-closed, com controle negativo e qualificação proporcional, preservando os PASS anteriores (R9 23/23 `MET`; F01–F04 fechados na R11). V003, backend de census e fronteiras econômicas intocados.

- **R11-ORIGIN-01 (BLOQUEANTE) — `close()` fechava o handle do Job com árvore viva antes do `raise`.** No ramo em que `SetInformationJobObject` falhava, `close()` ainda chamava `CloseHandle(port/job)` e só depois levantava — logo, com `KILL_ON_JOB_CLOSE` ativo, o fechamento podia matar a árvore viva; e no ramo de sucesso, fechar o Job + sair liberava a lease W04 com o filho vivo. **Correção:** função pura `job_close_plan` decide **antes** de qualquer `CloseHandle`; com árvore viva **nunca fecha o handle do Job nem mata** (retém Job + W04 até o fim do processo); `close()` não levanta; o `Supervision.run` registra a **decisão reservada à origem** (`W04_NOKILL_LIVE_TREE_RESERVED_DECISION`). O resíduo (morte só no fim do processo, apenas se o flag não pôde ser limpo) é reservado, não ação do supervisor.
- **R11-ORIGIN-02 (LACUNA DE PROVA) — Q11 ainda casava por PID histórico.** **Correção:** `grandchild_contained` exige o PID do neto com **exatamente um `(pid, creation_time)` resolvido**; PID solto/ambíguo não prova contenção. A prova temporal nativa real fica para a campanha do titular.
- **R11-ORIGIN-03 (LIFECYCLE) — `cust.close()` não garantido em pré-spawn falho.** **Correção:** `arm`, o gate pré-spawn e o `start` passam para **dentro do `try`**; `finally: cust.close()` roda **exatamente uma vez** em todos os caminhos pré-spawn falhos e em exceção de `start`, sem matar processo.

Fechamento em `receipts/V008/offline_final/r12_origin_fixes/` (`ORIGIN_FIXES_CLOSURE_V008R12.json`, `all_closed=true`, incl. F01–F04 e R11-ORIGIN-01/02/03). Evidência R10 (`r10_boundary_fix/`), R11 (`r11_audit_fixes/`) e campanha R9 (`native_campaign_r9/`) preservadas.

### Bytes finais (fora do ZIP)

| Artefato | SHA-256 |
|---|---|
| ZIP `…_FINAL_V008R12_20261023.zip` (2.952 membros) | `EA17EDE35C577CE1D69CB91D529F166B39FBD6B779D6F347487B65E3BF587082` |
| Manifesto final (M2) | `D49A54D8D9778A65CC597442FFCEB8041D3195C22566800EBB3E3536ACAD8035` |
| Manifesto testado (M1) | `BEDEFC7AAA5C6ED1442C0B74018C811002414BEDDEB08D6644EF366C1D9A29ED` |
| Bootstrap `BOOTSTRAP_…_V008R12_PS51.ps1` | `1A63EE3AA368E0588E309765A3076591854B5E1EA13711FD0F8B68E00C95E2F9` |
| Entry `CODE/pegasus_entry.py` | `F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB` |

**tested=packaged=delivered:** M1→M2 difere só por 16 arquivos de evidência sob `receipts/V008/offline_final/`; código e docs byte-idênticos. O extrato reconfere 2.951/2.951 arquivos; verify e **94/94** unit sobre os bytes entregues; mutantes do supervisor **30/30**. Supersede V008R11 (`DD1B3432…`).

## Qualificação nativa — PRESERVADA (R9: 23/23, MET)

A campanha R9 (`MET`, bytes `2C3F39EB…`) está preservada em `native_campaign_r9/` e na atestação externa `NATIVE_QUALIFICATION_ACHIEVED_V008R9.json` + `native_result_r9/`. As correções R10/R11/R12 são no lado do pai/decisão (gates), provadas por controles negativos offline.

## Re-execução (opcional) e prova nativa dirigida

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R12_PS51.ps1 -Mode Verify
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R12_PS51.ps1 -Mode QualifyNative
```

A prova nativa **dirigida** de timeout/kill (observar NO_KILL e a persistência W04 na árvore viva, R11-ORIGIN-01) e a identidade temporal real de Q11 (R11-ORIGIN-02) exigem processos sintéticos e **autorização da origem**, sem matar processos salvo salvaguardas explícitas; não foram executadas aqui.

## Estado honesto dos gates

| Gate | Estado |
|---|---|
| G1 | PASS |
| G2 W04 full | QUALIFICADO NATIVO (R9); F01/F02 + R11-ORIGIN-01/03 fechados |
| G3 W04 JIT/Job | QUALIFICADO NATIVO (R9); F03 + R11-ORIGIN-02 fechados |
| G4 SAFE_STOP/retomada | QUALIFICADO NATIVO (R9); F04 + R11-ORIGIN-01 fechados (NO_KILL real) |
| G5 Windows nativo | 23/23 (R9); R12 fecha a revisão da origem |
| G6 CANDIDATE_COMPLETENESS | Engenharia completa; todos os achados fechados; native MET (bytes R9); reauditoria focal e selagem com a origem |

A custódia normativa MASTER/HEAD permanece exclusivamente com o ChatGPT de origem.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
