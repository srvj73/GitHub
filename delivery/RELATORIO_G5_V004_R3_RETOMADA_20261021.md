# CDT21 — G5 V004 R3: retomada determinística da mesma campanha V004

**Papel:** implementador. Este documento não é parecer B06.
- MASTER/HEAD não foi consultado.
- A B06 independente continua reservada ao Work da irmã do titular.

## 1. Pendência da origem — confirmada

O R2 removeu o modo de retomada e recusava qualquer `REUSE_COMMITTED`. Uma campanha V004 interrompida por SAFE_STOP, por queda abrupta ou durante o fechamento perderia as unidades já comprometidas e teria de recomeçar.

**Contrato congelado do V004 (mesmos bytes do V003 para a máquina G5):**

| Elemento congelado | O que estabelece |
|---|---|
| `PRE_G06_CAMPAIGN.run_unit` | reutiliza o COMMIT da **mesma raiz** quando: fechado (PASS, exit 0, sem descendentes); com artefatos; com `package_sha256` e `code_sha256` iguais aos da execução; com cada artefato re-hasheado. Senão, recusa com `COMMITTED_UNIT_NOT_CLOSED`, `COMMITTED_INPUT_DRIFT` ou `PHYSICAL_REF_DRIFT` |
| `test_cdt19_native_campaign_contract` | `test_committed_same_bytes_reused` e `test_cross_package_commit_cannot_be_rebound` |
| `main` | reentrante |
| `run_unit` | arquiva tentativas interrompidas em `INTERRUPTED_ATTEMPTS` |
| `seal_return` | “retomada verificada no mesmo pacote” |
| `PRE_G06_COMPLETENESS` | preserva `FINAL_G5` anterior, completo ou interrompido, “sem replay de testes nativos” |

**Conclusão contratual:** a retomada da mesma campanha V004 é **aplicável e necessária**. A reutilização de COMMITs de outro candidato (V003) ou de outra campanha permanece **proibida**.

## 2. Correção — supervisor R3 (`2765FAAAC4725F5925921E25B93E145D3719EFC686BDFD7511A110440B0A1DAD`)

O R3 é derivado do R2 (`2A5F4B71…`) por substituições contadas. Ignorando espaços em branco, saem 16 linhas, todas assinaturas ou textos substituídos.

**Campanha nova:** comportamento do R2 preservado literalmente. Raiz e laboratório novos (sem `exist_ok`), `NEW_RUN_REUSED_A_COMMIT`, `COMMITTED_NOW_NE_PLAN`, correção NTFS e evidência por entrada continuam iguais.

**Acréscimo — prova de “mesma campanha”:** o livro-razão `CDT21_SUPERVISOR_LEDGER/<chave>.json`. Quando o **próprio filho de campanha** do supervisor imprime `COMMITTED <chave>`, o supervisor grava o SHA do arquivo de COMMIT, o `run_id`, a tentativa e o SHA do supervisor. O registro é escrito em `TEMP`, fora do selo congelado, e movido atomicamente. O livro-razão é selado no `R08_RETURN` e vai no retorno externo.

**Retomada (`--resume-root`):** a Fase Q, somente leitura, admite a raiz só se todas as condições abaixo valerem:
1. **Local:** a raiz está em `LOCALAPPDATA\CDT20_R08\R08_Q1_<14>_<12 hex>`, sem link nem junction.
2. **Bootstrap:** escrito **por este supervisor** (mesmo SHA), em modo `NEW_RUN_V004`, com pacote, código, manifesto, campanha e fechamento do V004, `v003_commits_reused = 0` e livro-razão declarado.
3. **Identidade:** dono da raiz, dono do laboratório D:, testemunha e pacote de `INPUTS` idênticos aos do V004.
4. **COMMITs:** cada COMMIT está no plano; não é do V003; está fechado e vinculado ao V004; tem artefatos re-hasheados e dentro da raiz; e **consta do livro-razão com o mesmo SHA**. Também não pode haver registro sem COMMIT.
5. **Estado anterior:** `SAFE_STOP`, `BLOCKED`, `PASS` do `main` (fechamento interrompido) ou ausente (queda). Vínculos presentes têm de coincidir.
6. **Processos e lock:** os processos anteriores estão mortos (`R.dead` congelado) e o `CAMPAIGN.lock` está livre.

