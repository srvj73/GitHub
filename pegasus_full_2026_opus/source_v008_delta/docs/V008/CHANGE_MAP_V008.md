# Mapa diferencial V008 contra os parents

## Base e parents (identidade por SHA-256, sem seleção por data ou nome)

| Parent | Identidade | Uso no V008 |
|---|---|---|
| Codex FULL V003 consolidado | ZIP `CC37261C…`; payload `73EF2833…`; manifesto `701DF5EC…` | Base única. 2.867 arquivos byte-idênticos; somente `MANIFEST_SHA256.json` da raiz é regenerado |
| G4 original congelado | `61330A93…` | Não alterado. O núcleo econômico `minotauro_*` do V003 é idêntico ao do G4; os 7 módulos `r1r11_*` divergentes já eram delta do Codex (V002/V003) |
| `pegasus_entry.py` (V003) | `F77B5266…` | Não alterado; a suíte final do V003 rodou agora sobre esses bytes empacotados |
| `r1r11_resources.py` (V003) | `719988E1…` | Não alterado (correção de `RunLock.__enter__` do Codex preservada) |
| Backend W04 R14R3 | `native_handle_backend_v001.py` `8FEF1313…` | Copiado byte-idêntico para `supervisor/`; usado como census de corroboração |
| SAFE_STOP V006 | `pegasus_qs4_stop_bridge_v006.py` `178CEBBC…` | Copiado byte-idêntico; `DurableStopAdapter` ligado ao `Orchestrator` pelo binding QS4 |
| QS4 V002 R001 | candidato `0680FE65…`; harness `E52AF782…` | `QS4_HARNESS_R001/` byte-idêntico (28 arquivos) |
| V007 parent controlado | `2137D303…` | Mantido como prova histórica de identidade; substituído funcionalmente pelo supervisor V008 |

## Arquivos novos (todo o código novo está fora de `CODE/`)

| Arquivo | Função |
|---|---|
| `supervisor/pegasus_supervisor_v008.py` | Pai executado: verify, admissão B/C antes de efeitos, W04 JIT, custódia, SAFE_STOP confirmado, porta de conclusão, watchdog por heartbeat, CLI |
| `supervisor/pegasus_win_native_v008.py` | Camada Windows: Job (suspenso → assign → resume, IOCP, contabilidade), lease, diretórios, USN, identidade, census |
| `supervisor/pegasus_qs4_binding_v008.py` | Regra de binding QS4 por bytes; instalação do `DurableStopAdapter`; filho QS4 bloqueado até admissão |
| `supervisor/pegasus_qualify_v008.py` | Qualificação integrada não econômica sobre o runtime real (Q01–Q09; Q10–Q11 nativos) |
| `supervisor/tests/test_supervisor_v008.py`, `mutation_supervisor_v008.py` | Testes unitários e controles negativos por mutação |
| `supervisor/launcher/BOOTSTRAP_PEGASUS_FULL_2026_V008_PS51.template.ps1` | Bootstrap PS 5.1 (Verify/QualifyNative/Install/Rollback) |

**Por que nada entrou em `CODE/`:** `r1r11_full_2026.verify_package()` exige que `CODE/SHA256SUMS.txt` liste exatamente os arquivos de `CODE/`; acrescentar um módulo ali quebraria o caminho FULL.

## Testes reaproveitados e não repetidos

- Não repetidos (bytes inalterados): 80/80 QS4 R001 Linux, retirement V002, identidade V007, causa R14R2, smoke R14R3, 8 controles do delta `RunLock` V003, suítes históricas do G4.
- Executados agora porque **nunca haviam rodado nos bytes finais**: a cadeia `tests/qualify.py` do V003 havia parado em `during_pending` (3º de 8 faults). Rodou integralmente: 19/19 PASS.
- Executado pela primeira vez: probe instrumentado `during_pending` (o V003 registrava `directed_instrumented_probe=NOT_EXECUTED`).
- Novos: 46 testes unitários do supervisor, 14 mutantes, qualificação supervisionada Q01–Q09.

## Custos e efeitos

Nenhum crédito pago; nenhuma execução econômica; nenhuma escrita em D:, ACL produtiva, serviço ou tarefa. Downloads de terceiros no ambiente de build: apenas o PowerShell 7.4.6 oficial (hash da release conferido), usado só para análise sintática.
