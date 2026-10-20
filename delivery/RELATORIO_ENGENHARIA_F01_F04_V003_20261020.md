# RELATÓRIO DE ENGENHARIA — CDT21 — FECHAMENTO F-01 / F-04 — CANDIDATO SUCESSOR V003

`RESULT_RETURN_TO=ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compressão De Ticks 21`

- Data: 2026-10-20.
- Papel: **IMPLEMENTADOR** (não auditor B06).
- Executor: Claude Code (Anthropic), sessão `session_017rrbzfRq9DGx2KFMSp8Mcy`, modelo `claude-opus-5-5`.

## 0. Resultado

```
ENGINEERING_RESULT=DELTA_COMPLETE_FROZEN_V003
F01=CLOSED_IN_CODE (cerca de entrada legada + exigência na cadeia oficial)
F04=CLOSED_IN_CODE (launcher/loader congelados fixados por handle na rota oficial)
SUCCESSOR=CDT21_FINAL_PACKAGE_V003_20261020.zip SHA256=69DA2D5964BABA95D8B90D5BC17E12683B5F5E91D1C7D7ABD01938A7AE014A50
RUNTIME_CODE_MANIFEST=D59BC4EE4F0D5C689335C8F478A0342CC0146930E3B0B44C707B6B95267B3953
LINUX_REQUALIFICATION=PASS (75/75 arquivos de teste idênticos à linha de base V002; nova suíte 27 PASS + 3 nativos pendentes)
WINDOWS_NATIVE=TARGET_RUNTIME_PENDING (runner G0 entregue)
PARENT_V002=INALTERADO 4942871541629C3B38F47EDA55EA2C9E310361533887CB55E577D9641542E7C5
G5_V002=NAO_TRANSFERIDO_AO_V003
B06=NOT_STARTED | B07/D4/D5/CANARIO/FULL=NAO_EXECUTADOS | PRODUCAO=NENHUM_EFEITO | CREDITO_PAGO=NAO
```

## 1. Identidade, papel e independência (relato fiel)

- **Handoff recebido:**
  - `HANDOFF_CDT21_F01_PARA_OPUS_20261020.zip`, SHA `E0347C42EF08C59897D09F6517D48921CB4434C1344B5A0843632592DE952CE9`, 17.246.767 bytes, CRC íntegro. Confere com a testemunha.
  - Manifesto técnico `A7ACEAAA…1138`: 11/11 membros conferem.
  - `BASELINE/FINAL_PACKAGE_V002.zip` é idêntico, byte a byte, ao parent `4942…E7C5`.
- **Contexto da execução:** o handoff pedia retomar a conversa do Opus que implementou o V002. **Esta não é essa conversa.** É a conversa em que esta mesma sessão conduziu, antes, o preflight B06 do V002, a pedido do titular. O titular determinou expressamente que a engenharia fosse feita aqui.
- **Consequência:** esta sessão, e o mesmo modelo, **participou da implementação do V003**. Por isso não pode servir de auditor B06 do sucessor, e o preflight anterior não vale como avaliação independente do V003.
- Não consultei, li nem validei MASTER, HEAD, captura normativa ou política.

## 2. Diagnóstico confirmado nos bytes congelados

**F-01**

- `recovery/TICKSTORE_V004R1_MASTER_ORCHESTRATOR.ps1` (`18900BCC…`), linhas 11–12, executa `python -I -S -B modules/orchestrator.py <comando> --package <raiz>` para 10 comandos. O próprio script não grava nada.
- `orchestrator.py` (`3C16FC13…`):
  - `main()` constrói `State(cfg["control_root"])` antes de qualquer outra ação. O mesmo ocorre em `O.__init__` e em `confirm_stale_lock`.
  - `State.__init__` sempre executa `atomj(self.sp, …)`, que passa por `atom()`: `open("STATE.json.partial","wb")` seguido de `os.replace`.
  - Efeitos resultantes: cria STATE em `A0/NEW`, regrava STATE existente e reinicia com journal órfão. O controle discriminante do teste 02 reproduz esses efeitos.
  - `O.gate()` emite `"authorized": True` por conta própria.
- O mesmo vale para `python orchestrator.py` direto e para **qualquer cópia implantada**: ambas as versões do orquestrador presentes nos bytes recebidos usam o mesmo padrão.
- O `control_root` produtivo é o mesmo em todas as cópias.

**F-04**

- `recovery/modules/Launch-TickstoreBundle.ps1` (`56B7F4FD…`) faz `Get-FileHash` do loader e depois `ReadAllBytes`, abrindo uma janela entre o hash e a releitura.
- Essa superfície **integra a rota oficial pós-D4**: `adapted_launch` recorre a `original_launch` para bundles fora da geração-alvo, como os de produção.
- Fato complementar verificado: o modo RECOVER do motor abre o evento global de safe-stop antes de `acquire()` e de qualquer efeito (`engine:2028`, `SAFE_STOP_EVENT_NOT_FOUND`).

## 3. Correção mínima (sem tocar um byte do pacote sucessor congelado)

**Alternativas rejeitadas, com prova**

