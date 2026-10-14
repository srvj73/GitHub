# TICKSTORE CDT15 R47: entrega final sucessora (revisão consolidada R46 da origem, opção A)

Papel: **ENGINEER_ONLY / SOURCE_ONLY**. Limites desta entrega:
- nenhuma alteração produtiva, nenhum FULL, nenhum B06 próprio, nenhuma execução B07 ou D4;
- nenhuma migração aplicada, nenhum corte de energia, nenhum crédito pago;
- nenhum recibo G5, B06 ou B07 fabricado; nada declarado PASS sem evidência; a reconciliação de política continua `NOT_ISSUED`.

## O que é
O candidato TICKSTORE FULL R47 congelado. Ele absorve todos os achados da revisão R46:
- **LEGACY-ENTRY:** recertificação RC1 → RC1R1 com proveniência histórica, sucessor D4 V002R23 e migração SOURCE_ONLY;
- **G11:** G4 imposto no código antes de G5;
- **política R41:** como autoridade de reconciliação;
- **POWERLOSS-SCRATCH-01:** defeito de retomada após queda no scratch do MULTIWORK, achado pela própria pré-qualificação R47 e corrigido.

| Arquivo | Conteúdo |
|---|---|
| `RECERTIFICACAO_RC1R1.md` | causa, delta exato, proveniência C0/S0, sucessor V002R23, migração e provas |
| `RELATORIO_COMPLETUDE_R47.md` | tratamento de cada achado, completude em cinco partes e testes |
| `DEPENDENCIAS_EXTERNAS_R47.md` | execuções e decisões externas (sem pedido de decisão pendente) |
| `LEDGER_INTERNO.md` | causas, correções e testes; 0 itens abertos |
| `IDENTIDADES_R47.json` | hashes completos (FINAL, QUAL, bootstraps, núcleo, sucessor, binding) |
| `R47_POLICY_RECONCILIATION_REQUEST.json` | pedido, não recibo: `NOT_ISSUED`, contra R41 ou posterior |
| `RC1R1_MUTATION_EVIDENCE_R47.txt`, `B07_MUTATION_EVIDENCE_R46.txt` | controles adversariais |
| `DIFF/` | diff físico R46 → R47 e delta por arquivo com SHA |
| `RUNNERS/` | FINAL R47 com testemunha, QUAL R47 com testemunha, bootstraps QUAL/B07, `CHECK_PS51_SYNTAX.ps1`, R44D2 (ZIP, PS1, testemunha) |
| `SUCCESSOR_D4/` | `TICKSTORE_V004R1_D4_RESUMABLE_V002R23_PACKAGE.zip`, pacote de revisão do delta V002R23, identidades |
| `PREFLIGHT_OFFLINE/` | campanha offline em dois segmentos (SAFE_STOP e retomada) e harness R3 106/106 |

## Ordem no Windows
Os comandos rodam em `PS C:\Users\silvi>`, e os arquivos ficam em `C:\Users\silvi\OneDrive\Downloads`.
1. `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\CHECK_PS51_SYNTAX.ps1"`
2. **Somente se ainda não existir RETURN R44D2 nativo:** `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\RUN_TICKSTORE_CDT15_R44D2_DROOT.ps1"`.
3. `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\RUN_TICKSTORE_CDT15_R47_QUAL.ps1"`. Esta é a campanha G4 sobre os bytes definitivos R47 (suítes S8–S22), com janela elevada.
   - **Pausar (SAFE_STOP):** crie o arquivo `STOP` na pasta RUN.
   - **Retomar:** acrescente `-ResumeFrom "<…\QUAL_RETURN_<RUN>.zip>"`.
   - **Acompanhar:** `HEARTBEAT.json`.
4. Daí em diante, siga `procedures/PROCEDIMENTO_OPERACIONAL_GATES.md` dentro do FINAL. A sequência é: G5 (decisão da origem), B06 independente, B07 (`RUN_TICKSTORE_CDT15_R47_B07.ps1`), cadeia até B07, migração do sucessor (passo 8b), D4 e os estágios seguintes.

Os logs ficam sempre em `C:\Users\silvi\OneDrive\Downloads\TICKSTORE_RUNS\<MODO>_<timestamp>_<PID>\RUN_LOG.txt`. Devolva o RETURN ZIP indicado no final do log.

## Estado
`LEGACY_ENTRY=CLOSED_IN_CODE_RC1R1 | G11=CLOSED_IN_CODE | G4=INCOMPLETE (aguarda campanha nativa R47) | G5=INCOMPLETE (prova física de energia) | B06=NOT_STARTED | B07=PREPARED_NOT_EXECUTED | SUCCESSOR_MIGRATION=PREPARED_NOT_APPLIED | POLICY_RECONCILIATION=NOT_ISSUED (contra R41+) | FULL_STARTED=NO`
