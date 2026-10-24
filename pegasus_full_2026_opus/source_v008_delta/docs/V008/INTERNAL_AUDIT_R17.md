# Auditoria interna adversarial e convergência sistêmica — V008R17

Resposta ao parecer de **convergência integrada** sobre a R16. A revisão tratou a implementação **como um
sistema completo** e fechou a **família causal única** que três resíduos materiais (I-01/I-02/I-03) expõem,
não cada sintoma em separado. Nenhum núcleo econômico V003, census ou G4 foi tocado. A R16 (N1/N2/N3), a
auditoria profunda R15 (A01–A04 + INT), F01–F04 (R11), R11/R12/R13-ORIGIN e a campanha nativa R9 (23/23, MET)
permanecem preservadas.

## 1. Família causal

A R16 fechou a *classificação* (N1), a *prova de fechamento* (N2) e a *coerência de desfecho* (N3). A
convergência R17 fecha o que a R16 deixou **estruturalmente incompleto** na mesma classe — o contrato entre:

1. **retenção física da custódia** (a W04 estava sendo **liberada fisicamente** por `disarm→release` ANTES de
   o fechamento do Job ser comprovado);
2. **verdade terminal única** (os ramos `except` de `_run_supervised` não passavam pela decisão terminal única
   — um fallback FAIL coexistia com banner/exit BLOCKED);
3. **rota executável de autorização** (não existia admissão de produção real nem encadeamento B→C→FULL — só a
   admissão sintética selada; `run-full` escolhia `phase=B`).

## 2. Os três resíduos, fechados por fato (não por sintoma)

| # | Fronteira | Defeito R16 | Correção R17 |
|---|---|---|---|
| **I-01** | `_finalize` / `_emergency_hold_and_result` → `guard.disarm(tree_empty=True)` → `W04NativeLease.disarm` → `release()` | `disarm` **liberava os handles da lease** (release físico) antes de `cust.close()` ser confirmado; close recusado/UNKNOWN caía no hold de emergência com a W04 **já solta** — o hold de W04+Job prometido não era demonstrado. | `W04NativeLease.disarm(tree_empty, release=False)` e `W04Guard.evaluate()` separam a **avaliação** do veredito W04 da **liberação física** (`release`). `_finalize` avalia a W04 com os handles **retidos**, confirma `custody_close_confirmed` e **só então** chama `guard.release()`. Close recusado/UNKNOWN ⇒ hold de emergência com **W04+Job fisicamente retidos** (`w04_held_pending_close=True`, NO_KILL). Mesma ordem no hold de emergência. |
| **I-02** | `_run_supervised`, `except PrespawnBlocked` e `except BaseException` | ramo pré-spawn retornava `BLOCKED`/exit 2 mesmo quando `persist_run_receipt` falhava o canônico e gravava o fallback **FAIL/exit 3** — verdade terminal incoerente entre recibo, banner e exit. | `terminal_for_prespawn_block(receipt_persisted)` e `terminal_for_post_spawn_fail(...)` centralizam o desfecho de **todos** os ramos: `BLOCKED`/exit 2 só é legítimo com o recibo **canônico** persistido; sobre o fallback FAIL o desfecho degrada a **FAIL/exit 3**, coerente com o recibo realmente gravado. `_emit_summary` torna a emissão do resumo **à prova de falha** nos três ramos (pré-spawn, pós-spawn, sucesso). |
| **I-03** | `DefaultReleaseAdmission` / `_run_supervised` / `run-full` | não havia rota executável de admissão de produção (só a sintética selada); `plan.economic=True` era rejeitado incondicionalmente; `run-full` selecionava `phase=B`; o encadeamento B→C→FULL não existia. | `production_admission_verdict` (puro) + `ProductionReleaseAdmission` (pacote de autorização **externo do titular**, gates técnicos R01–R06, QS4 sucessor, QS5/B06, PolicyRoot, qualificação Windows dirigida, admissão de fontes por hash, volume/espaço e runtime — cada um vinculado por SHA-256 + `status=PASS`) + `cmd_run_full` encadeando **B→C→FULL** (C exige B; FULL exige B e C). Mesmo um pacote completo bloqueia no **selo final** `entry.release_admission` (RUN_RELEASED=NO). |

