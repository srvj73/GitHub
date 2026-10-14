# TICKSTORE CDT15 R47: recertificação do núcleo RC1 → RC1R1 (decisão da origem, opção A)

Papel: **ENGINEER_ONLY / SOURCE_ONLY**. Nenhum efeito foi aplicado no PC produtivo. A migração da release instalada é preparada, testada e documentada, mas só é aplicada pelo titular no Windows e somente depois da cadeia técnica até B07.

## 1. Causa
A revisão R46 da origem registrou o achado **LEGACY-ENTRY**: o núcleo RC1 (`D3A1557253461BA6C19D40E60D70AF99962290D4BB488C88035D4D9D52D5F6C0`) ainda aceitava, pela CLI direta, um Owner Gate FULL_SERIAL forjado e vinculado às bindings correntes. A origem decidiu pela **opção A** (recertificar o CORE_RC1) e determinou que essa decisão não fosse pedida de novo.

## 2. Alteração do núcleo (RC1R1 = `749EEC5DF5C4F396D553AD75C1765D5BDA108391F877CC0C9179D82590429E00`)

| Definição | Mudança |
|---|---|
| `FULL_SERIAL_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE` | `True` → `False`. A CLI `--mode FULL_SERIAL` e `run_full_serial` falham antes de qualquer acesso, mesmo com um gate forjado exato |
| `PILOT_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE` | `True` → `False`. A CLI `--pilot-date` falha antes de qualquer acesso |
| `RC1_HISTORICAL_RUNNER_SHA256` | nova constante (RC1 `D3A15572…`) |
| `_rc1_historical_rebuild`, `historical_rc1_oracle`, `historical_rc1_scratch_oracle`, `reject_historical_rc1_transient` | novas funções de proveniência histórica |
| `reconcile_full_readonly` | usa o oráculo histórico quando o commit é do RC1 |

**Prova estrutural:** o teste `tests/test_rc1r1_recertification.py` compara a AST de primeiro nível do RC1 com a do RC1R1, ignorando comentários. O delta é **exatamente** a lista acima. Nenhuma função de construção, validação, publicação ou compressão mudou. O mesmo teste prova o delta dos motores (`CORE_SHA`, `CORE_B64`, `oracle_contract`, `RC1_HISTORICAL_CORE_SHA`) e do verificador pós-FULL (`CORE_SHA`, `verify`, `RC1_HISTORICAL_CORE_SHA`).

## 3. Proveniência histórica (nada é reetiquetado)

| Conjunto | Origem física | Tratamento RC1R1 |
|---|---|---|
| C0: 151 pares publicados (2 R8 + RC1) | destino canônico | R8: regra certificada inalterada. RC1: o oráculo é reconstruído com os `runner_ids` do próprio commit e precisa ser igual ao contrato do ledger e à referência congelada; continua com runner RC1 |
| S0: 1399 dias de scratch `VALIDATED_PENDING_PUBLISH` do RC1 | scratch multiwork (RC4R2/RC4/RC3/RC2R3) | o MULTIWORK publica com o oráculo RC1 do journal, que identifica o produtor do payload. A validação completa do payload contra o oráculo é mantida |
| Construção RC1 inacabada (`BUILDING`) | scratch | **fail-closed** (`FULL_RC1_HISTORICAL_SCRATCH_NOT_VALIDATED`). Nunca é continuada sob a identidade RC1 |
| Transação canônica RC1 transitória | destino | **fail-closed** (`FULL_RC1_HISTORICAL_TRANSIENT_TRANSACTION`), antes de qualquer acesso à fonte |
| Dias novos | — | runner RC1R1 |

O motor de recuperação (CERTIFY_SCRATCH, CERTIFY_CANONICAL e postverify) e o verificador independente pós-FULL aceitam `runner ∈ {RC1R1, RC1}` com a mesma verificação de referência; R8 segue inalterado e qualquer outro runner falha fechado.

**Achado da própria recertificação (R47-S0-PROVENANCE):** sem esse tratamento, o MULTIWORK RC1R1 recusaria os 1399 dias S0 e os pares C0 do RC1, porque o oráculo atual carrega o runner RC1R1. O defeito foi corrigido antes da entrega e coberto por testes com mutação.

## 4. Pacote sucessor D4: V002R22 → V002R23

