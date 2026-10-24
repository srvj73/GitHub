# PEGASUS FULL 2026 — ENTREGA DE ENGENHARIA V008R17 (Opus, 24/10/2026)

**Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 15 · **Papel:** implementador integrado (não auditor independente).

## O que é esta entrega — convergência integrada única sobre a R16

A origem revisou o candidato R16 (`PACKAGE_INTEGRITY_R16=PASS`) e identificou **três resíduos materiais**
(I-01/I-02/I-03) de **uma mesma classe causal**: o contrato entre **retenção física da custódia**, **verdade
terminal única** e **rota executável de autorização/encadeamento**. A R17 fecha a classe **como sistema, num
único candidato**, preservando a R16 congelada (N1/N2/N3), a auditoria profunda R15 (A01–A04 + INT), F01–F04
(R11), R11/R12/R13-ORIGIN e a campanha Windows R9 (23/23 `MET`, só bytes R9). Não li, baixei nem revalidei
política/MASTER/HEAD. **D4 (término forçado do supervisor) não está autorizado.**

### Os três resíduos, fechados por fato

- **I-01 — retenção física W04+Job até prova de fechamento.** `_finalize` chamava `guard.disarm(tree_empty=True)`
  (que no nativo faz `release()`, fechando os handles da lease) **antes** de confirmar `cust.close()`; um close
  recusado/UNKNOWN caía no hold de emergência com a W04 **já solta**. **Correção:** `W04Guard.evaluate()` e
  `W04NativeLease.disarm(..., release=False)` separam a **avaliação** do veredito W04 da **liberação física**.
  `_finalize` avalia a W04 com os handles **retidos**, confirma `custody_close_confirmed` e **só então** chama
  `guard.release()`. Close recusado/UNKNOWN ⇒ hold com **W04+Job fisicamente retidos** (`w04_held_pending_close`,
  NO_KILL). Mesma ordem no hold de emergência.
- **I-02 — verdade terminal única em todos os ramos.** O ramo `except PrespawnBlocked` retornava `BLOCKED`/exit 2
  mesmo quando `persist_run_receipt` gravava o fallback **FAIL/exit 3**. **Correção:** `terminal_for_prespawn_block`
  e `terminal_for_post_spawn_fail` centralizam o desfecho: `BLOCKED`/exit 2 só com o recibo **canônico**
  persistido; sobre o fallback, **FAIL/exit 3** coerente. `_emit_summary` torna a emissão do resumo **à prova de
  falha** nos três ramos.
- **I-03 — rota executável de admissão de produção + encadeamento B→C→FULL.** Não havia admissão de produção real
  (só a sintética selada); `run-full` escolhia `phase=B`. **Correção:** `production_admission_verdict` (puro) +
  `ProductionReleaseAdmission` (pacote de autorização **externo do titular**, gates técnicos R01–R06, QS4 sucessor,
  QS5/B06, PolicyRoot, qualificação Windows dirigida, admissão de fontes por hash, volume/espaço, runtime — cada um
  vinculado por SHA-256) + `cmd_run_full` encadeando **B→C→FULL**. Mesmo um pacote completo bloqueia no **selo
  final** `entry.release_admission` (RUN_RELEASED=NO). Nada fabricado; QS4/Phase B/C não antecipados; sem Owner
  Gate hipotético; PolicyRoot verificado só por presença+SHA (política não lida).

### Bytes finais (fora do ZIP)

