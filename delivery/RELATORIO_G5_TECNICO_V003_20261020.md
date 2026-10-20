# TICKSTORE CDT21 — G5 técnico do V003: prova de lacuna e procedimento nativo mínimo

**Papel:** implementador (Opus 5.5). Este documento não é parecer de auditoria B06.
**Candidato único:** `CDT21_FINAL_PACKAGE_V003_20261020.zip`
- SHA do pacote: `69DA2D5964BABA95D8B90D5BC17E12683B5F5E91D1C7D7ABD01938A7AE014A50`
- SHA do manifesto de código: `D59BC4EE4F0D5C689335C8F478A0342CC0146930E3B0B44C707B6B95267B3953`

**Gates:** G5 do titular APROVADO, sem nova solicitação. B06, B07, D4/D5, canário e FULL estão `NOT_STARTED`.

## 1. Resultado

| Item | Situação |
|---|---|
| Pendência entre o produtor de cinco partes e as evidências aprovadas | **Resolvida por prova.** O contrato congelado do V003 exige uma campanha nativa integrada vinculada ao V003. Nenhum PASS histórico satisfaz esse vínculo sem remarcação. |
| Rota *delta-only* compatível com o contrato | **Inexistente.** Demonstrado com o próprio gate congelado (controles negativos na §4). |
| Unidades faltantes | **34 contratualmente obrigatórias.** Elas produzem os 31 papéis do gate e os 9 `REQUIRED_DELTA`. O plano congelado tem 38 unidades: inclui 4 diagnósticas, que o `main()` congelado executa incondicionalmente (≈ 20 s). |
| Defeito material que exija sucessor | **Nenhum.** O V003 permanece intocado. |
| Procedimento Windows mínimo | **Pronto e qualificado no Linux** (20/20 verificações; PS 5.1 com 0 erros de análise). |
| Recibo técnico G5 de cinco partes do V003 | **Ainda não emitido.** Ele só pode nascer da execução nativa do procedimento. Não foi fabricado. |

## 2. Por que a campanha nativa é obrigatória

O recibo de cinco partes é produzido por `PRE_G06_COMPLETENESS.close()` (`15B10B10…`), que chama `G5_FINAL_COMPLETENESS_PRODUCER.produce()` (`34CA561C…`). Ambos são congelados no V003 e exigem o seguinte:

1. **Retorno nativo.** `FULL_G5_COMPLETE_PROOF_GATE.verify_native_campaign` (`EC6D9B2D…`) exige:
   - `ENGINEERING_RESULT` com schema `CDT19_PRE_B06_NATIVE_ENGINEERING_V002` e status `PASS_NATIVE_INTEGRATED_PRE_B06`;
   - `code_manifest_sha256 = D59BC4EE…` e `final_zip_sha256 = 69DA2D59…`;
   - conjunto de testes **igual** aos 31 papéis: 24 SUITE + 6 G5 + `PRE_B06_11_CHAIN`;
   - cada recibo de prova, o dossiê dos 11 consumidores e as projeções causais G3/G6 vinculados ao mesmo código e pacote.
2. **9 `REQUIRED_DELTA`.** Cada um precisa de um COMMIT com `package_sha256`/`code_sha256` do V003, `skipped=False` e log nativo selado.
3. **Quatro achados pré-B06.** Cada um se vincula a linhas `... ok` de logs nativos já presos ao resultado.
4. **Granularidade do vínculo.** O vínculo é sempre o SHA do manifesto **inteiro** e o SHA do ZIP **inteiro**. O código congelado não oferece vínculo por arquivo nem por delta.

Do V002 para o V003 mudaram 6 arquivos de runtime:
- `adapter/runtime_locator_orchestrator_entry.py`
- `adapter/runtime_locator_adapter.py`
- `adapter/RUNTIME_LOCATOR_ADAPTER_BINDING.json`
- `control/FIRST_ADMISSION_BINDING.json`
- `control/LEGACY_ENTRY_FENCE.py`
- `g5proof/PRE_G06_CONSUMER_REVIEW.json`

Como o manifesto mudou, nenhum dos 38 commits V002 (`3C97A2D7…`/`4942…`) é aceitável.

### Unidades do plano congelado (38)

