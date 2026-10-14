# TICKSTORE CDT15: retorno do engenheiro à decisão da origem R44/G5 (20261014)

**RESULT_RETURN_TO:** ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compressão De Ticks 15
**Handoff recebido:** `HANDOFF_OPUS55_CDT15_R44_G5_ORIGIN_DECISION_20261014.zip`, SHA `01F1CE07…`. Manifesto 4/4 conferido; a captura R40 é idêntica (MASTER `695DCD64…`, HEAD `B3B41959…`).
**PAPEL:** ENGINEER_ONLY. Nenhum gate emitido; G5=INCOMPLETE; B06/B07 NOT_STARTED; FULL_STARTED=NO; PRODUCTION_MODIFIED=NO; nenhum corte de energia.

## 1. Bytes físicos para reconciliação (em `PHYSICAL/`, sem reexecução)
| Arquivo | SHA-256 |
|---|---|
| QUAL_RETURN_R44_QUAL_20261014_065214_300_41492.zip (RETURN nativo R44) | 02036B1EA45370BE570865E281F8F5FC4C5D1C5364171680E2EE493EC7C5BB6D |
| TICKSTORE_CDT15_R44_G5_EVIDENCIA_NATIVA_RETORNO_ORIGEM_20261014.zip (pacote G5) + testemunha | 2B96E0619619A4B62278FF6313A97A40C78A37BCF68614B51A3BD7461E2C3695 |
| TICKSTORE_CDT15_R44_B2_RETORNO_ORIGEM_20261014.zip (pacote B2) + testemunha | BF87A341CD0DAFECDA6F11EFDCA6A14E219DD6282271254DB2C6F05B7B5FB22D |
| R44 RUN_LOG.txt | ver MANIFEST_SHA256.json |

O pacote G5 contém em `INPUTS/` o próprio RETURN R44 e o FINAL `0FBB6C36…`. Todos os hashes também constam de `MANIFEST_SHA256.json`.

## 2. G5
Mantido INCOMPLETE. O único bloqueio é `CHECKPOINT_POWERLOSS_RECOVERY`. Nenhum recibo PASS e nenhuma alteração de contrato. `POWERLOSS_EMULATED` permanece separado e não substitui a prova.

## 3. R44-DROOT-01: delta, sem repetir os 126
- **Causa-raiz:** no R44, o bootstrap validava LOG_ROOT e LOCALAPPDATA contra reparse, mas **não** `D:\TICKSTORE_QUALIFICATION_SANDBOX`; o driver também não validava esse diretório.
- **Correção para os próximos runners:**
  - bootstrap: `NoReparseBelow` mais `FinalPath==DParent` antes de usar o D:;
  - driver: `SANDBOX_ADMISSION.admit_root` (nenhum componente reparse, caminho final igual ao próprio caminho, NTFS e identidade volume/arquivo) antes de qualquer escrita, e `revalidate` no POSTCHECK.
- **Runner R44D** (para o titular), com elevação:
  - auditoria somente leitura da topologia usada pelo R44: raiz D:, diretório de execução D:, raiz de trabalho C:, censo de reparse dentro da árvore D: do R44 e data de criação;
  - sondas negativas nativas em diretórios privados no C: e no D: (este só se a raiz D: for admitida): junction, symlink de diretório e de arquivo, ancestral junction, arquivo, raiz ausente, caminho relativo e troca da raiz por junction ou por outro diretório.
  - Os bytes FINAL do R44 não são tocados.
  - **Limitação declarada:** a evidência é posterior ao fato; observa a topologia no momento da auditoria, não no instante da execução R44.

## 4. Queda física de energia: SOURCE_ONLY (`POWERLOSS_LAB/`)
- Protocolo detalhado conforme os 6 pontos da origem.
- `LAB_POWERLOSS.py`:
  - **preflight**: recusa o PC produtivo (seriais `C4B23CE5`/`7435A171` e caminhos produtivos), volume de sistema, volume com pagefile, letras C/D, volume sem rótulo ou sentinela de descarte, falta de registrador externo e falta de **autorização separada do titular** vinculada ao serial do volume do laboratório e com validade;
  - plano semeado (3 janelas × 3 repetições + 2 controles);
  - classificadores de inspeção pós-religamento e de reconciliação, em que qualquer ambiguidade resulta em BLOCKED;
  - `arm`, `inspect` e `reconcile` **não ligados**.
- Modelos de autorização, de declaração do registrador e de recibo de rodada. Testes 9/9.
- **`PHYSICAL_POWERLOSS_ENVIRONMENT_NOT_AVAILABLE=BLOCKED`**: nenhum laboratório isolado foi identificado.

## 5. B2C: fixtures aprovadas (não reeditadas) e integração
- **Correção de escopo:** a revogação dos caminhos legados que eu havia posto em `full/tickstore_serial_runner.py` foi **retirada**. Esse arquivo é o núcleo congelado RC1 (`D3A15572…`, `CORE_RC1_FROZEN`, fixado em `test_full_multiwork` e `static_multiwork_preaudit`). Os caminhos legados FULL_SERIAL, piloto e full-history continuam no código histórico, inalcançáveis pelo FULL_RUNNER: é **risco residual para decisão da origem** (pôr os lançadores legados em quarentena no empacotamento ou aceitá-los como históricos).
- **Prontidão portátil da árvore mesclada** (R44 + B2C + B2D + B07, com as quatro sobreposições aprovadas, inclusive as fixtures B2C `E74F3701…` e `40B396FC…`):
  - 106/106 IDs portáteis;
  - testes do pacote: 272 OK;
  - `test_full_multiwork` e `test_full_serial_r9` OK;
  - pré-auditoria estática: PASS.
- `R45_INTEGRATION_PLAN.md`: qualificação nativa necessária (os 126 sobre os novos bytes, as provas G5 refeitas e as provas B2C específicas).
- **Insumo pedido à origem:** um registro real de reconciliação de política emitido pela origem, de validade curta. Sem ele, a prova B2C nativa fica BLOCKED; o engenheiro não fabrica reconciliação.

## 6. B07: SOURCE_ONLY (`B07/`)
- `B07_TECHNICAL_PRODUCER.py`:
  - gera o `TICKSTORE_B07_TECHNICAL_RECEIPT_V001` no formato que o consumidor D4 lê;
  - usa as mesmas verificações físicas do consumidor G5 sobre o RETURN B07 fechado e o FINAL;
  - exige o veredito B06 independente, com SHA informado à parte, `INDEPENDENT_REVIEW=YES` e 0 achados críticos ou maiores;
  - exige a captura de política verificada;
  - exige um recibo tipado por check, cobrindo os 10 B07_CHECKS (testes nativos exatos, sondas e artefatos).
  - Nunca emite o recibo de **estágio** B07; esse só vem de uma decisão da origem materializada pelo B2D.
- `B07_CHECK_RUNNERS.py`: a única porta de entrada é o `FULL_RELEASE_CHAIN.ReleaseChain(..., until='B06')` de produção. Sem B06 PASS, bloqueia.
- Testes 7/7. **Nada executado.**

## 7. Próximos passos
1. Titular: executar o R44D e devolver o RETURN.
2. Se o R44D passar: construir o R45 (integração e qualificação nativa), mediante o insumo de reconciliação da origem.
3. G5 continua bloqueado pela prova física de queda de energia. Não encaminhar candidato incompleto ao B06.
