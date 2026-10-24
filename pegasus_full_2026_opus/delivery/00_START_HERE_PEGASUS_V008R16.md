# PEGASUS FULL 2026 — ENTREGA DE ENGENHARIA V008R16 (Opus, 24/10/2026)

**Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14 · **Papel:** implementador integrado (não auditor independente).

## O que é esta entrega — fechamento sistêmico único do parecer físico da origem sobre a R15

A origem revisou **fisicamente** o candidato R15 (`PACKAGE_INTEGRITY_R15=PASS`; `MANIFEST=2962/2962`) e reproduziu, em simulação sobre o código selado, **três inconsistências (N1/N2/N3)** que convergem para **uma família causal única**: a ausência de um contrato exaustivo entre **fase real do filho, efeitos já possíveis, custódia/handles realmente retidos ou liberados, resultado terminal e recibo/exit final**. A R16 fecha a classe **como sistema, num único candidato** — não um patch por sintoma nem uma nova série de microversões. Preserva a R15 congelada, o núcleo econômico V003, o census, o G4, todos os PASS válidos e a campanha Windows R9 (23/23 `MET`, só bytes R9). Não li, baixei nem revalidei política/MASTER/HEAD. **D4 (término forçado do supervisor) não está autorizado.**

### Os três negativos, fechados por fato

- **N1 — classificação de efeitos pós-resume.** `Supervision._run_spawned`, ao receber falha de `cust.start` com `resumed_threads≥1` e `child_alive=False` (filho que executou e morreu rápido), classificava como `PrespawnBlocked`/sem efeito (exit 2). **Correção:** função pura `start_failure_effect_class(created, assigned, resumed, alive, rollback)` — retomada ≥1 thread EXECUTOU ⇒ `EFFECTS_POSSIBLE_CHILD_EXECUTED`; "sem efeito" só quando PROVADO (nenhum filho; ou suspenso revertido que nunca retomou). `_run_spawned` só sai BLOCKED sem efeito via `start_failure_is_no_effect`; efeitos possíveis/incerteza ⇒ `effects_started=True` e FAIL exit 3 / hold, **nunca exit 2**.
- **N2 — prova de fechamento do custodiante.** `Supervision._finalize` declarava `custody_closed=True`/fase `CUSTODIAN_CLOSED` mesmo com `close()` recusando fechar (`ActiveProcesses>0`, retorno `None`). **Correção:** `close()` (POSIX e Windows) devolve **prova estruturada** (`closed`, `active_processes`, `handles_closed`); `_finalize` reconfere a **contabilidade final** ANTES de qualquer disarm/close e só declara `CUSTODIAN_CLOSED` via `custody_close_confirmed` (closed=True ∧ ativo=0 ∧ árvore verificada vazia). Contradição/recusa/UNKNOWN ⇒ **hold observável** com W04+Job retidos (**NO_KILL**); o hold de emergência também consome a prova.
- **N3 — coerência de resultado e recibos.** `_run_supervised` imprimia `result=PASS_SUPERVISED_RUN` com `exit_code=3` quando `persist_run_receipt` falhava. **Correção:** `supervised_final_outcome(completed, stopped, receipt_persisted)` centraliza o desfecho — recibo canônico ausente ⇒ **FAIL** (nunca 0/130), qualquer que seja o veredito. `result`/`exit_code`/`exit_class`/`supervision.phase`/banner derivam do mesmo desfecho; gate `custody_resolved`; a emissão do próprio resumo é à prova de falha (não altera o código nem derruba).

### Bytes finais (fora do ZIP)

| Artefato | SHA-256 |
|---|---|
| ZIP `…_FINAL_V008R16_20261024.zip` (2.969 membros, 87.508.969 bytes) | `CE1E923D9403774496906A51F849AB2E896277469E5FEDD412BACCD52DA656FD` |
| Manifesto final (M2) | `6332DCAD249CF74B149AEDE177BC87348AACC0A17F8797B8FC936BA752A25EBE` |
| Manifesto testado (M1) | `776A54F3E250B97CBE0C088CA78424DA31E8DD502ECCADEB3A0261CCD5406F8B` |
| Bootstrap `BOOTSTRAP_…_V008R16_PS51.ps1` | `B1983D678177DE0734F537E5C0FFE77E67B0D8719E0122AD1EC57868B0F4D319` |
| Entry `CODE/pegasus_entry.py` | `F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB` |

**tested=packaged=delivered:** M1→M2 difere só por **18** arquivos de evidência sob `receipts/V008/offline_final/`; código e docs byte-idênticos. O extrato reconfere 2.968/2.968 arquivos; verify e **173/173** unit sobre os bytes entregues; mutantes do supervisor **48/48**. Supersede V008R15 (`75EE96E7…`).

## Qualificação integrada e campanha nativa — PRESERVADA (R9: 23/23, MET)

Offline sobre os bytes finais: cadeia V003 **19/19**; qualificação integrada **18 PASS** (incl. Q16, Q17) **+ 2 SKIPPED_NON_NATIVE**; unit **173/173**; mutantes do supervisor **48/48**; fronteira do bootstrap **20/20 + 8/8**. Regressões N1/N2/N3 (`R16EffectClassPure`, `R16CloseProofPure`, `R16OutcomeCoherencePure`, `R16Integration`) **falham na R15 congelada** e **PASS nos bytes R16**. Probe de convergência N1/N2/N3 `all_safe` nos bytes R16 e **UNSAFE reproduzido** nos bytes R15 congelados. Campanha nativa R9 preservada em `native_campaign_r9/` e em `NATIVE_QUALIFICATION_ACHIEVED_V008R9.json` + `native_result_r9/`.

## Re-execução (opcional) e prova nativa dirigida

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R16_PS51.ps1 -Mode Verify
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R16_PS51.ps1 -Mode QualifyNative
```

O bootstrap grava o log **sempre** em pasta absoluta fixa, nova por execução, independente da pasta atual: `C:\Users\silvi\Downloads\PEGASUS_FULL_2026_RUNS\<MODO>_<yyyyMMdd_HHmmss_fff>_<PID>\RUN_LOG.txt`. A prova nativa **dirigida** das rotas N1/N2/N3 modificadas usa **processos sintéticos** e exige **autorização** (ver `docs/V008/WINDOWS_DIRECTED_QUALIFICATION_PROTOCOL_R16.md` no ZIP); **D4 não autorizado**; não foi executada aqui.

## Estado honesto dos cinco eixos (nenhum inferido de outro)

| Eixo | Estado |
|---|---|
| ENGINEERING_COMPLETE | **SIM** — N1/N2/N3 + família INT (vizinhos) fechados; A01–A04 (R15), F01–F04 e R11/R12/R13-ORIGIN preservados |
| NATIVE_QUALIFICATION | **MET nos bytes R9** (23/23 numa execução); efetividade Win32 das rotas R16 = **TARGET_RUNTIME_PENDING** (qualificação dirigida pendente) |
| CANDIDATE_COMPLETENESS | **engenharia completa**; selagem formal `=PASS` é da origem |
| INDEPENDENT_AUDIT | **pendente** — reauditoria formal independente é da origem |
| RUN_RELEASED | **NO** (G0 desligado; nenhuma corrida liberada) |

Fronteiras preservadas: `G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_B/C_ECONOMIC=NO · RESELECTION_2026=FORBIDDEN · INSTALL_PRODUTIVO=NO · PAID_CREDIT=NOT_USED`. A custódia normativa MASTER/HEAD permanece exclusivamente com o ChatGPT de origem. **Não declaro READY** enquanto a prova nativa dirigida não for executada.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
