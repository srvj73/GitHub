# R45 — Isolamento comprovado das entradas legadas FULL_SERIAL, piloto e full-history

O núcleo congelado RC1 (`candidate/full/tickstore_serial_runner.py`, SHA-256 `D3A1557253461BA6C19D40E60D70AF99962290D4BB488C88035D4D9D52D5F6C0`) **não foi alterado**. O isolamento usa quatro camadas. Nenhuma delas depende apenas da ausência no menu.

| Camada | Prova | Onde |
|---|---|---|
| 1. Núcleo byte-idêntico | SHA-256 do RC1 igual ao congelado | `tests/test_legacy_entry_isolation.py::test_01`, `test_b2c_policy_capture_binding.py::test_22` |
| 2. Quarentena de empacotamento | Os 3 lançadores legados (`run_tickstore_full_serial_r9.ps1`, `RUN_WINDOWS_GATE_B.ps1`, `run_tickstore_serial.ps1`) e as 3 auditorias de release do r3/r8/r9 saíram da árvore FINAL e estão em `legacy_quarantine/` (fora de `source/`, logo fora do FINAL e do manifesto de runtime) | `test_02` |
| 3. Não-alcançabilidade estática | Nenhum `.ps1/.bat/.cmd/.vbs` e nenhum módulo Python não-teste do pacote carrega rota CLI legada (`--mode FULL_SERIAL`, `--pilot-date`, `--pilot-gate-file`, `--full-history`, `--full-gate-file`, `--full-gate-sha256`, `PILOT_LOW/HIGH`), e nenhum chama, por AST, `run_full_serial`, `run_one_day`, `require_pilot_owner_gate`, `validate_full_owner_gate`, `validate_full_gate_arguments`, `run_fresh_windows_preflight` ou `core.main` | `test_03`, `test_04` |
| 3b. Callee preso ao núcleo | `WINDOWS_GATE_B_PREFLIGHT_V005.py` entra em todo binding do RC1 (`file_ids.preflight_sha256`) e só pode sair alterando o núcleo. Está fixado por SHA `CDC49F5E…AE0F`, e nenhum outro módulo o referencia | `test_03b` |
| 3c. Prova de mutação | Lançadores plantados (`.ps1/.cmd/.bat`) e um módulo com `'FULL_SERIAL'` são detectados (4/4), o que mostra que o scanner não é vácuo | `test_08` |
| 4. Entrada direta (negativa, executada nativamente no R45) | Invocar o núcleo diretamente fecha sem efeito: `--mode FULL_SERIAL` → `FULL_OWNER_GATE_REQUIRED`; com gate sem SHA → `FULL_OWNER_GATE_TRUSTED_SHA256_REQUIRED`; `--full-history` → `FULL_HISTORY_EXECUTION_NOT_AUTHORIZED_BY_PACKAGE`; piloto fora do caso congelado → `PILOT_DATE_NOT_FROZEN_GATE_B_CASE`; piloto 20260731 sem raízes/preflight/gate → `BLOCKED`. Na API multiwork, os argumentos do gate legado → `LEGACY_ADMINISTRATIVE_OWNER_GATE_REVOKED` | `test_05`, `test_06`, `test_07` |

A suíte entra no plano de qualificação R45 como `S14_LEGACY_ENTRY_ISOLATION` (9 testes) e roda a partir do FINAL extraído (testado = empacotado).

## Risco residual (declarado, não ocultado)

O RC1 congelado aceita um gate de dono FULL_SERIAL que um humano forje e vincule exatamente aos bindings correntes (fontes, destino, ledger, SHAs do núcleo/referência/spec/preflight). A R40 proíbe emitir esse gate e revogou o OWNER_GATE administrativo. A barreira restante é procedimental: nenhum gate desse tipo existe, é produzido ou é aceito por qualquer outro caminho do pacote.

Fechar o residual por código exige alterar o RC1, com nova certificação, ou retirar o RC1 do FINAL. As duas opções mudam o núcleo congelado. **Decisão reservada à origem.** O engenheiro não alterou o núcleo.