**A fase E:**
- repete a admissão e exige o mesmo conjunto de COMMITs da Q;
- adquire o lock;
- preserva o terminal anterior (copiado; o `SAFE_STOP.request` é movido para `INTERRUPTED_ATTEMPTS/PRIOR_TERMINAL_<stamp>`);
- registra `CDT21_SUPERVISOR_RESUME_<stamp>.json` e executa a campanha congelada.

**Ao final, a fase E exige:**
- reutilizadas ⊆ admitidas;
- nenhuma unidade recomitida;
- reutilizadas + novas = plano de 38;
- 38 COMMITs vinculados ao V004 e todos no livro-razão;
- somente a raiz retomada e seu laboratório alterados, nenhuma raiz nova;
- `D:\Base CSV` inalterado.

## 3. Executor único integrado — `RUN_CDT21_G5_V004_R3_20261021.ps1`

**SHA-256:** `B68494D29563702592C867051FC94BDCE72A7A496AF006A691AC8CFB522D6E39` (117.097 bytes).

| Modo | Comando |
|---|---|
| Nova campanha (igual ao R2) | `powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\Downloads\RUN_CDT21_G5_V004_R3_20261021.ps1" -AutorizoLabD` |
| Retomada da mesma campanha (raiz informada pelo supervisor na linha `RETOMADA_DA_MESMA_CAMPANHA`) | `powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\Downloads\RUN_CDT21_G5_V004_R3_20261021.ps1" -AutorizoLabD -RetomarRaiz "<raiz>"` |