1. **Alterar ou retirar o PS1 ou o orquestrador do pacote R24.**
   - Esses arquivos estão fixados na configuração selada (`master_ps1_sha256`, `orchestrator_py_sha256`, `launch_tickstore_bundle_sha256`), no ZIP R24 `CAC345D3…` e no review pack, artefatos externos que não estavam disponíveis. Também estão fixados no wrapper e no bootstrap, e o bootstrap **exige** o PS1 por hash.
   - Além disso, essa alteração não alcançaria as cópias já implantadas nem `python orchestrator.py` direto.
2. **Remover o PS1:** insuficiente pelos mesmos motivos.

**Implementado**

1. **`control/LEGACY_ENTRY_FENCE.py`** (novo, `53DCF599…`).
   - Cria o diretório `state/STATE.json.partial` com o marcador `LEGACY_ENTRY_FENCE.json`.
   - A primeira escrita de qualquer `State` congelado falha antes de qualquer alteração. Isso vale para os 10 comandos, para o PS1 legado, para `python` direto e para qualquer cópia.
   - A ferramenta funciona em modo diagnóstico por padrão. `--apply` instala a cerca sob a mesma fronteira de processo da entrada D4, re-diagnostica e nunca apaga nada.
   - Bloqueia diante de detrito `.partial`, link/reparse, marcador inválido ou fronteira ocupada.
2. **`adapter/runtime_locator_orchestrator_entry.py`** (`5BFECEA3…` → `5D0CC1AC…`).
   - `require_legacy_entry_fence` passa a ser exigido em `validate_d4_start` (primeira admissão e entrada D4).
   - Também é exigido em `guard_frozen_state_reads` com `AdmittedStart` (entrada D4 e `FULL_STAGE_CONTINUATION`) e em todo commit CAS admitido de STATE.
   - O modo por caminho (cenários G3/G6, fixture pré-B06) permanece inalterado.
3. **`adapter/runtime_locator_adapter.py`** (`D50AB3CE…` → `00F9C7AB…`), F-04.
   - O fallback para o launcher congelado agora abre o launcher e o loader, verifica o SHA a partir dos próprios handles e mantém esses handles abertos, sem compartilhamento de escrita ou exclusão no Windows, até o filho terminar (também no modo assíncrono).
   - Adulteração bloqueia antes do lançamento.

**Pins e declarações**

- `RUNTIME_LOCATOR_ADAPTER_BINDING.json`: `C8F675D7…` → `D02AF542…`.
- `FIRST_ADMISSION_BINDING.json`: `674FD454…` → `8956A5F0…`. Este SHA continua sendo fornecido externamente ao bootstrap.
- `PRE_G06_CONSUMER_REVIEW.json`: `03EF54F4…` → `590DE08D…`. Atualiza as fontes dos 2 consumidores alterados e **retira a declaração falsa** de que `orchestrator.py` "não é root executável".

**Arquivos acrescentados**

- `tests/test_cdt21_f01_legacy_entry_fence.py` (`9FD7B21F…`)
- `qual/CDT21_F01_G0_QUALIFICATION.py` (`5C56104A…`)
- `README_CDT21_V003_F01_F04.md`
- `procedures/PROCEDIMENTO_CDT21_LEGACY_ENTRY_FENCE.md`
- Gerados pelo congelamento: patch, recibo de delta e registro de completude

**Não alterados, por decisão registrada**

- Motor, orquestrador, launchers, loader, config e manifestos do sucessor R24: o recibo de delta lista os SHA inalterados.
- `FULL_STAGE_CONTINUATION.py`, já que o enforcement ocorre no guard.
- `QUALIFICATION_CONTRACT.json` e o B07, cuja alteração de escopo cabe à origem.
- `README_FIRST.txt` histórico.

## 4. Qualificação

**Linux, CPython 3.14.6, sobre o ZIP final extraído (testado = empacotado)**

| Verificação | Resultado |
|---|---|
| Nova suíte F-01/F-04 | 30 testes: 27 PASS, 3 nativos Windows pulados (G0) |
| Varredura dos 75 arquivos de teste do pacote, linha de base V002 vs. V003 | **resultados idênticos**: 905/905 testes; diferença 0 |
| Resultados não-zero comuns a ambos | 21 arquivos (8 sem testes coletáveis neste ambiente, 13 dependentes de Windows/PS 5.1 ou de fixture ausente, p.ex. `tests/fixtures/R40_CAPTURE_NON_AUTHORITATIVE`); idênticos na linha de base; nenhum introduzido pelo delta |
| `verify_final_zip` do próprio projeto | PASS (código `D59BC4EE…`) |
| Sintaxe PowerShell (runner e launchers congelados) | 0 erros |

Controles negativos da nova suíte:

- **Discriminante:** sem a cerca, os bytes V002 criam STATE `A0/NEW` e regravam STATE existente.
- **Com a cerca:** os 10 comandos, com STATE ausente, presente ou journal órfão, saem com código diferente de zero e deixam o snapshot do `control_root` idêntico (bytes, inode e mtime). Nenhum diretório em `runs/` nem token em `inbox/` é criado.
- **Ferramenta da cerca:**
  - diagnóstico somente leitura;
  - `--apply` idempotente;
  - detrito preservado;
  - marcador inválido, link e diretório ausente bloqueiam;
  - fronteira ocupada bloqueia.