| Grupo | Unidades | Obrigatória | Papéis produzidos |
|---|---|---|---|
| Provas G5 | `PS51_INSTALL_MENU`, `STAGE_B_REAL_ISOLATED_PATH_NATIVE`, `D4_REAL_ISOLATED_PATH_NATIVE` | sim | 3 papéis G5 + 4 suítes STAGE (logs colhidos da prova Stage B) |
| SUITE | 20 suítes | sim | 20 papéis SUITE |
| `REQUIRED_DELTA` | 9 | sim | exigidos por `close()` e pelos achados |
| DELTA diagnóstico | `final_completeness_contract`, `r06_integrated_contract`, `cdt18_..._d4_technical_bridge`, `r04_preb06_g6` | não (só pelo `main()` congelado) | — |
| Cadeia | `PRE_B06_11_CHAIN` | sim | 1 papel e dossiê `EVIDENCE/PRE_B06` |
| G3/G6 | `G3_G6_NATIVE` | sim | 3 papéis projetados: `PROCESS_TREE_CRASH_CONTAINMENT`, `SAFE_STOP_RESUME_ROW_GROUP`, `POWERLOSS_EMULATED` |

O detalhamento por unidade está em `CDT21_G5_V003_UNIT_GAP_PROOF.json`. Para cada unidade, o arquivo registra:
- o motivo contratual;
- o commit V002, com o vínculo que o torna não reutilizável;
- a cobertura pelo G0 V003;
- o SHA da fonte do teste.

### O G0 V003 (preservado: 11/11 unidades, 148/148 testes) não é a campanha

- Seu schema é `CDT21_F01_F04_G0_NATIVE_QUALIFICATION_V001` e suas chaves usam o prefixo `CDT21_`.
- Ele cobre o mesmo arquivo de teste de 5 das 38 unidades e de 7 dos 31 papéis.
- Não contém recibos de prova G5 nem projeção G3/G6.
- Cobre 1 dos 9 `REQUIRED_DELTA`, e sob outra chave.
- O `REUSE_COMMITTED` congelado aceita apenas `COMMITS/<chave>.json` da **mesma** raiz de execução.

## 3. Análise de defeito material antes da campanha

Verifiquei se a nova exigência de cerca (F-01) poderia derrubar unidades da campanha no V003:

- **G3/G6 nativo:** `guard_frozen_state_reads` recebe o caminho do STATE (`config=None`). Nesse caso, nem a guarda nem `commit_state` exigem a cerca.
- **Prova D4:** `test_pre_g06_d4_real_runtime_isolated.py` não carrega o módulo de entrada.
- **Prova Stage B:** 3 de suas 4 suítes já passaram nativamente no G0 V003.
- **Cadeia dos 11 consumidores:** também passou nativamente no G0 V003.
- **Demais suítes:** a requalificação Linux deu resultado idêntico à base V002 (75 arquivos, 905 testes).

**Conclusão:** nenhum defeito material identificado. O V003 permanece intocado e não há sucessor.

## 4. Inexistência de rota *delta-only*: controles negativos executados com o código congelado

| Controle | Resultado obtido |
|---|---|
| Evidência nativa V002, reconstruída do handoff, contra a identidade V003 | `G5_FINAL_NATIVE_G5_SOURCE_BINDING` (recusada) |
| Mesmos bytes contra a identidade V002 | Passam o vínculo de origem e o dossiê dos 11 consumidores. Param apenas em `NATIVE_CAUSAL_SUMMARY_MISSING`, porque `WORK/G3_G6_NATIVE` não integra o subconjunto transportado. A recusa no V003 é, portanto, de identidade. |
| `ENGINEERING_RESULT` V002 remarcado com os hashes do V003 (controle negativo, descartado em seguida) | `G5_FINAL_PRE_B06_CODE_BINDING` (recusado mais adiante) |
| Commit V002 colocado em raiz V003 (`run_unit`) | `PRE_G06_LAB_COMMITTED_INPUT_DRIFT` |
| Campanha bloqueada (`BLOCKED`) entregue ao gate | `G5_FINAL_NATIVE_G5_RUN_NOT_PASS` |
| `close()` com a revisão V003 sobre retorno bloqueado | Aceita a revisão e recusa o retorno: `NATIVE_G5_RUN_NOT_PASS`. Nada é escrito em `FINAL_G5`. |

