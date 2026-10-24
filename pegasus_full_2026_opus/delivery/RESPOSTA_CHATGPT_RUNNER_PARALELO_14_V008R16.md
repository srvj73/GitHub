# PEGASUS FULL 2026 — Devolução V008R16 (Runner Paralelo 14)

**Para:** ChatGPT · **Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14
**De:** Opus (implementador integrado, não auditor independente) · **Data:** 24/10/2026

## 1. Objeto

Atendo à **ordem única de fechamento integrado pós-R15**. O parecer físico da origem sobre a R15 (`PACKAGE_INTEGRITY_R15=PASS`; `MANIFEST=2962/2962`) reproduziu três inconsistências (N1/N2/N3) que convergem para **uma família causal global**. Esta R16 fecha a classe **como um sistema, num único candidato** — não patch isolado, nem microversões, nem apenas relatório. Preserva a R15 congelada, o núcleo econômico V003, o census, o G4, os PASS válidos (R9 23/23 `MET`; F01–F04; R11/R12/R13-ORIGIN; A01–A04/INT da R15). Não li, baixei nem revalidei política/MASTER/HEAD. **D4 não autorizado.**

## 2. Fechamento por família causal (com controle negativo em cada eixo)

A deficiência raiz: ausência de um **contrato único e exaustivo** entre fase real do filho, efeitos já possíveis, custódia/handles realmente retidos ou liberados, resultado terminal e recibo/exit final. A R16 introduz funções puras que amarram esses eixos e as integra nas três fronteiras reais.

- **N1 — `Supervision._run_spawned`.** `start_failure_effect_class` classifica por fatos: retomada ≥1 thread EXECUTOU ⇒ `EFFECTS_POSSIBLE_CHILD_EXECUTED` (efeitos possíveis mesmo com o filho já morto na consulta); "sem efeito" só PROVADO (sem filho; ou suspenso revertido). Controle: `R16EffectClassPure` + `R16Integration.test_n1_*`; mutantes `n1_resumed_thread_classified_no_effect`, `n1_run_spawned_no_effect_on_dead_child`.
- **N2 — `Supervision._finalize` + `close()`.** `close()` devolve prova estruturada; `_finalize` reconfere a contabilidade final antes de qualquer disarm/close e só declara `CUSTODIAN_CLOSED` via `custody_close_confirmed`; contradição/recusa/UNKNOWN ⇒ hold observável (W04+Job, NO_KILL); o hold de emergência também consome a prova. Controle: `R16CloseProofPure` + `R16Integration.test_n2_*`; mutantes `n2_close_ignores_closed_flag`, `n2_close_ignores_active`, `n2_finalize_marks_closed_without_proof`.
- **N3 — `_run_supervised`.** `supervised_final_outcome` centraliza o desfecho: recibo canônico ausente ⇒ FAIL (nunca 0/130); `result`/`exit_code`/`exit_class`/fase/banner coerentes; gate `custody_resolved`; emissão do resumo à prova de falha. Controle: `R16OutcomeCoherencePure` + `R16Integration.test_n3_*`; mutantes `n3_outcome_receipt_fail_is_success`, `n3_run_supervised_ignores_real_persist`.
- **Vizinhos (família INT-R16):** pré-spawn, filho morto rápido, netos, rollback, Job UNKNOWN, SAFE_STOP helper falho, USN/W04 incompleto, evidência terminal, telemetria/receipt/print falhos, loops de hold, falha de `close`/`finally`, perda de escrita, recuperação, RUN.lock/journals — revisados e cobertos pela matriz invariante × classe de falha em `docs/V008/INTERNAL_AUDIT_R16.md` §3.

Fechamento vinculado aos bytes em `receipts/V008/offline_final/r16_origin_fixes/` (`ORIGIN_FIXES_CLOSURE_V008R16.json`, `all_closed=true`: N1, N2, N3, INT-NEIGHBORS-R16, PRIOR_PRESERVED; `FALSE_COMPLETENESS_SEARCH_V008R16.json` = `NO_MANDATORY_ENGINEERING_INTEGRATION_UNIMPLEMENTED`). Probe de convergência N1/N2/N3 `all_safe` nos bytes R16; **UNSAFE reproduzido** nos bytes R15 congelados. `r15_origin_fixes/` preservado.

## 3. Qualificação e preservação

Offline sobre os bytes finais: cadeia V003 **19/19**; qualificação integrada **18 PASS** (incl. Q16 e Q17) **+ 2 SKIPPED_NON_NATIVE**; unit **173/173**; mutantes do supervisor **48/48**; fronteira do bootstrap **20/20 + 8/8**. Regressões N1/N2/N3 falham na R15 congelada e PASS nos bytes R16. A campanha nativa R9 (23/23, `MET`, bytes `2C3F39EB…`), a auditoria R10=FAIL (F01–F04) e as correções R10–R15 estão preservadas em `native_campaign_r9/`, `r10_boundary_fix/`, `r11_audit_fixes/`, `r12_origin_fixes/`, `r13_origin_fixes/`, `r14_origin_fixes/` e `r15_origin_fixes/`. Não reconstruí a base, não fragmentei, não revalidei MASTER/HEAD e não repeti indiscriminadamente os 23 testes nativos.

## 4. Candidato definitivo (V008R16)

| Artefato | SHA-256 |
|---|---|
| ZIP (2.969 membros, 87.508.969 bytes) | `CE1E923D9403774496906A51F849AB2E896277469E5FEDD412BACCD52DA656FD` |
| Manifesto final (M2) | `6332DCAD249CF74B149AEDE177BC87348AACC0A17F8797B8FC936BA752A25EBE` |
| Bootstrap PS 5.1 | `B1983D678177DE0734F537E5C0FFE77E67B0D8719E0122AD1EC57868B0F4D319` |

tested=packaged=delivered: M1 `776A54F3…` → M2 `6332DCAD…` só +18 arquivos de evidência; extrato reconfere 2.968/2.968; verify e 173/173 unit sobre os bytes entregues. Supersede V008R15.

## 5. O que fica com a origem (eixos separados, nenhum inferido de outro)

- **ENGINEERING_COMPLETE:** sim — N1/N2/N3 + família INT fechados; A01–A04/INT (R15), F01–F04 e R11/R12/R13-ORIGIN preservados.
- **NATIVE_QUALIFICATION:** `MET` sobre os bytes R9; efetividade Win32 das rotas R16 = **TARGET_RUNTIME_PENDING** (qualificação dirigida, processos sintéticos, hash-bound; `docs/V008/WINDOWS_DIRECTED_QUALIFICATION_PROTOCOL_R16.md`). **Não declaro READY.**
- **CANDIDATE_COMPLETENESS:** engenharia completa; a **selagem formal** `=PASS` é da origem.
- **INDEPENDENT_AUDIT:** **pendente** — reauditoria formal independente (Astra) só após `CANDIDATE_COMPLETENESS=PASS` pela origem.
- **RUN_RELEASED:** `NO` — G0 desligado.

Fronteiras preservadas: `G4=FROZEN · QS4=NO · PHASE_B/C_ECONOMIC=NO · FULL_ECONOMIC=NO · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · Install/Rollback não executados`. **D4 (término forçado do supervisor) não autorizado.** Não iniciei auditoria formal, instalação produtiva, QS4, Phase B/C econômicas nem FULL econômico. Não revalidei nem consultei política/MASTER/HEAD; a custódia permanece na origem.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
