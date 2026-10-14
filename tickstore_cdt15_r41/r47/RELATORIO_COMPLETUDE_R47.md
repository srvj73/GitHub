# TICKSTORE CDT15 R47: relatório de completude da engenharia (sucessor único da revisão R46)

**Candidato congelado: R47.**
- FINAL `3F36D8C0EC1EBF4FFD54E567131325E69187503C7A226C07EA6F9DB8E8AF29EF`.
- Manifesto de código `FE1C3B464C88B8DA73B89B246F1B016D32E4C9F4A537D76230A67D2D4175F571`.
- Hashes completos em `IDENTIDADES_R47.json`.
- FINAIS anteriores preservados, sem reconstrução: R44 `0FBB6C36…`, R45 `C0D19216…`, R45B `3155EE11…` e R46 `0CAA565C…`.
- Fixtures aprovadas byte-idênticas: B1A `29981D15`, B1B `2E95CADE`, B2C `E74F3701` e `40B396FC`.

## 1. Achados da revisão R46 e tratamento

| Achado da origem | Tratamento R47 | Evidência |
|---|---|---|
| **LEGACY-ENTRY**: opção A, recertificação | Núcleo RC1R1 com rotas legadas fechadas no código. Proveniência histórica RC1 em núcleo, MULTIWORK, motores e verificador pós-FULL. Sucessor D4 V002R23 com pinos regenerados. Migração SOURCE_ONLY | `RECERTIFICACAO_RC1R1.md`; S14, S19, S20 e S21; mutações 14/14 |
| **G11**: ledger aberto | A lacuna real foi fechada no código: o binder aceitava qualquer `NATIVE_RETURN_ZIP`. Agora G5 só é materializado sobre o RETURN ZIP nativo fechado de G4 (recibo QUAL nativo vinculado a FINAL e código, idêntico à proveniência da completude), e B07 exige o ZIP do próprio recibo técnico. G4 está documentado como pré-cadeia deliberada | S11 (21 testes: 16–19 novos); mutação eliminada; `procedures/PROCEDIMENTO_OPERACIONAL_GATES.md` |
| **Política**: R40 não autoritativa, R41 ativa | Procedimentos, pedido de reconciliação e testemunha da campanha nomeiam a R41 (MASTER `B00AF978…`, HEAD `0F812705…`) e exigem reconciliação viva contra R41 ou posterior. Sem mudança de código: o vínculo não fixa revisão | `R47_POLICY_RECONCILIATION_REQUEST.json` (`NOT_ISSUED`) |
| **Achado próprio da pré-qualificação R47 (POWERLOSS-SCRATCH-01)** | A primeira pré-qualificação offline R47 falhou em 1 teste do S18, com corte emulado sob contenção de CPU. A causa raiz foi uma queda na escrita atômica do journal de scratch, que deixava a sombra `.journal.json.partial`, ou na inicialização do dia, que deixava partial sem journal. Nos dois casos a retomada do MULTIWORK bloqueava. O defeito é preexistente. A correção classifica esses detritos como o caminho canônico do RC1: descarte após leitura do journal principal; partial sem journal descartado; journal sem partial segue fail-closed. A falha **não foi tratada como intermitência** | 4 testes unitários (S20), e2e determinístico S22 byte-igual ao controle (sem a correção reproduz `ATOMIC_PARTIAL_ALREADY_EXISTS`), 12/12 rodadas sob carga, mutação eliminada |
| **Qualificação e gates externos** | Inalterados como dependências externas. A campanha longa R46 **não** foi pedida; a R47 cobre os bytes definitivos | `DEPENDENCIAS_EXTERNAS_R47.md` |

## 2. Completude em cinco partes (avaliação da engenharia; a decisão é da origem)

| Parte | Situação R47 |
|---|---|
| 1. Implementação e integrações | Completa. RC1R1 integrado em núcleo, MULTIWORK, motores, verificador pós-FULL, pinos D4 e migração. Não há rota legada aberta |
| 2. Bloqueios internos conhecidos | Nenhum: o ledger tem 0 itens abertos. G11, LEGACY-ENTRY, R47-S0-PROVENANCE, R47-POWERLOSS-SCRATCH-01, R47-POLICY e R47-MIGRATION estão corrigidos |
| 3. Testado = empacotado | O manifesto de fontes e o de código são fechados, e a campanha roda a partir do FINAL extraído. A prova nativa depende de A3 (G4), externa |
| 4. Busca de falsa completude | Buscas feitas: literais `D3A15572…` e `BFC44DA9…` restantes (só no histórico, em fixtures e na proveniência explícita); pinos D4 contra wrapper, bootstrap e migração (teste S21); consumidores dos oráculos (achado R47-S0-PROVENANCE, corrigido); itens "aberto" no ledger (0) |
| 5. FINAL congelado sem mudanças planejadas | R47 congelado. Não há alteração planejada nos bytes. Os próximos passos são execuções e decisões externas |

**Declaração:** a engenharia não conhece defeito corrigível internamente. `CANDIDATE_COMPLETENESS` continua sendo avaliado pela origem. Nenhum PASS de gate foi declarado. G4, G5 (energia física), B06 e B07 dependem de execução ou decisão externa.

## 3. Testes internos (Linux, sem valor nativo)

| Bateria | Resultado |
|---|---|
| `source/tests` (28 arquivos, incluindo os novos `test_rc1r1_recertification`, `test_rc1r1_successor_migration` e `test_scratch_powerloss_debris`) | todos OK; laboratório de energia 15/15 com os novos motores |
| `full/` | `test_full_serial_r9` 43 OK (1 pulado, só nativo); `test_full_multiwork` 38 OK; scripts R3–R8 PASS; `static_multiwork_preaudit` PASS (inclui `RC1_HISTORICAL_PROVENANCE`) |
| `adapter_tests` | 29 OK |
| Pacote de recuperação (`tests`, `tests_release`) | equivalente ao histórico (mesmas dependências nativas) |
| Harness R3 com os 4 overlays aprovados | 106/106 PASS sobre os bytes R47 |
| Mutações | B07 3/3 (R46) e **RC1R1/G11/migração/scratch 15/15** |
| Pré-qualificação offline R47 | dois segmentos: SAFE_STOP mais retomada (`PREFLIGHT_OFFLINE/`) |
| Parser PowerShell | bootstraps R47, wrapper D4, preflight MULTIWORK, launcher e instalador: PARSE_OK |
