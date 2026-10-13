# README — Sequência integrada no Windows até o C2 FULL

**Projeto:** Perseu MT5 (Astra) · **Conversa:** PERSEU_C2_DISK_SPACE_RECONCILIATION
**Estado:** todos os artefatos são `SOURCE_ONLY` até o G0 no alvo; nenhum foi executado no seu PC por mim.
Todos os comandos partem de `PS C:\Users\silvi>`, sem `cd`, usam `powershell.exe -File` e caminhos absolutos. Cada script grava log e recibo em pasta absoluta nova por execução, independentemente da pasta atual.

## 0. Artefatos (salvar em `C:\Users\silvi\OneDrive\Downloads\`, sem renomear)

| Arquivo | Bytes | SHA-256 | Papel |
|---|---:|---|---|
| `PERSEU_HD1_RECON_PROBE_V003.ps1` | 88857 | `F627A7CE61CBC1C5A6293ED52C563C5D098078E1CB3B60BF88B6D919988E1700` | HD1: G0, inventário e probe de metadados (substitui o V002; não rodar o V002 de novo) |
| `PERSEU_HD1_TOP4_READBACK_V001.ps1` | 90432 | `8136B9C7923AD03492087AC3D4D427B25262D0F4E826A1E3EED97BF6F82CD00E` | HD1: readback SHA integral do TOP4 (1530 arquivos), com retomada |
| `PERSEU_C2_SOURCE_LOCATOR_V002.ps1` | 61643 | `A231233459AD2670824FC7C5F09A41EC0D9EB19727DD65370D3474DA66E0E60D` | C2: localizar e recuperar fontes no C: e no arquivo frio HD2 |
| `PERSEU_C2_FULL_LAUNCHER_V001.ps1` | 42217 | `D582543534ADB8A71BE6C58AACF762A30F60904A59B7F50C8D6B9A1360148D26` | C2: instalar a partir das fontes recuperadas, preflight e execução do FULL |

**Passo 0 — identidade física (obrigatório antes de qualquer execução):**

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath "C:\Users\silvi\OneDrive\Downloads\PERSEU_HD1_RECON_PROBE_V003.ps1","C:\Users\silvi\OneDrive\Downloads\PERSEU_HD1_TOP4_READBACK_V001.ps1","C:\Users\silvi\OneDrive\Downloads\PERSEU_C2_SOURCE_LOCATOR_V002.ps1","C:\Users\silvi\OneDrive\Downloads\PERSEU_C2_FULL_LAUNCHER_V001.ps1"
```

Prossiga somente se os quatro `Hash` coincidirem exatamente com a tabela.

## 1. Estágio W1 — sem nenhuma troca de disco (pode ser feito agora)

**1.1 G0 no alvo dos quatro instrumentos** (somente leitura; fixtures próprias na pasta de run):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\PERSEU_HD1_RECON_PROBE_V003.ps1" -Mode SelfTest
```
```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\PERSEU_HD1_TOP4_READBACK_V001.ps1" -Mode SelfTest
```
```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\PERSEU_C2_SOURCE_LOCATOR_V002.ps1" -Mode SelfTest
```
```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\PERSEU_C2_FULL_LAUNCHER_V001.ps1" -Mode SelfTest
```

Esperado em cada um: `RESULT=PASS…`, `EXIT_CODE=0`. No V003, `CLEANUP_STATUS=RETAINED_EMPTY_BY_DESIGN` e `RUN_DIR_EXACT_SET=PASS` (nenhum `Directory.Delete` é tentado).

