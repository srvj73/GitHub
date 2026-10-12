# README_WINDOWS_TARGET — PERSEU_HD1_RECON_PROBE_V002

**Projeto:** Perseu MT5 (Astra) · **Conversa:** PERSEU_C2_DISK_SPACE_RECONCILIATION · **Subfrente:** PERSEU_HD1_ARCHIVE_RECONCILIATION
**Estado do artefato:** `SOURCE_ONLY` — `G0_TARGET_RUNTIME` pendente. Não é runner `READY`.

## 1. O que é entregue

Um único arquivo executável, autocontido (o payload Python está embutido e fixado por SHA-256; não há ZIP a extrair):

| Arquivo | Bytes | SHA-256 |
|---|---:|---|
| `PERSEU_HD1_RECON_PROBE_V002.ps1` | 83499 | `3F78E1A2704DD82C52947061F842AAF72DC9D3F2004BE225FA306DA04FA6E8D5` |
| payload embutido `PERSEU_HD1_RECON_PROBE_V002.py` | 38171 | `2FE0174AFB117209C02A77278BCE2FA1549A1933ECD2259D0D823B6FB84CD675` |

Codificação do `.ps1`: ASCII puro, CRLF, sem BOM (não há bytes não-ASCII, logo `PS1_NON_ASCII_REQUIRES_UTF8_BOM` não se aplica). Payload: UTF-8 sem BOM, LF, ASCII puro.

## 2. Garantias e limites

- **Somente leitura.** O wrapper executa apenas `Get-Disk`, `Get-Partition` e `Get-Volume` (consulta) e o payload lê metadados (e, em `Probe`, o SHA de arquivos pequenos de primeiro nível e do CSV de manifesto). Nenhum `Set-*`, `Initialize-*`, `Format-*`, `chkdsk`, online/offline ou atribuição de letra.
- **Efeitos de evidência apenas** na pasta fixa e absoluta, criada nova a cada execução, **independentemente da pasta atual**:
  `C:\Users\silvi\OneDrive\Downloads\PERSEU_HD1_RECON_V002_RUNS\<MODO>_<yyyyMMdd_HHmmss_fff_PID>\`
  (contém `RUN_LOG.txt`, `RECEIPT_<MODO>.json`, `SNAPSHOT_*.json`, `OUT_*.json` e a cópia materializada do payload).
- **Binding do HD1 por serial+modelo+bytes+DiskNumber+partição** (`6VMCLT3M`, `ST3500418AS`, `500107862016`), nunca por letra. O HD2 (`WD-WCAYUS916314`) é identificado apenas como guarda negativa; nada é lido no HD2.
- Python pinado: `C:\Users\silvi\AppData\Local\Python\pythoncore-3.14-64\python.exe`, invocado com `-I -B -X utf8` (sem `py.exe`, sem cwd, sem bytecode). Ausente ou fora da série 3.14 → `BLOCKED`.
- Exige Windows PowerShell **5.1 Desktop**; outra edição → `BLOCKED` sem criar arquivos.
- Watchdog finito com heartbeat a cada 30 s; **timeout não mata processo**: o PID é reconciliado e o resultado nunca é PASS.
- Códigos de saída: `0=PASS`, `2=BLOCKED_SEM_EFEITOS_PROTEGIDOS`.
- **Efeitos gerenciados pelo sistema operacional** (não controláveis pelo probe): ao montar um volume NTFS, o Windows pode atualizar o log NTFS, `System Volume Information` e carimbos de último acesso. Ver a decisão D2 na seção 5.

## 3. Sequência integrada (a partir de `PS C:\Users\silvi>`, sem `cd`)

Salve o `.ps1` recebido em `C:\Users\silvi\OneDrive\Downloads\` sem renomear.

**Passo 1 — identidade física do arquivo entregue (antes de qualquer execução):**

```powershell
Get-FileHash -LiteralPath "C:\Users\silvi\OneDrive\Downloads\PERSEU_HD1_RECON_PROBE_V002.ps1" -Algorithm SHA256
```

Prossiga somente se o `Hash` for exatamente `3F78E1A2704DD82C52947061F842AAF72DC9D3F2004BE225FA306DA04FA6E8D5`. Divergência = `BLOCKED`; não execute e devolva à origem.

**Passo 2 — G0 no runtime alvo (HD1 continua desconectado; nenhuma troca de disco):**

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\PERSEU_HD1_RECON_PROBE_V002.ps1" -Mode SelfTest
```

Esperado: `RESULT=PASS`, `EXIT_CODE=0`, estágios `PAYLOAD_SELFTEST=PASS` e `INVENTORY_CHECK=PASS`, com o inventário relatando `hd1_count=0` e `hd2_count=1`. O `-ExecutionPolicy Bypass` vale apenas para este processo (escopo `Process`), e somente após o Passo 1.

**Pare aqui.** Devolva ao ChatGPT de origem o console completo e os arquivos `RECEIPT_SELFTEST.json` e `RUN_LOG.txt` da pasta indicada em `RUN_DIR=`. A conexão física do HD1 depende das decisões da seção 5 e de autorização própria.

