# Protocolo de prova física CHECKPOINT_POWERLOSS_RECOVERY: SOURCE_ONLY, não executar

**Estado:** `PHYSICAL_POWERLOSS_ENVIRONMENT_NOT_AVAILABLE=BLOCKED`. Nenhum laboratório isolado foi identificado e a origem não autorizou a execução.
**Base:** decisão da origem de 20261014 (`CDT15_ORIGIN_R44_G5_DECISION_V001`). `POWERLOSS_EMULATED`, TerminateProcess, Job Objects e power-off de VM **não** equivalem a esta prova.

## 1. Ambiente (pré-requisitos, todos obrigatórios)
- Computador Windows **separado** do PC produtivo. O preflight recusa qualquer máquina que exponha os volumes produtivos (seriais `C4B23CE5`/`7435A171`) ou os caminhos `D:\Base CSV` e `...\TICKSTORE\ACTIVE_DEPLOYMENT.json`.
- Volume NTFS **exclusivo e descartável**: letra diferente de C/D, sem pagefile, não é a unidade de sistema, rótulo contendo `TICKSTORE_POWERLOSS` e sentinela `TICKSTORE_POWERLOSS_SACRIFICIAL_VOLUME.txt` com o texto exato.
- Alimentação externamente isolável do host e do armazenamento (por exemplo, PDU comutável). Nunca puxar cabo SATA ou de alimentação de disco no PC produtivo.
- Registrador **externo** ao equipamento sob ensaio, declarado em `EXTERNAL_LOGGER_DECLARATION` (modelo abaixo). Registra o instante do corte, o instante do religamento, o identificador da rodada e o estado da alimentação.
- Inventário e backups verificados. A superfície de escrita física fica restrita ao volume descartável.

## 2. Autorização separada do titular
`USER_AUTHORIZATION` (modelo abaixo), cujo SHA-256 o operador informa à parte. O documento vincula o serial do volume do laboratório, declara `production_pc=false`, tem validade explícita e só pode ser emitido **depois** de o laboratório estar identificado e de o preflight físico e administrativo ser aprovado.

## 3. Plano semeado (`LAB_POWERLOSS.py plan --seed N`)
Janelas de transação: `PRE_COMMIT_WRITE`, `POST_COMMIT_PRE_CHECKPOINT` e `JOURNAL_RECEIPT_UPDATE`, com 3 repetições de corte por janela e 2 rodadas de controle sem interrupção. A ordem é embaralhada pela semente e o plano é amarrado por hash. O código e a configuração são os bytes congelados do candidato (`TESTED_CODE_EQUALS_PACKAGED_CODE` obrigatório). Os datasets são sintéticos e reproduzíveis pela semente.

## 4. Rodada
1. `preflight` deve dar PASS no próprio laboratório; caso contrário, BLOCKED.
2. `arm`: a carga de trabalho no volume descartável segura dentro da janela pedida e anuncia `READY_TO_CUT` (beacon com fsync).
3. O operador corta a alimentação externa; o registrador externo grava o instante.
4. Religamento controlado. **Antes de qualquer retomada**, executar `inspect`, que é somente leitura: bit dirty do NTFS, saídas, journals, locks, checkpoint, processos vivos e correlação com o registrador. Qualquer ambiguidade resulta em BLOCKED.
5. Retomada **pelo próprio produto**. Um reinício fail-closed (por exemplo, `WRITER_LOCK_EXISTS`) é aceito como `ROUND_FAIL_CLOSED` e a reconciliação segue o procedimento documentado.
6. `reconcile`: os contêineres devem ser byte a byte iguais aos do controle, sem perda, duplicação ou sobrescrita. Gerar o recibo da rodada (`TICKSTORE_PHYSICAL_POWERLOSS_ROUND_RECEIPT_V001`) com as evidências brutas fechadas.

## 4b. Comandos (ferramenta conectada; execução só no laboratório)
Todos exigem Windows e os bytes congelados do candidato (`--candidate-impl` = `implementation_v001` extraído do FINAL e `--code-manifest-sha256` do manifesto de runtime). Raiz do ensaio: `<VOL>:\TICKSTORE_POWERLOSS_LAB\<plan_sha[:16]>\<round_id>`.
- `arm`: reexecuta o `preflight` ao vivo, exige `plan_sha256` na autorização e liga o candidato byte a byte. Roda o motor MULTIWORK empacotado sobre a carga sintética semeada e anuncia `READY_TO_CUT`. Mantém um `BEACON.jsonl` com fsync a cada ~50 ms, que registra o estado observado e a janela classificada.
- `inspect` (somente leitura, antes de qualquer retomada): lê o beacon (o último registro pode estar rasgado), o bit dirty (`fsutil dirty query`), o estado de cada dia (`COMMITTED_VERIFIED`, `PARTIAL_UNCOMMITTED` ou `COMMIT_WITHOUT_MATCHING_BYTES`), os journals, o processo dono do lock e o registro do logger externo (com SHA informado à parte). Grava `INSPECTION.json`.
- `reconcile`: o **produto** retoma sozinho. Se ocorrer fail-closed por lock, aplica a reconciliação documentada somente se a inspeção provou que não há processo vivo. Em seguida, compara os contêineres byte a byte com um controle não interrompido da mesma semente e grava `ROUND_RECEIPT.json`. Janela planejada não atingida resulta em `ROUND_WINDOW_MISSED`.
- `aggregate`: cobertura por janela e status `PROPOSABLE_TO_ORIGIN` ou `INCOMPLETE`. Nunca é veredito G5.

## 5. Resultado
O agregado só pode ser proposto à origem se todas as rodadas forem PASS ou FAIL_CLOSED reconciliado, com evidência completa. O consumidor G5 continua sem executor aceito para esta prova até que a origem promova a regra e o tipo de recibo. O engenheiro não altera o contrato.

## 6. Sem laboratório isolado
O gate permanece bloqueado. Qualquer reinterpretação do requisito só pode ser uma candidata de política, nunca uma dispensa local.