| Artefato | SHA-256 |
|---|---|
| ZIP `…_FINAL_V008R17_20261024.zip` (2.973 membros, 87.527.642 bytes) | `67BFF721609866ADA51CF283DDF67CCA5DF66FEC6183B3714AB665A389D396EA` |
| Manifesto final (M2) | `58EB5FFD9B6AFA7B9B1C3B9D42274E9150E9D577D29ADDDA6B80C8C0F70ABDBB` |
| Manifesto testado (M1) | `AB4260C73C672A203C9C1EE3C5D99A22F491C9FD3C56AFAE14770B5444C95FA0` |
| Bootstrap `BOOTSTRAP_…_V008R17_PS51.ps1` | `DC45953F6480BFAF3EF0EA77C4F54138BF93D55D83633CC196D246A4668AB9F3` |
| Supervisor `supervisor/pegasus_supervisor_v008.py` | `8D1A5CFE19D10F3B3CDCB4BF0B66F4C9DC46031DEBAD912011AC9926DC40EBEE` |
| Entry `CODE/pegasus_entry.py` (V003, inalterado) | `F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB` |

**tested=packaged=delivered:** M1→M2 difere só por **18** arquivos de evidência sob
`receipts/V008/offline_final/`; **código e docs byte-idênticos** (0 alterados, 0 removidos). Os bytes
**entregues** (ZIP extraído) verificam: `supervisor verify = PASS_PACKAGE_VERIFIED`, `entry verify =
PACKAGE_INTEGRITY=PASS`, 2.973 arquivos, manifesto = M2. Supersede V008R16 (`CE1E923D…`).

## Qualificação offline sobre os bytes finais

- Unit do supervisor: **191/191 PASS** (inclui `R17W04EvaluateVsRelease`, `R17TerminalCoherencePure/Integration`,
  `R17ProductionAdmissionPure/FailClosed`, além das regressões R16/R15/R11).
- Mutantes do supervisor: **48/48 KILLED**.
- Qualificação integrada (sintética, não econômica): **18 PASS (incl. Q16, Q17) + 2 SKIPPED_NON_NATIVE**.
- Cadeia V003 preservada; QS4 binding `BLOCKED` (pin do adaptador); PS parse: `pwsh` indisponível no sandbox,
  template PS5.1 byte-validado na R16 (mesma gramática).
- Campanha nativa R9 **23/23 MET** preservada em `receipts/V008/offline_final/native_campaign_r9/`.

## Re-execução (opcional) e prova nativa dirigida

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R17_PS51.ps1 -Mode Verify
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R17_PS51.ps1 -Mode QualifyNative
```

O bootstrap grava o log **sempre** em pasta absoluta fixa, nova por execução, independente da pasta atual:
`C:\Users\silvi\Downloads\PEGASUS_FULL_2026_RUNS\<MODO>_<yyyyMMdd_HHmmss_fff>_<PID>\RUN_LOG.txt`. A prova nativa
**dirigida** das rotas I-01/I-02/I-03 usa **processos sintéticos** e exige **autorização** (ver
`docs/V008/WINDOWS_DIRECTED_QUALIFICATION_PROTOCOL_R17.md` no ZIP); **D4 não autorizado**; não foi executada aqui.

## Estado honesto dos cinco eixos (nenhum inferido de outro)

| Eixo | Estado |
|---|---|
| ENGINEERING_COMPLETE | **SIM** — I-01/I-02/I-03 + N1/N2/N3 + A01–A04/INT + F01–F04 + R11/R12/R13-ORIGIN fechados |
| NATIVE_QUALIFICATION | **MET nos bytes R9** (23/23); efetividade Win32 das rotas R17 = **TARGET_RUNTIME_PENDING** |
| CANDIDATE_COMPLETENESS | **engenharia completa**; selagem formal `=PASS` é da origem |
| INDEPENDENT_AUDIT | **pendente** — reauditoria formal independente é da origem |
| PRODUCTION_AUTHORIZED / RUN_RELEASED | **NO** (selo final bloqueia; rota de admissão de produção alcançável mas fail-closed) |

Fronteiras preservadas: `G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_B/C_ECONOMIC=NO ·
RESELECTION_2026=FORBIDDEN · INSTALL_PRODUTIVO=NO · PAID_CREDIT=NOT_USED`. A custódia normativa MASTER/HEAD
permanece exclusivamente com o ChatGPT de origem. **Não declaro READY** enquanto a prova nativa dirigida não for
executada.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 15`
