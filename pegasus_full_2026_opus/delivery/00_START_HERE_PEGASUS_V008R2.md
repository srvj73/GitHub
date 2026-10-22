# PEGASUS FULL 2026 — ENTREGA DE ENGENHARIA V008R2 (Opus, 22/10/2026)

**Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14 · **Papel:** implementador integrado (não auditor independente).

## O que é esta entrega

Um único candidato de engenharia **integrado, qualificado offline e congelado**, construído sobre o **Codex V003 físico** (`CC37261C…`, payload `73EF2833…`): os 2.867 arquivos do V003 permanecem **byte-idênticos** (manifesto parent `701DF5EC…` preservado). O V008R2 sucede o V008R1 fechando a **fronteira completa de exit codes e stdio** — causa-raiz do `EXIT=3` da campanha nativa R1.

### Bytes finais (fora do ZIP; vinculados por SHA-256)

| Artefato | SHA-256 | Tamanho |
|---|---|---|
| ZIP `PEGASUS_FULL_2026_ENGINEERING_FINAL_V008R2_20261022.zip` | `4A1676816C81DB5CA343261712238DCCBEA1F9C6ECBDE1AA8013307D8514EFE2` | 87.368.861 B · 2.944 membros |
| Manifesto final (M2) | `9FA39FC91CD3B46A263E62628BF005CBDB4F1871BDA3B77B991616DA9A5C7C02` | 2.943 arquivos |
| Manifesto testado (M1, congelado antes da evidência) | `165BE55F17160ECB260F0DA5AC74F6092C78E00D99B45F5350ED67BA7B780A25` | 2.914 arquivos |
| Bootstrap `BOOTSTRAP_PEGASUS_FULL_2026_V008R2_PS51.ps1` | `DF1DF8C3145378E58E4A1779E97B1658A00CF3C5DD3A069C1240B2B26A1C901E` | 22.858 B |
| Entry `CODE/pegasus_entry.py` | `F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB` | — |

**tested=packaged=delivered:** M1→M2 difere **apenas** por 29 arquivos de evidência sob `receipts/V008/offline_final/` (0 removidos, 0 alterados); o código e os docs são byte-idênticos. O extrato do ZIP reconfere 2.943/2.943 arquivos contra o manifesto, e os testes unitários rodam 55/55 sobre os bytes entregues.

## Fronteira de exit codes fechada (R2)

A campanha nativa R1 terminou `EXIT=3` por um defeito do PowerShell 5.1: `Start-Process -PassThru` **não retém o handle** do processo; o `ExitCode` `$null` de um filho rápido era coagido a `0` — **falso PASS** em toda etapa que espera 0, inclusive no relé do UAC. O S03 gravou `ARGV_PROBE.json` com `pass=true` (a fonte sai 37), mas o bootstrap registrou `NATIVE_EXIT code=0`.

Correção integral (não um remendo de S03):

- **Bootstrap** reescrito: captura nativa por `System.Diagnostics.Process.Start()` com `$null = $Child.Handle`; `Get-PegasusExitCode` **fail-closed** (exit ausente/não encerrado nunca vira 0); dreno assíncrono de stdout/stderr (`ReadToEndAsync`, sem deadlock); higiene de ambiente; watchdog que **não mata** o filho e grava recibo de reconciliação; relé do UAC que confronta o exit do processo elevado com o exit gravado (divergência/nulo ⇒ 3); recibo por etapa `{expected, observed, classification, pid, creation_time_utc, stdout_bytes, stderr_bytes}`.
- **Supervisor**: `classify_exit` exato — 0 PASS; 2 BLOCKED (sem efeito); 3 FAIL técnico após efeito; 130 SAFE_STOP; ausente/não-inteiro ⇒ fail-closed. `_run_supervised` grava `exit_code`/`exit_class`; `main()` converte exceção técnica em 3.

Controles sobre os **bytes reais** do template (extração por AST): `test_bootstrap_exit_boundary_v008.ps1` 20/20; `mutation_bootstrap_exit_boundary_v008.py` 8/8 mutantes mortos. Unit 55/55; mutantes do supervisor 20/20. Qualificação acrescida de **Q14** (matriz de propagação de exit por subprocesso) e **Q15** (classificação técnica). O recibo de qualificação embute `native_completeness_evaluation` (veredito `NOT_MET` fora do Windows nativo).

## Fronteiras (inalteradas)

`G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO`. `run-b/-c/-full` bloqueiam antes de qualquer efeito (exit 2, efeito NONE). A custódia da política vigente permanece exclusiva do ChatGPT de origem; nada de MASTER/HEAD foi consultado ou validado.

## Execução — campanha única no Windows do titular

A partir de `PS C:\Users\silvi>` (sem `cd`), com o ZIP e o bootstrap em `C:\Users\silvi\Downloads`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R2_PS51.ps1 -Mode Verify
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R2_PS51.ps1 -Mode QualifyNative
```

1. **Verify** confere o SHA do ZIP (`4A167681…`) e do manifesto (`9FA39FC9…`), extrai com segurança e roda `pegasus_entry verify` + `supervisor verify`.
2. **QualifyNative** executa a campanha integrada sob Job real: W04 JIT (Q10a–f), custódia Job e linhagem sem lacunas (Q11), SAFE_STOP e retomada exactly-once, MULTIWORK A/B, observabilidade, controles negativos e a matriz de exit (Q14/Q15).

O log fica sempre em `C:\Users\silvi\Downloads\PEGASUS_FULL_2026_RUNS\<MODO>_<yyyyMMdd_HHmmss_fff>_<PID>\RUN_LOG.txt`, **independentemente da pasta atual**; a instância elevada (UAC) usa a mesma pasta. O resultado é um `..._RESULT.zip` ao lado da pasta da execução — devolva-o a esta conversa.

## Estado honesto dos gates

| Gate | Estado |
|---|---|
| G1 vínculo de origem | PASS (V003 físico; entry testado=empacotado=entregue; caminho supervisionado e fronteira de exit fechados; binding QS4 BLOQUEADO provado) |
| G2 W04 full | Implementado; qualificado offline na decisão; **nativo pendente da campanha** |
| G3 W04 JIT/Job | Implementado; orquestração qualificada offline; **nativo pendente da campanha** |
| G4 SAFE_STOP/retomada | PASS offline (runtime real sintético); classificação de exit exata; **nativo pendente** |
| G5 Windows nativo integrado | Campanha pronta, **não executada**; bootstrap da fronteira de exit reescrito |
| G6 CANDIDATE_COMPLETENESS | **NOT_PASS** — único bloqueio externo: execução nativa da campanha no PC do titular |

Nenhum PASS foi declarado sem execução efetiva. `native_completeness_evaluation` no recibo de qualificação só reporta `MET` quando os casos nativos (W04 Q10a–f, Job Q11, ≥4 `PASS_NATIVE_SAME_ATTEMPT`, ≥3 `GAPLESS_NATIVE_JOB`) ocorrerem no Windows — fora dele, `NOT_MET`.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
