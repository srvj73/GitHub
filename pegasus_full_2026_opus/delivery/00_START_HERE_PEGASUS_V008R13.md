# PEGASUS FULL 2026 — ENTREGA DE ENGENHARIA V008R13 (Opus, 23/10/2026)

**Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14 · **Papel:** implementador integrado (não auditor independente).

## O que mudou da R12 para a R13 — correção da revisão preparatória da origem

A origem inspecionou os bytes R12 e apontou dois bloqueios materiais ainda abertos; ambos corrigidos fail-closed, com controle negativo e qualificação proporcional, preservando os avanços da R12 e os PASS anteriores (R9 23/23 `MET`; F01–F04 fechados na R11; R11-ORIGIN-01/02/03 fechados na R12). V003, backend de census e fronteiras econômicas intocados. Os testes Windows usam exclusivamente processos sintéticos, sem efeitos econômicos nem encerramento forçado não autorizado.

- **R12-ORIGIN-01 (BLOQUEANTE) — custódia não durável: reter handles só até o encerramento do supervisor não é custódia.** Na R12, com árvore viva, retinham-se Job + lease W04 *até o fim do processo* — mas, no fim, ou o `KILL_ON_JOB_CLOSE` não pôde ser limpo (risco de morte residual) ou a saída liberava a W04 com o filho vivo; a proteção não cobria **toda a vida da árvore** e não havia recuperação. **Correção:** função pura `custody_finalize_decision(tree_empty, reconcile_deadline_reached, production)` + a reconciliação custódia-preservada de `Supervision.run`. Com árvore viva, o **custodiante permanece VIVO supervisionando** (W04 + Job retidos, drenagem cooperativa por SAFE_STOP, revalidação) **até `TREE_EMPTY`** — esta é a custódia durável, garantindo simultaneamente NO_KILL, proteção W04 por toda a vida da árvore, custódia efetiva e recuperação. Produção não tem prazo (`HOLD_SUPERVISE_UNTIL_TREE_EMPTY_NO_KILL`); só na qualificação limitada o esgotamento de `RECONCILE_HOLD_S` emerge como **decisão reservada à origem** (`RESERVED_DECISION_FAIL_CLOSED_NO_KILL`), nunca matando e nunca soltando a W04. A decisão **nunca finaliza nem abandona** árvore viva (mutante `custody_finalize_abandons_live_tree` morto por `CustodyFinalizeDecision.test_never_finalizes_live_tree`).
- **R12-ORIGIN-02 (LACUNA DE PROVA) — identidade do neto não era temporalmente vinculada.** A existência de um único `creation_time` histórico para um PID não prova, independentemente e no tempo, que o neto é o processo contido. **Correção:** o próprio neto reporta a sua identidade — `(pid, creation_time)` obtido por `GetProcessTimes` **sobre si mesmo** (programa sintético `_JOB_GRANDCHILD`) — e `grandchild_contained(gpid, gctime, job_idents)` exige que **esse par independente** conste da observação independente do Job (resolvida via `process_ctime`) e seja o **único** ctime daquele PID. Duas fontes independentes concordando sobre `(pid, creation_time)` = sobreposição verificável de vida/pertença ao Job. Recusa fail-closed: sem ctime independente (`NO_INDEPENDENT_GRANDCHILD_CTIME`), ctime divergente (`INDEPENDENT_CTIME_DIVERGENT_FROM_JOB`), PID ausente (`PID_NOT_RESOLVED_IN_JOB`) ou ambíguo (`AMBIGUOUS_PID_MULTIPLE_CTIME`). Q11 injeta o neto sintético e grava `grandchild_self_identity` no recibo (mutante `grandchild_contained_accepts_divergent_ctime` morto por `GrandchildContained.test_divergent_ctime_rejected`).

