# PEGASUS FULL 2026 — ENTREGA DE ENGENHARIA V008R15 (Opus, 24/10/2026)

**Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14 · **Papel:** implementador integrado (não auditor independente).

## O que é esta entrega — convergência integrada única (não mais um micro-ajuste)

A origem realizou uma **auditoria preparatória profunda** sobre o candidato R14 congelado (`PACKAGE_INTEGRITY_R14=PASS`; `MANIFEST=2955/2955`) e exigiu **uma convergência integral única** — examinar a implementação como sistema completo, corrigir internamente **todas** as deficiências materialmente demonstráveis no escopo autorizado e qualificar a integração por **invariantes e classes de falha**, não por achado isolado. Esta R15 é esse candidato único, congelado e vinculado por hashes. Preserva integralmente os PASS válidos (R9 23/23 `MET`; F01–F04; R11-ORIGIN-01/02/03; R12-ORIGIN-01/02; R13-ORIGIN-01) e mantém V003, backend de census e fronteiras econômicas intocados. Testes Windows só com processos sintéticos; sem encerramento forçado nem efeito econômico; campanha R9 não repetida. Não consultei, li, baixei nem revalidei política/MASTER/HEAD.

### Famílias causais fechadas (não sintomas)

- **A01 — exceção/falha pós-spawn encerrava a custódia com a árvore viva.** `Supervision` passou a ser uma **máquina de estados** (`PRESPAWN → SPAWNING → RUNNING → STOP_REQUESTED → DRAINING → LIVE_TREE_BLOCKED → TREE_EMPTY → W04_DISARMED → CUSTODIAN_CLOSED → RESULT_PERSISTED`). **Nenhuma** exceção controlável sai de `run()` depois que um filho existe: toda chamada pós-spawn passa por `_guard`; `request_stop` é **estruturado** (helper nonzero/timeout nunca derruba o hold); `observe_tree` é **tri-estado** (`LIVE`/`EMPTY`/`UNKNOWN`, e `UNKNOWN` nunca libera); `close()` só ocorre com a árvore **VERIFICADA vazia** (duas observações consecutivas). Reproduzido **UNSAFE** nos bytes R14 congelados; `all_safe` nos bytes R15.
- **A02 — leitor USN declarava cobertura completa sem progressão.** Função **pura** `usn_scan_coverage` prova cobertura até `end_usn` (cursor progressivo, EOF, IOCTL, registro malformado, versão, FRN128, ordem); `_read_usn` virou **adaptador fino**. `w04_verdict` passou a exigir **o bloco de prova de cobertura**, não só o booleano `read_complete` (`USN_COVERAGE_PROOF_ABSENT`/`_INCOMPLETE`/`_SHORT_OF_END`). Reproduzido bit-a-bit pela origem (bytes `97A9543C…`); bloqueado na R15.
- **A03 — conclusão sem evidência terminal vinculada à tentativa.** `terminal_evidence_verdict(mode=COMPLETION|SAFE_STOP)` exige STATUS V003 do produtor **dentro da árvore supervisionada**, `run_instance` **fresco** para esta tentativa, `PROCESS_TREE_CLEAN=YES`, `ACTIVE=0`, `COMMITTED==TOTAL>0` e `CHECKPOINT` coerente. `completion_verdict`/`safestop_verdict` passaram a **exigir** essa evidência (caso Q17).
- **A04 — falha técnica podia não emitir recibo estruturado.** `persist_run_receipt` grava recibo canônico em **todo** desfecho (só o canônico conta para 0/130; nunca levanta); `main()` emite JSON `FAIL_TECHNICAL` e `PrespawnBlocked` sai **2** (sem efeito).
- **INT (família de fronteiras/exceções) + C4 (isolamento --admission).** Matriz de fronteiras tratada em bloco: rollback só do filho **suspenso** que nunca retomou thread (nunca de filho em execução); liberação pelo titular só com `KILL_ON_JOB_CLOSE` removido; `CUSTODY_STATE` persistente e observável a cada heartbeat. `--admission` só aceita o módulo sintético **selado** do pacote (caminho exato + SHA do manifesto); o argv de plano não econômico não pode apontar o runtime econômico (`CODE/`), provado por `plan_isolation_verdict`.

