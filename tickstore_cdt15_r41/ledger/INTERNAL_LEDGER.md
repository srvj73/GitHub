# Ledger interno — TICKSTORE CDT15 conclusão FULL (diretiva da origem: encerrar ping-pong)

Base: commit dfe680a (R45B interno). RC1 D3A15572… preservado.

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
| G11 | auditoria | G4 fora da cadeia (só status) | documentação | aberto |
| G12 | auditoria | validate_multiwork_gate morto (gate legado) | interna | CORRIGIDO (validador de gate multiwork removido) |
| G13 | auditoria | regra de log do titular não aplicada a ferramentas | interna | CORRIGIDO (RUN_LOG_FIXED nas CLIs; instalador e writer com RUN_LOG fixo) |
| G14 | auditoria | laboratório de energia: arm/inspect/reconcile não ligados | interna (execução externa) | CORRIGIDO (arm/inspect/reconcile/aggregate conectados; e2e offline; execução física externa) |
| LEGACY-ENTRY | origem | CLI direta do RC1 aceita owner gate forjado | externa (release instalada + proveniência) | decisão consolidada |
| B2D-B06 | engenharia | binder exige review_verdict == SHA do recibo B06 (inconsistente com produtor/D4) | interna | CORRIGIDO (recibo B06 vs veredito B06 distintos e cruzados; testes) |
| G13 | (parcial) | RUN_LOG_FIXED aplicado às CLIs Python; falta INSTALL_TICKSTORE_FULL.ps1 | interna | CORRIGIDO (RUN_LOG_FIXED nas CLIs; instalador e writer com RUN_LOG fixo) |
