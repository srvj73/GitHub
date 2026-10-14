# TICKSTORE CDT15: procedimento operacional da cadeia de gates (preparado, não executado)

Este procedimento é congelado com o FINAL e todos os passos usam somente os bytes do candidato. Nenhum passo autoriza a si mesmo: o gate seguinte só aceita o recibo do gate anterior. Os recibos G5, B06 e B07 nunca são emitidos pelo engenheiro.

**Convenções**
- Todos os comandos rodam em `PS C:\Users\silvi>`, sem `cd`.
- `PY` = `C:\Users\silvi\AppData\Local\Python\pythoncore-3.14-64\python.exe` (SHA fixado).
- `CAND` = `implementation_v001\candidate` da instalação ativa.
- Logs: cada ferramenta grava em `C:\Users\silvi\OneDrive\Downloads\TICKSTORE_RUNS\<MODO>_<yyyyMMdd_HHmmss_fff>_<PID>\RUN_LOG.txt`.
- Todo digest marcado como "à parte" é digitado separadamente pelo operador e nunca é lido do próprio arquivo.
- **Política:** a política ativa é a R41 (MASTER `B00AF978A2C4728D8E12BAC8F56F4F4963032D62FDEA399C1CC7085DD0BCB23C`, HEAD `0F8127056E9DA3EFB9D69CC96F436AA6D888AD261CC218420D204274CF480590`, revisão `20261014T085300-0300-B00AF978A2C4728D`). Toda reconciliação viva exigida pelos estágios com efeito é emitida pela origem contra a R41 ou revisão posterior. A captura R40 empacotada é apenas fixture de teste e nunca é autoridade. O código não fixa revisão: o vínculo é sempre a reconciliação viva, verificada fisicamente.

**Sequência canônica:** `G4 → G5 → B06 → B07 → D4 → D5 → CANARY → FULL_PREP → FULL_ADMISSION → FULL`

**G4 é uma etapa pré-cadeia deliberada (G11).** G4 não tem recibo de estágio próprio. Sua prova é o próprio RETURN ZIP nativo fechado, e os recibos da cadeia técnica (`FULL_RELEASE_CHAIN.STAGES`) começam em G5. A imposição está no código:
- o `ORIGIN_DECISION_BINDER` só materializa G5 se o RETURN ZIP apresentado for fechado (`RETURN_MANIFEST` exato);
- o recibo QUAL contido nesse ZIP precisa ser nativo (Windows/PS 5.1/NTFS/elevado) e vinculado ao SHA do FINAL e do manifesto de código;
- esse ZIP e esse recibo QUAL precisam ser exatamente os que a `ENGINEERING_COMPLETENESS` cita como proveniência nativa, com `windows_qualification=PASS`;
- B07 só materializa se o recibo técnico B07 citar o mesmo RETURN ZIP apresentado.