**1.2 Recuperação de fontes no arquivo frio HD2** (somente leitura no disco com serial `WD-WCAYUS916314`; nenhum job de cópia/hash deve estar gravando em `F:`):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\PERSEU_C2_SOURCE_LOCATOR_V002.ps1" -Mode HD2Index
```
```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\PERSEU_C2_SOURCE_LOCATOR_V002.ps1" -Mode HD2Deep
```

O `HD2Index` lê o primeiro nível de `<HD2>:\ARQUIVO_FRIO\CHATGPT_DLS_20261007_093221` e procura, em índices/manifestos de texto, os SHAs conhecidos e os nomes-alvo. O `HD2Deep` percorre `DATA` (limite de 60000 entradas, sem seguir links), calcula o SHA de arquivos de até 64 MiB (orçamento de 4 GiB; o arquivamento histórico tem cerca de 1,36 GB), identifica **por conteúdo** (mesmo renomeados) o R4R9, o runner, o accel, os wrappers, o hotfix e o D1, e copia cada identificado para `…\PERSEU_C2_SOURCE_LOCATOR_V002_RUNS\HD2DEEP_<RUN_ID>\RECOVERED\`, com SHA verificado. O HD2 nunca é gravado. `EXIT_CODE=0` indica apenas que a varredura foi concluída; a completude das fontes aparece em `C2_SOURCE_GATE`.

**Devolva** os recibos (`RECEIPT_*.json`, `LOCATOR_RESULT_*.json`, `RUN_LOG.txt`) e a pasta `RECOVERED` à conversa de origem.

## 2. Estágio W2 — custódia do HD1 (fronteira física; decisão do titular)

Pré-condições: nenhum job em `D:`/`E:`/`F:`; HD2 permanece conectado; se SATA interno, desligar o PC antes; se o Windows oferecer "Inicializar disco" → **Cancelar**; "Verificar e corrigir" → **não**. Decisões: **D1** (conexão: `SATA_INTERNAL_POWERED_OFF` ou `USB_DOCK`) e **D2** (proteção: `ACCEPT_OS_METADATA_EFFECTS`, `HARDWARE_WRITE_BLOCKER` ou `DISK_READONLY_ATTRIBUTE_SET_BY_OWNER`). Os scripts nunca mudam atributos de disco.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\PERSEU_HD1_RECON_PROBE_V003.ps1" -Mode Inventory
```
```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\PERSEU_HD1_RECON_PROBE_V003.ps1" -Mode Probe
```
Se o Probe der `PASS` (metadados 1530/414020605824 por conjunto, manifesto `416A385C…` íntegro), rode o readback, substituindo os dois valores pelas suas decisões reais:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\PERSEU_HD1_TOP4_READBACK_V001.ps1" -Mode Readback -D1Connection USB_DOCK -D2WriteProtection ACCEPT_OS_METADATA_EFFECTS
```

Duração estimada: cerca de 55 min a 120 MiB/s (cerca de 82 min a 80 MiB/s). Heartbeat a cada 30 s, com progresso, ETA e horário previsto de término. **Ctrl+C** = SAFE_STOP (exit 130) na fronteira de arquivo; rodar **o mesmo comando** retoma do journal sem refazer arquivos já confirmados. O estado ativo fica em `C:\Users\silvi\PERSEU_STATE\TOP4_READBACK_V001\` (fora do OneDrive). Resultado: `PASS` (exit 0) somente com 1530/1530 SHA iguais e conjuntos exatos; `FAIL` (exit 1) lista as divergências em `READBACK_REPORT.json`.

## 3. Estágio W3 — C2 FULL (somente após as fontes serem fixadas pela origem)

A origem, com os bytes recuperados, emite `C2_SOURCE_LOCK_V001.json` (especificação em `C2_SOURCE_LOCK_V001_SPEC.md`) e informa o SHA-256 dele. Coloque o lock em `C:\Users\silvi\OneDrive\Downloads\` e use o SHA fornecido pela origem:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\PERSEU_C2_FULL_LAUNCHER_V001.ps1" -Mode Install -SourceLockPath "C:\Users\silvi\OneDrive\Downloads\C2_SOURCE_LOCK_V001.json" -SourceLockSha256 <SHA_DO_LOCK> -SourceDir "<pasta RECOVERED ou extraída indicada pela origem>"
```
```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\PERSEU_C2_FULL_LAUNCHER_V001.ps1" -Mode Preflight -SourceLockPath "C:\Users\silvi\OneDrive\Downloads\C2_SOURCE_LOCK_V001.json" -SourceLockSha256 <SHA_DO_LOCK>
```
```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\PERSEU_C2_FULL_LAUNCHER_V001.ps1" -Mode Run -SourceLockPath "C:\Users\silvi\OneDrive\Downloads\C2_SOURCE_LOCK_V001.json" -SourceLockSha256 <SHA_DO_LOCK>
```

O `Run` executa o wrapper canônico original do R4R9, inalterado. `C2_FULL_STARTED=YES` só aparece quando o processo do runner foi de fato iniciado. `PASS_C2_FULL_RUN_EXIT_0` exige rc 0, `RUN_STATUS.json` com `state=PASS` e identidades inalteradas após o run; a validação científica (prerregistro V004/D1) continua sendo um gate separado. Ctrl+C no lançador = SAFE_STOP 130, e o runner é reconciliado, nunca morto.

---

Devolva este resultado ao ChatGPT, no projeto “Perseu MT5 (Astra)”, conversa “PERSEU_C2_DISK_SPACE_RECONCILIATION”. Anexe as evidências existentes e cole esta resposta.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Perseu MT5 (Astra) | THREAD=PERSEU_C2_DISK_SPACE_RECONCILIATION`