- **Entrada admitida:**
  - sem cerca, falha antes de alterar o namespace;
  - com cerca, o commit CAS admitido funciona e a rota legada continua bloqueada;
  - remoção da cerca no meio da execução bloqueia o commit sem gerar detrito;
  - marcadores adulterados bloqueiam;
  - o modo por caminho permanece inalterado.
- **F-04:**
  - bytes congelados verificados;
  - launcher ou loader adulterado, ou loader ausente, bloqueiam;
  - o fallback lança somente com fontes fixadas, e uma troca após o primeiro lançamento bloqueia;
  - no modo assíncrono, o pin é liberado só após a saída do filho.

**Windows nativo: `TARGET_RUNTIME_PENDING`.** O runner `RUN_CDT21_F01_G0_V003_20261020.ps1` (PS 5.1 elevado, a partir de `C:\Users\silvi`) executa:

- o PS1 legado real sob a cerca;
- a junção (link) no nome da cerca;
- os pins com negação real de escrita, rename e exclusão;
- o launcher congelado real sob pin, até `ANCHOR_HASH_REQUIRED`;
- as 7 suítes afetadas, o conjunto fechado, o isolamento legado e a cadeia dos 11 consumidores (`PRE_B06_ENGINEERING_GATE.verify_dossier(native_required=True)`).

Tudo roda em raiz própria em `%LOCALAPPDATA%`, com containment por Job, via `PRE_G06_CAMPAIGN.run_unit`. O log fica em `C:\Users\silvi\OneDrive\Downloads\CDT21_F01_RUNS\G0_<yyyyMMdd_HHmmss_fff_PID>\RUN_LOG.txt`.

**Não reexecutados** (apenas bytes idênticos herdam o PASS V002):

- os demais históricos;
- G3/G6, cujos cenários usam o guard por caminho e nunca alcançam o fallback de launch; os testes 25 e 26 cobrem esse ponto.

## 5. Completude em cinco partes (V003, verdadeira)

| Parte | Status |
|---|---|
| `all_implementations_integrated` | PASS em código e Linux |
| `all_known_fixable_blockers_closed` | F-01 e F-04 fechados em código; prova nativa pendente. F-02 fechado pela origem (479/479). F-03 roda e passa fora do Windows. |
| `tested_equals_packaged` | PASS em Linux; Windows `TARGET_RUNTIME_PENDING` |
| `frozen_for_independent_audit` | bytes congelados; B06 NOT_STARTED |
| `adversarial_false_completeness_check` | declarações limitadas (ver `CDT21_V003_ENGINEERING_COMPLETENESS.json`) |

O **recibo de cinco partes do produtor G5 (`produce`) para o V003 não foi emitido**: ele exige o retorno nativo da campanha completa sob o novo manifesto de código.

## 6. Pendências exatas (nenhuma é de engenharia aberta)

1. **G0 nativo:** o titular executa o runner, elevado, com o ZIP V003 na pasta Downloads, e devolve `RUN_LOG.txt`, `G0_RESULT.json` e `CDT21_F01_G0_RETURN.zip`.
2. **Instalação da cerca no `control_root` produtivo:** requer autorização da origem. Procedimento em `procedures/PROCEDIMENTO_CDT21_LEGACY_ENTRY_FENCE.md`. Sem a cerca, a cadeia oficial falha fechada (`LEGACY_ENTRY_FENCE_MISSING`).
3. **Decisão G5 da origem para os bytes V003.** Inclui decidir se basta o G0 do delta ou se é exigida a campanha nativa completa para o recibo `produce`.
4. **B06 independente**, por auditor sem participação no V003 (não esta sessão).

## 7. Artefatos entregues

| Arquivo | SHA-256 |
|---|---|
| `CDT21_FINAL_PACKAGE_V003_20261020.zip` | `69DA2D5964BABA95D8B90D5BC17E12683B5F5E91D1C7D7ABD01938A7AE014A50` (17.296.518 bytes, 312 membros) |
| `RUN_CDT21_F01_G0_V003_20261020.ps1` | `D431E2D967A5F27E0AD39ABDB920EEB36CA58AC0A62A84F589F6201190668F0C` |
| `CDT21_F01_F04_ENGINEERING_EVIDENCE_V003_20261020.zip` | ver testemunha |
| `WITNESS_CDT21_F01_F04_V003_20261020.json` | testemunha externa |

Manifestos do V003:

- PACKAGE `5DCC431B…8A51`
- SOURCE `9060B6AF…172D` (309)
- RUNTIME `D59BC4EE…3953` (163)
- patch `7606FFD6…F92B`
- recibo de delta `DFE97A45…5E18`

Devolva este resultado ao ChatGPT, no projeto ‘Base de Dados CSV / Tickstore’, conversa ‘Compressão De Ticks 21’. Anexe as evidências existentes e cole esta resposta.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compressão De Ticks 21`