| # | Etapa | Quem executa | Entrada | Ferramenta | Saída |
|---|---|---|---|---|---|
| 0 | Qualificação nativa (G4: evidência de ponta a ponta) | titular, no Windows | QUAL ZIP congelado | `RUN_TICKSTORE_CDT15_<REV>_QUAL.ps1` (SAFE_STOP por arquivo `STOP`, retomada com `-ResumeFrom`) | RETURN ZIP fechado (126 IDs, suítes, 6 provas, recibo V003) |
| 1 | Pacote de evidência G5 | engenharia (rascunho) | RETURN nativo + FINAL | `CAND\control\G5_EVIDENCE_BUILDER.py` | pacote G5. Fica `INCOMPLETE` enquanto faltar a prova física `CHECKPOINT_POWERLOSS_RECOVERY` |
| 1b | Prova física de queda de energia | laboratório **separado**, com autorização específica | plano semeado | `powerloss_lab\LAB_POWERLOSS.py preflight/plan/arm/inspect/reconcile/aggregate` | recibos de rodada + agregado (`PROPOSABLE_TO_ORIGIN`). Nunca no PC produtivo |
| 2 | Instância técnica | titular | `TEMPLATE_INSTANCE_INPUTS.json` preenchido | `PY -I -B CAND\control\FULL_INSTANCE_PREPARE.py prepare --inputs <arq> --inputs-sha256 <hex> --output <INSTANCE.json>` | `INSTANCE.json` (dados apenas; não é autoridade) |
| 3 | Decisão G5 | **origem** | pacote G5 completo | `TEMPLATE_ORIGIN_STAGE_DECISION.json` (emitido pela origem) | decisão + SHA à parte |
| 3b | Recibo de estágio G5 | titular (cópia vinculada) | decisão, captura de política, reconciliação | `PY -I -B CAND\control\ORIGIN_DECISION_BINDER.py --stage G5 ...` (verifica a política fisicamente; ambiente não nativo vira `FIXTURE_NOT_NATIVE`, inconsumível) | `STAGE_G5.json` |
| 4 | B06 independente | **revisor independente** | FINAL congelado + pacote de revisão | fora do pacote; modelos `TEMPLATE_B06_STAGE_RECEIPT.json` e `TEMPLATE_B06_VERDICT.txt` | recibo B06 + veredito |
| 4b | Conformidade do B06 | titular | recibo B06, recibo G5, manifesto, instância, veredito + SHA à parte | `PY -I -B CAND\control\B06_RECEIPT_CHECK.py ...` (somente leitura) | `B06_RECEIPT_SHA256` e `B06_VERDICT_SHA256` |
| 5 | Cadeia até B06 | titular | instância, manifesto, recibos G5+B06 | `FULL_INSTANCE_PREPARE.py chain --until B06 ...` | `EXECUTION_CHAIN` (G5, B06) + SHA |
| 6 | Verificações nativas B07 | titular, no Windows | cadeia até B06, B06 (recibo + veredito), captura, reconciliação | `RUN_TICKSTORE_CDT15_<REV>_B07.ps1 -ChainFile ... -ChainSha256 ... -B06Sha256 ... -B06Verdict ... -B06VerdictSha256 ... -PolicyRoot ... -PolicyReconciliation ... -PolicyReconciliationSha256 ...` | RETURN B07 fechado + `B07_TECHNICAL_RECEIPT.json` (recibo técnico, não veredito) |
| 7 | Decisão B07 | **origem** | recibo técnico B07 + RETURN | decisão da origem | decisão + SHA à parte |
| 7b | Recibo de estágio B07 | titular | decisão, recibo B06 (`--b06-receipt`), `--b06-verdict-sha256` | `ORIGIN_DECISION_BINDER.py --stage B07 ...` | `STAGE_B07.json` |
| 8 | Cadeia até B07 | titular | recibos G5+B06+B07 | `FULL_INSTANCE_PREPARE.py chain --until B07 ...` | `EXECUTION_CHAIN` + SHA |
| 8b | Migração do pacote sucessor D4 (RC1R1, V002R22 → V002R23) | titular, no Windows | cadeia até B07; `TICKSTORE_V004R1_D4_RESUMABLE_V002R23_PACKAGE.zip` | Simulação (somente leitura): `PY -I -B CAND\control\RC1R1_SUCCESSOR_MIGRATION.py --successor-zip <zip>`. Aplicação: o mesmo comando com `--apply --chain-file <cadeia até B07> --chain-sha256 <hex> --b06-sha256 <hex>` | `SUCCESSOR_PACKAGE` = V002R23; V002R22 preservado como `SUCCESSOR_PACKAGE.V002R22_BACKUP.<RUN>` (nunca apagado); recibo `migration\<RUN>\MIGRATION_RECEIPT.json`. Não toca STATE, checkpoint, authority, destino nem scratch |
| 9 | D4 (primeira admissão) | titular | cadeia até B07, reconciliação **corrente** da origem | MENU, opção 10 → `D4` (pede a reconciliação e o SHA à parte), ou `CAND\control\RUN_TICKSTORE_FULL.ps1 -Stage D4 ...` | D4 executado pelo wrapper selado (já elevado; Ctrl+C = SAFE_STOP cooperativo do wrapper); `D4Close` publica o recibo D4 |
| 10 | D5 | titular | cadeia até D4 + reconciliação | MENU → `D5` | recibo D5 (readback do certificado canônico) |
| 11 | CANARY | titular | cadeia até D5 + reconciliação | MENU → `CANARY` | recibo CANARY (verificadores congelado e independente concordam: 1550 dias, 7.049.522.162 linhas, 3101 arquivos) |
| 12 | FULL_PREP | titular | cadeia até CANARY | MENU → `FULL_PREP` | pacote Stage B pronto para revisão |
| 13 | Revisão Stage B + FULL_GO | revisor/origem | pacote Stage B | `inbox\STAGE_B_REVIEW_V001.txt`, `inbox\FULL_GO.txt` | — |
| 14 | FULL_ADMIT | titular | cadeia até FULL_PREP + revisão | MENU → `FULL_ADMIT` | recibo FULL_ADMISSION (vale 300 s; reemitido por `FULL_READMIT`) |
| 15 | FULL | titular | cadeia até FULL_ADMISSION (fresca) | MENU → `FULL` (AUTOCPU, heartbeat, ETA; `Stop` = SAFE_STOP cooperativo; Ctrl+C também) | FULL completo + verificação pós-FULL |
| — | Monitor | qualquer | cadeia | MENU → `Monitor` (somente leitura: barra, %, ETA, watchdog) | — |

**Regras de falha**
- **Qualquer bloqueio:** o processo para com `*_BLOCKED=<motivo>` e nada é inferido.
- **Ctrl+C em D5, CANARY ou FULL_PREP:** o nó fica `FAIL`, e reexecutar a mesma etapa retoma do nó interrompido.
- **Lock órfão após morte abrupta:** é fail-closed (`WRITER_LOCK_EXISTS`). A reconciliação só é permitida depois de provado que não há processo vivo.
- **Debris de CAS do STATE:** `STATE_CAS_RECOVERY.py` diagnostica em modo somente leitura e só aplica R1, R2 ou R3 sob a fronteira.

**LEGACY-ENTRY fechado no código (RC1R1, decisão da origem: opção A).**
- O núcleo recertificado tem `FULL_SERIAL_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE=False` e `PILOT_EXECUTION_AUTHORIZED_BY_THIS_PACKAGE=False`. As rotas CLI legadas falham antes de qualquer acesso, mesmo com um Owner Gate forjado.
- O FULL roda somente por MULTIWORK e pela cadeia técnica.
- Os dias publicados pelo RC1 (C0) e os dias de scratch validados pelo RC1 (S0) mantêm a proveniência RC1. Uma construção RC1 inacabada nunca é continuada pelo RC1R1 (fail-closed).
