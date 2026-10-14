# TICKSTORE CDT15 R46: provas e gates que dependem legitimamente de execução ou decisão externa

Lista única e consolidada. Nada aqui é dispensado nem declarado PASS sem evidência.

## A. Execuções nativas do titular (Windows, sem efeito produtivo)

| # | Execução | Script | Observação |
|---|---|---|---|
| A1 | Parser PS5.1 | `CHECK_PS51_SYNTAX.ps1` | somente leitura; cobre todos os `RUN_TICKSTORE_CDT15_*.ps1` em Downloads |
| A2 | R44D2 (admissão física de `D:`) | `RUN_TICKSTORE_CDT15_R44D2_DROOT.ps1` | já admitido pela origem; `D:\TICKSTORE_QUALIFICATION_SANDBOX` deve existir; não roda os 126 do R44 |
| A3 | Campanha nativa R46 | `RUN_TICKSTORE_CDT15_R46_QUAL.ps1` | elevado; 126 IDs **sobre os bytes R46**, 11 suítes, probe B2C e 6 provas. Para pausar com SAFE_STOP, crie o arquivo `STOP` na pasta RUN. Para retomar, use `-ResumeFrom <RETURN ZIP>` |
| A4 | B07 nativo | `RUN_TICKSTORE_CDT15_R46_B07.ps1` | **somente depois de B06 independente PASS** e da cadeia até B06 (procedimento, passos 4–6) |

## B. Decisões e recibos exclusivos da origem ou de terceiros independentes

| # | Item | Responsável | Estado |
|---|---|---|---|
| B1 | Decisão G5 (`TICKSTORE_ORIGIN_STAGE_DECISION_V001`) | origem | aguarda A3 e B4 |
| B2 | **B06 independente** (recibo de estágio + veredito) | revisor independente | NOT_STARTED; não deve receber candidato incompleto |
| B3 | Decisão B07 | origem | aguarda A4 |
| B4 | **Prova física `CHECKPOINT_POWERLOSS_RECOVERY`** | laboratório separado, com autorização específica do titular | `PHYSICAL_POWERLOSS_ENVIRONMENT_NOT_AVAILABLE=BLOCKED`. A ferramenta está completa (`powerloss_lab/`). POWERLOSS_EMULATED não a substitui. **Nunca no PC produtivo** |
| B5 | Reconciliação operacional de política (`TICKSTORE_ORIGIN_POLICY_RECONCILIATION_V001`) | origem | `NOT_ISSUED`; necessária só para D4 e os estágios seguintes, perto do uso real. O probe negativo da campanha espera `NOT_ISSUED` |
| B6 | Revisão Stage B + `FULL_GO` | revisor/origem | depois de FULL_PREP |
| B7 | Execuções produtivas D4, D5, CANARY, FULL_PREP, FULL_ADMIT e FULL | titular, na sequência canônica e só após os gates | não iniciadas |

## C. Pedido único consolidado de decisão à origem

**LEGACY-ENTRY:** a CLI direta do RC1 aceitaria um Owner Gate administrativo FULL_SERIAL forjado. A engenharia completou o isolamento possível sem alterar o RC1 e confirmou que os dados não podem ser corrompidos por essa rota. Fechar o resíduo por código exige alterar o RC1. Isso, por sua vez, exige:
1. uma **nova release de recuperação reinstalada no PC produtivo**, porque o RC1 está embutido e autenticado no engine `BFC44DA9…`, admitido pelo D4 junto do ZIP instalado `4BC28843…`;
2. a redefinição da proveniência aceita para os 1399 dias já publicados.

Ambos são efeitos produtivos e decisões canônicas fora da autorização vigente. Peço que a origem escolha entre:
- **(A)** autorizar um ciclo próprio de recertificação do RC1: flags FULL_SERIAL e piloto em `False`, engine com proveniência histórica RC1 aceita, nova release e reinstalação controlada;
- **(B)** aceitar formalmente o resíduo de governança para a admissão produtiva.

Análise completa em `LEGACY_ENTRY_ISOLATION.md`. Até a decisão, `LEGACY_ENTRY=RESIDUAL_BLOCKS_PRODUCTION`.