## 3. O que NÃO foi feito (fronteiras preservadas, por decisão)

- Os bloqueios econômicos **não** foram removidos para forçar uma corrida. A dupla barreira
  (`make_run_plan` recusa plano econômico sem autorização provada; `_run_supervised` revalida
  `release_admission`) permanece.
- **Nenhuma credencial/recibo fabricado.** `production_admission_verdict` apenas verifica presença + SHA +
  `status=PASS` dos recibos que o **titular/origem** fornecerá; não cria, assina nem antecipa nenhum.
- **QS4, Phase B e Phase C não antecipados.** O encadeamento é estrutural e hoje bloqueia já em B.
- **Nenhum Owner Gate hipotético.** Não há aprovação administrativa fabricada.
- **PolicyRoot** permanece entrada técnica obrigatória (verificada só por presença + SHA do recibo). Este
  código **não lê, baixa, autentica nem revalida** MASTER/HEAD/política.
- **D4 (término forçado do supervisor) não autorizado.** O supervisor nunca mata por iniciativa própria.

## 4. Matriz invariante × classe de falha (vizinhos revisados na R17)

| Classe de falha | Invariante exigido | Onde é provado |
|---|---|---|
| close do Job recusado após avaliar W04 | W04 **não** liberada; W04+Job retidos (NO_KILL) | **I-01** `W04Guard.evaluate`/`release`, `R16Integration.test_n2` (`guard.released==0`), `R17W04EvaluateVsRelease` |
| hold de emergência com árvore viva | avaliar retendo; liberar só após prova de close | **I-01** `_emergency_hold_and_result` reordenado |
| pré-spawn bloqueado, recibo canônico falha | FAIL/exit 3 coerente (nunca BLOCKED/exit 2 sobre fallback) | **I-02** `terminal_for_prespawn_block`, `R17TerminalCoherenceIntegration` |
| falha técnica pós-spawn, recibo falha | FAIL/exit 3 em ambos os casos | **I-02** `terminal_for_post_spawn_fail` |
| emissão do resumo falha | exit preservado; sem crash | **I-02** `_emit_summary` |
| autorização de produção ausente/incompleta | BLOCKED com causa; não chega ao selo final | **I-03** `production_admission_verdict`, `R17ProductionAdmissionFailClosed` |
| autorização completa e válida em SHA | ainda bloqueia no selo final (RUN_RELEASED=NO) | **I-03** `ProductionReleaseAdmission.admit` |
| run-full | encadeia B→C→FULL; bloqueia em B hoje | **I-03** `cmd_run_full`, `CliFailClosed` |
| N1/N2/N3, A01–A04/INT, F01–F04, R9 | preservados | regressões R16/R15/R11 + `native_campaign_r9/` |

## 5. Evidência

`receipts/V008/offline_final/r17_origin_fixes/` (`ORIGIN_FIXES_CLOSURE_V008R17.json`, `all_closed=true`:
I-01, I-02, I-03, PRIOR_PRESERVED; `FALSE_COMPLETENESS_SEARCH_V008R17.json` =
`NO_MANDATORY_ENGINEERING_INTEGRATION_UNIMPLEMENTED`). Regressões `R17W04EvaluateVsRelease`,
`R17TerminalCoherencePure/Integration`, `R17ProductionAdmissionPure/FailClosed` falham na R16 congelada
(símbolo ausente ou comportamento contraditório) e PASS nos bytes R17; probe de convergência I-01/I-02/I-03
`all_safe` na R17 e UNSAFE reproduzido na R16. A efetividade Win32 das rotas modificadas fica na qualificação
dirigida (processos sintéticos; **D4 não autorizado**): enquanto pendente, `TARGET_RUNTIME_PENDING`.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 15`
