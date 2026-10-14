# TICKSTORE CDT15 R47: provas e gates que dependem legitimamente de execução ou decisão externa

Esta é a lista única e consolidada. Nada aqui é dispensado nem declarado PASS sem evidência. **Não há pedido de decisão pendente:** a opção A (LEGACY-ENTRY) foi implementada, e nenhum arquivo foi pedido ao titular, porque o ZIP instalado `4BC28843…` não é necessário (ver `RECERTIFICACAO_RC1R1.md` §4).

## A. Execuções nativas do titular (Windows, sem efeito produtivo)

| # | Execução | Script | Observação |
|---|---|---|---|
| A1 | Parser PS5.1 | `CHECK_PS51_SYNTAX.ps1` | somente leitura |
| A2 | R44D2 (admissão física de `D:` para a sandbox de qualificação) | `RUN_TICKSTORE_CDT15_R44D2_DROOT.ps1` | **Só se ainda não existir RETURN R44D2 nativo**; não repetir. Exige `D:\TICKSTORE_QUALIFICATION_SANDBOX` existente (sem ela, BLOCKED sem criar nada). Não roda os 126 IDs do R44 |
| A3 | **Campanha nativa R47 (G4)** | `RUN_TICKSTORE_CDT15_R47_QUAL.ps1` | Elevada. Roda os 126 IDs **sobre os bytes R47**, que mudaram, por isso a reexecução é legítima. Inclui as suítes S8–S21 (S19–S21: recertificação RC1R1, núcleo e MULTIWORK nativos, migração), o probe B2C e as 6 provas. SAFE_STOP: arquivo `STOP` na pasta RUN. Retomada: `-ResumeFrom <RETURN ZIP>` |
| A4 | B07 nativo | `RUN_TICKSTORE_CDT15_R47_B07.ps1` | **somente depois do B06 independente PASS** e da cadeia até B06 (procedimento, passos 4–6) |
| A5 | Migração do sucessor D4 (V002R22 → V002R23) | `RC1R1_SUCCESSOR_MIGRATION.py` (procedimento, passo 8b) | primeiro a simulação somente leitura; `--apply` só com a cadeia até B07; nunca apaga o V002R22 |

## B. Decisões e recibos exclusivos da origem ou de terceiros independentes

| # | Item | Responsável | Estado |
|---|---|---|---|
| B1 | Decisão G5 (`TICKSTORE_ORIGIN_STAGE_DECISION_V001`) | origem | Aguarda A3 e B4. O binder só materializa G5 sobre o RETURN ZIP nativo fechado de A3 (G11) |
| B2 | **B06 independente** sobre o FINAL R47 e o pacote de revisão V002R23 | revisor independente | NOT_STARTED |
| B3 | Decisão B07 | origem | aguarda A4 |
| B4 | **Prova física `CHECKPOINT_POWERLOSS_RECOVERY`** | laboratório separado, com autorização específica | `PHYSICAL_POWERLOSS_ENVIRONMENT_NOT_AVAILABLE=BLOCKED`. A ferramenta está completa. POWERLOSS_EMULATED não a substitui. **Nunca no PC produtivo** |
| B5 | Reconciliação operacional de política **contra a R41 ou revisão posterior** | origem | `NOT_ISSUED`. Necessária para D4 e estágios seguintes. A captura R40 empacotada não é autoridade (`R47_POLICY_RECONCILIATION_REQUEST.json`) |
| B6 | Revisão Stage B + `FULL_GO` | revisor/origem | depois de FULL_PREP |
| B7 | Execuções produtivas D4, D5, CANARY, FULL_PREP, FULL_ADMIT e FULL | titular, na sequência canônica e só após os gates | não iniciadas |
