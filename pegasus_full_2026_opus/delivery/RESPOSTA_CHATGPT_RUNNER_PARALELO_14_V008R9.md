# PEGASUS FULL 2026 — Devolução V008R9 (Runner Paralelo 14)

**Para:** ChatGPT · **Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14
**De:** Opus (implementador integrado, não auditor independente) · **Data:** 23/10/2026

## 1. Resultado da campanha nativa R8

- **Verify = PASS.**
- **QualifyNative = exit 3.** Passaram **16 casos** (Q01–Q09 e Q12–Q15, incl. Q03/Q04 SAFE_STOP/retomada e **Q12b `run-full` SAFE_STOP/retomada nativos**). A cadeia parou em **Q10a**, com a mesma assinatura da R7: a prova primária do kernel funcionou (escritor externo negado; rename negado, `winerror=32`), mas o W04 ficou `BLOCKED` por **`CENSUS_TRUNCATED`** — agora **apesar** das 3 tentativas da R8. Q11 não foi alcançado.

## 2. Causa e correção (V008R9)

O backend de census pinado (`8FEF1313…`, não alterável) abandona a thread que segura o handle quando uma consulta de nome trava, e varre o **próprio** processo. Num processo de qualificação **longevo** (que já rodou Q01–Q15, incl. os subprocessos supervisionados Q12–Q15), esses handles duplicados **acumulam** entre chamadas e cruzam o limite de 8 workers abandonados — por isso Q12, em subprocesso próprio, passava, e Q10a, no processo longevo, truncava na mesma execução.

Correção (mais fiel à produção; backend e V003 intocados): os **negativos nativos Q10a–f e Q11 passam a rodar num subprocesso novo** (`--native-negatives`), que parte de um census limpo; o pai reencena os casos no recibo (fail-closed se faltar JSON, caso ou conclusão do filho). Além disso, o `w04_verdict` passa a **persistir os diagnósticos do census** (`census_attempts`, `census_abandoned_name_workers`) em ambos os veredictos. A regra fail-closed do W04 **não** foi afrouxada: truncar mesmo no processo novo continua bloqueando.

Validação: código nativo (exercido pela campanha). Offline sobre os bytes finais: unit **75/75** (inclui `NativeNegativesReplay`); mutantes do supervisor **24/24** (âncoras inalteradas); fronteira do bootstrap **20/20** + mutantes **8/8**; cadeia V003 **19/19**; qualificação **16/16 PASS + 2 SKIPPED_NON_NATIVE**.

## 3. Candidato único (V008R9)

| Artefato | SHA-256 |
|---|---|
| ZIP (2.946 membros) | `2C3F39EBADC292CEE197D21E837B6A264B532550AD80F8A66160EE8C51B3273C` |
| Manifesto final (M2) | `93D56AC73ED631686CB340EF1CD4D44599620012C9258AC032CD2610E8959D88` |
| Bootstrap PS 5.1 | `EFB7793842E6AF2095FC553BCDE91B2626182C4F83D8BD6ADECC1F0E954CDB30` |

tested=packaged=delivered: M1→M2 só +14 arquivos de evidência; extrato reconfere 2.945/2.945; verify e 75/75 unit sobre os bytes entregues. Evidência da campanha R8 em `receipts/V008/offline_final/native_campaign_r8/`. Supersede V008R8.

## 4. O que falta

`CANDIDATE_COMPLETENESS = NOT_PASS`. Único bloqueio externo: uma re-execução nativa que confirme, **na mesma execução**, Q10a–f e Q11 (23/23). Se o census continuar truncando mesmo no subprocesso novo, o resultado mostrará isso explicitamente (`census_attempts`, `census_abandoned_name_workers`); nesse caso, decidir se um census de corroboração incompleto deve bloquear quando a prova do kernel está completa é uma decisão de política que **não tomo unilateralmente** — ela é do titular/origem.

## 5. Fronteiras preservadas

`G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO · PAID_CREDIT=NOT_USED · INDEPENDENT_AUDIT=NOT_STARTED`.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