As alternativas restantes seriam:
- alterar o gate, o produtor ou o `close()`, o que exige novos bytes e é proibido (`NO_REPUBLISH_V003_AS_NEW_BYTES`);
- usar um orquestrador não congelado que redija o `ENGINEERING_RESULT` a partir de um plano parcial, o que equivale a fabricar o resultado.

Ambas foram rejeitadas.

## 5. Procedimento Windows mínimo qualificado

**Arquivo único:** `RUN_CDT21_G5_V003_FIVE_PART_20261020.ps1`
- SHA: `337BBF0ED943F505F98F135280B76E906C16A6D21C5817FA2D384A81AA5608C2`
- Codificação: ASCII, CRLF.
- Conteúdo embutido, com SHA fixado:
  - supervisor `CDT21_G5_V003_SUPERVISOR.py` (`7B482A4B…B920`);
  - revisão `CDT19_IMPLEMENTER_SOURCE_REVIEW_V003.json` (`BB2BDE03…5348`).

**Execução** em PowerShell 5.1 **elevado**, a partir de `PS C:\Users\silvi>`, sem `cd`:

```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\RUN_CDT21_G5_V003_FIVE_PART_20261020.ps1"
```

**Pré-requisitos:**
- `C:\Users\silvi\OneDrive\Downloads\CDT21_FINAL_PACKAGE_V003_20261020.zip`, o mesmo usado no G0;
- Python fixado (`4942B86A…`);
- volume D: em NTFS.

**Log:** sempre em `C:\Users\silvi\OneDrive\Downloads\CDT21_G5_V003_RUNS\G5_<yyyyMMdd_HHmmss_fff_PID>\RUN_LOG.txt`, independentemente da pasta atual.

**O que o supervisor faz.** Ele cumpre apenas as obrigações de lançador que o código congelado verifica, e não grava PASS:

1. **Pré-voo sem efeitos:**
   - Windows, Python 3.14 e elevação;
   - SHA do pacote e vínculo da revisão;
   - `LOCALAPPDATA` canônico (sem `%` nem nome 8.3; ver B06-F04);
   - C: e D: em NTFS, com espaço livre;
   - Job *kill-on-close*.
2. **Raiz própria** `%LOCALAPPDATA%\CDT20_R08\R08_Q1_<14 dígitos>_<12 hex>`:
   - `TEMP` canônico;
   - `PACKAGED` extraído byte a byte;
   - `INPUTS` com o pacote e o witness `CDT19_R08Q1_ENGINEERING_WITNESS_V001`;
   - `OWNER.json` idêntico em `D:\TICKSTORE_CDT19_PRE_G06_LABS\<mesmo nome>`;
   - `QUAL_C` e `WRITER_EFFECTFUL`;
   - `CAMPAIGN.lock` com trava exclusiva de faixa de bytes, mantida até o término do filho.
3. **Campanha.** Executa o `PRE_G06_CAMPAIGN.py` congelado (`347767D1…`) como processo filho: 38 unidades, com heartbeats e `SAFE_STOP.request`.
4. **Fechamento.** Somente se a campanha retornar `PASS_NATIVE_INTEGRATED_PRE_B06`, executa o `PRE_G06_COMPLETENESS.close()` congelado, que gera `FINAL_G5` (cinco partes e quatro achados).
5. **Retorno.** Gera `CDT21_G5_V003_RETURN.zip` e `SUPERVISOR_RESULT.json` na pasta de log. O lançador monta ainda `ENVIAR_AO_CHATGPT_CDT21_G5_V003_<carimbo>.zip`.

**Duração estimada:** 12 a 15 min. A referência nativa V002 é de 712 s para 37 unidades, mais 1 unidade sem base e o fechamento.

**Códigos de saída:**

| Código | Significado |
|---|---|
| 0 | PASS de cinco partes |
| 2 | Pré-voo |
| 3 | Campanha não PASS |
| 4 | Fechamento |
| 5 | Empacotamento |
| 130 | Parada segura |