- O launcher valida `-RetomarRaiz` antes de qualquer chamada, repassa o valor ao filho UAC e entrega `--resume-root` às fases Q e E.
- Classificação R1, revisão `E84E5C39…`, caminhos, log (`C:\Users\silvi\Downloads\CDT21_G5_V004_RUNS\G5V4_<carimbo>\`) e retorno estão inalterados.
- Parser com 0 erros, ASCII e CRLF.
- Substitui os launchers `54C5ED19…`, `E3F83D0A…` e `8CC1ACB6…`.

## 4. Condição de retomada — comprovada (Linux, `main()` real do R3)

Rodam de verdade: as fases Q e E do R3, extração, `verify_package` e plano congelados, o **`run_unit` congelado na reutilização**, `write_terminal` e `seal_return` congelados, digests, livro-razão, preservação e retorno.

Foram substituídos, e isso está registrado no resultado:
- guarda de plataforma, administrador, NTFS, Job e lock (via flock);
- censo `R.dead`;
- b2d nativo, já provado nativamente;
- execução de unidade **nova** (dublê no formato congelado);
- `PRE_G06_COMPLETENESS.close` (dublê que preserva o `FINAL_G5` anterior como o congelado).

| Cenário | Resultado |
|---|---|
| Campanha nova | PASS; 38 novas, 0 reutilizadas, 38 registros |
| SAFE_STOP após 5 → retomada | PASS; **exatamente as 5** reutilizadas, 33 novas, 2 tentativas no livro-razão; terminal preservado, pedido consumido, recibo de retomada no retorno |
| Queda abrupta (sem terminal) → retomada | PASS; 3 reutilizadas, 35 novas; unidade interrompida preservada |
| Dois SAFE_STOP → retomada | PASS; 3 tentativas |
| Fechamento interrompido após PASS → retomada | PASS; 38 reutilizadas, 0 novas; `FINAL_G5` anterior preservado |

**Recusas, todas antes de qualquer efeito na raiz (Fase Q):**

| Situação | Código |
|---|---|
| COMMIT do V003 | `RESUME_COMMIT_BOUND_TO_V003` |
| COMMIT de outro candidato | `RESUME_COMMIT_NOT_BOUND_TO_V004` |
| **COMMIT de outra campanha V004, com os mesmos bytes e artefatos íntegros** | **`COMMIT_NOT_LEDGERED`** |
| Livro-razão adulterado | `LEDGER_DRIFT` |
| Artefato adulterado | `RESUME_COMMIT_ARTIFACT_DRIFT` |
| Registro sem COMMIT | `LEDGER_WITHOUT_COMMIT` |
| Chave fora do plano | `RESUME_FOREIGN_COMMIT` |
| Raiz de outro supervisor | `RESUME_BOOTSTRAP_BINDING` |
| Raiz do V003 | `RESUME_BOOTSTRAP_BINDING` |
| Raiz fora de `CDT20_R08` | `RESUME_ROOT_LOCATION` |
| Lock em uso por processo vivo | `campaign_lock_free` |
| Processo anterior vivo | `OWNER_OR_CHILD_LIVE` |

**Recusas na fase E:**

| Situação | Código |
|---|---|
| Q de campanha nova usada para retomada | `QUALIFICATION_OTHER_RUN` |
| Q da raiz A usada para a raiz B | `QUALIFICATION_OTHER_RUN` |
| Raiz alterada entre Q e E | `FOREIGN_ROOTS_CHANGED_SINCE_QUALIFICATION`, com evidência por entrada |
| Campanha nova que vê `REUSE_COMMITTED` | `NEW_RUN_REUSED_A_COMMIT` |
| Outra raiz alterada durante a retomada | `FOREIGN_ROOT_CHANGED`, com evidência por entrada |

**Total: 28/28.**

**Mutantes do R3:** **7/7 mortos.** Cada enfraquecimento da admissão é detectado exatamente no caso que o protege:

| Mutante | Enfraquecimento | Detectado em |
|---|---|---|
| M1 | sem checagem do livro-razão | N03, N04, N06 (COMMIT de outra campanha V004 passaria) |
| M2 | sem checagem específica do V003 | N01 (o vínculo ao V004 ainda recusa: defesa em profundidade) |
| M3 | bootstrap de qualquer supervisor | N08 |
| M4 | campanha nova aceita `REUSE_COMMITTED` | N15 |
| M5 | retomada com a regra de raízes da campanha nova | S2c, S3b, S4, S5b |
| M6 | pedido de SAFE_STOP não consumido | S2c, S2d, S2e, S4 |
| M7 | sem checagem de processos anteriores | N12 |

**Launcher, fragmentos verbatim: 8/8.**
- Sem retomada, não há argumento de retomada.
- Com raiz válida, `--resume-root` chega às fases Q e E.
- Fora de `CDT20_R08`, hex maiúsculo, raiz inexistente, nome inválido ou sem `LOCALAPPDATA`: recusa antes de qualquer chamada.
- O filho UAC recebe a raiz intacta, mesmo com espaços, e a repassa.

**Regressões:**
- Correção NTFS do R2: todos os casos de comportamento passam no R3. As checagens de composição e conjunto de códigos mudam por construção.
- Validação V004: 37/41. As 4 diferenças são checagens da decisão anterior “sem retomada”, invertidas pela auditoria. As proteções equivalentes estão provadas em N09, N13 e N15.

**Não repetidos, por não serem afetados:** G0, b2d nativo, classificação R1 e qualificação NTFS nativa.

## 5. Resíduos declarados (falha fechada)

- **COMMIT publicado e não registrado:** se a máquina cair nos milissegundos entre a publicação de um COMMIT e seu registro no livro-razão, a retomada dessa raiz é recusada (`COMMIT_NOT_LEDGERED`) e é necessária campanha nova. Nunca se reutiliza COMMIT sem prova de origem.
- **Mesmo supervisor:** a retomada exige o mesmo supervisor que criou a raiz.
- **Ambiente Windows:** lock, Job e `R.dead` reais são exercidos na campanha nativa. A Fase Q de uma retomada os verifica antes de qualquer efeito.

## 6. Arquivos

| Arquivo | SHA-256 |
|---|---|
| `RUN_CDT21_G5_V004_R3_20261021.ps1` | `B68494D29563702592C867051FC94BDCE72A7A496AF006A691AC8CFB522D6E39` |
| `CDT21_G5_V004_R3_RETOMADA_EVIDENCE_20261021.zip` | `017A987AD8A81B87F9FCB42D5EA8EA4D17AEF922FCF3BF5624088C4C2108BD06` (164.139 bytes, 27 membros, `MANIFESTO.json` `32CF17AD…0CDB`) |
| `WITNESS_CDT21_G5_V004_R3_20261021.json` | registrado no commit |
| `RELATORIO_G5_V004_R3_RETOMADA_20261021.md` (este) | registrado no commit |

## 7. Preservado e não executado

| Item | Situação |
|---|---|
| V004 `AD334869…99DD` e código `D2C626FD…66FF` | intactos |
| Revisão `E84E5C39…` | intacta |
| Correção NTFS R2 e classificação R1 | intactas |
| Evidências aprovadas | intactas |
| G0 | não repetido |
| Campanha G5 | não executada |
| B06 (independente), B07, D4/D5, canário, FULL e produção | não iniciados |

RESULT_RETURN_TO=ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compressão De Ticks 21