### Bytes finais (fora do ZIP)

| Artefato | SHA-256 |
|---|---|
| ZIP `…_FINAL_V008R15_20261023.zip` (2.963 membros) | `75EE96E700408876B4F5509DB2B6397517AE993C29A05BA713480D912C5A1490` |
| Manifesto final (M2) | `ABCEB1E67F0242127211B15B7DCA6DAC1D17C07F24A82A4D9136AEB5B7E380EC` |
| Manifesto testado (M1) | `945481B3B9FB2238B5C1CF7773511424B7B9AC9BB9CAEC0E07CAF290EC51CDB1` |
| Bootstrap `BOOTSTRAP_…_V008R15_PS51.ps1` | `036193A34F931F6C083AB64E2CF74FC058DAD79C4C8CA3E76C35680E1DE3E150` |
| Entry `CODE/pegasus_entry.py` | `F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB` |

**tested=packaged=delivered:** M1→M2 difere só por **18** arquivos de evidência sob `receipts/V008/offline_final/`; código e docs byte-idênticos. O extrato reconfere 2.962/2.962 arquivos; verify e **156/156** unit sobre os bytes entregues; mutantes do supervisor **41/41**. Supersede V008R14 (`012D4347…`).

## Qualificação integrada e campanha nativa — PRESERVADA (R9: 23/23, MET)

Offline sobre os bytes finais: cadeia V003 **19/19**; qualificação integrada **18 PASS** (incl. **Q16** W04-BLOCKED bloqueia conclusão e **Q17** conclusão exige evidência terminal) **+ 2 SKIPPED_NON_NATIVE**; unit **156/156**; mutantes do supervisor **41/41**; fronteira do bootstrap **20/20** + **8/8**. O probe de convergência confirma `all_safe` nos bytes R15 e reproduz `UNSAFE` (A01) nos bytes R14. A campanha nativa R9 (`MET`, 23/23) está preservada em `native_campaign_r9/` e na atestação `NATIVE_QUALIFICATION_ACHIEVED_V008R9.json` + `native_result_r9/`.

## Re-execução (opcional) e prova nativa dirigida

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R15_PS51.ps1 -Mode Verify
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R15_PS51.ps1 -Mode QualifyNative
```

O bootstrap grava o log **sempre** em pasta absoluta fixa, nova por execução, independente da pasta atual: `C:\Users\silvi\Downloads\PEGASUS_FULL_2026_RUNS\<MODO>_<yyyyMMdd_HHmmss_fff>_<PID>\RUN_LOG.txt`. A prova nativa **dirigida** das propriedades A01/A02/A03 e de `KILL_ON_JOB_CLOSE` ativo/removido usa **processos sintéticos** e exige **autorização da origem** (ver `WINDOWS_DIRECTED_QUALIFICATION_PROTOCOL_R15.md` no ZIP); não foi executada aqui.

## Estado honesto dos cinco eixos (nenhum inferido de outro)

| Eixo | Estado |
|---|---|
| ENGINEERING_COMPLETE | **SIM** — A01–A04 + família INT + C4-ISOLATION fechados fail-closed; F01–F04 e R11/R12/R13-ORIGIN preservados |
| NATIVE_QUALIFICATION | **MET nos bytes R9** (23/23 numa execução); re-execução confirmatória nos bytes R15 pendente |
| CANDIDATE_COMPLETENESS | **engenharia completa**; selagem formal `=PASS` é da origem |
| INDEPENDENT_AUDIT | **pendente** — reauditoria formal independente é da origem |
| RUN_RELEASED | **NO** (G0 desligado; nenhuma corrida liberada) |

Fronteiras preservadas: `G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_B/C_ECONOMIC=NO · RESELECTION_2026=FORBIDDEN · INSTALL_PRODUTIVO=NO · PAID_CREDIT=NOT_USED`. A custódia normativa MASTER/HEAD permanece exclusivamente com o ChatGPT de origem.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