**Critérios de aceitação para a origem:**
- `SUPERVISOR_RESULT.status = PASS_NATIVE_V003_G5_TECHNICAL_FIVE_PART`, com `owned_processes_at_end = 0`;
- `ENGINEERING_RESULT` em `PASS_NATIVE_INTEGRATED_PRE_B06`, vinculado a `69DA2D59…`/`D59BC4EE…`;
- `ENGINEERING_COMPLETENESS` com as 5 partes em PASS;
- `FINAL_ENGINEERING_STATUS.engineering_five_part_completeness = PASS`;
- quatro achados em `PASS_NATIVE_REGRESSION`;
- duplicatas indexadas em `RETURN_INDEX` iguais ao pacote V003 e ao `R08_RETURN.zip`.

## 6. Validação executada (Linux; sem simular Windows)

`CDT21_G5_V003_SUPERVISOR_LINUX_VALIDATION.json`: **20/20 PASS**, com CPython 3.14.6, usando o código congelado extraído pelo próprio supervisor.

- **Aceitação pelo código congelado:**
  - `verify_package` congelado aceita a extração;
  - o witness atende ao vínculo da campanha e à derivação de `G5_PROOF_RUNNERS`;
  - o `OWNER` atende a `RUN_OWNER`/`D_LAB_OWNER` e à verificação G3;
  - `close()` aceita a revisão.
- **Falhas fechadas:**
  - a campanha falha fechada fora do Windows, com retorno selado sem o lock;
  - o supervisor falha fechado no pré-voo, sem criar raiz.
- **Empacotamento:** o retorno é empacotado corretamente.
- **Controles negativos da §4.**

**Não simulados:** Job do Windows, trava `msvcrt`, NTFS, elevação e as 38 unidades nativas.

`PS_PARSE_AND_EMBEDDED_CHECK.txt` registra a verificação do PS1: 0 erros de análise, e os blocos base64 decodificam exatamente para os SHA fixados.

## 7. Artefatos

| Arquivo | SHA-256 |
|---|---|
| `RUN_CDT21_G5_V003_FIVE_PART_20261020.ps1` | `337BBF0ED943F505F98F135280B76E906C16A6D21C5817FA2D384A81AA5608C2` |
| `CDT21_G5_V003_SUPERVISOR.py` | `7B482A4B2CD33734ED9AC2AAAE82ABEBB21B2439A1AB654380A74EDC6195B920` |
| `CDT19_IMPLEMENTER_SOURCE_REVIEW_V003.json` | `BB2BDE03B17C38AB54F998A0D0682F8CEC9848DFD433B1C200B6146554635348` |
| `CDT21_G5_V003_UNIT_GAP_PROOF.json` | `BFDACCCDEB4794FE2CE1C31632279DD5642996C8D968A1FCBBC195E275E32450` |
| `CDT21_G5_V003_SUPERVISOR_LINUX_VALIDATION.json` | `E6FCEB53CF7D4F9AAAF803CC55EFE2E197F3B3E029E46EC2039B6BCB5327A35F` |
| `CDT21_G5_V003_TECHNICAL_STATUS.json` | `DCC7799B8538AC1FF984D8511305DE6FE32ED069667BB7F7EF67D3361522EAAE` |

O ZIP de evidências e a testemunha externa trazem os hashes de todos os membros.

## 8. Não alegado

- Recibo G5 de cinco partes do V003 emitido: depende da execução nativa.
- `CANDIDATE_COMPLETENESS = PASS`.
- B06, B07, D4/D5, canário e FULL.
- Cerca instalada em produção.
- Perda física de energia (`NOT_TESTED_PHYSICAL_POWERLOSS`).
- Reaproveitamento ou remarcação de evidência V002.

## 9. Próximo passo

Executar o PS1 acima uma única vez e devolver `ENVIAR_AO_CHATGPT_CDT21_G5_V003_<carimbo>.zip` à origem. Com PASS, o recibo técnico G5 de cinco partes do V003 estará emitido pelo produtor congelado sobre os bytes exatos do V003. A partir daí, a origem decide sobre `CANDIDATE_COMPLETENESS` e sobre a admissão de um auditor B06 independente.

RESULT_RETURN_TO=ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compressão De Ticks 21
