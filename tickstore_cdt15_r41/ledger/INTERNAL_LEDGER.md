# Ledger interno — TICKSTORE CDT15 conclusão FULL (diretiva da origem: encerrar ping-pong)

Base: commit dfe680a (R45B interno). R47: núcleo recertificado RC1R1 749EEC5D… (decisão da origem, opção A). O RC1 D3A15572… está preservado como histórico em `history/RC1_V002R22` e nos fixtures de teste.

| ID | Origem | Lacuna | Classe | Estado |
|---|---|---|---|---|
| B07-PROVENANCE-01 | origem R45 | produtor B07 aceitava captura sintética | interna | CORRIGIDO (R45B) |
| B07-ORDER-01 | origem R45 | produced_after_independent_b06 incondicional | interna | CORRIGIDO (R45B) |
| B2D-PROVENANCE | engenharia | binder aceitava captura sintética; sem CLI | interna | CORRIGIDO |
| G1 | auditoria | ID de teste B07 com classe errada (EffectfulWriter vs Concurrency) | interna | CORRIGIDO (ID Concurrency; teste de resolução de IDs) |
| G2 | auditoria | sem montador de cadeia até B06 para o runner B07 | interna | CORRIGIDO (assemble_chain until B06|B07; testes) |
| G3 | auditoria | sem driver/RETURN ZIP do B07; árvore de testes não vinculada; tx ids do chamador | interna | CORRIGIDO (driver modo B07 + bootstrap B07 + recibo técnico do RETURN fechado) |
| B07-RUNNER | engenharia | probe de política sem digest selado; cardinalidade fixa; probe sandbox usa R44D | interna | CORRIGIDO (verificador selado, cardinalidade observada, R44D2, árvore própria) |
| G4 | auditoria | MENU não repassa reconciliação; sem Monitor; sem teste | interna | CORRIGIDO (MENU: Monitor + reconciliação; testes) |
| G5 | auditoria | CLIs de compatibilidade sempre bloqueiam | interna | CORRIGIDO (multiwork/continuação repassam reconciliação e log) |
| G6 | auditoria | autoelevação do wrapper quebrada (-ElevatedChild bloqueado) | interna | CORRIGIDO (wrapper fail-closed antes de qualquer efeito; binding regenerado) |
| G7 | auditoria | Ctrl+C mata o wrapper D4 (subprocess.call) | interna | CORRIGIDO (pai ignora SIGINT durante o wrapper; teste com filho real) |
| G8 | auditoria | Stop só no nó G3 | interna/desenho | FECHADO POR DESENHO (Stop cooperativo em FULL; demais estágios: FAIL retomável, testado) |
| G9 | auditoria | STATE_CAS_RECOVERY sem testes | interna | CORRIGIDO (11 testes da tabela R1–R4 e do apply) |
| G10 | auditoria | readback D5, full_admission_facts e FULL_GO sem teste | interna | CORRIGIDO (D5, FULL_PREP, FULL_ADMIT/FULL_GO, full_admission_facts) |
| G11 | auditoria + origem R46 | G4 fora da cadeia (só status): o binder aceitava qualquer `NATIVE_RETURN_ZIP` sem checagem semântica | interna | CORRIGIDO (R47). G4 é pré-cadeia deliberada e imposta no código. `ORIGIN_DECISION_BINDER` só materializa G5 sobre RETURN ZIP fechado, com recibo QUAL nativo vinculado a FINAL e código, idêntico à proveniência da completude e com `windows_qualification=PASS`. B07 exige o mesmo ZIP do recibo técnico. Testes 16–19; a mutação sem a checagem gera 7 falhas |
| G12 | auditoria | validate_multiwork_gate morto (gate legado) | interna | CORRIGIDO (validador de gate multiwork removido) |
| G13 | auditoria | regra de log do titular não aplicada a ferramentas | interna | CORRIGIDO (RUN_LOG_FIXED nas CLIs; instalador e writer com RUN_LOG fixo) |
| G14 | auditoria | laboratório de energia: arm/inspect/reconcile não ligados | interna (execução externa) | CORRIGIDO (arm/inspect/reconcile/aggregate conectados; e2e offline; execução física externa) |
| LEGACY-ENTRY | origem | CLI direta do RC1 aceita owner gate forjado | interna após decisão (opção A) | CORRIGIDO (R47, RC1R1). Rotas FULL_SERIAL e PILOT fecham por capacidade antes de qualquer acesso, mesmo com gate forjado. Delta AST restrito e provado. Motores e verificador pós-FULL aceitam a proveniência RC1 histórica. Sucessor D4 V002R23 com migração SOURCE_ONLY |
| R47-S0-PROVENANCE | engenharia (achado da recertificação) | após trocar o núcleo, o MULTIWORK recusaria os 1399 dias S0 validados pelo RC1 e os 151 pares C0 publicados pelo RC1 (oráculo com runner RC1) | interna | CORRIGIDO. C0 e S0 validados mantêm a proveniência RC1 (oráculo reconstruído e conferido contra ledger e referência). Construção RC1 inacabada ou transiente canônico RC1 falham fechado. Testes em núcleo e multiwork, com mutação |
| R47-POWERLOSS-SCRATCH-01 | engenharia (achado da pré-qualificação offline R47, S18 com corte emulado sob contenção de CPU) | queda dentro da escrita atômica do journal de scratch deixa `<dia>.journal.json.partial`; queda na inicialização deixa partial sem journal; a retomada do MULTIWORK bloqueava (`ATOMIC_PARTIAL_ALREADY_EXISTS` / `SCRATCH_PARTIAL_JOURNAL_PAIR_MISMATCH`). Preexistente (não introduzido pelo RC1R1) | interna | CORRIGIDO (R47). `_discard_scratch_crash_debris` classifica como o caminho canônico do RC1: sombra não comprometida descartada após o journal principal ser lido; partial sem journal descartado (autoridade zero); journal sem partial segue fail-closed. 4 testes unitários, e2e determinístico S22 byte-igual ao controle, sondas sob carga, mutação eliminada |
| R47-POLICY | origem R46 | captura R40 empacotada não é autoridade; a política ativa é a R41 | documentação | CORRIGIDO. Procedimentos e pedido de reconciliação exigem reconciliação viva contra R41 ou posterior. Sem mudança de código: o vínculo não fixa revisão |
| R47-MIGRATION | origem R46 (opção A) | release D4 instalada (V002R22) precisa migrar para os bytes recertificados | interna (aplicação externa) | CORRIGIDO no código. `RC1R1_SUCCESSOR_MIGRATION.py`: simulação por padrão. `--apply` só com cadeia até B07; backup por renomeação, staging verificado, recibo técnico e retomada após queda. A aplicação no Windows é externa |
| B2D-B06 | engenharia | binder exige review_verdict == SHA do recibo B06 (inconsistente com produtor/D4) | interna | CORRIGIDO (recibo B06 vs veredito B06 distintos e cruzados; testes) |
| G13 | (parcial) | RUN_LOG_FIXED aplicado às CLIs Python; falta INSTALL_TICKSTORE_FULL.ps1 | interna | CORRIGIDO (RUN_LOG_FIXED nas CLIs; instalador e writer com RUN_LOG fixo) |
