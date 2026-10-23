# PEGASUS FULL 2026 — ENTREGA DE ENGENHARIA V008R9 (Opus, 23/10/2026)

**Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14 · **Papel:** implementador integrado (não auditor independente).

## O que mudou da R8 para a R9

Na campanha nativa R8 a cadeia avançou **16 casos** (Q01–Q09 e Q12–Q15, todos PASS, incluindo Q12b `run-full` SAFE_STOP/retomada) e parou de novo em **Q10a** — com a mesma assinatura da R7: a prova primária do kernel funcionou (escritor externo negado; rename negado com `winerror=32`), mas o veredito W04 ficou `BLOCKED` por `CENSUS_TRUNCATED`, agora **apesar** das 3 tentativas da R8. A nova tentativa limitada não bastou.

Causa-raiz precisa (sem alterar o backend pinado `8FEF1313…`): o backend de census enumera **todos** os processos, inclusive o próprio, e, quando uma consulta de nome trava, **abandona a thread que segura o handle** (não fecha, não faz join). Num **processo de qualificação longevo** — que já rodou Q01–Q15, incluindo os subprocessos supervisionados Q12–Q15 — esses handles duplicados acumulam entre chamadas, até cruzar o limite de 8 workers de nome abandonados e declarar truncamento. Por isso Q12 (em subprocesso próprio) passava e Q10a (no processo longevo) truncava **na mesma execução**.

**Correção R9** (mais fiel à produção, onde cada execução supervisionada é um processo próprio; backend e V003 intocados):

- **Negativos nativos em subprocesso novo:** os casos Q10a–f e Q11 passam a rodar num processo `-I -B` recém-criado (`pegasus_qualify_v008.py --native-negatives`), que parte de um census limpo. O filho coleta os casos e grava `NATIVE_NEGATIVES_RESULT.json`; o pai reencena cada caso no recibo e levanta na primeira falha. Fail-closed reforçado: sem JSON, faltando qualquer caso nativo esperado, ou sem conclusão do filho, o pai levanta (nunca PASS silencioso).
- **Observabilidade do census:** o `w04_verdict` passa a registrar `census_attempts` e `census_abandoned_name_workers` (início/fim) em **ambos** os veredictos (PASS e BLOCKED). O truncamento deixa de ser opaco.

A regra fail-closed do W04 **não** foi afrouxada: um census que trunque mesmo num processo novo continua **bloqueando** o W04.

### Bytes finais (fora do ZIP)

| Artefato | SHA-256 |
|---|---|
| ZIP `…_FINAL_V008R9_20261022.zip` (2.946 membros) | `2C3F39EBADC292CEE197D21E837B6A264B532550AD80F8A66160EE8C51B3273C` |
| Manifesto final (M2) | `93D56AC73ED631686CB340EF1CD4D44599620012C9258AC032CD2610E8959D88` |
| Manifesto testado (M1) | `7B85DA44B5435106E428960FFB33F8F14C4F0B248C030BE33536494E9BC24CD4` |
| Bootstrap `BOOTSTRAP_…_V008R9_PS51.ps1` | `EFB7793842E6AF2095FC553BCDE91B2626182C4F83D8BD6ADECC1F0E954CDB30` |
| Entry `CODE/pegasus_entry.py` | `F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB` |

**tested=packaged=delivered:** M1→M2 difere só por 14 arquivos de evidência sob `receipts/V008/offline_final/`; código e docs byte-idênticos. O extrato reconfere 2.945/2.945 arquivos; verify e 75/75 unit passam sobre os bytes entregues. Supersede V008R8 (`17A9FB12…`).

## Re-execução — a mesma campanha única (bootstrap R9)

A partir de `PS C:\Users\silvi>`, com o ZIP e o bootstrap R9 em `C:\Users\silvi\Downloads`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R9_PS51.ps1 -Mode Verify
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R9_PS51.ps1 -Mode QualifyNative
```

Esta campanha precisa confirmar, numa mesma execução, Q10a–f (W04 nativo) e Q11 (contenção de breakaway). Se tudo passar, a `QualifyNative` termina com exit 0 e `native_completeness_evaluation=MET`. Devolva o `..._RESULT.zip`. Se o census ainda truncar no processo novo, o resultado mostrará `census_attempts` e `census_abandoned_name_workers`, e aceitar corroboração degradada com a prova de kernel completa é decisão de política do titular/origem.

## Estado honesto dos gates

| Gate | Estado |
|---|---|
| G1 | PASS |
| G2 W04 full | Q10a–f nativos PASS na R6; negativos em processo novo (R9); confirmar na re-run |
| G3 W04 JIT/Job | 22/23 nativos PASS na R6; Q11 contenção real (R7) pendente de execução nativa |
| G4 SAFE_STOP/retomada | Q03/Q04 nativos PASS (R6); Q12b `run-full` nativo PASS (R8) |
| G5 Windows nativo | re-run para confirmar 23/23 numa mesma execução |
| G6 CANDIDATE_COMPLETENESS | **NOT_PASS** — único bloqueio externo: re-execução nativa |

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
