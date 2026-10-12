# C2 — Engenharia estática sobre o Complemento de Fontes V001

**Projeto:** Perseu MT5 (Astra) · **Conversa:** PERSEU_C2_DISK_SPACE_RECONCILIATION
**Escopo:** leitura e compilação dos bytes recuperados, **sem executar** nenhum código recuperado, sem C2, sem tocar dados científicos.
**Evidência:** `evidence_sandbox/10_c2_recovered_static_review_py314.json` (gerado por `tests/c2_recovered_static_review.py`).

## 1. Aceitação do delta

| Verificação | Resultado |
|---|---|
| SHA-256 do ZIP vs. testemunha externa | `DF5192F6935F23A54AE91A7FC1E8C5EFD133AA2167C0C148509A0F16CF7BA907` = **PASS**; 399774 bytes = **PASS** |
| Vínculo ao pai | `parent_zip_sha256` `435FA919…` = pai validado; `parent_witness_sha256` `6926B552…` = SHA físico da testemunha pai = **PASS** |
| `MANIFEST_SHA256.json` (`77089CF7…`) vs. testemunha | **PASS** |
| CRC, caminhos, symlinks, duplicatas case-insensitive | **PASS** (22 entradas) |
| 21 membros: SHA e tamanho; exact-set em disco | **21/21 PASS**; exact-set **PASS** |
| ZIPs internos (6): CRC, caminhos, casefold | **PASS**; R4R8: 89 entradas = 87 arquivos + 2 diretórios (o mapa de proveniência conta 89 entradas) |
| Política | mesma captura do pai (`5B135DA0…` / `2DA2939C…`, `FROZEN`) — Biblioteca viva não consultada |

## 2. Separação de identidades (sem confusão)

