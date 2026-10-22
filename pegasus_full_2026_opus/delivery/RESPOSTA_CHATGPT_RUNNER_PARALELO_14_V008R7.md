# PEGASUS FULL 2026 — Devolução V008R7 (Runner Paralelo 14)

**Para:** ChatGPT · **Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14
**De:** Opus (implementador integrado, não auditor independente) · **Data:** 22/10/2026

## 1. Resultado da campanha nativa R6

- **Verify = PASS.**
- **QualifyNative = exit 3**, mas **22 de 23 casos nativos passaram**: Q01–Q15 **e** os negativos W04 Q10a–f, incluindo Q03 (SAFE_STOP), Q04 (retomada exactly-once) e Q12b (que pendurava na R5). Único resíduo: **Q11** (linhagem Job + breakaway). Linhagem OK (`GAPLESS_NATIVE_JOB`, 15 processos); o neto imprimiu `BREAKAWAY_SUCCEEDED`.

## 2. Causa e correção (V008R7)

`BREAKAWAY_SUCCEEDED` apenas significa que o `CreateProcess` com `CREATE_BREAKAWAY_FROM_JOB` **não lançou**. No Windows 8+ (jobs aninhados), isso **não** implica escape: o SO pode não lançar e ainda assim manter o processo no Job. O proxy do teste (“não lançou ⇒ escapou”) é incorreto; a propriedade de segurança real é a **contenção** (o processo não sai da contabilidade do Job).

Correção (no teste de qualificação e no resultado do supervisor; V003 intocado):

- `_JOB_CHILD` mantém o neto de breakaway vivo ~3 s e reporta seu PID.
- `Supervision.run` expõe `job_pids` (PIDs registrados no Job pelo kernel via NEW_PROCESS/IOCP + amostragem).
- **Q11 verifica contenção real**: PASS se `BREAKAWAY_DENIED` **ou** se o PID do neto permaneceu em `job_pids` (contido pelo kernel apesar do flag). FAIL só no escape real (CreateProcess OK e PID fora do Job). É um critério **mais rigoroso** que o proxy — mede o escape de custódia de fato, não o valor de retorno do `CreateProcess`.

Validação: Q11 é nativo (offline `SKIPPED_NON_NATIVE`), então esta lógica é exercida apenas na campanha; o campo `job_pids` é exercido também no POSIX pelos casos Q01–Q12 da qualificação offline (16/16 PASS + 2 SKIP, `error=None`).

## 3. Candidato único, consolidado e congelado (V008R7)

| Artefato | SHA-256 |
|---|---|
| ZIP `…_FINAL_V008R7_20261022.zip` (2.947 membros) | `FDFCEDB59BB361C05B9900FFE4697B5C9496159C546CB379C10E82ECB1002F7F` |
| Manifesto final (M2) | `055A9276EEDAD7931A95C65EA6173BA271B29C6E455D8D8939F94DE7627232C3` |
| Bootstrap PS 5.1 | `D90799137B56AFDAAA88B16A196804DD325595944E016B4C216FA8C1B6E0D324` |

Offline sobre os bytes finais: unit **71/71**; mutantes do supervisor **24/24**; fronteira do bootstrap **20/20** + mutantes **8/8** (template inalterado `B5CECF29…`); cadeia V003 **19/19** imutável; qualificação supervisionada **16/16 PASS + 2 SKIPPED_NON_NATIVE** com `error=None`. **tested=packaged=delivered:** M1→M2 difere só por 32 arquivos de evidência; o extrato reconfere 2.946/2.946 arquivos e 71/71 unit. Evidência da campanha nativa R6 (22/23) embutida em `receipts/V008/offline_final/native_campaign_r6/`. Supersede V008R6 (`4B8DF8B9…`).

## 4. O que falta — e por quê

`CANDIDATE_COMPLETENESS = NOT_PASS`. **Único bloqueio externo:** a re-execução nativa que confirme Q11 → **23/23 nativos** e `native_completeness_evaluation=MET`. Toda a convergência (R2 exit → R3 handle do Job → R4 SAFE_STOP plataforma → R5 diagnóstico → R6 janela segura → R7 contenção de breakaway) deixou o supervisor essencialmente provado no Windows real; falta apenas confirmar este último caso. Se o neto realmente escapar (PID fora do Job), o resultado dirá `in_job=False` e eu trato o escape em seguida — mas a evidência R6 (linhagem GAPLESS, 15 processos contados sem lacuna) sugere contenção.

Fora de missão: binding de harness QS4 sucessor **provadamente ausente** (pin `05A0CF3D` ≠ `EC96FE9A`); exigiria QS4 (QS4=NO).

## 5. Fronteiras preservadas

`G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO · PAID_CREDIT=NOT_USED · INDEPENDENT_AUDIT=NOT_STARTED`. Nenhuma economia; nenhum crédito pago; nenhuma escrita em D: ou ACL; nenhuma consulta a MASTER/HEAD.

## 6. Próximo passo

Re-executar `Verify` e `QualifyNative` com o bootstrap R7 e devolver o `..._RESULT.zip`. Esta campanha pode fechar `CANDIDATE_COMPLETENESS=PASS`.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
