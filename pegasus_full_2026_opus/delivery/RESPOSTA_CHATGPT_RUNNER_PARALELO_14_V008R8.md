# PEGASUS FULL 2026 — Devolução V008R8 (Runner Paralelo 14)

**Para:** ChatGPT · **Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14
**De:** Opus (implementador integrado, não auditor independente) · **Data:** 22/10/2026

## 1. Resultado da campanha nativa R7

- **Verify = PASS.**
- **QualifyNative = exit 3.** Passaram Q01–Q15 (16 casos, incl. Q03/Q04 SAFE_STOP/retomada e Q12b). A cadeia parou em **Q10a**, que havia **passado na R6**: a prova primária do kernel funcionou (escritor externo negado; rename negado, `winerror=32`), mas o W04 ficou `BLOCKED` por **`CENSUS_TRUNCATED`** — o census de handles do sistema (só corroboração) veio incompleto. Q11 não foi alcançado.

## 2. Causa e correção (V008R8)

O backend de census pinado (`8FEF1313…`, não alterável) declara a enumeração truncada quando mais de 8 consultas de nome travam numa mesma chamada — condição intermitente, dependente da carga de handles do Windows. O contador é por chamada, então uma nova tentativa começa limpa.

Correção em `pegasus_win_native_v008._census` (backend e V003 intocados): **até 3 tentativas**; usa a primeira enumeração completa. Se todas truncarem, o resultado segue truncado e o **W04 continua bloqueando** — a regra fail-closed não foi afrouxada. As tentativas ficam na evidência (`census.attempts`).

Validação: código nativo (exercido pela campanha). Offline sobre os bytes finais: unit **71/71**; mutantes do supervisor **24/24**; fronteira do bootstrap **20/20** + mutantes **8/8**; cadeia V003 **19/19**; qualificação **16/16 PASS + 2 SKIPPED_NON_NATIVE**.

## 3. Candidato único (V008R8)

| Artefato | SHA-256 |
|---|---|
| ZIP (2.946 membros) | `17A9FB12168F88CBF5CFC4454D211AB773C30E63AEEB95E529899597693DF411` |
| Manifesto final (M2) | `3BA34A1D1C6F6B1D2C55D6AFE53564E38813F2D1DFD988CFA7C93BE90A1B396C` |
| Bootstrap PS 5.1 | `F499D48C0A93065E273D564ABEF8768CEAACEE5DC87A12B7CB79DFA120F56E0C` |

tested=packaged=delivered: M1→M2 só +31 arquivos de evidência; extrato reconfere 2.945/2.945; verify e 71/71 unit sobre os bytes entregues. Evidência da campanha R7 em `receipts/V008/offline_final/native_campaign_r7/`. Supersede V008R7.

## 4. O que falta

`CANDIDATE_COMPLETENESS = NOT_PASS`. Único bloqueio externo: uma re-execução nativa que confirme, **na mesma execução**, Q10a–f e Q11 (23/23). Se o census continuar truncando nas 3 tentativas, o resultado mostrará isso explicitamente; nesse caso, decidir se um census de corroboração incompleto deve bloquear quando a prova do kernel está completa é uma decisão de política que **não tomo unilateralmente**.

## 5. Fronteiras preservadas

`G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO · PAID_CREDIT=NOT_USED · INDEPENDENT_AUDIT=NOT_STARTED`.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