**Passo 3 — somente após autorização e cumprimento das pré-condições da seção 4, com o HD1 conectado:**

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\PERSEU_HD1_RECON_PROBE_V002.ps1" -Mode Inventory
```

Esperado: `hd1_count=1` e `HD1_STATE=CONNECTED_BOUND`. Se o HD1 aparecer `Offline` ou sem letra, o resultado será `BLOCKED` (`HD1_NOT_ONLINE_NO_MUTATION_ATTEMPTED` ou `HD1_DRIVE_LETTER_CARDINALITY_0`) e **nada deve ser alterado**: devolva à origem.

**Passo 4 — probe de metadados (somente se o Passo 3 deu PASS):**

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\PERSEU_HD1_RECON_PROBE_V002.ps1" -Mode Probe
```

Resultado `PASS` significa apenas: HD1 identificado, manifesto `ARCHIVE_SOURCE_MANIFEST_SHA256.csv` com SHA `416A385C…` e 1530 linhas de dados, e censo de metadados do `PAYLOAD` igual a 1530 arquivos / 414020605824 bytes, conjunto a conjunto. **Não** é prova de custódia (`CUSTODY_FINAL=NOT_PROVEN_FROM_METADATA_ALONE`); o readback SHA integral é um estágio posterior, ainda não construído.

## 4. Pré-condições humanas antes de conectar o HD1 (Passo 3)

1. Nenhum job ativo de cópia, hash, MT5 ou arquivamento gravando em `F:` (HD2) ou em `D:`/`E:`.
2. Não desconectar nem mover o HD2.
3. Se a conexão for SATA interna, desligar o PC antes; não fazer hot-plug interno.
4. Se o Windows exibir **"Inicializar disco"**, clicar **Cancelar**. Se oferecer **"Verificar e corrigir"** (chkdsk), **não aceitar**. Não usar o Gerenciamento de Disco para colocar online, atribuir letra ou formatar.
5. Não abrir o volume do HD1 no Explorer antes do probe (evita miniaturas/indexação).

## 5. Decisões que cabem ao titular/origem (não automatizadas)

- **D1 — Método de conexão do HD1** (SATA interno com desligamento ou dock USB).
- **D2 — Montagem protegida contra escrita:** o probe não controla escritas do próprio NTFS. Opções: (a) aceitar os efeitos de metadados do SO; (b) bloqueador de escrita em hardware; (c) marcar o disco como somente leitura antes de colocá-lo online — isso é **mutação de atributo do disco** e exige autorização e contrato próprios. Nenhuma opção é executada por este artefato.
- **D3 — HD1 Offline por política SAN:** colocá-lo online é mutação; exige autorização própria.

## 6. Frente C2 — localizador de fontes somente leitura (independente do HD1)

| Arquivo | Bytes | SHA-256 |
|---|---:|---|
| `PERSEU_C2_SOURCE_LOCATOR_V001.ps1` | 38640 | `07F665511BEF201BF363F418846174840ECA6E3EEEE385FD71BC4B19E82D935D` |

PowerShell puro (sem Python), ASCII, CRLF, sem BOM. Não depende do HD1 e pode rodar antes de qualquer decisão sobre discos. Lê somente: caminhos exatos derivados dos scripts recuperados; nomes de primeiro nível de `C:\Users\silvi\OneDrive\Downloads` e `C:\Users\silvi\Downloads` com padrões fixos; inventário limitado (≤ 5000 arquivos) da pasta `PACOTE_PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R9_20260921_CONFIRMATORY`, sem seguir links/reparse; e apenas existência e contagem de primeiro nível das três pastas de run em `D:\PerseuRuns`. Placeholders de nuvem (Offline/RecallOnOpen/RecallOnDataAccess) **não** são lidos. Nada em `D:\Base CSV`, `F:`, HD1 ou HD2. Evidência em `C:\Users\silvi\OneDrive\Downloads\PERSEU_C2_SOURCE_LOCATOR_V001_RUNS\<MODO>_<RUN_ID>\`.

**Passo C1 — identidade física:**

```powershell
Get-FileHash -LiteralPath "C:\Users\silvi\OneDrive\Downloads\PERSEU_C2_SOURCE_LOCATOR_V001.ps1" -Algorithm SHA256
```

Prossiga somente com `07F665511BEF201BF363F418846174840ECA6E3EEEE385FD71BC4B19E82D935D`.

**Passo C2 — G0 no alvo:**

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\PERSEU_C2_SOURCE_LOCATOR_V001.ps1" -Mode SelfTest
```

Esperado `RESULT=PASS_SELFTEST_ONLY`, `EXIT_CODE=0` (15 verificações sobre fixture sintética própria; no Windows o teste de placeholder Offline e o de junction são efetivamente exercidos).

**Passo C3 — inventário real:**

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\PERSEU_C2_SOURCE_LOCATOR_V001.ps1" -Mode Locate
```

Esperado `RESULT=PASS_INVENTORY_ONLY`, `EXIT_CODE=0`, e `C2_SOURCE_GATE=BLOCKED` com a lista `C2_BLOCKER=`. **`EXIT_CODE=0` significa apenas que o inventário foi concluído**; a completude das fontes é dada exclusivamente por `C2_SOURCE_GATE`. Devolva à origem o console e `LOCATOR_RESULT_LOCATE.json`.

---

Devolva este resultado ao ChatGPT, no projeto “Perseu MT5 (Astra)”, conversa “PERSEU_C2_DISK_SPACE_RECONCILIATION”. Anexe as evidências existentes e cole esta resposta.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Perseu MT5 (Astra) | THREAD=PERSEU_C2_DISK_SPACE_RECONCILIATION`
