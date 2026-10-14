# TICKSTORE CDT15 R46: pacote final de engenharia (revisão de completude pela origem)

Papel: **ENGINEER_ONLY**. Nenhuma alteração produtiva, nenhum FULL, nenhum B06 próprio, nenhuma execução B07, nenhum corte de energia, nenhum crédito pago. Nenhum recibo G5, B06 ou B07 foi fabricado, e nada foi declarado PASS sem evidência.

## O que é
O candidato TICKSTORE FULL **integralmente implementado e congelado** (R46), com:
- código-fonte e runners;
- manifestos e SHA-256;
- testes internos e controles negativos;
- a campanha nativa consolidada;
- os procedimentos de todos os gates.

Os hashes completos estão em `IDENTIDADES_R46.json`, os componentes em `RELATORIO_COMPLETUDE_R46.md`, e o que depende de terceiros em `DEPENDENCIAS_EXTERNAS_R46.md`, que contém o único pedido consolidado de decisão: LEGACY-ENTRY.

## Conteúdo
| Caminho | Conteúdo |
|---|---|
| `RUNNERS/` | FINAL R46 + testemunha, QUAL R46 + testemunha, bootstraps QUAL e B07, `CHECK_PS51_SYNTAX.ps1`, R44D2 (ZIP, PS1, testemunha) |
| `DIFF/` | diff físico R45 → R46 e delta por arquivo com SHA |
| `PREFLIGHT_OFFLINE/` | campanha offline em dois segmentos (SAFE_STOP e retomada) + harness R3 106/106 |
| `B07_MUTATION_EVIDENCE_R46.txt` | mutações rejeitadas pelos testes B07 (3/3) |
| `LEDGER_INTERNO.md` | causas, correções e testes de cada lacuna |
| `R46_POLICY_RECONCILIATION_REQUEST.json` | solicitação, não recibo: `POLICY_RECONCILIATION=NOT_ISSUED` |
| `LEGACY_ENTRY_ISOLATION.md` | isolamento aplicado, análise do resíduo e opções A/B |

## Ordem de execução no Windows (`PS C:\Users\silvi>`; arquivos em `C:\Users\silvi\OneDrive\Downloads`)
1. `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\CHECK_PS51_SYNTAX.ps1"`
2. `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\RUN_TICKSTORE_CDT15_R44D2_DROOT.ps1"`. Exige que `D:\TICKSTORE_QUALIFICATION_SANDBOX` já exista; se não existir, o script para em BLOCKED sem criar a pasta.
3. `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\RUN_TICKSTORE_CDT15_R46_QUAL.ps1"`. Abre uma janela elevada e roda a campanha longa: 126 IDs sobre os bytes R46, 11 suítes, probe B2C e 6 provas.
   - **Pausar (SAFE_STOP):** criar o arquivo `STOP` na pasta RUN mostrada no log.
   - **Retomar:** acrescentar `-ResumeFrom "<…\QUAL_RETURN_<RUN>.zip>"`.
   - **Acompanhar:** `HEARTBEAT.json` na pasta RUN.
4. `RUN_TICKSTORE_CDT15_R46_B07.ps1` **somente depois de B06 independente PASS** (ver `procedures/PROCEDIMENTO_OPERACIONAL_GATES.md` dentro do FINAL).

Os logs ficam sempre em `C:\Users\silvi\OneDrive\Downloads\TICKSTORE_RUNS\<MODO>_<timestamp>_<PID>\RUN_LOG.txt`. Devolva o RETURN ZIP indicado no final do log.

## Estado
`G4=INCOMPLETE (aguarda campanha nativa R46) | G5=INCOMPLETE (prova física de energia) | B06=NOT_STARTED | B07=PREPARED_NOT_EXECUTED | POLICY_RECONCILIATION=NOT_ISSUED | LEGACY_ENTRY=RESIDUAL_BLOCKS_PRODUCTION | FULL_STARTED=NO`
