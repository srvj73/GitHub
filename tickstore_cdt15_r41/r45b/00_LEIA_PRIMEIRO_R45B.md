# TICKSTORE CDT15 — R45B: correção de B07-PROVENANCE-01 e B07-ORDER-01

Papel: ENGINEER_ONLY. Nenhuma alteração produtiva, FULL, B06, execução B07, corte de energia ou crédito pago adicional.
O escopo é restrito aos dois bloqueios apontados pela origem. RC1, o FINAL R44, o FINAL R45, as quatro derivações de fixture aprovadas e a quarentena das entradas legadas estão preservados.

## Patches mínimos (pai → derivado)

| Arquivo | Pai R45 | Derivado R45B |
|---|---|---|
| `candidate/control/B07_TECHNICAL_PRODUCER.py` | `A7F8E9DF6E60904865A4E4E02F63B04E937BCD75253793467B6A8062E3D6F199` | `79FC375B0F7091DBFBC8BCDDDBE16A6927C724897862C78CD01F301272FE0272` |
| `tests/test_b07_technical_producer.py` | `6DC34B0689DC32E44069321EB5DF4EFB1F96BE059F34EB6C7CFB06B7C8AF15D6` | `68C9803555342D0E90EFFE2BB0BD5CA7FC93B56DFD7840BED011A7F813D88FA3` |

Nenhum outro arquivo de runtime mudou. `FIRST_ADMISSION_BINDING.json`, `POLICY_CAPTURE_BINDING.py`, `D4_FIRST_ADMISSION_*` e RC1 estão byte-idênticos ao R45. O delta físico entre os FINAL R45 e R45B está em `R45B_VS_R45_FINAL_FILE_DELTA.json`.

### B07-PROVENANCE-01
- `build()` não aceita mais `policy_capture`. Recebe `policy_root`, `policy_reconciliation` e `policy_reconciliation_sha256`, este último fornecido separadamente pelo operador.
- A nova função `verify_policy` faz, nesta ordem:
  1. carrega `POLICY_CAPTURE_BINDING` pelo leitor selado `D4_FIRST_ADMISSION_PREP.Reads`, admitido somente pelo digest de `FIRST_ADMISSION_BINDING.json`;
  2. executa `verify_capture` sobre os bytes físicos da captura e do registro de reconciliação;
  3. revalida as leituras.

  Em Windows, as leituras usam handles Win32 que negam escrita e exclusão. Fora do Windows o recibo nunca é PASS (`POLICY_CAPTURE_READ_NOT_NATIVE_PROTECTED`).
- O campo `policy` do recibo passa a vir apenas da verificação, com `verified_by`, `read_mode` e `binding_module_sha256`. Qualquer falha resulta em `POLICY_CAPTURE_NOT_VERIFIED:<motivo>`, campos nulos e NOT_PASS.

### B07-ORDER-01
- `produced_after_independent_b06` é igual ao veredito B06 efetivamente conferido: o arquivo existe, o SHA confere com o digest fornecido separadamente e o conteúdo traz VERDICT=PASS, INDEPENDENT_REVIEW=YES, 0 críticos e 0 maiores.
- O novo campo `b06_independent_verdict` vale `VERIFIED_PASS` ou `NOT_VERIFIED`.
- Um veredito ausente gera `B06_VERDICT_MISSING`, com `review_verdict_sha256=null` e flag `False`.

## Provas adversariais (`S12_B07_TECHNICAL_PRODUCER`, 15 testes; antes eram 7)
- **test_07:** o dicionário sintético com o mesmo schema (o negativo exigido pela origem) é recusado, e nenhum recibo é gravado.
- **test_08:** master, head ou revisão fictícios no registro de reconciliação → `POLICY_RECONCILIATION_BINDING`.
- **test_09:** digest divergente, malformado ou registro ausente → bloqueio.
- **test_10:** captura V38 histórica, MASTER adulterado, arquivo extra e registro `NOT_ISSUED` → bloqueio.
- **test_11:** reconciliação expirada ou com janela acima de 72h → bloqueio.
- **test_12:** módulo verificador adulterado → recusado pelo digest selado.
- **test_02, 02b, 02c:** B06 ausente, FAIL, com achado crítico ou maior, ou com digest errado nunca resulta em `produced_after_independent_b06=True`. A flag reflete o estado do B06, não o status global.
- **Mutações (`B07_MUTATION_EVIDENCE.txt`):** o pai R45, a flag fixada em `True` e o desvio da verificação com identidade forjada foram todos rejeitados pelos testes (`B07_MUTATION_CHECK=PASS`).

A reconciliação de unidade usada nos testes é um fixture temporário, marcado `unit_fixture_not_origin_record`, e é apagado ao fim do teste. Não é registro da origem.

## Estado
- R44D2: admitido para a sandbox nativa (os artefatos são os mesmos já entregues). Rodar `CHECK_PS51_SYNTAX.ps1` antes. Se a raiz `D:\TICKSTORE_QUALIFICATION_SANDBOX` estiver ausente, ele para em BLOCKED, sem criar a pasta.
- R45: **substituído pelo R45B**. O FINAL R45 está preservado, mas não deve ser qualificado.
- R45B: congelado para a qualificação nativa, com seus próprios 126 IDs e todas as suítes. Não herda o PASS do R44.
- `POLICY_RECONCILIATION_FOR_R45=NOT_ISSUED`. Não é precondição do probe negativo; a solicitação foi atualizada para os bytes R45B.
- `LEGACY_ENTRY=RESIDUAL_BLOCKS_PRODUCTION`, ainda aberto. A proposta de patch explícito do RC1 está em `LEGACY_ENTRY_ISOLATION.md` e a decisão cabe à origem.
- G4 INCOMPLETE · G5 INCOMPLETE (prova física de queda de energia) · B06 NOT_STARTED · B07 SOURCE_ONLY · FULL_STARTED=NO.

## Ordem no Windows (`PS C:\Users\silvi>`)
1. `CHECK_PS51_SYNTAX.ps1`
2. `RUN_TICKSTORE_CDT15_R44D2_DROOT.ps1`
3. Somente se o R44D2 der PASS: `RUN_TICKSTORE_CDT15_R45B_QUAL.ps1`, elevado. **Não executar `RUN_TICKSTORE_CDT15_R45_QUAL.ps1`.**

Logs em `C:\Users\silvi\OneDrive\Downloads\TICKSTORE_RUNS\<MODO>_<timestamp>_<PID>\RUN_LOG.txt`.