Fechamento em `receipts/V008/offline_final/r13_origin_fixes/` (`ORIGIN_FIXES_CLOSURE_V008R13.json`, `all_closed=true`, incl. F01–F04, R11-ORIGIN-01/02/03 e R12-ORIGIN-01/02). Evidência R10 (`r10_boundary_fix/`), R11 (`r11_audit_fixes/`), R12 (`r12_origin_fixes/`) e campanha R9 (`native_campaign_r9/`) preservadas.

### Bytes finais (fora do ZIP)

| Artefato | SHA-256 |
|---|---|
| ZIP `…_FINAL_V008R13_20261023.zip` (2.954 membros) | `2643D6280F159CA68BC0013932C7FF32FEBC69D0D5FBD47A812D85EA312C6E87` |
| Manifesto final (M2) | `69C90D16005609A83B67FC5970A57515C5B7AA3CB9EC1C844E19E432BDB22062` |
| Manifesto testado (M1) | `AC6F6AB92604F04D7CEA24DA3ED8916D8479F0CE446BA49FF6C312D5E7CB11C0` |
| Bootstrap `BOOTSTRAP_…_V008R13_PS51.ps1` | `5EE03C35DDB4C054F8EC382934BD37B90572F8E47F4C9887CDDF40FA406C3FA7` |
| Entry `CODE/pegasus_entry.py` | `F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB` |

**tested=packaged=delivered:** M1→M2 difere só por 16 arquivos de evidência sob `receipts/V008/offline_final/`; código e docs byte-idênticos. O extrato reconfere 2.953/2.953 arquivos; verify e **100/100** unit sobre os bytes entregues; mutantes do supervisor **31/31**. Supersede V008R12 (`EA17EDE3…`).

## Qualificação nativa — PRESERVADA (R9: 23/23, MET)

A campanha R9 (`MET`, bytes `2C3F39EB…`) está preservada em `native_campaign_r9/` e na atestação externa `NATIVE_QUALIFICATION_ACHIEVED_V008R9.json` + `native_result_r9/`. As correções R10/R11/R12/R13 são no lado do pai/decisão (gates), provadas por controles negativos offline.

## Re-execução (opcional) e prova nativa dirigida

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R13_PS51.ps1 -Mode Verify
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R13_PS51.ps1 -Mode QualifyNative
```

A prova nativa **dirigida** de custódia durável/NO_KILL (observar o custodiante vivo até `TREE_EMPTY`, com a W04 persistente por toda a vida da árvore — R12-ORIGIN-01) e a identidade `(pid, creation_time)` independente do neto no Windows (R12-ORIGIN-02) usam **processos sintéticos** e exigem **autorização da origem**, sem matar processos salvo salvaguardas explícitas; não foram executadas aqui. A campanha R9 (23/23) não deve ser repetida indiscriminadamente.

## Estado honesto dos gates

| Gate | Estado |
|---|---|
| G1 | PASS |
| G2 W04 full | QUALIFICADO NATIVO (R9); F01/F02 + R11-ORIGIN-01/03 + R12-ORIGIN-01 fechados (W04 por toda a vida da árvore) |
| G3 W04 JIT/Job | QUALIFICADO NATIVO (R9); F03 + R11-ORIGIN-02 + R12-ORIGIN-02 fechados (identidade `(pid,ctime)` INDEPENDENTE e única) |
| G4 SAFE_STOP/retomada | QUALIFICADO NATIVO (R9); F04 + R11-ORIGIN-01 + R12-ORIGIN-01 fechados (NO_KILL real; custodiante vivo até `TREE_EMPTY`) |
| G5 Windows nativo | 23/23 (R9); R13 fecha a revisão da origem sobre R12 |
| G6 CANDIDATE_COMPLETENESS | Engenharia completa; todos os achados fechados; native MET (bytes R9); reauditoria focal e selagem com a origem |

A custódia normativa MASTER/HEAD permanece exclusivamente com o ChatGPT de origem. Não iniciei auditoria formal, instalação produtiva, QS4, Phase B/C econômicas nem FULL econômico.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
