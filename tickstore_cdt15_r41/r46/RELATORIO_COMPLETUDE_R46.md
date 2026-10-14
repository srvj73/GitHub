# TICKSTORE CDT15 R46: relatório de completude da engenharia

Candidato congelado: **R46** (os hashes estão em `IDENTIDADES_R46.json`). O núcleo RC1 continua byte-idêntico (`D3A15572…`). Os FINAL anteriores R44 (`0FBB6C36…`), R45 (`C0D19216…`) e R45B (`3155EE11…`) foram preservados e não foram reconstruídos.

Resultado: **nenhum defeito corrigível internamente ficou pendente**. O que falta depende de execução ou decisão externa (ver `DEPENDENCIAS_EXTERNAS_R46.md`).

## 1. Matriz de componentes

| Componente | Implementação | Testes (portáteis/nativos) | Evidência nativa disponível | Estado |
|---|---|---|---|---|
| Motor FULL (conversão/publicação) | `full/tickstore_full_multiwork.py` (RC1 como biblioteca) | `test_full_multiwork` 26, IDs `tests_native_delta` | R42/R44 (bytes do multiwork mudaram só na CLI de compatibilidade) | COMPLETO; requalificação nativa R46 |
| MULTIWORK | idem + `FULL_LIFECYCLE`, `FULL_RUNNER` | `tests_full_lifecycle` 18 | R42, R44 | COMPLETO |
| AUTOCPU | `choose_workers`, `available_logical_cpus` | `tests_delta` auto_cpu, prova SAFE_STOP com outra contagem de workers | R41R2, R42, R44 | COMPLETO |
| SAFE_STOP | evento nomeado FULL (Stop), Ctrl+C cooperativo; D4 pelo wrapper (STOP + CancelKeyPress); **R46:** o pai ignora SIGINT enquanto o wrapper roda (G7) | S15 test_06/07 (filho real), provas | R42, R44 | COMPLETO |
| Retomada determinística | scratch por instância, journal por row-group; continuação retoma nó FAIL (G8) | `NativeResumeTests`, S15 test_09 | R44 | COMPLETO (energia física: externa) |
| Checkpoints | journal atômico, estado V002, checkpoint D4 assinado, `STATE_CAS_RECOVERY` | `tests_stage_closure`, **S17 (11, novo)** | R44 (emulado) | COMPLETO (prova física: externa) |
| ETA / heartbeat / watchdog | `FULL_OBSERVABILITY`, `MainLoopWatchdog`, `FULL_RUNNER.monitor` | observabilidade 14, S15 | R41R2, R42 | COMPLETO |
| Locks / leases | `acquire_lock`, `FullProcessLease`, Job, lease de census | `test_native_process_control_r41` (N) | R42 | COMPLETO |
| Instalação | `INSTALL_TICKSTORE_FULL.ps1` (**R46:** RUN_LOG fixo) | instalador 18 + 11 | R42, prova R44 PS51_INSTALL_MENU | COMPLETO |
| MENU / writer oficial | `menu/MENU.py` (**R46:** Monitor + reconciliação corrente, G4), `MENU_OFFICIAL_WRITER.py` | writer 40+27+17+18, S15 | R42, R44 | COMPLETO |
| Recuperação | engine de release congelado, `STATE_CAS_RECOVERY` | `recovery/tests_release` (N), S17 | R44 (IDs nativos) | COMPLETO |
| Cadeia de gates | `FULL_RELEASE_CHAIN`, `FULL_STAGE_EVIDENCE`, `ORIGIN_DECISION_BINDER` (**R46:** política física, CLI, B06 recibo≠veredito), `B06_RECEIPT_CHECK` (**novo**), `FULL_INSTANCE_PREPARE chain --until B06/B07` (G2) | `tests_delta.ChainTests`, S11 (17), **S16 (11)** | — | COMPLETO |
| G5 (gerador/verificador) | `G5_EVIDENCE_BUILDER`, `FULL_QUALIFICATION_CONTRACT`, `g5proof/` | S8 34, S9 3 | R44 (pacote INCOMPLETE só por energia física) | COMPLETO; prova física externa |
| B07 | `B07_CHECK_RUNNERS` (**R46:** verificador selado, cardinalidade observada, R44D2, árvore própria), `B07_TECHNICAL_PRODUCER` (PROVENANCE-01, ORDER-01, ID correto, árvore de testes vinculada, IDs do contrato), driver modo B07 + bootstrap B07 (G3) | S12 (21) + mutações | — (só após B06) | COMPLETO (preparado, não executado) |
| D4 | `FULL_RUNNER.d4_command` → wrapper selado (**R46:** elevação fail-closed antes de qualquer efeito, G6) → BOOTSTRAP/TRANSACTION → `FULL_D4_CLOSURE` | 22 TX + 9 bootstrap + `tests_delta`, S15 test_10/11 | prova R44 D4_CLOSURE (sintética) | COMPLETO (preparado) |
| D5 / CANARY / FULL_PREP / FULL_ADMIT / FULL | `FULL_STAGE_CONTINUATION` (**R46:** CLI com reconciliação, G5) | canary 13+7, stageb 12, postverify 17, **S16** (D5, FULL_PREP, FULL_ADMIT, admission facts) | prova R44 STAGE_B (sintética) | COMPLETO (preparado) |
| Isolamento legado | quarentena + não-alcançabilidade + negativas de entrada direta; **R46:** validador do gate multiwork removido (G12) | S14 (9) | — | ENGENHARIA COMPLETA; **resíduo de governança depende de decisão da origem** |
| Regra de log do titular | `RUN_LOG_FIXED` nas CLIs Python; bootstraps, launcher e instalador com raiz fixa (G13) | S15 (instalador), testes de instalador | — | COMPLETO |
| Laboratório físico de energia | `powerloss_lab/LAB_POWERLOSS.py` preflight/plan/**arm/inspect/reconcile/aggregate** (G14) | **S18 (15, e2e com motor real e corte emulado)** | — | FERRAMENTA COMPLETA; execução física externa |
| Campanha nativa | `QUAL_DRIVER` (**R46:** heartbeat de campanha, SAFE_STOP por arquivo `STOP`, retomada `-ResumeFrom` com o mesmo RUN_ID) + bootstraps QUAL/B07 | preflight offline: SAFE_STOP + retomada exercitados | — | COMPLETO |

## 2. Lacunas da auditoria interna e defeitos da origem: todos fechados

B07-PROVENANCE-01, B07-ORDER-01, B2D-PROVENANCE, B2D-B06, G1…G14 e B07-RUNNER foram fechados. O detalhe, a causa e o teste de cada um estão em `LEDGER_INTERNO.md`. Nenhum teste foi pulado ou desativado. As fixtures aprovadas pela origem (B1A, B1B e as duas B2C) seguem byte-idênticas.

## 3. Testes internos (Linux, sem valor nativo)

| Bateria | Resultado |
|---|---|
| `source/tests` (25 suítes) | todas OK |
| `full/` | `test_full_multiwork` OK; `test_full_serial_r9` OK (1 pulado, só nativo) |
| `static_multiwork_preaudit` | PASS |
| `adapter_tests` | OK |
| Harness R3 com os 4 overlays aprovados | 106/106 PASS (os 20 IDs só nativos ficam para o Windows) |
| Mutações B07 | 3/3 mortas |
| Preflight offline R46 | dois segmentos: SAFE_STOP + retomada (ver `PREFLIGHT_OFFLINE/`) |

`TESTED_CODE_EQUALS_PACKAGED_CODE`: a campanha extrai o FINAL do QUAL ZIP, verifica o manifesto fechado antes e depois de rodar, e todos os testes rodam a partir do FINAL extraído.