| Objeto | Identidade | Classe |
|---|---|---|
| R4R9 original `PACOTE_PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R9_20260921.zip` | `70D6E131…F69F`, 102 arquivos no manifesto interno, observado em `C:\Users\silvi\OneDrive\Downloads\` em 22/09 (evidência terminal original) | **ausente** |
| R4R8 predecessor | `799B4914…3A3F` | referência; **não** é R4R9 |
| Prerregistro **V003** | `76833706…C408` | histórico; **não** é V004 |
| Prerregistro **V004** corrigido | sem bytes e sem SHA | **ausente** |
| Telemetria **V004_REENVIO** (ZIP / script) | `8BF75A54…63CA2` / `46E4E52F…7D07` | exata; **não** é a original |
| Telemetria **V004 original** | sem bytes e sem SHA | **ausente** |
| Hotfix R1/R2/R3 (scripts de preparação) | `7DBA5E7D…`, `B92867AA…`, `CFAFC741…` | histórico de design; **não** prova aplicação no alvo |

### 2.1 Membros do R4R9 com identidade conhecida (evidência terminal original, linhas L11–L17)

| Membro | SHA-256 | Bytes disponíveis? |
|---|---|---|
| `perseu_parallel_auto.py` (runner R4R9) | `28DF85A4…E68C` | **não** |
| `perseu_r4r9_accel.py` | `042FA9CB…F2E5` | **não** |
| `test_parallel_auto.py` | `5D3DB8FD…AB7E` | **não** |
| `test_r4r9_gate.py` | `B8E1417E…E8B8` | **não** |
| `perseu_exploratorio.py` (core) | `A331F308…607F` | **sim — byte-idêntico ao R4R8** (`perseu_exploratorio.py` e `BASELINE_R4R7/…`) |
| `test_perseu_exploratorio.py` | `7CC5A79C…4A80` | **sim — byte-idêntico ao R4R8** |
| `BASELINE_R4R8/perseu_parallel_auto.py` | `8EE1A1B1…41FB` | **sim — byte-idêntico ao runner do R4R8** |

A recuperação acima é por **igualdade de SHA-256**, não por inferência de versão: os bytes do R4R8 com esses SHAs são, por definição, os mesmos bytes desses membros do R4R9. Nenhum outro arquivo do R4R8 é tratado como R4R9.

### 2.2 Cadeia do hotfix C1 — identidade derivada e validada

Os preparadores gravam o módulo com `HOTFIX_SOURCE.encode("utf-8")` via `write_bytes` (bytes exatos). Derivação por AST, sem execução:

| Módulo | SHA derivado | Confirmação independente |
|---|---|---|
| `perseu_parallel_auto_resume_hotfix_r1.py` | `23AAE257…D62B` | igual a `EXPECTED_R1_HOTFIX` declarado no preparador R2 |
| `perseu_parallel_auto_resume_hotfix_r2.py` | `07562BD1…8CDF` | igual a `EXPECTED_R2_HOTFIX` declarado no preparador R3 |
| `perseu_parallel_auto_resume_hotfix_r3.py` | `6F77DFA4AB70BE0A3804B406CEF8DF2D8567A02470BE1993E51AA5F5CB5BBB13` | **DERIVED_STATIC** — método validado 2/2; prova física pendente |

Isso identifica **o que deveria estar instalado** se o R3 foi preparado; não prova que foi aplicado nem executado.

## 3. Achados de engenharia (estáticos)

| # | Severidade | Achado | Consequência |
|---|---|---|---|
| F1 | **Alta** | O REENVIO grava **sem guarda de colisão** `perseu_r4r9_telemetry_v4.py`, `RUN_WINDOWS_R4R9_CONFIRM_C2_202608_TELEMETRY_V4.ps1` e o relatório `PREP_PERSEU_R4R9_C2_TELEMETRY_V004.json`, com a **mesma** `VERSION="PREP_PERSEU_R4R9_C2_TELEMETRY_V004"` do original. A lista `KNOWN_FAILED` cobre V1–V3, não V4. | No Windows, original e REENVIO são indistinguíveis por nome; se o REENVIO rodou depois, os bytes originais nessa raiz foram sobrescritos. Distinção possível apenas por SHA (o localizador rotula). |
| F2 | **Alta** | O sidecar declara `EMBEDDED_V4_SHIM_SHA256=882C90AF…` (bytes LF). `write_text` no Windows traduz `\n`→`\r\n`; o shim instalado deve ter `8BF0BFBB6D142B0088E4FED5E0F7A74F1786AD2D427AE8338C45F7F29B624710` (derivado). | Comparar o arquivo instalado com o sidecar produz **falsa divergência**. Hipótese não comprovada: parte da divergência histórica V004×REENVIO pode vir disso. |
| F3 | Média | O wrapper V4 é lido com `utf-8-sig` e regravado com `utf-8` **sem BOM**; os wrappers C1/C2 foram gerados com BOM. | Se houver não-ASCII no wrapper, viola `PS1_NON_ASCII_REQUIRES_UTF8_BOM`. Verificação **bloqueada**: bytes do wrapper C2 ausentes. |
| F4 | Média | `py_compile.compile(V4_SHIM)` grava `__pycache__` dentro da raiz instalada. | byproduct na raiz do pacote (8.1). |
| F5 | Média | Gates de processo por `powershell.exe -Command` inline e filtro textual de `CommandLine`; teste de spawn via `python -c` não trivial; hotfix R3 lança via `py.exe`. | divergência com 9.5/10.AB/`PS51_PYTHON_DASH_C_NONTRIVIAL_FORBIDDEN`; o R3 qualifica explicitamente o `py.exe` por selftest, o que só vale com o recibo físico. |
| F6 | Baixa | Códigos de saída 10/30 fora do mapa canônico 0/1/2/3/130. | consumidores precisam de mapeamento explícito. |
| F7 | Baixa | Comentários e rótulos herdados ("Write V3 only", `V3_STATIC_FIELD_MISSING`) no V004. | risco de leitura errada de logs. |
| F8 | Informativo | A cadeia de hotfix R1→R3 é **do C1** (deriva do wrapper C1 `78830B5A…`). O C2 usa o shim de telemetria com `RESUME_METADATA_HOTFIX_MODE` interno. | não confundir hotfix C1 com o modo de retomada do C2. |
| F9 | Alta (científico) | O código confirmatório V001R2 está vinculado ao **V003** (`PREREG_SHA256=76833706…`) e à auditoria de contaminação `E5971B40…`. A identidade D1 `93092E9A…` **não aparece** em nenhum dos 17 recuperados. | um V004 corrigido exige novo vínculo e requalificação do código; vínculo D1 segue não provado. |
| F10 | Informativo | O fixture-fix V002 aplicou o patch somente em cópia temporária; a instalação deve manter `test_parallel_auto.py` = `5D3DB8FD…`. | qualquer outro SHA instalado é drift. |

Todos os 13 `.py` recuperados (incluindo os do ZIP de código confirmatório) e os dois payloads embutidos (`HOTFIX_SOURCE` do R3 e `SHIM_TEXT` do REENVIO) **compilam** em CPython 3.14.6 e 3.13.16 (somente `compile()`, sem bytecode gravado).

## 4. Verificações que permanecem bloqueadas (dependem de arquivos ausentes)

| Verificação | Depende de |
|---|---|
| Selftest do shim V4 (`--telemetry-selftest`) e import estilo spawn | runner `28DF85A4…`, accel `042FA9CB…` (o shim importa `perseu_parallel_auto` e `perseu_exploratorio`) |
| Selftest do hotfix R3 (`--hotfix-selftest`) | runner e accel |
| G0 do runner/accel R4R9 (estático, negativo, integração) | ZIP R4R9 `70D6E131…` |
| BOM/encoding do wrapper V4 e do C2 (F3) | `RUN_WINDOWS_R4R9_CONFIRM_C2_202608.ps1` `53C8A1FB…` |
| Identidade da telemetria V004 original | bytes originais |
| Vínculo prerregistro V004 ↔ D1 ↔ código | V004 e certificado D1 `93092E9A…` |
| Aplicação do hotfix no alvo | `PERSEU_R4R9_INMEMORY_RESUME_HOTFIX_R3_PREP_V003.json`, logs/recibos de execução |

---

Devolva este resultado ao ChatGPT, no projeto “Perseu MT5 (Astra)”, conversa “PERSEU_C2_DISK_SPACE_RECONCILIATION”. Anexe as evidências existentes e cole esta resposta.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Perseu MT5 (Astra) | THREAD=PERSEU_C2_DISK_SPACE_RECONCILIATION`