| Identidade | V002R22 (histórico) | V002R23 |
|---|---|---|
| release engine | `BFC44DA9…` | `0DF4DDEB2FDD29850168A345A30100D5D13A806694AF6332C96C781404365FBC` |
| candidate engine | `E9980324…` | `0C04283386C42F3E7DEC29479213FE1225D404FFE91E9311489F89BF638B053C` |
| postfull_verifier | `B5E753C3…` | `F64558BBEDC88D5AD57A3D02B6A0F70FCE4F967B4829501A09C5B2DFFEEBD6CD` |
| config STAGE_A | `B67527C0…` | `77B638CCC4B3B07D37E09D2EF40225023E2102E4C664AF96F4F599B99CC4557F` |
| CODE_MANIFEST | `60FE88C9…` | `B2D6CF0BC16585255AC4FE77C6C0316564D7C133CABBD516D53B5EDFEAC5FFD5` |
| 99_MANIFEST | `5199C7B0…` | `EE8A49DE2CE7EFC227FC5D53A5DC10CC854279EAED2FD1D03A5A233D80143EE9` |
| ZIP do pacote | `4BC28843…` | `5B1D8338D26F407A043665636EA79300AD6E4C79FDFE3397CE1CC79FDBD9656F` |
| pacote de revisão do delta | — | `EC281FEAC71A0A9EF79D4A98C6FA3533EC40F9B3359C4243F296971A1A14A03E` |

- O ZIP V002R23 é empacotamento determinístico (`stored`, metadados fixos) da árvore `candidate/recovery` do FINAL R47. O teste S21 reproduz o SHA a partir da árvore FINAL.
- Os pinos foram regenerados por `build/build_rc1r1_successor.py`, que é idempotente: D4 PREP, D4 BOOTSTRAP, wrapper efetivo, binding do adaptador e `FIRST_ADMISSION_BINDING`.
- O orquestrador, o script mestre, o loader, os testes do pacote e a referência permanecem inalterados.
- O cabeçalho do veredito D4 continua `TICKSTORE_D4_RESUMABLE_CODE_DELTA_REVIEW_V002R22`, porque é identificador de formato lido pelo motor.

**Não transportados:** 37 arquivos documentais e de revisão do V002R22 (docs, histórico de política, prompts e patches de revisão, `README_EXECUCAO.md`, `BUILD_AUDIT.json`).
- Nenhum nó os executa.
- Os SHA-256 continuam registrados no manifesto V002R22, preservado byte a byte em `history/V002R22/99_MANIFEST_SHA256.json` dentro do sucessor.
- O pacote instalado V002R22 é preservado como backup pela migração.

Por isso o ZIP instalado `4BC28843…` **não é necessário** e nenhum arquivo foi pedido ao titular.

**Equivalência não regressiva dos testes do pacote (Linux):**
- Rodaram `recovery/tests` e `recovery/tests_release` com os motores V002R23 e com os motores históricos.
- O resultado é idêntico: as mesmas 24 dependências nativas de rename e o mesmo arquivo `baseline/` de workspace ausente.
- Esses testes só têm valor no Windows.

## 5. Migração SOURCE_ONLY (`candidate/control/RC1R1_SUCCESSOR_MIGRATION.py`)
1. **Simulação (padrão, somente leitura).**
   - Prova que o ZIP é exatamente a árvore `candidate/recovery` do FINAL instalado, coberta por B06 e B07.
   - Classifica o `SUCCESSOR_PACKAGE` instalado: V002R22, V002R23 ou ausente.
   - Bloqueia se houver `RUN_AUTHORITY` admitida ou pendente, conteúdo desconhecido, ausência sem backup ou um artefato divergente.
2. **Aplicação (`--apply`).**
   - Exige Windows nativo e `FULL_RELEASE_CHAIN.ReleaseChain` validada até **B07** sobre os bytes do FINAL, com o digest independente do B06. Os pinos ficam retidos durante a troca.
   - O V002R22 é **renomeado** para `SUCCESSOR_PACKAGE.V002R22_BACKUP.<RUN>` e nunca é apagado.
   - O V002R23 é extraído para `…V002R23_STAGING.<RUN>`, relido e verificado, e então promovido por rename.
   - O ZIP é copiado para `artifacts`, com create-new e conferência de SHA.
   - É gerado o recibo técnico `migration/<RUN>/MIGRATION_RECEIPT.json`.
3. **Queda no meio.** Fica o pacote antigo, ou o backup mais um staging. A reexecução retoma; o staging anterior é apenas listado e nunca apagado.
4. **Fora do escopo.** STATE, checkpoint, authority, destino canônico e scratch nunca são tocados.

## 6. Provas
- **S19:** 9 testes (delta estrutural, identidade embutida, proveniência no motor e no pós-FULL, rotas fechadas).
- **S20:** 81 testes nativos (núcleo e MULTIWORK com C0/S0 RC1 e detritos de queda do scratch).
- **S22:** e2e de retomada após detritos de queda no scratch (POWERLOSS-SCRATCH-01).
- **S21:** 15 testes da migração.
- **S11:** 21 testes (G11).
- **S14:** 9 testes (isolamento legado com as rotas fechadas).
- **Mutações:** 15 de 15 eliminadas (`RC1R1_MUTATION_EVIDENCE_R47.txt`).
- **Harness R3:** 106/106 sobre os bytes R47.
- **Laboratório de energia S18:** 15/15 com os novos motores.
