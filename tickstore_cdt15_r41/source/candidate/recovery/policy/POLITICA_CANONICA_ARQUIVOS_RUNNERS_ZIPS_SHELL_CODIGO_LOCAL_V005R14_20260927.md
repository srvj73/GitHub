# POLÍTICA CANÔNICA — ARQUIVOS, RUNNERS, ZIPs, SHELL E SEMÂNTICA DE CÓDIGO LOCAL

**Documento:** `POLITICA_CANONICA_ARQUIVOS_RUNNERS_ZIPS_SHELL_CODIGO_LOCAL_V005R14_20260927`  
**Versão:** V005R14 (revisão da V005R3; substitui a V005R3 de 27/09/2026)  
**Data:** 27/09/2026  
**Status:** **CANÔNICO — OBRIGATÓRIO**  
**Escopo:** todos os projetos técnicos do usuário e todos os assistentes (Chat, Work, Codex, Claude).  
**Prevalência:** para localização de pacotes, ZIP, runners, PowerShell/CMD, Python, logs e execução local, este documento prevalece sobre instruções anteriores incompatíveis ou ambíguas. Uma SPEC de projeto pode **endurecer** estas regras; nunca pode afrouxá-las sem declarar a exceção por escrito, com a justificativa e o escopo.

---

## 0. CONTROLE DE VERSÃO

### 0.1 Delta V005

A V005 **preserva todas as regras da V004**; nenhuma foi removida ou enfraquecida (a rastreabilidade está no Anexo B). As mudanças se agrupam em quatro frentes.

**A. Correções de defeitos da V004** (exemplos que falhariam no ambiente-alvo):

| ID | Defeito na V004 | Correção na V005 |
|---|---|---|
| E1 | O padrão da §9.9 (`& $Exe 2> $ErrPath`) foi dado para um bootstrap que declara `$ErrorActionPreference='Stop'` (§9). No Windows PowerShell 5.1, redirecionar stderr nativo com `Stop` ativo converte a **primeira linha de stderr em erro terminante** (`NativeCommandError`), mesmo com exit code 0. O exemplo reproduzia o problema que a seção pretendia evitar | §9.9 reescrita: `ErrorActionPreference='Continue'` com escopo local só na chamada nativa, sentinela de `$LASTEXITCODE` e helper canônico `Invoke-NativeChecked` (Anexo A) |
| E2 | O exemplo de probe Python da §9.5 tinha o mesmo defeito de E1 | §9.5 passa a usar `Invoke-NativeChecked` |
| E3 | Não havia regra de encoding. No PS 5.1, um `.ps1` UTF-8 **sem BOM** é lido na página de código ANSI: literais com acento (`Nelógica`, `Manutenção`) são corrompidos em runtime, e o gate de parsing (§9.8) **não detecta** isso | Nova §9.11 (encoding) e gate de encoding na autoauditoria |
| E4 | Não havia regra de log. A preferência permanente do usuário (log sempre na pasta correta, independentemente do diretório corrente) não estava codificada | Nova §5.6 |
| E5 | Blocos-resumo de regras duplicados e fora de ordem (o bloco da §9.5 declarava regras definidas só nas §9.6–9.8; algumas chaves apareciam até 4 vezes) | Registro único e deduplicado na §22; as seções citam as chaves sem redeclará-las |
| E6 | `Join-Path` com unidade inexistente lança erro **antes** do bloco `try` principal, e o runner termina sem status nem receipt | §12.4: caminhos de configuração calculados com `[IO.Path]::Combine`; validação de unidade dentro do `try` |
| E7 | A §7.3 recomendava pasta irmã com o basename do ZIP, sem regra para reextração: a segunda extração colidiria com a primeira ou a sobrescreveria | §7.3: se o destino existir, BLOCKED ou novo sufixo de execução; nunca sobrescrever |

**B. Lacunas preenchidas:** convenções de invocação (`py`, crase, grafia `silvi`), Mark-of-the-Web, espaços/acentos/MAX_PATH, cultura invariante em saídas de máquina, schema padrão de receipt, mapa de exit codes, lock de escritor único, dry-run por padrão, gate de autorização, pacote de entrega único, Git, leitura de bordas de arquivos grandes, dados canônicos com identidade vinculada ao caminho.

**C. Usabilidade:** esqueleto canônico de runner PS 5.1 **testado** (Anexo A) com os helpers `Invoke-NativeChecked`, `Assert-FileSha256`, `Write-Log`, `Write-JsonAtomicNew`, lock e receipt.

**D. Organização:** numeração limpa, registro único de regras, anexo de rastreabilidade.

### 0.2 Validação dos exemplos desta versão

- O esqueleto do Anexo A passou pelo parser do PowerShell (0 erros) e foi executado nos cenários BLOCKED (edição de shell, `OutBase` ausente, lock presente, `OutRoot` existente), DRY_RUN e EXECUTE. Nesses testes surgiram e foram corrigidos E6, a colisão de `RunId` no mesmo segundo e a linha `RECEIPT=` apontando para um arquivo não gravado.
- **Limitação declarada da V005 original:** a validação usou PowerShell 7.4 em Linux. Sintaxe e fluxo foram confirmados; o comportamento específico do 5.1 (E1 e E3) era conhecido e documentado, mas o esqueleto integral não havia sido executado em 5.1 naquela revisão.

### 0.3 Delta V005R1 — achados de campo no Windows PowerShell 5.1 / Win32

A V005R1 preserva integralmente a V005 e acrescenta regras derivadas de falhas e gates físicos observados depois da publicação da V005. Nenhuma regra anterior foi afrouxada.

| ID | Achado de campo | Regra acrescentada na V005R1 |
|---|---|---|
| R1-01 | Um runner com erro de sintaxe não chega a executar o próprio `ParseFile($PSCommandPath)`. Logo, **presença de self-parse no arquivo não é prova de parse** | §9.8: parse externo no shell-alvo ou aceitação DRY-RUN sem efeitos antes de qualquer execução com efeitos; `SELF_PARSE_PRESENT` é inspeção, nunca `POWERSHELL_PARSE_GATE=PASS` |
| R1-02 | `catch[IO.IOException]` falhou no parser do Windows PowerShell 5.1; a sintaxe aceita é `catch [IO.IOException] { ... }` | §9.8: forma canônica de `catch` tipado e obrigação de validar no parser-alvo |
| R1-03 | Mesmo com `ErrorActionPreference='Continue'`, o redirecionamento `2>` do PS 5.1 pode produzir **ErrorRecord formatado pelo PowerShell** (`NativeCommandError`, localização do script, `RemoteException`) no arquivo capturado | §9.9: stderr capturado por operador do PowerShell é **diagnóstico normalizado**, não stream bruto; quando bytes/texto bruto forem requisito, usar `System.Diagnostics.Process` com `RedirectStandardError` |
| R1-04 | Um `CreateFileW` usado para pin de diretórios ancestrais pedia `FILE_ADD_FILE (0x2)` sem necessidade. A máscara abriu em diretórios do usuário, mas recebeu `ERROR_ACCESS_DENIED (5)` em `C:\` e `C:\Users`; remover apenas esse direito resolveu e manteve a validação de identidade | §12.6: **mínimo privilégio para access masks Win32**; direito de criar/escrever é proibido em handle de leitura/pin/identidade salvo necessidade provada |
| R1-05 | Processo terminado pode continuar contabilizado no Job enquanto referências/handles ao objeto de processo permanecerem vivos | §14.1: antes de census final de Job, processo deve ter terminado **e** seus handles/referências OS devem ser liberados deterministicamente; não depender de GC |
| R1-06 | `PREP_WORKER_ERROR` correto foi mascarado por `PREP_RESIDUAL_JOB_PROCESSES` durante `finally/close()` | §14.2: erro primário precede erro de cleanup; cleanup secundário é anexado/registrado, nunca substitui a causa original |
| R1-07 | Teste executado dentro de Job preexistente não pode presumir que o conjunto inicial de membros seja apenas `{current_pid}` | §14.3: harness captura baseline físico antes de spawn e exige retorno exato ao baseline; isso **não** enfraquece invariantes de produção de Job dedicado |
| R1-08 | `os.symlink()` falhou com WinError 1314 por privilégio ausente, embora o objetivo do teste fosse somente provar rejeição de reparse point | §17.5: fixture obrigatória não depende de privilégio opcional quando existe equivalente não privilegiado (ex.: junction); não converter gate obrigatório em skip |
| R1-09 | Uma candidata com deltas Win32/process/security falhou com 32 resultados ruins; o DRY-RUN-only impediu instalação e permitiu corrigir até 68/70 sem tocar no workspace | §17.4: deltas nativos/de segurança/processos passam primeiro por **runner de qualificação incapaz de instalar**; instalação vem em ação separada só após PASS integral |
| R1-10 | `unittest` e outras ferramentas podem escrever progresso normal no stderr; presença de stderr não equivale a falha | §9.9 e §17.1: exit code + artefato de resultado são autoridade; `stderr != vazio` nunca é gate FAIL por si só |
| R1-11 | Um DRY-RUN que executa validações substantivas é uma execução auditável, ainda que não altere projeto/dado | §13.3: DRY-RUN substantivo deve gerar log/receipt; `RECEIPT=NOT_WRITTEN` só é aceitável quando o runner não chegou a inicializar evidência (ex.: parser falhou antes de executar) ou em preflight console-only explicitamente declarado |
| R1-12 | Alguns achados aparentes eram apenas hipóteses (ex.: suspeita inicial de serialização de `Generic.List[object]`) e não foram fisicamente provados | Governança: hipótese não comprovada **não vira regra canônica**. Só entram nesta revisão comportamentos reproduzidos ou corroborados por documentação de plataforma |

### 0.4 Base técnica corroboradora da V005R1

Além dos testes físicos locais, os pontos Win32 foram conferidos contra documentação da Microsoft:

- `FILE_ADD_FILE (0x2)` em diretório significa direito de criar arquivo;
- `CreateFile` admite `dwDesiredAccess=0` para determinadas consultas de metadata e exige apenas os direitos necessários à operação;
- handles de processo permanecem válidos até `CloseHandle`, mesmo depois do término do processo;
- `JOBOBJECT_BASIC_ACCOUNTING_INFORMATION.ActiveProcesses` só é decrementado depois que o processo termina **e todas as referências ao processo são liberadas**;
- criação de symbolic link pode exigir `SeCreateSymbolicLinkPrivilege`/Developer Mode, enquanto uma fixture de reparse pode usar mecanismo alternativo compatível com o objetivo do teste.

A regra canônica é sempre a semântica mais restritiva descrita neste documento; números de access mask específicos de um projeto (por exemplo `0x001000A1` no TICKSTORE) **não** são promovidos a constante universal.

---

### 0.5 Delta V005R2 — ownership de processos em Job compartilhado e atualização automática da política

A V005R2 corrige uma regra introduzida na V005R1 e acrescenta uma regra de governança solicitada explicitamente pelo usuário.

| ID | Descoberta / decisão | Regra V005R2 |
|---|---|---|
| R2-01 | Em um harness executado dentro de Job compartilhado, o conjunto global de PIDs sofreu churn externo durante ~3 s: surgiu PID que não existia no baseline e desapareceram vários PIDs antigos | §14.3: **proibido** exigir `FINAL_JOB_MEMBERS == BASELINE_JOB_MEMBERS` em Job compartilhado |
| R2-02 | O supervisor já recebe dos workers `pid + process_creation_time`, permitindo distinguir worker próprio de PID reciclado | §14.3: rastrear identidades próprias `(PID, creation_time)` e provar que nenhuma identidade própria permanece após cleanup |
| R2-03 | A propriedade global estrita continua necessária em Job dedicado de produção | §14.3: lançar pelo root-loader/Job dedicado e validar ali o invariante global mais forte |
| R2-04 | O usuário determinou que toda nova descoberta real de erro/regra de sintaxe, Python, PowerShell, shell, runner, Win32/PInvoke ou execução local atualize a documentação canônica | §17.6: nova descoberta comprovada gera **imediatamente** nova revisão versionada da política; a versão anterior fica preservada |
| R2-05 | Uma hipótese anterior de igualdade global do Job foi refutada no run seguinte | §17.6: regra canônica nova também é falsificável; se evidência posterior a refutar, emitir revisão corretiva imediatamente, sem preservar a regra errada por compatibilidade |

A correção R2-01 **não revoga** as regras V005R1 de fechamento determinístico de handles nem de precedência do erro primário. Elas permanecem vigentes.

---

### 0.6 Delta V005R3 — binding .NET/PowerShell 5.1 em mutação crítica e semântica de efeitos

A V005R3 incorpora um achado físico do primeiro `-Execute` do Gate 2 TICKSTORE. O runner chegou à instalação com todos os gates prévios PASS, criou backup de evidência, mas a primeira chamada:

```powershell
[System.IO.File]::Replace($Partial, $Target, $null, $true)
```

falhou no Windows PowerShell 5.1 com:

```text
ArgumentException / "O caminho tem um formato inválido."
```

antes de substituir qualquer arquivo do workspace.

A documentação do .NET permite `null` em `destinationBackupFileName`. Portanto esta revisão **não** declara que `File.Replace` proíbe `null`; registra uma incompatibilidade física da forma de chamada/binding usada no PowerShell 5.1 do ambiente-alvo.

| ID | Descoberta | Regra V005R3 |
|---|---|---|
| R3-01 | Contrato documentado da API não foi suficiente para garantir que a forma de chamada PowerShell 5.1 com `$null` funcionasse no caminho crítico | §12.7: overload .NET crítico + argumento `$null` exige probe no runtime-alvo com a mesma assinatura/forma de argumentos |
| R3-02 | `File.Replace(...,$null,$true)` falhou antes da mutação | §12.7: em runner crítico, preferir backup path absoluto, não nulo, no mesmo volume; validar backup/resultados |
| R3-03 | O runner havia feito escrita de evidência/backup, mas corretamente reportou que o workspace protegido não havia sido alterado | §13.3.1: separar `PROTECTED_STATE_EFFECTS_OCCURRED` de `EVIDENCE_WRITES_OCCURRED`; `EFFECTS_OCCURRED` deve declarar seu escopo |
| R3-04 | A falha só apareceu no primeiro caminho de instalação real; o DRY-RUN não exercitou o overload efetivo | §17.4: qualificador pré-instalação de operação nativa/.NET crítica deve exercitar a **mesma primitive/overload/argument shape** em fixture descartável antes de autorizar efeitos |
| R3-05 | `EFFECTS_OCCURRED=NO` significa que o estado protegido está intacto, mas não que repetir um runner com defeito determinístico tenha valor | §13.3.2: separar segurança de rerun de autorização/utilidade de rerun |

---
### 0.7 Delta V005R4 — identificador de contrato não é nome de artefato

A V005R4 incorpora um achado físico da pré-auditoria Stage A do bundle canário TICKSTORE.

O artefato homologado chamado:

```text
INLINE_ROOT_LOADER_V004_R1R1.ps1
```

possui SHA-256:

```text
CFAE1BE4F834A896CEC29E74F18D6501DEBF91EFCAC6EE4AFBF551FFC8E05C78
```

mas o seu contrato lógico de external anchor exige:

```text
inline_root_loader_revision = INLINE_ROOT_LOADER_V004_R1
```

O executável congelado no bundle, por outro lado, exigia:

```text
inline_root_loader_revision = INLINE_ROOT_LOADER_V004_R1R1
```

e o `OWNER_GATE.json` publicava `R1R1`.

Não existe um único external anchor capaz de satisfazer simultaneamente essas duas exigências. O bundle era íntegro por hash/CRC/manifest, mas não era executável sob o protocolo completo.

A evidência histórica do próprio Gate1 confirma que o loader corrigido `R1R1.ps1` continuava gerando o anchor lógico `INLINE_ROOT_LOADER_V004_R1`. Logo, o sufixo do nome físico do arquivo foi indevidamente promovido a identificador de contrato em uma etapa posterior.

| ID | Descoberta | Regra V005R4 |
|---|---|---|
| R4-01 | Nome/revisão física de artefato foi confundido com identificador lógico de protocolo | §12.8: nome do arquivo, label de build e contract ID são namespaces distintos |
| R4-02 | Hashes e testes locais PASS não provaram que root loader e executável aceitavam o mesmo anchor | §17.5: release gate exige satisfatibilidade end-to-end de todos os contract IDs compartilhados |
| R4-03 | Static scan apenas verificava presença de `R1R1`, não o valor exato esperado por cada consumidor | §17.5: extrair e comparar valores efetivos dos produtores/consumidores; presença textual não basta |
| R4-04 | Bundle íntegro podia ser logicamente inexequível | §17.5: `BUNDLE_INTEGRITY_PASS` e `PROTOCOL_ADMISSION_COMPATIBILITY_PASS` são gates independentes |

---
## 1. OBJETIVO

Eliminar erros causados por:

- caminho corrente presumido;
- ZIP extraído manualmente de forma diferente;
- runners dependentes de `cd`;
- caminhos relativos;
- arquivos, **logs** e receipts criados no lugar errado;
- sobrescrita de evidência;
- shell diferente do esperado;
- interpretação de texto como PASS em vez de exit code;
- comportamento não determinístico entre Python e PowerShell;
- **encoding implícito** (ANSI, UTF-16, BOM) e **cultura implícita** (vírgula decimal, datas `dd/MM`);
- falha silenciosa;
- retomada não segura;
- **execução concorrente** do mesmo runner.

---

## 2. SHELL, PONTO INICIAL E CONVENÇÕES DE INVOCAÇÃO

### 2.1 Shell padrão

```text
SHELL_PREFERENCE=Windows PowerShell 5.1
PSEDITION=Desktop
DEFAULT_EXE=C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe
```

`pwsh` 7, ISE, CMD ou outro shell só são usados com razão técnica explícita. Todo runner que dependa de semântica do 5.1 deve **verificar a edição em runtime** e bloquear se ela divergir (ver o Anexo A: `SHELL_NOT_WINDOWS_POWERSHELL_5_1`).

Antes de cada comando local, a instrução deve indicar:

```text
AMBIENTE=PowerShell
```

Se CMD for realmente necessário:

```text
AMBIENTE=CMD
MOTIVO_CMD=<razão técnica específica>
```

### 2.2 Diretório corrente inicial

Todo comando fornecido ao usuário presume:

```text
PS C:\Users\silvi>
```

A grafia é `silvi` (nunca `silvio`). O usuário **não deve precisar de `cd` manual** antes de colar um comando.

### 2.3 Convenções de invocação

| Tema | Regra |
|---|---|
| Continuação de linha no PowerShell | Crase (`` ` ``) como **último** caractere da linha, sem espaço depois. `^` é sintaxe de CMD e é **proibido** em comandos PowerShell |
| Preferência de forma | Comando de uma linha; continuação só para comandos muito longos |
| Python no terminal do usuário | `py` (launcher), nunca `python`. Com versão exigida: `py -3.14` |
| Python dentro de runner com runtime pinado | Caminho absoluto do interpretador certificado (§11.1). O launcher `py -X.Y` só vale quando a SPEC aceita qualquer build daquela versão; mesmo assim, o runner registra `sys.executable` e `sys.version` no receipt |
| Invocação de runner | `powershell.exe -NoProfile -ExecutionPolicy Bypass -File '<absoluto>'` |

---

## 3. CAMINHOS — REGRA GERAL

### 3.1 Caminhos absolutos

Comandos destinados ao usuário usam caminhos absolutos sempre que a localização for conhecida.

Evitar:

```powershell
.\runner.ps1
python script.py
cd pasta
```

Preferir:

```powershell
& 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -NoProfile -ExecutionPolicy Bypass -File 'D:\Projeto\Pacote\RUNNER.ps1'
```

### 3.2 Arquivos acompanhantes

| Linguagem | Âncora do pacote |
|---|---|
| PowerShell | `$PSScriptRoot` |
| CMD/BAT | `%~dp0` |
| Python | `Path(__file__).resolve().parent`, ou caminho recebido/configurado |

É proibido usar `os.getcwd()`, `Path.cwd()`, `Get-Location` ou `.\` como identidade do pacote ou da raiz do projeto.

### 3.3 Espaços, acentos, colchetes e tamanho de caminho

- Caminhos com espaço (`D:\Base CSV`) sempre entre aspas simples no PowerShell e aspas duplas no CMD.
- Caminhos com colchetes `[` `]` exigem `-LiteralPath` (com `-Path`, eles são interpretados como wildcard).
- Caminhos com acento (`Nelógica`, `Manutenção`) só podem aparecer como literal em `.ps1` salvo em UTF-8 **com BOM** (§9.11). Alternativa preferida: receber o caminho de configuração ou descobri-lo por enumeração.
- Caminhos acima de 260 caracteres (MAX_PATH): o runner deve medir e bloquear (`PATH_TOO_LONG`) em vez de falhar no meio de uma cópia. Nomes versionados longos (§6) tornam isso realista.

### 3.4 Marcador de raiz

Quando um script precisa descobrir a raiz de um projeto subindo diretórios, o marcador deve ser um arquivo **dedicado e sem outra função** (ex.: `PROJECT_ROOT.marker`), e não um arquivo de configuração que possa ser movido por outro motivo.

---

## 4. DOWNLOADS — ZONA DE ENTRADA, NÃO RAIZ DE PROJETO

Pacotes entregues pelo Chat, Work, Codex ou Claude normalmente chegam à pasta de Downloads, que é **zona de entrada**, não raiz canônica. O caminho físico não deve ser inventado.

Candidatos já observados:

```text
C:\Users\silvi\Downloads
C:\Users\silvi\OneDrive\Downloads
```

Regras:

- caminho exato já mostrado → usar o caminho exato;
- não comprovado → o bootstrap procura nos candidatos conhecidos, com cardinalidade normalizada (§9.4);
- mais de um arquivo com o mesmo nome e hashes diferentes → parar;
- nunca escolher silenciosamente o primeiro;
- arquivo em pasta sincronizada pelo OneDrive pode estar **somente na nuvem** (placeholder). O runner deve ler o hash completo antes de usar; se a leitura falhar ou demorar de forma anômala, BLOCKED (`FILE_NOT_LOCALLY_AVAILABLE`).

---

## 5. LOCAL DE SALVAMENTO — CLASSES DE ARQUIVO

### 5.1 Pacote recebido / artefato de transferência
Fica inicialmente em Downloads (ZIP de handoff, pacote Codex, pacote de auditoria, runner portátil, documento canônico).

### 5.2 Repositório de código
Alterações de código ficam na raiz Git já existente do projeto (§20). É proibido criar uma raiz canônica nova em Downloads por conveniência. Raiz não comprovada → bloquear ou pedir configuração.

### 5.3 Dados canônicos
Dados homologados permanecem em seus diretórios canônicos. Runners não movem, renomeiam, reorganizam, deletam, recompactam nem substituem dados canônicos sem autorização explícita e gate específico.

**Identidade vinculada ao caminho:** quando selos, manifestos, journals ou certificados registram o caminho absoluto, a data de modificação ou o identificador de arquivo de um dado canônico, esse dado é **imóvel**. Movê-lo, renomeá-lo, copiá-lo ou fazer `touch` invalida a evidência e exige nova versão do componente que selou. Exemplo real: o runner TICKSTORE RC1 vincula `normalized_path`, `mtime_ns` e `st_ino` do CSV mensal.

### 5.4 Saídas de execução
Saídas vão para `out_root` explícito, absoluto, **novo por execução** e versionado:

```text
<drive adequado>:\<ProjetoRuns>\<NOME_EXECUCAO_VERSIONADO>_<RUN_ID>
```

`RUN_ID` = `yyyyMMdd_HHmmss_fff_<PID>`, para evitar colisão entre execuções no mesmo segundo. Runner pesado não usa a pasta do pacote fonte como output.

### 5.5 Evidências e auditorias
Evidência de execução tem diretório próprio. Falhas preservam logs e receipts até o diagnóstico fechar. É proibido sobrescrever evidência histórica para "limpar" uma falha.

### 5.6 Logs — sempre no local correto, independentemente do diretório corrente

Regra permanente do usuário, agora canônica:

- o caminho do log é **absoluto e determinado pelo runner** (a partir de `out_root`, de configuração fixa ou de `$PSScriptRoot`/`__file__`), **nunca** pelo diretório corrente;
- local padrão: `<out_root>\logs\`; para pipelines que já têm pasta de saída canônica (ex.: `<raiz do projeto>\outputs`), usar essa pasta resolvida pela raiz do projeto;
- o runner imprime o caminho absoluto do log no início e no fim;
- cada execução gera log novo; nunca acrescentar a log de outra execução;
- encoding UTF-8 sem BOM, carimbo ISO-8601 com fuso (`2026-09-27T08:46:00.000-03:00`);
- não usar `>`/`Out-File` do PS 5.1 para logs (gravam UTF-16LE); usar `[IO.File]::AppendAllText(..., UTF8Encoding($false))` (Anexo A, `Write-Log`);
- `Start-Transcript` é complementar, nunca a única evidência (não captura de forma fiel a saída de processos nativos).

### 5.7 Estado ativo × relatório
Checkpoints, journals, locks e arquivos de proveniência lidos em runtime são **estado ativo**, mesmo quando ficam numa pasta de saída. Eles não podem ser tratados como log em limpezas nem movidos por padrão de nome. Estado ativo deve ter subdiretório próprio (ex.: `outputs\_state\`), separado de `outputs\_runs\`.

---

## 6. NOMENCLATURA, VERSIONAMENTO E PACOTE DE ENTREGA

Arquivos e diretórios relevantes incluem, quando aplicável: projeto, fase, versão, revisão, data e papel do artefato.

```text
MINOTAURO_R1R11_V004R1_OWNER_GATES_20260927
```

- Nova tentativa relevante cria nova revisão (`R1`, `R2`…) ou nova raiz versionada.
- **Entrega com mais de um arquivo** = um único ZIP versionado com o conjunto completo, nunca arquivos avulsos.
- **Nome de ZIP de entrega nunca é reutilizado**, mesmo para uma correção mínima: evita que o navegador gere `nome (1).zip` e que o bootstrap encontre dois candidatos (§4).
- Entregas do Claude seguem o prefixo `CLD_SRVJ_V##`, com número crescente por entrega.

---

## 7. TRATAMENTO CANÔNICO DE ZIP

### 7.1 ZIP fonte é imutável
O ZIP recebido é evidência e não é modificado in-place.

### 7.2 Antes de extrair
Havendo SHA-256 esperado: confirmar a existência, calcular o hash, comparar exatamente (§16.2) e, se divergir, parar.

### 7.3 Extração
- extrair para pasta **nova e limpa**; preferencialmente pasta irmã com o basename do ZIP;
- **se o destino já existir:** BLOCKED (`EXTRACT_DIR_EXISTS`) ou novo destino com sufixo `_<RUN_ID>`; nunca extrair por cima;
- não misturar com extração anterior nem extrair sobre evidência;
- não exigir extração manual quando o bootstrap puder fazê-la com segurança.

### 7.4 Segurança estrutural (validar **antes** de extrair)
CRC; path traversal (`..`); caminhos absolutos ou com unidade; entradas duplicadas, **inclusive duplicatas que só diferem em maiúsculas/minúsculas**, que colidem no NTFS; membros extras; manifesto interno; SHA-256 dos membros quando disponível.

`Expand-Archive` não executa todas essas verificações. Para pacotes selados, validar a lista de entradas (via `System.IO.Compression.ZipFile` ou `zipfile` do Python) antes de extrair.

### 7.5 Manifesto
Se houver `SHA256SUMS`:

```text
MANIFEST_MUST_PASS=YES
EXTRA_FILES_IN_SEALED_PACKAGE=FORBIDDEN
```

Exceção: arquivos que a SPEC declara serem criados pelo owner fora da árvore selada (`config.json`, outputs, logs).

### 7.6 Autoextração / bootstrap
Padrão preferido para pacotes portáteis: (1) localizar o ZIP em Downloads; (2) validar a identidade; (3) extrair para diretório novo; (4) **desbloquear o Mark-of-the-Web** (§7.7); (5) localizar o runner pela raiz extraída; (6) executar por caminho absoluto; (7) nunca exigir `Set-Location` manual.

### 7.7 Mark-of-the-Web
Arquivos baixados carregam a marca `Zone.Identifier`, que pode fazer o PowerShell recusar ou alertar sobre scripts extraídos. Depois de validar o hash do ZIP (e somente depois), o bootstrap aplica `Unblock-File -LiteralPath` aos `.ps1`, `.psm1`, `.cmd` e `.bat` extraídos. É proibido desbloquear um arquivo cujo hash não foi validado.

---

## 8. `$PSScriptRoot` É A ÂNCORA DE PACOTES POWERSHELL

```powershell
$Root = $PSScriptRoot
Join-Path $PSScriptRoot 'arquivo'
```

`Get-Location` e `.\arquivo` não são identidade do pacote: o diretório corrente é contexto do usuário, não do runner. `$PSScriptRoot` só existe quando o script é executado por `-File` ou por `&` com caminho de arquivo; código colado no console não o tem e deve usar caminho absoluto explícito.

---

## 9. BOOTSTRAP POWERSHELL — SEMÂNTICA CANÔNICA

Por padrão:

```powershell
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
```

quando compatível. Obrigações:

- validar pré-condições antes de criar efeitos;
- `-LiteralPath` para caminhos conhecidos;
- `Join-Path` apenas após validar a unidade (§12.4);
- verificar o exit code de processos externos;
- parar no primeiro gate bloqueante;
- não continuar após identidade divergente;
- imprimir resumo final inequívoco (§13.4).

### 9.1 Exit code é autoridade
PASS/FAIL de executável externo depende do exit code e dos artefatos esperados, **não** de procurar `PASS` no texto. Se um pipeline puder obscurecer `$LASTEXITCODE`, capturá-lo imediatamente e tratar a falha de forma fail-closed.

### 9.2 Stdout/stderr
A ordem relativa entre stdout e stderr não é lógica de gate.

### 9.3 `python -u`
Quando saída ao vivo for necessária, usar `-u` (`PYTHON_UNBUFFERED=YES`). Isso afeta visibilidade, não o PASS/FAIL.

### 9.4 Cardinalidade 0/1/N no Windows PowerShell 5.1
No 5.1, uma pipeline com um único item retorna um **escalar**. Sempre que o código depender de `.Count`, de indexação `[0]`, de iteração 0/1/N ou de comparação de quantidade de candidatos, normalizar para array:

```powershell
$Candidates = @(
    @(
        'C:\Users\silvi\Downloads\runner.ps1'
        'C:\Users\silvi\OneDrive\Downloads\runner.ps1'
    ) | Where-Object {
        Test-Path -LiteralPath $_ -PathType Leaf
    }
)

if ($Candidates.Count -ne 1) {
    throw "DISCOVERY_BLOCKED: FOUND=$($Candidates.Count)"
}

$Runner = [string]$Candidates[0]
```

É proibido indexar resultado de pipeline não normalizado: se `$Candidates` for uma string escalar, `$Candidates[0]` é o **primeiro caractere**.

Regras: `PS_CARDINALITY_NORMALIZE`, `PS_INDEX_UNNORMALIZED_FORBIDDEN` (§22).

### 9.5 PowerShell 5.1 → Python: `python -c` e quoting nativo
No 5.1, argumentos passados a executáveis nativos sofrem serialização/quoting própria. Código Python com aspas, JSON, barras invertidas, quebras de linha ou expressões compostas pode chegar ao interpretador diferente do escrito. Em particular, **argumento contendo aspas duplas é corrompido**.

Padrão obrigatório para probes, gates, hashes, identidade de runtime ou qualquer execução fail-closed:

1. criar `.py` temporário;
2. gravar em UTF-8 **sem BOM**;
3. executar o arquivo pelo interpretador pinado, **via `Invoke-NativeChecked`** (Anexo A);
4. o helper já separa stderr, captura o exit code e limpa os temporários;
5. remover o `.py` no `finally`.

```powershell
$ProbePath = [IO.Path]::Combine([IO.Path]::GetTempPath(), ('probe_' + [guid]::NewGuid().ToString('N') + '.py'))
try {
    $ProbeCode = @'
import json
import sys
print(json.dumps({"python": ".".join(map(str, sys.version_info[:3])), "exe": sys.executable}))
'@
    [IO.File]::WriteAllText($ProbePath, $ProbeCode, (New-Object Text.UTF8Encoding($false)))
    $R = Invoke-NativeChecked -FilePath $Python -ArgumentList @('-B', $ProbePath)
    $Probe = ($R.Stdout -join "`n") | ConvertFrom-Json
}
finally {
    Remove-Item -LiteralPath $ProbePath -Force -ErrorAction SilentlyContinue
}
```

(`GetTempFileName()` cria um arquivo `.tmp`; para scripts Python, preferir nome explícito `.py`.)

`python -c` trivial só é aceitável quando não depende de quoting complexo e não é parte de gate canônico. Nenhum argumento nativo pode carregar aspas duplas; dados complexos vão por arquivo.

Regras: `PS51_PYTHON_DASH_C_NONTRIVIAL_FORBIDDEN`, `PS51_NATIVE_ARG_DOUBLE_QUOTE_FORBIDDEN`, `CRITICAL_PYTHON_PROBE_USE_SCRIPT_FILE`, `TEMP_FILE_CLEANUP_IN_FINALLY`.

### 9.6 `Set-StrictMode` e propriedades opcionais de JSON/PSCustomObject
Com StrictMode ativo, acessar uma propriedade inexistente de objeto vindo de `ConvertFrom-Json` lança `PropertyNotFoundStrict`. Receipts PASS e FAIL têm schemas **deliberadamente diferentes** (PASS pode ter `result`; FAIL pode ter `error`/`traceback` sem `result`).

Proibido:

```powershell
if ($null -ne $Receipt.result) { ... }
```

Padrão obrigatório:

```powershell
function Get-OptionalPropertyValue {
    param(
        [Parameter(Mandatory=$true)][AllowNull()]$Object,
        [Parameter(Mandatory=$true)][string]$Name
    )
    if ($null -eq $Object) { return $null }
    $Property = $Object.PSObject.Properties[$Name]
    if ($null -eq $Property) { return $null }
    return $Property.Value
}

function Get-RequiredPropertyValue {
    param(
        [Parameter(Mandatory=$true)]$Object,
        [Parameter(Mandatory=$true)][string]$Name
    )
    $Property = $Object.PSObject.Properties[$Name]
    if ($null -eq $Property) { throw "REQUIRED_PROPERTY_MISSING=$Name" }
    return $Property.Value
}
```

(Ajuste V005: `[AllowNull()]` em `$Object`. Sem ele, um parâmetro `Mandatory` rejeita `$null` antes de chegar à checagem interna.)

Regras: `STRICTMODE_OPTIONAL_PROPERTY_DIRECT_ACCESS_FORBIDDEN`, `JSON_OPTIONAL_PROPERTY_VIA_PSOBJECT`, `PASS_FAIL_RECEIPT_SCHEMA_MAY_DIFFER`, `FAIL_RECEIPT_NOT_PARSED_AS_PASS`.

### 9.7 Falha de gate não pode ser mascarada por erro do wrapper
Quando o processo filho já produziu resultado autoritativo (ex.: `G4=FAIL`), erro posterior do wrapper é **secundário**. O wrapper deve:

1. preservar o exit code nativo;
2. tentar coletar a evidência disponível;
3. nunca transformar FAIL em PASS;
4. nunca transformar FAIL de gate em "erro de sintaxe";
5. registrar à parte `WRAPPER_COLLECTION_ERROR`;
6. não rerodar automaticamente gate one-shot.

Regras: `CHILD_GATE_RESULT_PRECEDENCE`, `ONE_SHOT_GATE_AUTO_RERUN_FORBIDDEN`, `WRAPPER_MUST_SUPPORT_FAIL_SCHEMA`.

### 9.8 Gate obrigatório de sintaxe antes de executar runner gerado
Todo `.ps1` gerado ou revisado passa pelo parser **antes** de qualquer execução que crie, altere ou consuma estado:

```powershell
$Tokens = $null
$Errors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($Runner, [ref]$Tokens, [ref]$Errors)
if (@($Errors).Count -ne 0) {
    $Errors | ForEach-Object { Write-Host "POWERSHELL_PARSE_ERROR=$($_.Message) L$($_.Extent.StartLineNumber)" }
    throw "POWERSHELL_PARSE_GATE_FAIL errors=$(@($Errors).Count)"
}
Write-Host 'POWERSHELL_PARSE_GATE=PASS'
```

Para Python sem efeitos na importação: `py_compile.compile(<arquivo>, doraise=True)` ou `python -m py_compile <arquivo>`.

O gate sintático **não substitui** os testes de schema/StrictMode nem o gate de encoding (§9.11): os três são cumulativos.

#### 9.8.1 Self-parse não é gate de parse pré-execução

Um candidato `.ps1` **não pode provar a própria sintaxe executando**:

```powershell
[System.Management.Automation.Language.Parser]::ParseFile($PSCommandPath, ...)
```

porque, se existir erro sintático no próprio candidato, o Windows PowerShell falha **antes de executar a primeira linha**. Portanto:

1. `SELF_PARSE_PRESENT=PASS` significa somente **inspeção estrutural**;
2. `POWERSHELL_PARSE_GATE=PASS` só pode ser declarado quando o parser realmente foi executado sobre os bytes candidatos;
3. quando o ambiente que gerou o arquivo não dispõe de Windows PowerShell 5.1, a entrega declara explicitamente:
   ```text
   POWERSHELL_5_1_PARSE_EXECUTED_HERE=NO
   POWERSHELL_5_1_PARSE_STATUS=REQUIRES_LOCAL_ACCEPTANCE
   ```
4. antes de qualquer `-Execute`, o PC alvo faz **uma aceitação sem efeitos**: parse externo por wrapper confiável ou execução DRY-RUN cuja própria semântica proíbe efeitos;
5. o self-parse interno pode permanecer como defesa secundária contra troca do arquivo em disco, mas nunca substitui os itens 2–4.

Forma canônica de `catch` tipado no PowerShell:

```powershell
try {
    # ...
}
catch [System.IO.IOException] {
    # ...
}
```

Não usar `catch[System.IO.IOException]`: essa forma produziu erro de parser no Windows PowerShell 5.1 durante teste de campo.

Regras: `PS_PARSE_BEFORE_EFFECT`, `PS_TARGET_SHELL_PARSE_MUST_BE_EXECUTED_OR_LOCALLY_ACCEPTED`, `SELF_PARSE_PRESENT_IS_NOT_PARSE_PROOF`, `PS_TYPED_CATCH_CANONICAL_SYNTAX`, `PY_COMPILE_BEFORE_EFFECT_WHEN_APPLICABLE`, `PARSE_PASS_NOT_RUNTIME_PASS`.

### 9.9 Executável nativo, stderr e `NativeCommandError` no PowerShell 5.1 — **corrigido na V005**

**Fato do Windows PowerShell 5.1:** com `$ErrorActionPreference = 'Stop'`, **qualquer** redirecionamento do stderr de um executável nativo (`2>&1`, `2> arquivo`, `2>$null`) transforma a primeira linha de stderr em erro terminante. Isso vale mesmo que o processo termine com exit 0, e ocorre com frequência porque Python, Git e compiladores usam stderr para avisos e progresso. (No PowerShell 7.2+ o comportamento mudou; não depender disso.)

Consequências:

- `$Out = @(& $Exe $Args 2>&1)` é proibido em gate crítico;
- `$Out = @(& $Exe $Args 2> $ErrPath)` **também é proibido** enquanto `ErrorActionPreference` estiver em `Stop` (era o exemplo da V004);
- a chamada nativa deve ocorrer com `ErrorActionPreference='Continue'` em escopo local, restaurado no `finally`;
- `$LASTEXITCODE` deve ser pré-carregado com sentinela: se o executável não rodar, o valor anterior não pode ser confundido com o atual;
- stderr é exibido e registrado depois, nunca decide o gate;
- no 5.1, o arquivo gerado por `2>` fica em UTF-16LE; ler com `[IO.File]::ReadAllText`, que detecta o BOM.

Implementação canônica: `Invoke-NativeChecked` (Anexo A), que também exige caminho absoluto do executável e recusa argumentos com aspas duplas (§9.5).

#### 9.9.1 Stderr capturado pelo PowerShell 5.1 não é stream bruto

Mesmo com `ErrorActionPreference='Continue'`, `2> arquivo` passa pela camada de streams/erros do Windows PowerShell 5.1. Na prática, o arquivo pode conter formatação de `ErrorRecord` (`<exe> : ...`, localização `No <script>:<linha>`, `RemoteException`, `FullyQualifiedErrorId`) além do texto emitido pelo processo nativo.

Consequências canônicas:

- o campo retornado por `Invoke-NativeChecked` é **diagnóstico de stderr observado pelo PowerShell**, não garantia de bytes/texto bruto do descritor 2;
- não fazer parser de protocolo, JSON, hash, cardinalidade ou causalidade com base nesse texto;
- `stderr` não vazio **não é FAIL**; Python `unittest`, Git, compiladores e outras ferramentas escrevem progresso/avisos normais ali;
- gate de processo nativo usa exit code + artefatos/receipts esperados;
- se o contrato exigir stderr bruto ou ordem exata de stdout/stderr, usar `System.Diagnostics.Process` (`UseShellExecute=false`, `RedirectStandardOutput=true`, `RedirectStandardError=true`) ou wrapper equivalente que não use os operadores de redirecionamento do PowerShell.

Regras: `NATIVE_EXIT_CODE_AUTHORITATIVE`, `NATIVE_STDERR_MUST_NOT_OVERRIDE_EXIT_CODE`, `NATIVE_STDERR_NONEMPTY_IS_NOT_FAILURE`, `PS51_REDIRECTED_NATIVE_STDERR_IS_NOT_RAW`, `RAW_NATIVE_STDERR_USE_SYSTEM_DIAGNOSTICS_PROCESS`, `PS51_NATIVE_REDIRECT_UNDER_EAP_STOP_FORBIDDEN`, `LASTEXITCODE_SENTINEL_BEFORE_NATIVE_CALL`.

### 9.10 Falha após efeito parcial — reconciliação antes de qualquer retry
Se o runner criou, substituiu, moveu ou alterou arquivo de projeto/dado antes de falhar, a saída de erro e o receipt declaram:

```text
EFFECTS_OCCURRED=YES|NO
FILES_CHANGED=<lista ou receipt>
STATE_AFTER_FAILURE=<hashes/paths relevantes>
SAFE_TO_RERUN_SAME_RUNNER=YES|NO
```

Criar o próprio `out_root`, log e receipt **não** conta como efeito; alterar projeto, dado, configuração ou ambiente conta.

Depois de `EFFECTS_OCCURRED=YES`:

- é proibido instruir o usuário a rerodar o mesmo runner sem reconciliação;
- a próxima etapa valida os hashes e o estado físico atuais;
- o novo runner é de continuação/recovery ou de rollback deliberado;
- o backup pré-efeito é preservado;
- a evidência da falha não é sobrescrita;
- exit code padrão `3` (§13.2).

Regras: `PARTIAL_EFFECT_STATE_MUST_BE_REPORTED`, `BLIND_RERUN_AFTER_PARTIAL_EFFECT_FORBIDDEN`, `POST_FAILURE_RECONCILIATION_BEFORE_RETRY`.

### 9.11 Encoding e cultura — **novo na V005**

| Situação | Regra |
|---|---|
| `.ps1`/`.psm1` com qualquer caractere não ASCII (acento, `ç`, `→`) | Salvar em **UTF-8 com BOM**. Sem BOM, o 5.1 lê em ANSI e corrompe literais em runtime, e o parser não acusa |
| `.ps1` só com ASCII | Qualquer encoding; preferir ASCII puro (o Anexo A é ASCII) |
| Arquivos gravados pelo runner e lidos por Python, Git ou outra ferramenta (JSON, CSV, `.py`, logs) | UTF-8 **sem BOM** via `[IO.File]::WriteAllText/AppendAllText` com `UTF8Encoding($false)` |
| `Out-File` e `>` no 5.1 | Gravam UTF-16LE: **proibidos** para artefatos consumidos por máquina |
| `Set-Content -Encoding UTF8` no 5.1 | Grava **com** BOM: proibido para `.py`, JSON e CSV consumidos por outras ferramentas |
| `Export-Csv` no 5.1 | Default ASCII; sempre `-Encoding UTF8` (com BOM) ou gravação manual sem BOM, conforme o consumidor declarado |
| Leitura com `Get-Content` | Sempre `-Encoding UTF8` (ou `[IO.File]::ReadAllText`) quando o arquivo for UTF-8 |
| Números e datas em saídas de máquina | Cultura invariante (`[Globalization.CultureInfo]::InvariantCulture`): ponto decimal, ISO-8601. Em pt-BR, `Export-Csv`/`ToString()` produzem `421,188828` e `23/09/2026`, ambíguos para parsers |
| Processo Python chamado pelo runner | Definir `PYTHONUTF8=1` (e, se houver saída acentuada no console, `PYTHONIOENCODING=utf-8`) no escopo da chamada, restaurando depois |

Gate de encoding (autoauditoria §17.1): se o `.ps1` tiver bytes > 0x7F, deve começar com `EF BB BF`.

Regras: `PS1_NON_ASCII_REQUIRES_UTF8_BOM`, `MACHINE_FILES_UTF8_NO_BOM`, `PS51_OUTFILE_REDIRECT_FOR_MACHINE_FILES_FORBIDDEN`, `MACHINE_OUTPUT_INVARIANT_CULTURE`.

---

## 10. LAUNCHERS — EVITAR COMANDO INLINE FRÁGIL

Evitar launchers extensos com `powershell.exe -Command "..."`, quoting complexo, `^`, várias camadas de escape ou lógica grande inline. Preferir `.cmd` simples que chame `powershell.exe -File runner.ps1`, ou PowerShell direto com `-File`.

**Motivo adicional:** com `-Command`, o exit code do processo pode não refletir o do script (um `throw` vira exit 1 genérico, e um `exit N` dentro de bloco pode se perder). Com `-File`, `exit N` é propagado.

A lógica real fica em `.ps1`/`.py`, versionável e auditável.

---

## 11. SEMÂNTICA CANÔNICA DE PYTHON

### 11.1 Interpretador
Com runtime certificado/pinado, usar o caminho absoluto desse Python. É proibido trocar silenciosamente para `python` do `PATH` quando a versão faz parte da identidade. O receipt registra `sys.executable` e `sys.version`. Ver §2.3 para o uso de `py`.

### 11.2 Entrada e saída
UTF-8 explícito; nada de locale implícito; caminhos por configuração/argumento ou resolvidos a partir de `__file__`; sem dependência de `cwd`; erro claro e exit não zero em falha. Padrão de projeto: `SCRIPT_DIR = Path(__file__).resolve().parent`, `PROJECT_ROOT = SCRIPT_DIR.parent`, saídas em `PROJECT_ROOT/"outputs"` (criada automaticamente), sem fallback por nome de pasta.

### 11.3 Exit codes

```text
EXIT_0=SUCCESS
ANY_NONZERO=NOT_PASS
```

Mapa padrão na §13.2. Nunca inferir PASS de texto se o processo terminou com código não zero.

### 11.4 Exceptions
Proibido `except Exception: pass` ou fallback silencioso. Falha inesperada é registrada, impede promoção e devolve exit não zero.

### 11.5 Determinismo
Ordenação explícita; nada de ordem acidental do filesystem, de hash randomization ou de concorrência definindo output; timestamps fora de artefatos que exigem identidade de bytes, salvo se o contrato os incluir.

### 11.6 Escrita atômica

```text
WRITE_TEMP (mesmo diretório/volume do destino)
FLUSH/FSYNC quando exigido
ATOMIC_REPLACE (os.replace)
```

O checkpoint não avança antes da publicação segura do estado correspondente. O temporário fica no **mesmo volume** do destino; caso contrário, `replace` deixa de ser atômico.

### 11.7 Grandes arquivos
Streaming, chunks, iteradores e memória limitada. **Primeira/última data de arquivo grande:** ler só as bordas por seek binário (primeiras e últimas ~5 linhas não vazias). Full scan (que pode levar mais de 10 minutos) só em script de censo dedicado.

### 11.8 Código Python gerado — compilar os bytes exatos antes de instalar

```text
GENERATE_EXACT_BYTES → WRITE_TO_STAGING → HASH_EXACT_BYTES → COMPILE/PARSE_EXACT_BYTES
→ ONLY THEN INSTALL/REPLACE PROJECT FILE → RUN TARGETED/FULL TESTS
```

É proibido instalar primeiro e descobrir depois um erro de sintaxe que o staging teria detectado. Payload embutido (Base64 etc.): o SHA-256 esperado dos bytes decodificados é declarado, verificado antes da instalação, e a compilação ocorre sobre os mesmos bytes instalados. Compilar fecha só o gate sintático; não autoriza promoção.

### 11.9 Processos longos
Todo processo longo (walk-forward, Optuna, conversões, auditorias integrais) tem: indicador de progresso; checkpoint em disco retomável; flag de resume; timeout global de relógio (`--timeout-horas`); relatório final automático.

---

## 12. SEMÂNTICA CANÔNICA DE POWERSHELL

O PowerShell atua como bootstrap, orquestrador, gatekeeper, validador de identidade, launcher, coletor de evidência e integrador de exit codes. A lógica pesada permanece em Python/MQL5 quando esse for o desenho do projeto.

### 12.1 Fail-closed
Pré-condição crítica ausente termina em `throw`/exit não zero.

### 12.2 Comandos externos
Sempre via `Invoke-NativeChecked` (Anexo A) ou equivalente com as garantias da §9.9. Não mascarar o exit code com pipeline posterior.

### 12.3 Paths
`Test-Path`, `Get-FileHash`, `Get-Item` e `Copy-Item` sempre com `-LiteralPath` para nomes exatos. Wildcard só quando deliberado.

### 12.4 Cálculo de caminhos antes da validação
`Join-Path` resolve a unidade e **lança erro se ela não existir**. Caminhos de configuração calculados no topo do script, antes do `try`, usam `[IO.Path]::Combine`. A existência de unidade e diretórios é verificada dentro do `try`, onde gera `BLOCKED` com receipt.

### 12.5 Escopo de variáveis de ambiente
Variáveis alteradas pelo runner (`PYTHONUTF8`, `PYTHONDONTWRITEBYTECODE` etc.) têm o valor anterior salvo e restaurado no `finally`.

### 12.6 P/Invoke / Win32 — access mask com mínimo privilégio

Ao abrir arquivo/diretório/volume com `CreateFileW`, `NtCreateFile`, `OpenProcess`, `OpenThread` ou API equivalente, pedir **somente os direitos necessários** à operação que o handle realmente fará.

Regras:

1. decodificar a access mask por bits/constantes; número hexadecimal sem decomposição não é justificativa;
2. handle usado para **pin, leitura de metadata, identidade ou traversal** não pede direitos de criar, gravar, deletar, mudar ACL/owner ou modificar atributos salvo necessidade funcional provada;
3. ao percorrer ancestrais, testar fisicamente também diretórios mais protegidos que podem aparecer na cadeia (`C:\`, `C:\Users`, raiz de volume/diretório corporativo), e não apenas pastas sob o perfil do usuário;
4. `FILE_ADD_FILE (0x2)` em diretório significa direito de **criar arquivo**; não deve aparecer em pin read-only por conveniência;
5. `FILE_FLAG_BACKUP_SEMANTICS` permite obter handle de diretório, mas não autoriza pedir direitos desnecessários;
6. access mask reduzida precisa continuar passando todos os gates de identidade/metadata/reparse/share-mode exigidos; mínimo privilégio **não** significa remover direitos às cegas;
7. o valor `0x001000A1` corrigiu um caso TICKSTORE específico; não é constante global desta política.

Quando o objetivo for somente metadata, considerar `dwDesiredAccess=0` ou `FILE_READ_ATTRIBUTES` se suficiente ao conjunto físico de chamadas de validação. A escolha final vem das operações executadas e da SPEC.

Regras: `WIN32_HANDLE_ACCESS_LEAST_PRIVILEGE`, `WIN32_ACCESS_MASK_BITWISE_JUSTIFICATION`, `WIN32_READ_PIN_CREATE_WRITE_RIGHTS_FORBIDDEN_UNLESS_REQUIRED`, `WIN32_ANCESTOR_ACCESS_TEST_ON_PROTECTED_PATHS`.

---

### 12.7 PowerShell 5.1 chamando métodos .NET sobrecarregados — provar a forma de argumentos

Em caminho crítico, documentação da API e compatibilidade do runtime são necessárias, mas não suficientes para provar que **a forma de chamada do PowerShell** selecionará/converterá argumentos como esperado.

Especial atenção a:

- métodos .NET sobrecarregados;
- parâmetros `string` que aceitam `null` na API;
- `$null`, arrays, enums e inteiros cuja conversão depende do binder;
- métodos com efeitos atômicos/destrutivos (`File.Replace`, ACL, rename, move, registry etc.).

Regra:

```text
API_DOC_SUPPORTS_CALL = necessário
TARGET_RUNTIME_SAME_CALL_SHAPE_PROBE = obrigatório
```

O probe deve usar:

1. o mesmo Windows PowerShell/runtime;
2. a mesma sobrecarga;
3. o mesmo número e tipos aparentes de argumentos;
4. os mesmos valores especiais (`$null`, enum, bool etc.);
5. fixture descartável no mesmo filesystem/volume quando isso afeta a API;
6. validação de resultado e side effects.

#### 12.7.1 `System.IO.File.Replace` em runner crítico

Apesar de a documentação do .NET admitir `null` para `destinationBackupFileName`, o ambiente-alvo rejeitou fisicamente a forma:

```powershell
[IO.File]::Replace($Source, $Destination, $null, $true)
```

com erro de caminho inválido.

Portanto, para os runners cobertos por esta política:

- **não usar `$null` como backup argument de `File.Replace` em caminho crítico**, salvo se essa forma exata tiver sido provada no runtime-alvo e a SPEC exigir;
- preferir `destinationBackupFileName` absoluto, não vazio, no mesmo volume;
- o backup de replace recebe nome único por run;
- depois do replace, validar:
  - hash do destino novo;
  - hash do backup = hash do destino antigo esperado;
  - ausência/presença esperada do source temporário;
- preservar o backup até PASS final ou autorização de cleanup;
- antes de tocar no alvo real, executar self-test com a **mesma sobrecarga e backup não nulo** em fixture descartável.

Regras: `CRITICAL_DOTNET_OVERLOAD_TARGET_RUNTIME_PROBE`, `CRITICAL_DOTNET_ARGUMENT_SHAPE_MUST_MATCH_PROBE`, `PS51_CRITICAL_FILE_REPLACE_NULL_BACKUP_FORBIDDEN_UNLESS_PROVEN`, `CRITICAL_FILE_REPLACE_EXPLICIT_BACKUP_PATH`, `FILE_REPLACE_BACKUP_HASH_VALIDATION`.


### 12.8 Nome físico, revisão de build e identificador lógico de contrato são distintos

Nunca inferir automaticamente um identificador de protocolo a partir de:

- nome de arquivo;
- sufixo `R1`, `R1R1`, `R2`;
- nome de pasta;
- nome de ZIP;
- nome de runner;
- label humana de build.

Exemplo válido:

```text
ARQUIVO_FISICO=INLINE_ROOT_LOADER_V004_R1R1.ps1
PROTOCOL_CONTRACT_ID=INLINE_ROOT_LOADER_V004_R1
```

Isso não é contradição se o contrato declara explicitamente essa relação.

Regras:

```text
ARTIFACT_FILENAME_REVISION_IS_NOT_PROTOCOL_CONTRACT_ID=YES
PROTOCOL_CONTRACT_ID_MUST_BE_EXPLICIT=YES
CONTRACT_ID_INFERENCE_FROM_FILENAME=FORBIDDEN
```

Se uma correção de bytes preserva deliberadamente o contract ID lógico, o novo hash identifica os bytes; o contract ID só muda quando o protocolo muda explicitamente.


## 13. PASS / FAIL / BLOCKED

### 13.1 Definições
- **PASS:** exit autorizado, todos os gates obrigatórios passaram, os artefatos esperados existem e as identidades conferem.
- **FAIL:** a execução ocorreu e uma condição testada falhou.
- **BLOCKED:** não é seguro executar ou concluir por falta de evidência, arquivo, runtime, identidade, pré-condição ou autorização.

`BLOCKED` nunca vira PASS por suposição. Status compostos usados em auditorias (`PASS_WITH_BLOCKERS`, `PASS_WITH_WARNINGS`) **não** são PASS para fins de promoção ou autorização: um gate que exige PASS trata qualquer sufixo como NOT_PASS.

### 13.2 Mapa padrão de exit codes (salvo declaração diferente na SPEC)

| Exit | Significado |
|---|---|
| 0 | PASS |
| 1 | FAIL sem efeitos |
| 2 | BLOCKED (sem efeitos) |
| 3 | FAIL ou BLOCKED **após efeito parcial** (`EFFECTS_OCCURRED=YES`): exige reconciliação |
| 130 | Interrupção (Ctrl+C), somente se o runner implementar SAFE_STOP |
| outro | NOT_PASS, com a semântica declarada pela SPEC |

### 13.3 Receipt padrão
Todo runner com gate grava `RECEIPT.json` (UTF-8 sem BOM, escrita atômica, nunca sobrescrito) com, no mínimo:

```text
schema, runner, runner_sha256, run_id, mode (DRY_RUN|EXECUTE), status, exit_code, message,
effects_occurred, files_changed, safe_to_rerun_same_runner, out_root, finished_at
```

Campos de resultado específicos são opcionais e lidos pela §9.6.

**DRY-RUN substantivo também grava receipt.** Se o runner chegou a executar hashes, discovery, testes, probes, compilação, census ou qualquer gate material, `mode=DRY_RUN` continua sendo uma execução auditável e deve produzir log/receipt. `RECEIPT=NOT_WRITTEN` só é aceitável quando:

- o shell/parser rejeitou o candidato antes de executar o runner;
- a evidência não pôde ser inicializada por uma pré-condição anterior ao `out_root`, e isso é explicitamente reportado;
- ou a SPEC declarou previamente um preflight `CONSOLE_ONLY` sem artefatos.

Regras: `SUBSTANTIVE_DRY_RUN_RECEIPT_MANDATORY`, `SUCCESSFUL_SUBSTANTIVE_DRY_RUN_RECEIPT_NOT_WRITTEN_FORBIDDEN`.


### 13.3.1 `EFFECTS_OCCURRED` deve declarar o escopo

Um runner pode escrever logs, receipts, staging e backups de evidência sem alterar o estado protegido do projeto. Portanto, em runners novos/revisados:

```text
PROTECTED_STATE_EFFECTS_OCCURRED=YES|NO
EVIDENCE_WRITES_OCCURRED=YES|NO
```

são preferidos.

Se o contrato legado ainda usar apenas:

```text
EFFECTS_OCCURRED=YES|NO
```

o runner deve declarar no banner/schema qual é o escopo. Para esta política, quando não houver qualificador adicional, `EFFECTS_OCCURRED` significa **efeito no estado protegido/alvo**, não a criação normal de evidência auditável.

Uma falha pode portanto registrar:

```text
PROTECTED_STATE_EFFECTS_OCCURRED=NO
EVIDENCE_WRITES_OCCURRED=YES
```

e continuar segura para uma nova revisão, desde que o estado protegido seja reconciliado/provado intacto.

Regras: `EFFECTS_OCCURRED_SCOPE_MUST_BE_EXPLICIT`, `PROTECTED_STATE_EFFECTS_SEPARATE_FROM_EVIDENCE_WRITES`, `EVIDENCE_WRITE_IS_NOT_PROTECTED_STATE_MUTATION`.

### 13.3.2 `SAFE_TO_RERUN` não significa `RERUN_AUTHORIZED`

São conceitos diferentes:

- `SAFE_TO_RERUN_SAME_RUNNER=YES`: repetir não corromperia o estado protegido **com base apenas no estado atual**;
- `RERUN_AUTHORIZED=YES`: não existe defeito determinístico conhecido nem gate que exija correção/revisão antes de repetir.

Se uma falha determinística já foi isolada — sintaxe, hash esperado errado, overload incompatível, fixture impossível etc. — então:

```text
PROTECTED_STATE_EFFECTS_OCCURRED=NO
SAFE_TO_RERUN_SAME_RUNNER=YES
RERUN_AUTHORIZED=NO
RERUN_REASON=KNOWN_DETERMINISTIC_DEFECT
```

O runner antigo não deve ser repetido até uma revisão corrigir a causa. Segurança de estado não é justificativa para rerun cego.

Regras: `SAFE_TO_RERUN_NOT_EQUAL_RERUN_AUTHORIZED`, `KNOWN_DETERMINISTIC_DEFECT_RERUN_FORBIDDEN`, `RERUN_AUTHORIZATION_REASON_MUST_BE_EXPLICIT_WHEN_BLOCKED`.

### 13.4 Resumo final no console
As últimas linhas são sempre `CHAVE=VALOR`, sem cor como informação essencial:

```text
STATUS=PASS|FAIL|BLOCKED
EXIT_CODE=<n>
EFFECTS_OCCURRED=YES|NO
RECEIPT=<caminho absoluto>|NOT_WRITTEN
```

---

## 14. SAFE_STOP, CTRL+C, RESUME E CONCORRÊNCIA

- Ctrl+C é parada segura quando previsto; resultado parcial não é promovido; checkpoint consistente é preservado.
- Antes do resume, verificar processos órfãos.
- O resume reutiliza o mesmo launcher e contrato; não refaz histórico já confirmado quando a granularidade permitir retomada.
- Se SAFE_STOP não estiver definido, não inventar sua semântica.
- **Escritor único:** runner que altera estado adquire um lock exclusivo (`FileMode.CreateNew`, `FileShare.None`) antes de qualquer efeito. Lock presente = BLOCKED; o lock **não é apagado automaticamente** (pode ser de execução viva ou de crash, e isso exige diagnóstico). O lock é liberado no `finally`.

### 14.1 Windows Job Objects — processo terminado não implica handle liberado

No Windows, um handle de processo continua válido depois que o processo termina até que seja fechado. Para `JOBOBJECT_BASIC_ACCOUNTING_INFORMATION`, `ActiveProcesses` só é decrementado quando o processo terminou **e todas as referências ao objeto de processo foram liberadas**.

Consequências:

- `wait()` / `WaitForExit()` prova término, não prova liberação de todas as referências;
- antes de declarar `JOB_RESIDUAL_PROCESSES=0`, fechar deterministicamente handles de processo/thread que o launcher mantém;
- não depender de garbage collector, destrutor eventual ou saída de escopo;
- depois do close dos handles, repetir o census com deadline curto e fail-closed;
- em CPython/Windows, se o projeto precisar interagir com o handle interno de `subprocess.Popen`, o runtime Python fica pinado e o comportamento recebe teste regressivo; encapsular isso num helper do projeto em vez de espalhar acesso a atributo privado.

Regras: `PROCESS_TERMINATION_NOT_EQUAL_HANDLE_RELEASE`, `PROCESS_HANDLES_CLOSE_BEFORE_JOB_FINAL_CENSUS`, `JOB_ACTIVE_PROCESS_ACCOUNTING_REQUIRES_REFERENCE_RELEASE`, `PROCESS_HANDLE_CLEANUP_NO_GC_DEPENDENCY`.

### 14.2 Erro primário prevalece sobre erro de cleanup

Se a operação principal já produziu uma exceção/gate autoritativo e `finally`, `close()`, cleanup, coleta de evidência ou teardown também falhar:

1. preservar a exceção/status primário como causa;
2. anexar o erro secundário como `CLEANUP_ERROR`, `add_note`, campo de receipt ou equivalente;
3. nunca substituir `PREP_WORKER_ERROR`, `SOURCE_HASH_MISMATCH`, `GATE_X_FAIL` etc. por erro posterior de cleanup;
4. se o cleanup incompleto deixar risco operacional, o status continua NOT_PASS e o receipt registra a necessidade de reconciliação;
5. uma falha de cleanup **sem** erro primário continua sendo falha normal e não deve ser ignorada.

Essa regra é a versão intra-processo da precedência da §9.7.

Regras: `PRIMARY_ERROR_PRECEDENCE_OVER_CLEANUP_ERROR`, `CLEANUP_ERROR_RECORDED_SEPARATELY`, `CLEANUP_FAILURE_MUST_NOT_MASK_CAUSAL_GATE`.

### 14.3 Harness sob Job preexistente — ownership, não igualdade global

Um teste/harness pode ser executado dentro de Job já existente criado pelo shell, CI, launcher, sandbox, antivírus ou ferramenta de segurança. Esse Job pode conter processos externos ao teste e sofrer churn enquanto o teste roda.

Portanto, em **Job compartilhado**, são proibidos como gate:

```text
job_members() == { current_pid }
FINAL_JOB_MEMBERS == BASELINE_JOB_MEMBERS
```

O segundo padrão é especialmente perigoso: processos externos podem terminar ou nascer durante o teste, produzindo FAIL falso mesmo quando todos os workers próprios foram limpos corretamente.

#### 14.3.1 Identidade própria obrigatória

O harness mantém para cada processo que **ele próprio criou** uma identidade estável:

```text
OWNED = {
    worker_id: {
        pid,
        process_creation_time
    }
}
```

A criação/hello do worker deve provar:

1. PID recebido = PID do processo lançado;
2. `process_creation_time` recebido = tempo consultado pelo supervisor;
3. o PID próprio estava no Job exigido no momento do admission gate.

No cleanup:

```text
TERMINATE/STOP
→ WAIT
→ CLOSE PROCESS/THREAD HANDLES
→ FINAL_MEMBERS = job_members()
→ para cada identidade própria:
      se pid não está em FINAL_MEMBERS: PASS para essa identidade
      se pid está em FINAL_MEMBERS:
          consultar creation_time atual
          se atual == creation_time próprio: FAIL residual próprio
          se atual != creation_time próprio: PID foi reutilizado; não é residual próprio
```

Não depender apenas do número do PID porque PID pode ser reutilizado.

#### 14.3.2 Churn externo é diagnóstico, não autoridade

O harness pode registrar:

```text
BASELINE_GLOBAL_JOB_MEMBERS
FINAL_GLOBAL_JOB_MEMBERS
EXTERNAL_PIDS_ADDED
EXTERNAL_PIDS_REMOVED
```

Esses campos são diagnóstico. Em Job compartilhado, diferenças externas não podem causar PASS/FAIL do cleanup dos workers próprios.

#### 14.3.3 Job dedicado mantém contrato estrito

Se a SPEC exige Job dedicado contendo somente supervisor + descendentes próprios, o teste dessa propriedade deve criar/usar o **root-loader/Job dedicado real** (inclusive nested Job quando suportado) e validar o invariante global ali.

A regra de ownership para harness compartilhado **não enfraquece**:

- `KILL_ON_JOB_CLOSE`;
- assign-before-resume;
- breakaway denial;
- child membership;
- zero descendente próprio residual;
- ou qualquer cardinalidade estrita declarada para Job dedicado de produção.

Regras: `SHARED_JOB_GLOBAL_MEMBERSHIP_EQUALITY_GATE_FORBIDDEN`, `SHARED_JOB_HARNESS_TRACKS_OWNED_PROCESS_IDENTITIES`, `OWNED_PROCESS_IDENTITY_PID_PLUS_CREATION_TIME`, `OWNED_WORKERS_ABSENT_AFTER_CLEANUP`, `PID_REUSE_MUST_NOT_CREATE_FALSE_RESIDUAL`, `EXTERNAL_JOB_CHURN_DIAGNOSTIC_ONLY`, `DEDICATED_JOB_STRICT_INVARIANT_REMAINS_REQUIRED`.


---

## 15. TRANSAÇÃO E PROMOÇÃO

```text
SCRATCH/TEMP → VALIDAÇÃO → PENDING → ATOMIC PUBLISH → CHECKPOINT → CLEANUP
```

Proibido: publicar parcialmente; avançar checkpoint antes do estado; apagar evidência necessária para recovery; overwrite não atômico onde o contrato exige atomicidade. Antes de escrita volumosa, checar o espaço livre do volume de destino com reserva declarada (`INSUFFICIENT_FREE_SPACE` = BLOCKED).

---

## 16. HASHES E IDENTIDADE

### 16.1 Naturezas distintas
Sempre distinguir: SHA do ZIP externo, SHA do arquivo físico, hash lógico/canônico, SHA de configuração, de source e de manifesto. Não comparar hashes de naturezas diferentes como se fossem a mesma identidade.

### 16.2 Comparação
- `Get-FileHash` devolve hexadecimal **maiúsculo**; `hashlib.hexdigest()`, **minúsculo**. Normalizar ambos (`ToUpperInvariant()`/`.upper()`) antes de comparar.
- Comparação exata de 64 caracteres; prefixo ou truncamento nunca vale como identidade.

### 16.3 Bytes físicos e fim de linha
O hash de source é dos **bytes físicos**. Git com `core.autocrlf` pode converter LF↔CRLF no checkout e mudar o hash sem mudar o código. Pacotes selados e repositórios com hashes pinados devem ter `.gitattributes` explícito (`* -text` para artefatos selados, ou regra `eol` declarada), e o hash esperado deve ser calculado sobre os bytes efetivamente instalados.

---

## 17. CÓDIGO GERADO PELO ASSISTENTE — ENTREGA

Todo runner fornecido deve:

1. informar `AMBIENTE`;
2. funcionar a partir de `PS C:\Users\silvi>`;
3. não exigir `cd` manual;
4. usar caminhos absolutos ou autodetecção fail-closed;
5. declarar entradas e saídas;
6. imprimir banner com escopo e proibições;
7. bloquear pré-condição ausente;
8. separar source, output e evidence;
9. evitar overwrite;
10. indicar o que foi modificado;
11. declarar a semântica de exit (§13.2);
12. declarar SAFE_STOP/resume quando existirem;
13. evitar operação destrutiva por padrão;
14. **gravar o log em caminho absoluto definido pelo runner (§5.6)**;
15. **iniciar em DRY-RUN; efeitos só com `-Execute` (ou flag equivalente)**;
16. **gravar receipt padrão (§13.3)**;
17. **partir do esqueleto do Anexo A ou justificar a divergência**.

### 17.1 Autoauditoria pré-entrega obrigatória

Antes de entregar `.ps1`, `.cmd`, `.bat` ou bootstrap Python que possa alterar estado:

```text
POWERSHELL_PARSE_GATE=PASS
PS1_ENCODING_GATE=PASS              (ASCII puro, ou UTF-8 com BOM se houver byte > 0x7F)
PYTHON_CANDIDATE_COMPILE_GATE=PASS_WHEN_APPLICABLE
ABSOLUTE_PATH_OR_PSSCRIPTROOT=PASS
NO_MANUAL_CD=PASS
NO_CWD_DEPENDENCY=PASS
LOG_PATH_ABSOLUTE=PASS
PS51_QUOTING_RISK=PASS              (nenhum argumento nativo com aspas duplas)
NATIVE_EXIT_CODE_HANDLING=PASS      (Invoke-NativeChecked ou equivalente)
STDERR_HANDLING=PASS                (sem redirect nativo sob EAP=Stop)
CARDINALITY_0_1_N=PASS
STRICTMODE_OPTIONAL_PROPERTIES=PASS
PATHS_BEFORE_TRY_USE_COMBINE=PASS
HASH_PRECONDITIONS=PASS
EFFECT_ORDER=PASS                   (STAGE -> VALIDATE -> INSTALL -> TEST)
DRY_RUN_DEFAULT=PASS
SINGLE_WRITER_LOCK=PASS_WHEN_EFFECTFUL
FAIL_CLOSED=PASS
EVIDENCE_OVERWRITE=NO
PARTIAL_EFFECT_RECEIPT=DEFINED
EXIT_CODE_MAP=DECLARED
TARGET_SHELL_PARSE_EXECUTION=PASS_OR_EXPLICITLY_PENDING_LOCAL_ACCEPTANCE
SELF_PARSE_PRESENT_IS_NOT_PARSE_PROOF=PASS
NATIVE_STDERR_RAWNESS_ASSUMPTION=NONE
WIN32_ACCESS_MASK_LEAST_PRIVILEGE=PASS_WHEN_APPLICABLE
CRITICAL_DOTNET_OVERLOAD_ARGUMENT_SHAPE_TARGET_RUNTIME_PROBE=PASS_WHEN_APPLICABLE
ARTIFACT_FILENAME_VS_PROTOCOL_CONTRACT_ID=EXPLICIT
CROSS_COMPONENT_CONTRACT_SATISFIABILITY=PASS
SAME_ANCHOR_END_TO_END_ACCEPTANCE=PASS_WHEN_APPLICABLE
CRITICAL_FILE_REPLACE_NON_NULL_BACKUP_PATH=PASS_WHEN_APPLICABLE
EFFECTS_OCCURRED_SCOPE=EXPLICIT
SAFE_TO_RERUN_VS_RERUN_AUTHORIZED=DISTINGUISHED
PROCESS_HANDLE_LIFETIME=PASS_WHEN_JOB_CENSUS_APPLIES
PRIMARY_ERROR_PRECEDENCE_OVER_CLEANUP=PASS
SHARED_JOB_OWNERSHIP_MODEL=PASS_WHEN_APPLICABLE
SHARED_JOB_GLOBAL_EQUALITY_ASSUMPTION=ABSENT
MANDATORY_FIXTURE_PRIVILEGE_INDEPENDENCE=PASS_WHEN_APPLICABLE
DRY_RUN_RECEIPT=DEFINED_FOR_SUBSTANTIVE_GATES
```

Um runner não é entregue só porque "parece correto". O resultado da autoauditoria acompanha a entrega. Itens **executados** (parser, compilação) são reportados separadamente dos **inspecionados** visualmente.

### 17.2 Contagens e cardinalidades usadas como gate
Quantidade de testes, membros, arquivos, workers, casos ou evidências usada como gate vem de fonte física autoritativa: descoberta real da suíte, AST/parser, manifesto, inventário físico, receipt do processo ou autoridade da SPEC. Aritmética mental ou expectativa informal nunca é a única base de gate crítico.

### 17.3 Gate de autorização do usuário
- Nenhum código é escrito, nenhum script é modificado e nenhuma etapa é iniciada sem autorização explícita **por ação**. "Pode" = autorização. **Silêncio não é consentimento.**
- Um script entregue por turno, aguardando aprovação antes da próxima ação.
- Todo script vem com bateria de testes que inclui cenários calculados à mão **e** defeitos injetados deliberadamente.
- Toda afirmação técnica distingue **FATO VERIFICADO**, **HIPÓTESE** e **NÃO VERIFICÁVEL**.

### 17.4 Qualificação sem efeito antes de instalar deltas nativos/de segurança

Quando uma candidata altera qualquer um destes temas:

- P/Invoke / Win32 / NT API;
- access masks, share modes, reparse points ou identidade por handle;
- Job Objects, process tree, process census, IPC entre processos;
- SAFE_STOP/kill-on-close;
- trust de bundle, loader, runtime pinning;
- comportamento dependente exclusivamente de Windows;
- ou corrige uma falha que só apareceu no PC alvo,

a primeira revisão de qualificação deve ser **incapaz de instalar/promover**. Preferir runner `DRY_RUN_ONLY` que **nem contenha** caminho de instalação/replace. Ele:

1. materializa bytes candidatos em staging novo;
2. valida hashes e compila/parsa;
3. executa a bateria integral aplicável no ambiente-alvo;
4. deriva fisicamente a cardinalidade de testes;
5. exige `failures=0`, `errors=0`, `skips=0` quando a SPEC não permite skip;
6. para cada primitive nativa/.NET que só será usada na instalação, executa **self-test da mesma primitive, mesma sobrecarga e mesma forma de argumentos** em fixture descartável;
7. gera result/receipt;
8. termina com `PROJECT_INSTALL=NO`.

Somente após PASS integral existe nova ação/runner para instalar os **mesmos bytes** e repetir regressão pós-instalação.

Regras: `NATIVE_SECURITY_DELTA_PREINSTALL_QUALIFICATION_NO_EFFECT`, `DRY_RUN_ONLY_QUALIFIER_HAS_NO_INSTALL_PATH`, `INSTALL_RUNNER_SEPARATE_AFTER_QUALIFICATION_PASS`, `TESTED_BYTES_IDENTITY_CARRIED_TO_INSTALL`.

### 17.5 Fixtures obrigatórias não dependem de privilégio opcional

Teste obrigatório de segurança/NTFS/Win32 não pode virar skip apenas porque uma fixture escolheu mecanismo que exige privilégio opcional.

Exemplos:

- objetivo = detectar/rejeitar **reparse point**: uma junction de diretório pode ser fixture adequada; não exigir symbolic link se `SeCreateSymbolicLinkPrivilege`/Developer Mode não faz parte da SPEC;
- se o comportamento sob symbolic link especificamente for o objeto do gate, então o privilégio vira **pré-condição explícita** e ausência = BLOCKED, nunca PASS/skip silencioso.

Princípio:

```text
TEST_OBJECTIVE != FIXTURE_MECHANISM
```

Escolher a fixture menos privilegiada que preserve exatamente o fenômeno testado. Se não existir equivalente, declarar a dependência e bloquear.

Regras: `MANDATORY_FIXTURE_OPTIONAL_PRIVILEGE_FORBIDDEN_WHEN_EQUIVALENT_EXISTS`, `MANDATORY_GATE_SKIP_DUE_FIXTURE_PRIVILEGE_FORBIDDEN`, `FIXTURE_MECHANISM_MUST_MATCH_TEST_OBJECTIVE`.

### 17.6 Nova descoberta técnica atualiza a política canônica automaticamente

Sempre que execução, auditoria, parser, compilador, runtime, teste adversarial ou investigação revelar uma **nova regra real e comprovada** de:

- sintaxe Python / PowerShell / CMD / shell;
- encoding, quoting, argumentos ou redirecionamento;
- runners, wrappers, logs ou receipts;
- semântica de processo/Job/handle;
- Win32/PInvoke/NT API;
- Git, paths, ZIPs, filesystem ou execução local;
- ou qualquer outro comportamento transversal que possa evitar repetição do defeito,

não basta corrigir o projeto local.

Na **mesma etapa da descoberta**, o assistente deve:

1. corrigir/diagnosticar o caso local conforme autorização;
2. gerar nova revisão versionada desta política (`V005R2 → V005R3 → ...`, ou sucessora equivalente);
3. preservar a versão anterior como baseline histórica;
4. registrar descoberta, evidência física, regra corrigida/nova, forma canônica quando aplicável e impacto no checklist/registro único;
5. registrar a nova revisão como política vigente na memória;
6. nunca editar a versão anterior in-place;
7. nunca promover hipótese não comprovada a regra;
8. se evidência nova **refutar** uma regra recém-criada, emitir revisão corretiva imediatamente.

Essa atualização documental **não exige novo pedido do usuário** depois que a descoberta técnica foi comprovada. A autorização para corrigir o caso local não autoriza automaticamente efeitos destrutivos adicionais, mas a revisão documental canônica deve ser gerada.

Regras: `NEW_TECHNICAL_DISCOVERY_CANONICAL_POLICY_REVISION_MANDATORY`, `CANONICAL_POLICY_REVISION_SAME_STAGE_AS_DISCOVERY`, `CANONICAL_PRIOR_VERSION_PRESERVED`, `CANONICAL_HYPOTHESIS_PROMOTION_FORBIDDEN`, `CANONICAL_RULE_REFUTATION_REQUIRES_IMMEDIATE_CORRECTIVE_REVISION`.


---

### 17.5 Satisfatibilidade end-to-end de contrato antes de release/bundle

Antes de promover um bundle, gate ou external anchor, todos os campos compartilhados entre componentes devem possuir **um único valor satisfatível**.

Para cada contract ID compartilhado:

1. identificar o produtor;
2. identificar todos os consumidores;
3. extrair o valor efetivamente exigido por cada componente;
4. exigir igualdade/compatibilidade explícita;
5. construir uma fixture/anchor sintético único;
6. provar que a mesma fixture é aceita por todos os validadores relevantes;
7. só então permitir release/bundle.

Exemplos:

- `inline_root_loader_revision`;
- `python_version`;
- `spec_sha256`;
- schema/revision;
- codec/format;
- owner-gate role;
- release ID quando compartilhado.

Gates mínimos:

```text
CROSS_COMPONENT_CONTRACT_VALUES_EXTRACTED=YES
CROSS_COMPONENT_CONTRACT_SATISFIABLE=PASS
SAME_ANCHOR_ACCEPTED_BY_ROOT_LOADER_AND_EXECUTABLE=PASS_WHEN_APPLICABLE
```

Não basta:

- ambos os arquivos conterem a mesma substring em algum lugar;
- o nome dos arquivos parecer compatível;
- os hashes individuais estarem corretos;
- suítes unitárias isoladas passarem.

Um bundle pode ter:

```text
ZIP_INTEGRITY=PASS
MANIFEST_HASHES=PASS
SOURCE_HASH=PASS
```

e ainda assim ser:

```text
PROTOCOL_ADMISSION_COMPATIBILITY=FAIL
RELEASE_AUTHORIZATION=BLOCKED
```

Regra: `BUNDLE_INTEGRITY_PASS_DOES_NOT_IMPLY_PROTOCOL_ADMISSION_PASS`.


## 18. OPERAÇÕES DESTRUTIVAS

Delete, overwrite, move de dado canônico, cleanup irreversível ou alteração de fonte exigem autorização explícita.

```text
SOURCE_MUTATION=NO
CANONICAL_DATA_DELETION=NO
OVERWRITE_EVIDENCE=NO
```

Cleanup só ocorre quando: o alvo é inequivocamente transitório; a etapa dependente está fechada; existe autorização ou regra específica; hashes e backups exigidos foram preservados. Preferência: **arquivar movendo** (reversível) em vez de apagar; exclusão só com gate próprio e relatório prévio `REPORT_ONLY` idêntico ao que será executado.

---

## 19. REGRA FINAL DE LOCALIZAÇÃO

```text
DO_NOT_GUESS_PATH=YES
```

O runner usa caminho comprovado; ou localiza candidatos, valida identidade/hash e para se houver ambiguidade. Nunca cria diretório "parecido" para contornar arquivo ausente.

---

## 20. GIT — **novo na V005**

- Antes de aplicar qualquer patch: `git status --porcelain` e `git diff --stat` registrados no log. Alterações locais não relacionadas **nunca** são descartadas, resetadas ou incluídas no commit.
- Árvore suja em arquivo que o patch vai tocar → BLOCKED, até decisão do usuário.
- Um commit por mudança lógica, com mensagem versionada; rollback de código por `git revert`, não por reescrita de histórico.
- Proibido: `git reset --hard`, `git clean -fd`, `git push --force` e reescrita de histórico sem autorização específica.
- `git diff --check` antes do commit.
- Artefatos versionados/baselines (ex.: `TICKSTORE_R9_DEV\BASELINE_R8`, `RC1`) não recebem edição in-place; mudança = nova versão em diretório novo.

---

## 21. ANEXOS

- **Anexo A** — Esqueleto canônico de runner Windows PowerShell 5.1 (testado).
- **Anexo B** — Rastreabilidade V004 → V005.

---

## 22. REGISTRO CANÔNICO DE REGRAS (fonte única)

Este bloco substitui os blocos-resumo dispersos da V004. Em caso de divergência entre uma seção e este registro, prevalece a leitura **mais restritiva**.

```text
# --- Shell e invocação
LOCAL_EXECUTION_POLICY=ACTIVE
DEFAULT_SHELL=WINDOWS_POWERSHELL_5_1
SHELL_EDITION_CHECK_AT_RUNTIME=YES_WHEN_5_1_SEMANTICS_REQUIRED
LOCAL_SHELL_INITIAL_PROMPT=PS_C:\Users\silvi
MANUAL_CD_REQUIRED=NO
PS_LINE_CONTINUATION=BACKTICK
CARET_CONTINUATION_IN_POWERSHELL=FORBIDDEN
USER_PYTHON_LAUNCHER=py
LAUNCHER_INLINE_COMMAND_COMPLEX=FORBIDDEN

# --- Caminhos e localização
RELATIVE_PATH_DEPENDENCY=FORBIDDEN
CWD_AS_PACKAGE_OR_PROJECT_IDENTITY=FORBIDDEN
PACKAGE_USE_PSSCRIPTROOT=YES
POWERSHELL_USE_ABSOLUTE_PATHS=YES
LITERALPATH_FOR_EXACT_NAMES=YES
PATHS_BEFORE_TRY_USE_IO_PATH_COMBINE=YES
MAX_PATH_CHECK=YES
ROOT_MARKER_DEDICATED_FILE=YES
PACKAGE_LANDING_ZONE=DOWNLOADS
DOWNLOADS_PHYSICAL_PATH_MUST_NOT_BE_GUESSED=YES
ONEDRIVE_PLACEHOLDER_MUST_BE_HYDRATED_AND_HASHED=YES
PROJECT_ROOT_MUST_BE_EXPLICIT=YES
DO_NOT_GUESS_PATH=YES

# --- Classes de arquivo, logs e saídas
OUT_ROOT_NEW_PER_RUN=YES
RUN_ID_FORMAT=yyyyMMdd_HHmmss_fff_PID
LOG_PATH_ABSOLUTE_RUNNER_DEFINED=YES
LOG_NEVER_DEPENDS_ON_CWD=YES
LOG_NEW_PER_RUN=YES
ACTIVE_STATE_SEPARATED_FROM_REPORTS=YES
CANONICAL_DATA_WITH_PATH_BOUND_IDENTITY_IMMOVABLE=YES
OVERWRITE_CANONICAL_EVIDENCE=FORBIDDEN

# --- Nomenclatura e entrega
MULTI_FILE_DELIVERY_SINGLE_VERSIONED_ZIP=YES
DELIVERY_ZIP_NAME_REUSE=FORBIDDEN

# --- ZIP
ZIP_SOURCE_IMMUTABLE=YES
ZIP_HASH_BEFORE_EXTRACT=WHEN_AVAILABLE
ZIP_ENTRY_VALIDATION_BEFORE_EXTRACT=YES
ZIP_CASE_INSENSITIVE_DUPLICATES_FORBIDDEN=YES
ZIP_EXTRACT_TO_NEW_CLEAN_DIR=YES
ZIP_EXTRACT_OVER_EXISTING_DIR=FORBIDDEN
ZIP_MANIFEST_VERIFY=YES
EXTRA_FILES_IN_SEALED_PACKAGE=FORBIDDEN
UNBLOCK_FILE_ONLY_AFTER_HASH_PASS=YES

# --- PowerShell
POWERSHELL_FAIL_CLOSED=YES
PS_CARDINALITY_NORMALIZE=YES
PS_INDEX_UNNORMALIZED_FORBIDDEN=YES
STRICTMODE_OPTIONAL_PROPERTY_DIRECT_ACCESS_FORBIDDEN=YES
JSON_OPTIONAL_PROPERTY_VIA_PSOBJECT=YES
PASS_FAIL_RECEIPT_SCHEMA_MAY_DIFFER=YES
FAIL_RECEIPT_NOT_PARSED_AS_PASS=YES
CHILD_GATE_RESULT_PRECEDENCE=YES
ONE_SHOT_GATE_AUTO_RERUN_FORBIDDEN=YES
WRAPPER_MUST_SUPPORT_FAIL_SCHEMA=YES
PS_PARSE_BEFORE_EFFECT=MANDATORY
PS_TARGET_SHELL_PARSE_MUST_BE_EXECUTED_OR_LOCALLY_ACCEPTED=YES
SELF_PARSE_PRESENT_IS_NOT_PARSE_PROOF=YES
PS_TYPED_CATCH_CANONICAL_SYNTAX=catch_[Type]_brace
PARSE_PASS_NOT_RUNTIME_PASS=YES
ENV_VARS_RESTORED_IN_FINALLY=YES

# --- Processos nativos
NATIVE_EXIT_CODE_AUTHORITATIVE=YES
NATIVE_STDERR_MUST_NOT_OVERRIDE_EXIT_CODE=YES
NATIVE_STDERR_NONEMPTY_IS_NOT_FAILURE=YES
PS51_REDIRECTED_NATIVE_STDERR_IS_NOT_RAW=YES
RAW_NATIVE_STDERR_USE_SYSTEM_DIAGNOSTICS_PROCESS=YES
PS51_NATIVE_REDIRECT_UNDER_EAP_STOP_FORBIDDEN=YES
LASTEXITCODE_SENTINEL_BEFORE_NATIVE_CALL=YES
NATIVE_EXE_ABSOLUTE_PATH=YES
PS51_NATIVE_ARG_DOUBLE_QUOTE_FORBIDDEN=YES
PS51_PYTHON_DASH_C_NONTRIVIAL_FORBIDDEN=YES
CRITICAL_PYTHON_PROBE_USE_SCRIPT_FILE=YES
TEMP_FILE_CLEANUP_IN_FINALLY=YES

# --- Encoding e cultura
PS1_NON_ASCII_REQUIRES_UTF8_BOM=YES
MACHINE_FILES_UTF8_NO_BOM=YES
PS51_OUTFILE_REDIRECT_FOR_MACHINE_FILES_FORBIDDEN=YES
MACHINE_OUTPUT_INVARIANT_CULTURE=YES
TIMESTAMPS_ISO8601_WITH_OFFSET=YES

# --- Python
PYTHON_CWD_DEPENDENCY=FORBIDDEN
PYTHON_PINNED_RUNTIME_WHEN_SPECIFIED=YES
PYTHON_RUNTIME_RECORDED_IN_RECEIPT=YES
PY_COMPILE_BEFORE_EFFECT_WHEN_APPLICABLE=YES
EXACT_CANDIDATE_BYTES_COMPILE_BEFORE_INSTALL=YES
EMBEDDED_PAYLOAD_HASH_PINNING=MANDATORY
STAGING_BEFORE_PROJECT_REPLACE=MANDATORY_WHEN_APPLICABLE
SILENT_EXCEPTION_FALLBACK=FORBIDDEN
LARGE_FILE_EDGE_READ_BY_SEEK=YES
FULL_SCAN_ONLY_IN_DEDICATED_CENSUS=YES
LONG_PROCESS_CHECKPOINT_RESUME_TIMEOUT_REPORT=YES

# --- Status, exit, receipt
EXIT_0=PASS
ANY_NONZERO=NOT_PASS
EXIT_CODE_MAP_DEFAULT=0_PASS/1_FAIL/2_BLOCKED/3_PARTIAL_EFFECT/130_SAFE_STOP
COMPOSITE_STATUS_IS_NOT_PASS=YES
RECEIPT_STANDARD_SCHEMA=RUNNER_RECEIPT_V001
FINAL_CONSOLE_SUMMARY_KEY_VALUE=YES

# --- Transação, concorrência, efeitos
ATOMIC_CRITICAL_WRITES=YES
ATOMIC_TEMP_SAME_VOLUME=YES
FREE_SPACE_GATE_BEFORE_BULK_WRITE=YES
SINGLE_WRITER_LOCK=YES_WHEN_EFFECTFUL
STALE_LOCK_AUTO_DELETE=FORBIDDEN
SAFE_STOP_WHEN_DEFINED=YES
DETERMINISTIC_RESUME_WHEN_DEFINED=YES
WIN32_HANDLE_ACCESS_LEAST_PRIVILEGE=YES
CRITICAL_DOTNET_OVERLOAD_TARGET_RUNTIME_PROBE=MANDATORY
ARTIFACT_FILENAME_REVISION_IS_NOT_PROTOCOL_CONTRACT_ID=YES
PROTOCOL_CONTRACT_ID_MUST_BE_EXPLICIT=YES
CONTRACT_ID_INFERENCE_FROM_FILENAME=FORBIDDEN
CROSS_COMPONENT_CONTRACT_SATISFIABILITY=MANDATORY
BUNDLE_INTEGRITY_PASS_DOES_NOT_IMPLY_PROTOCOL_ADMISSION_PASS=YES
CRITICAL_DOTNET_ARGUMENT_SHAPE_MUST_MATCH_PROBE=YES
PS51_CRITICAL_FILE_REPLACE_NULL_BACKUP=FORBIDDEN_UNLESS_PROVEN
CRITICAL_FILE_REPLACE_EXPLICIT_BACKUP_PATH=MANDATORY
FILE_REPLACE_BACKUP_HASH_VALIDATION=MANDATORY
EFFECTS_OCCURRED_SCOPE_MUST_BE_EXPLICIT=YES
PROTECTED_STATE_EFFECTS_SEPARATE_FROM_EVIDENCE_WRITES=YES
SAFE_TO_RERUN_NOT_EQUAL_RERUN_AUTHORIZED=YES
KNOWN_DETERMINISTIC_DEFECT_RERUN=FORBIDDEN
WIN32_ACCESS_MASK_BITWISE_JUSTIFICATION=YES
WIN32_READ_PIN_CREATE_WRITE_RIGHTS=FORBIDDEN_UNLESS_REQUIRED
WIN32_ANCESTOR_ACCESS_TEST_ON_PROTECTED_PATHS=YES
PROCESS_TERMINATION_NOT_EQUAL_HANDLE_RELEASE=YES
PROCESS_HANDLES_CLOSE_BEFORE_JOB_FINAL_CENSUS=YES
PROCESS_HANDLE_CLEANUP_NO_GC_DEPENDENCY=YES
PRIMARY_ERROR_PRECEDENCE_OVER_CLEANUP_ERROR=YES
CLEANUP_ERROR_RECORDED_SEPARATELY=YES
SHARED_JOB_GLOBAL_MEMBERSHIP_EQUALITY_GATE=FORBIDDEN
SHARED_JOB_HARNESS_TRACKS_OWNED_PROCESS_IDENTITIES=YES
OWNED_PROCESS_IDENTITY=PID_PLUS_CREATION_TIME
OWNED_WORKERS_ABSENT_AFTER_CLEANUP=MANDATORY
PID_REUSE_FALSE_RESIDUAL=FORBIDDEN
EXTERNAL_JOB_CHURN=DIAGNOSTIC_ONLY
DEDICATED_JOB_STRICT_INVARIANT_REMAINS_REQUIRED=YES
PARTIAL_EFFECT_STATE_MUST_BE_REPORTED=YES
BLIND_RERUN_AFTER_PARTIAL_EFFECT_FORBIDDEN=YES
POST_FAILURE_RECONCILIATION_BEFORE_RETRY=MANDATORY

# --- Hashes
HASH_HEX_CASE_NORMALIZED_BEFORE_COMPARE=YES
HASH_PREFIX_AS_IDENTITY=FORBIDDEN
HASH_OVER_PHYSICAL_INSTALLED_BYTES=YES
GITATTRIBUTES_EXPLICIT_FOR_PINNED_HASHES=YES

# --- Entrega e governança
ASSISTANT_PREDELIVERY_RUNNER_AUDIT=MANDATORY
DRY_RUN_DEFAULT=YES
SUBSTANTIVE_DRY_RUN_RECEIPT=MANDATORY
SUCCESSFUL_SUBSTANTIVE_DRY_RUN_RECEIPT_NOT_WRITTEN=FORBIDDEN
NATIVE_SECURITY_DELTA_PREINSTALL_QUALIFICATION_NO_EFFECT=MANDATORY
DRY_RUN_ONLY_QUALIFIER_HAS_NO_INSTALL_PATH=YES
INSTALL_RUNNER_SEPARATE_AFTER_QUALIFICATION_PASS=YES
MANDATORY_FIXTURE_OPTIONAL_PRIVILEGE=FORBIDDEN_WHEN_EQUIVALENT_EXISTS
MANDATORY_GATE_SKIP_DUE_FIXTURE_PRIVILEGE=FORBIDDEN
RUNNER_SKELETON_ANNEX_A_BASELINE=YES
TEST_COUNT_GATE_MUST_BE_PHYSICALLY_DERIVED=YES
GATE_CARDINALITY_FROM_ASSUMPTION=FORBIDDEN
USER_AUTHORIZATION_PER_ACTION=YES
SILENCE_IS_NOT_CONSENT=YES
ONE_SCRIPT_PER_TURN=YES
TEST_BATTERY_WITH_INJECTED_DEFECTS=YES
FACT_HYPOTHESIS_NOT_VERIFIABLE_LABELS=YES
NEW_TECHNICAL_DISCOVERY_CANONICAL_POLICY_REVISION=MANDATORY
CANONICAL_POLICY_REVISION_SAME_STAGE_AS_DISCOVERY=YES
CANONICAL_PRIOR_VERSION_PRESERVED=YES
CANONICAL_HYPOTHESIS_PROMOTION=FORBIDDEN
CANONICAL_RULE_REFUTATION_CORRECTIVE_REVISION=IMMEDIATE

# --- Destrutivas e Git
SOURCE_MUTATION_DEFAULT=NO
CANONICAL_DATA_DELETION_DEFAULT=NO
ARCHIVE_BY_MOVE_PREFERRED_OVER_DELETE=YES
GIT_STATUS_BEFORE_PATCH=YES
UNRELATED_LOCAL_CHANGES_DISCARD=FORBIDDEN
GIT_DESTRUCTIVE_COMMANDS_WITHOUT_AUTH=FORBIDDEN
VERSIONED_BASELINE_IN_PLACE_EDIT=FORBIDDEN
```

---

## ANEXO A — ESQUELETO CANÔNICO DE RUNNER (WINDOWS POWERSHELL 5.1)

**Estado de validação:** parse 0 erros; executado nos cenários BLOCKED (shell, `OutBase` ausente, lock presente, `OutRoot` existente), DRY_RUN e EXECUTE, com PowerShell 7.4. A validação em 5.1 fica pendente como teste de aceitação no PC do usuário (§0.2). O arquivo é ASCII puro.

Uso:

```powershell
& 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -NoProfile -ExecutionPolicy Bypass -File 'D:\<PACOTE>\RUNNER.ps1'
& 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -NoProfile -ExecutionPolicy Bypass -File 'D:\<PACOTE>\RUNNER.ps1' -Execute
```

Pontos de personalização: `$RunnerName`, `$OutBase`, pré-condições (3.1), plano (3.2) e efeitos (3.3). Cada efeito em projeto/dado chama `Register-Effect`.

```powershell
#requires -Version 5.1
<#
    RUNNER CANONICO - ESQUELETO V005
    AMBIENTE=PowerShell (Windows PowerShell 5.1 Desktop)
    Salvar este arquivo em UTF-8 COM BOM quando contiver qualquer caractere nao ASCII.
    Padrao: DRY-RUN. Efeitos somente com -Execute.
#>
[CmdletBinding()]
param(
    [switch]$Execute
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

# ---------------------------------------------------------------------------
# 1. Identidade e configuracao fixa (caminhos absolutos; nunca o cwd)
# ---------------------------------------------------------------------------
$RunnerName    = 'PROJETO_FASE_V001R1'
$RunnerRoot    = $PSScriptRoot
$OutBase       = 'D:\Runs\PROJETO'          # configurar; absoluto e fora do pacote fonte
$Invariant     = [Globalization.CultureInfo]::InvariantCulture
$Utf8NoBom     = New-Object System.Text.UTF8Encoding($false)
$RunId         = [DateTime]::Now.ToString('yyyyMMdd_HHmmss_fff', $Invariant) + '_' + $PID
# [IO.Path]::Combine nao consulta a unidade; Join-Path falharia antes do try se D: nao existir.
$OutRoot       = [IO.Path]::Combine($OutBase, ($RunnerName + '_' + $RunId))
$LogDir        = [IO.Path]::Combine($OutRoot, 'logs')
$LogPath       = [IO.Path]::Combine($LogDir, 'runner.log')
$ReceiptPath   = [IO.Path]::Combine($OutRoot, 'RECEIPT.json')
$LockPath      = [IO.Path]::Combine($OutBase, ($RunnerName + '.lock'))

$script:Status          = 'BLOCKED'
$script:ExitCode        = 2
$script:Message         = ''
$script:EffectsOccurred = $false
$script:FilesChanged    = New-Object System.Collections.Generic.List[string]
$script:LockHandle      = $null
$script:LogReady        = $false
$script:ReceiptWritten  = $false

# ---------------------------------------------------------------------------
# 2. Funcoes utilitarias
# ---------------------------------------------------------------------------
function Write-Log {
    param([Parameter(Mandatory=$true)][string]$Text)
    $Line = [DateTime]::Now.ToString('yyyy-MM-ddTHH:mm:ss.fffzzz', $Invariant) + ' ' + $Text
    Write-Host $Line
    if ($script:LogReady) {
        [IO.File]::AppendAllText($LogPath, $Line + "`r`n", $Utf8NoBom)
    }
}

function Stop-Blocked {
    param([Parameter(Mandatory=$true)][string]$Reason)
    throw ('BLOCKED:' + $Reason)
}

function Assert-FileSha256 {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$Expected
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Stop-Blocked ('FILE_MISSING=' + $Path)
    }
    $Actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
    if ($Actual -ne $Expected.ToUpperInvariant()) {
        Stop-Blocked ('SHA256_MISMATCH=' + $Path + ' expected=' + $Expected + ' actual=' + $Actual)
    }
    Write-Log ('SHA256_OK=' + $Path)
}

function Invoke-NativeChecked {
    <#
        Executa processo nativo sem que stderr vire erro terminante no PS 5.1.
        Exit code e a autoridade. Argumentos nao podem conter aspas duplas.
        ATENCAO V005R1: Stderr retornado e diagnostico observado pelo PowerShell;
        nao e garantia de stream bruto do descritor 2. Ver secao 9.9.1.
    #>
    param(
        [Parameter(Mandatory=$true)][string]$FilePath,
        [string[]]$ArgumentList = @(),
        [switch]$AllowNonZero
    )
    if (-not [IO.Path]::IsPathRooted($FilePath)) {
        Stop-Blocked ('NATIVE_PATH_NOT_ABSOLUTE=' + $FilePath)
    }
    if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) {
        Stop-Blocked ('NATIVE_EXE_MISSING=' + $FilePath)
    }
    foreach ($A in @($ArgumentList)) {
        if ($A.Contains('"')) {
            Stop-Blocked 'NATIVE_ARG_WITH_DOUBLE_QUOTE_FORBIDDEN_UNDER_PS51'
        }
    }
    $ErrPath = [IO.Path]::GetTempFileName()
    $Sentinel = -2147483648
    $global:LASTEXITCODE = $Sentinel
    $PrevEap = $ErrorActionPreference
    $Out = @()
    $Code = $Sentinel
    try {
        $ErrorActionPreference = 'Continue'
        $Out = @(& $FilePath @ArgumentList 2> $ErrPath)
        $Code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $PrevEap
    }
    $Err = ''
    try {
        $Err = [IO.File]::ReadAllText($ErrPath)
    }
    finally {
        Remove-Item -LiteralPath $ErrPath -Force -ErrorAction SilentlyContinue
    }
    if ($Code -eq $Sentinel) {
        throw ('NATIVE_NOT_EXECUTED=' + $FilePath)
    }
    if ($Err.Length -gt 0) {
        Write-Log ('NATIVE_STDERR_BEGIN ' + $FilePath)
        Write-Log $Err.TrimEnd()
        Write-Log 'NATIVE_STDERR_END'
    }
    if (($Code -ne 0) -and (-not $AllowNonZero)) {
        throw ('NATIVE_FAILED exit=' + $Code + ' exe=' + $FilePath)
    }
    return [pscustomobject]@{ ExitCode = $Code; Stdout = $Out; Stderr = $Err }
}

function Register-Effect {
    param([Parameter(Mandatory=$true)][string]$Path)
    $script:EffectsOccurred = $true
    [void]$script:FilesChanged.Add($Path)
}

function Write-JsonAtomicNew {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)]$Object
    )
    if (Test-Path -LiteralPath $Path) {
        throw ('RECEIPT_ALREADY_EXISTS=' + $Path)
    }
    $Tmp = $Path + '.partial'
    $Json = $Object | ConvertTo-Json -Depth 8
    [IO.File]::WriteAllText($Tmp, $Json, $Utf8NoBom)
    [IO.File]::Move($Tmp, $Path)
}

# ---------------------------------------------------------------------------
# 3. Execucao
# ---------------------------------------------------------------------------
try {
    if (($PSVersionTable.PSEdition -ne 'Desktop') -or ($PSVersionTable.PSVersion.Major -ne 5)) {
        Stop-Blocked ('SHELL_NOT_WINDOWS_POWERSHELL_5_1=' + $PSVersionTable.PSVersion)
    }
    if (-not (Test-Path -LiteralPath $OutBase -PathType Container)) {
        Stop-Blocked ('OUT_BASE_MISSING=' + $OutBase)
    }
    if (Test-Path -LiteralPath $OutRoot) {
        Stop-Blocked ('OUT_ROOT_ALREADY_EXISTS=' + $OutRoot)
    }

    try {
        $script:LockHandle = [IO.File]::Open($LockPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    }
    catch {
        Stop-Blocked ('LOCK_PRESENT_OR_UNAVAILABLE=' + $LockPath + ' (nao apagar sem diagnostico)')
    }

    [void](New-Item -ItemType Directory -Path $LogDir -Force)
    $script:LogReady = $true

    Write-Log ('RUNNER=' + $RunnerName)
    Write-Log ('RUNNER_ROOT=' + $RunnerRoot)
    Write-Log ('OUT_ROOT=' + $OutRoot)
    Write-Log ('MODE=' + $(if ($Execute) { 'EXECUTE' } else { 'DRY_RUN' }))
    Write-Log 'SCOPE=<descrever>; FORBIDDEN=<descrever>'

    # 3.1 Pre-condicoes (sem efeitos)
    # Assert-FileSha256 -Path 'D:\...\entrada.csv' -Expected '<SHA256>'

    # 3.2 Plano
    Write-Log 'PLAN=<listar efeitos previstos>'

    if (-not $Execute) {
        $script:Status = 'PASS'
        $script:ExitCode = 0
        $script:Message = 'DRY_RUN_ONLY_NO_EFFECTS'
    }
    else {
        # 3.3 Efeitos: STAGE -> VALIDATE -> INSTALL -> TEST
        # Register-Effect -Path '<arquivo alterado>'
        $script:Status = 'PASS'
        $script:ExitCode = 0
        $script:Message = 'EXECUTED'
    }
}
catch {
    $Text = $_.Exception.Message
    if ($Text.StartsWith('BLOCKED:')) {
        $script:Status = 'BLOCKED'
        $script:ExitCode = 2
    }
    else {
        $script:Status = 'FAIL'
        $script:ExitCode = 1
    }
    if ($script:EffectsOccurred) {
        $script:ExitCode = 3
    }
    $script:Message = $Text
    Write-Log ('ERROR=' + $Text)
}
finally {
    if ($script:LogReady) {
        $Receipt = [ordered]@{
            schema            = 'RUNNER_RECEIPT_V001'
            runner            = $RunnerName
            runner_sha256     = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash
            run_id            = $RunId
            mode              = $(if ($Execute) { 'EXECUTE' } else { 'DRY_RUN' })
            status            = $script:Status
            exit_code         = $script:ExitCode
            message           = $script:Message
            effects_occurred  = $script:EffectsOccurred
            files_changed     = @($script:FilesChanged)
            safe_to_rerun_same_runner = (-not $script:EffectsOccurred) -or ($script:Status -eq 'PASS')
            out_root          = $OutRoot
            finished_at       = [DateTime]::Now.ToString('yyyy-MM-ddTHH:mm:ss.fffzzz', $Invariant)
        }
        try {
            Write-JsonAtomicNew -Path $ReceiptPath -Object $Receipt
            $script:ReceiptWritten = $true
        }
        catch {
            Write-Host ('WRAPPER_COLLECTION_ERROR=' + $_.Exception.Message)
        }
    }
    if ($null -ne $script:LockHandle) {
        $script:LockHandle.Dispose()
        Remove-Item -LiteralPath $LockPath -Force -ErrorAction SilentlyContinue
    }
    Write-Host ('STATUS=' + $script:Status)
    Write-Host ('EXIT_CODE=' + $script:ExitCode)
    Write-Host ('EFFECTS_OCCURRED=' + $(if ($script:EffectsOccurred) { 'YES' } else { 'NO' }))
    Write-Host ('RECEIPT=' + $(if ($script:ReceiptWritten) { $ReceiptPath } else { 'NOT_WRITTEN' }))
}
exit $script:ExitCode
```

---

## ANEXO B — RASTREABILIDADE V004 → V005

| V004 | V005 | Situação |
|---|---|---|
| §0 Delta V004 | §0.1 (histórico), §9.10, §11.8, §17.1, §17.2 | Preservado |
| §1 Objetivo | §1 | Ampliado (encoding, cultura, concorrência, logs) |
| §2 Shell / ponto inicial | §2.1–2.2 | Preservado; + checagem de edição, §2.3 convenções |
| §3 Caminhos | §3.1–3.2 | Preservado; + §3.3, §3.4 |
| §4 Downloads | §4 | Preservado; + OneDrive placeholder |
| §5.1–5.5 Classes | §5.1–5.5 | Preservado; + identidade vinculada ao caminho (§5.3), RUN_ID (§5.4) |
| — | §5.6 Logs, §5.7 Estado ativo | Novo |
| §6 Nomenclatura | §6 | Preservado; + pacote único, nome não reutilizado |
| §7 ZIP | §7 | Preservado; + §7.3 reextração, §7.4 validação/case, §7.7 MOTW |
| §8 `$PSScriptRoot` | §8 | Preservado; + limitação de código colado |
| §9, §9.1–9.4 | §9, §9.1–9.4 | Preservado |
| §9.5 | §9.5 | **Corrigido** (E2) |
| §9.6 | §9.6 | Preservado; + `[AllowNull()]` |
| §9.7, §9.8 | §9.7, §9.8 | Preservado |
| §9.9 | §9.9 | **Corrigido** (E1) |
| §9.10 | §9.10 | Preservado; + definição de "efeito", exit 3 |
| — | §9.11 Encoding/cultura | Novo (E3) |
| §10 Launchers | §10 | Preservado; + motivo de exit code |
| §11.1–11.8 | §11.1–11.8 | Preservado; + temp no mesmo volume, leitura de bordas |
| — | §11.9 Processos longos | Novo (regra existente do usuário) |
| §12.1–12.3 | §12.1–12.3 | Preservado |
| — | §12.4, §12.5 | Novo (E6) |
| §13 | §13.1 | Preservado; + status compostos |
| — | §13.2–13.4 | Novo |
| §14 | §14 | Preservado; + lock de escritor único |
| §15 | §15 | Preservado; + gate de espaço livre |
| §16 | §16.1 | Preservado; + §16.2, §16.3 |
| §17, §17.1, §17.2 | §17, §17.1, §17.2 | Preservado e ampliado |
| — | §17.3 Gate de autorização | Novo (regra existente do usuário) |
| §18, §19 | §18, §19 | Preservado; + arquivar por movimento |
| — | §20 Git | Novo |
| §20 Status canônico + blocos dispersos | §22 Registro único | Consolidado (E5); nenhuma chave V004 removida; chaves renomeadas mantêm o mesmo significado |

**Chaves V004 renomeadas no registro (mesmo significado):**

| V004 | V005 |
|---|---|
| `POWERSHELL_0_1_N_CARDINALITY_MUST_BE_NORMALIZED` | `PS_CARDINALITY_NORMALIZE` |
| `INDEX_UNNORMALIZED_PIPELINE_RESULT=FORBIDDEN` | `PS_INDEX_UNNORMALIZED_FORBIDDEN` |
| `PYTHON_DASH_C_NONTRIVIAL_UNDER_PS51=FORBIDDEN` | `PS51_PYTHON_DASH_C_NONTRIVIAL_FORBIDDEN` |
| `TEMP_PYTHON_PROBE_CLEANUP_IN_FINALLY` | `TEMP_FILE_CLEANUP_IN_FINALLY` (escopo ampliado) |
| `JSON_OPTIONAL_PROPERTY_MUST_USE_PSOBJECT_PROPERTIES` | `JSON_OPTIONAL_PROPERTY_VIA_PSOBJECT` |
| `FAIL_RECEIPT_MUST_NOT_BE_PARSED_AS_PASS_SCHEMA` | `FAIL_RECEIPT_NOT_PARSED_AS_PASS` |
| `CHILD_GATE_RESULT_HAS_PRECEDENCE_OVER_WRAPPER_COLLECTION_ERROR` | `CHILD_GATE_RESULT_PRECEDENCE` |
| `ONE_SHOT_GATE_AUTOMATIC_RERUN_AFTER_WRAPPER_ERROR=FORBIDDEN` | `ONE_SHOT_GATE_AUTO_RERUN_FORBIDDEN` |
| `POWERSHELL_PARSE_BEFORE_EFFECTFUL_EXECUTION` | `PS_PARSE_BEFORE_EFFECT` |
| `PYTHON_PY_COMPILE_BEFORE_EFFECTFUL_EXECUTION` | `PY_COMPILE_BEFORE_EFFECT_WHEN_APPLICABLE` |
| `PARSE_PASS_DOES_NOT_REPLACE_RUNTIME_SCHEMA_TESTS` | `PARSE_PASS_NOT_RUNTIME_PASS` |
| `PS51_NATIVE_STDERR_MERGE_IN_CRITICAL_GATE=FORBIDDEN_WHEN_AMBIGUOUS` | `PS51_NATIVE_REDIRECT_UNDER_EAP_STOP_FORBIDDEN` (endurecido) |
| `EXTERNAL_PROCESS_EXIT_CODE_AUTHORITATIVE` | `NATIVE_EXIT_CODE_AUTHORITATIVE` |
| `BLIND_RERUN_AFTER_PARTIAL_EFFECT=FORBIDDEN` | `BLIND_RERUN_AFTER_PARTIAL_EFFECT_FORBIDDEN` |
| `PS51_NATIVE_ARGUMENT_QUOTING_MUST_NOT_CARRY_CRITICAL_PYTHON_SOURCE` | coberta por `CRITICAL_PYTHON_PROBE_USE_SCRIPT_FILE` + `PS51_NATIVE_ARG_DOUBLE_QUOTE_FORBIDDEN` |
| `PYTHON_NONZERO_MEANS_NOT_PASS` | `ANY_NONZERO=NOT_PASS` |
| `SOURCE_MUTATION_DEFAULT=NO` | mantida |
| `STRICTMODE_OPTIONAL_PROPERTY_DIRECT_ACCESS=FORBIDDEN` | `STRICTMODE_OPTIONAL_PROPERTY_DIRECT_ACCESS_FORBIDDEN` |


---

## ANEXO C — RASTREABILIDADE V005 → V005R1

| ID V005R1 | Evidência que motivou a regra | Seção |
|---|---|---|
| R1-01 | Runner entregue continha self-parse, mas erro sintático em `catch[Type]` impediu qualquer linha de executar | §9.8.1 |
| R1-02 | Windows PowerShell 5.1 aceitou `catch [Type]`, rejeitou `catch[Type]` | §9.8.1 |
| R1-03 | Git/Python sob `2>` produziram texto com `NativeCommandError`, localização do script e `RemoteException`, embora o processo continuasse e o exit code fosse coletado | §9.9.1 |
| R1-04 | Probe físico: access mask com `FILE_ADD_FILE` falhou em `C:\`/`C:\Users` com Win32=5; remoção do direito passou `Validate()` | §12.6 |
| R1-05 | Testes PREP deixaram membros do Job contabilizados após `wait()`, motivando inspeção explícita de lifetime de handles | §14.1 |
| R1-06 | `PREP_WORKER_ERROR` foi substituído por erro posterior de cleanup | §14.2 |
| R1-07 | Suíte executada sob Job preexistente mostrou que `{current_pid}` não é baseline universal de harness | §14.3 |
| R1-08 | `os.symlink` falhou com WinError 1314; junction preservou o objetivo "reparse point" sem exigir aquele privilégio | §17.5 |
| R1-09 | DRY-RUN-only impediu instalação de candidata que inicialmente teve 32 resultados ruins e depois 2; workspace permaneceu intacto | §17.4 |
| R1-10 | `unittest` verbose escreveu progresso normal em stderr | §9.9.1 |
| R1-11 | DRY-RUN passou a ser tratado como execução auditável com receipt quando há gates substantivos | §13.3 |
| R1-12 | Hipóteses não reproduzidas foram deliberadamente excluídas desta revisão | §0.3 / governança |

### C.1 Regras deliberadamente **não** adicionadas

Não foi promovida a regra canônica nenhuma hipótese sem prova física suficiente. Em particular, suspeitas transitórias sobre serialização de coleções PowerShell/JSON permanecem fora da política enquanto não houver reprodução controlada que isole a causa.

### C.2 Relação com SPEC de projeto

Esta política define **como executar e provar**. Uma SPEC pode exigir invariantes mais fortes — por exemplo, Job dedicado contendo exclusivamente supervisor e descendentes, access mask exata, zero skips ou fixture específica — e esses invariantes continuam prevalecendo quando forem mais restritivos.


---

## ANEXO D — RASTREABILIDADE V005R1 → V005R2

| ID | Evidência | Correção |
|---|---|---|
| R2-01 | Gate2 V001R2: após cleanup, `FINAL_JOB_MEMBERS` ganhou PID 17236 e perdeu seis PIDs do baseline em ~3 s | Remove `FINAL == BASELINE` como autoridade em Job compartilhado |
| R2-02 | Workers já enviam `pid` e `process_creation_time` no hello autenticado | Ownership passa a usar identidade `(PID, creation_time)` |
| R2-03 | Gate1 já provou root-loader/Job dedicado, assign-before-resume, breakaway e kill-on-close | Invariante estrito permanece no contexto dedicado |
| R2-04 | Instrução explícita do usuário em 27/09/2026 | Toda nova descoberta técnica comprovada gera revisão canônica automaticamente |
| R2-05 | Regra V005R1 foi falsificada pelo run físico imediatamente seguinte | Evidência nova exige revisão corretiva imediata |

### D.1 Regra revogada

```text
HARNESS_JOB_FINAL_EQUALS_BASELINE=YES
```

foi **revogada**. Ela não deve aparecer em nenhum novo runner, teste ou SPEC como regra transversal para Job compartilhado.

### D.2 Regras da V005R1 que permanecem válidas

Continuam vigentes, entre outras:

- fechar deterministicamente handles de processo antes de census final;
- não depender de GC;
- preservar erro primário sobre erro de cleanup;
- qualificação DRY-RUN-only antes de instalar deltas nativos/de segurança;
- access masks Win32 de mínimo privilégio;
- fixture obrigatória sem privilégio opcional quando houver equivalente;
- stderr não vazio não é FAIL;
- self-parse não é prova de parse.


---

## ANEXO E — RASTREABILIDADE V005R2 → V005R3

| ID | Evidência | Regra |
|---|---|---|
| R3-01 | Gate2 installer V001, primeiro `-Execute`: `File.Replace($Partial,$Target,$null,$true)` lançou `ArgumentException: caminho inválido` | §12.7 exige probe da mesma forma de argumentos no runtime-alvo |
| R3-02 | Falha ocorreu na primeira substituição, antes de qualquer arquivo protegido ser alterado | `File.Replace` crítico passa a usar backup path absoluto não nulo e validação de hash |
| R3-03 | Backup/evidência já existiam, mas workspace continuou intacto | §13.3.1 separa efeitos protegidos de escritas de evidência |
| R3-04 | DRY-RUN anterior compilou/materializou, mas não exercitou o overload que falhou | §17.4 exige self-test da primitive/overload/argument shape antes do efeito real |
| R3-05 | Falha ocorreu com estado protegido intacto, porém repetir o mesmo runner reproduziria a causa conhecida | §13.3.2 separa segurança de rerun de autorização de rerun |

### E.1 Compatibilidade documental

A documentação Microsoft do `System.IO.File.Replace` informa que `destinationBackupFileName` pode ser `null`, inclusive no .NET Framework. A V005R3 **não contradiz esse contrato**. Ela registra que, para um runner PowerShell 5.1 crítico, o contrato documentado não substitui a prova física da forma de chamada usada pelo binder do shell.

### E.2 Estado do incidente que originou a revisão

```text
POWERSHELL_PARSE_GATE=PASS
MODE=EXECUTE
BACKUP_EVIDENCE_CREATED=YES
FIRST_PROTECTED_REPLACE=FAIL_BEFORE_REPLACEMENT
PROTECTED_STATE_EFFECTS_OCCURRED=NO
PROJECT_WORKSPACE_ROLLBACK_REQUIRED=NO
SAME_RUNNER_BLIND_RERUN=NO
```


---

## ANEXO F — RASTREABILIDADE V005R3 → V005R4

| ID | Evidência física | Consequência |
|---|---|---|
| R4-01 | `INLINE_ROOT_LOADER_V004_R1R1.ps1` SHA `CFAE...C78` exige external anchor revision `INLINE_ROOT_LOADER_V004_R1` | Nome do artefato não define contract ID |
| R4-02 | Gate1 access-fix harness do próprio loader constrói anchor com `INLINE_ROOT_LOADER_V004_R1` | `R1` é o contract ID comprovado do loader homologado |
| R4-03 | Source canário SHA `B79B...E897` exige `INLINE_ROOT_LOADER_V004_R1R1` | Incompatibilidade end-to-end comprovada |
| R4-04 | `OWNER_GATE.json` SHA `21D1...EB93` também publica `R1R1` | Gate/bundle precisam ser regenerados após correção |
| R4-05 | ZIP SHA `09BF...6840`, CRC e manifest estão íntegros | Integridade física não elimina incompatibilidade lógica |

### F.1 Veredito do incidente

```text
CANARY_RELEASE_BUNDLE_PHYSICAL_INTEGRITY=PASS
CANARY_RELEASE_BUNDLE_PROTOCOL_ADMISSION=FAIL
EXTERNAL_ANCHOR_SATISFIABLE=NO
CANARY_EXECUTION_AUTHORIZED=NO
PRODUCTION_RECOVERY_AUTHORIZED=NO
```

### F.2 Regra de correção

A correção deve partir do contract ID **comprovado pelo componente raiz homologado**, e não do sufixo do filename. Depois:

1. corrigir produtor/consumidores divergentes;
2. repetir suíte completa;
3. repetir gate de identidade tested-vs-installed;
4. regenerar owner gate/bundle;
5. repetir revisão independente Stage A;
6. somente então criar external release anchor.


---

## ANEXO G — DELTA V005R5: canais de controle e topologia de console Windows

A combinação `CREATE_NO_WINDOW` + `AttachConsole(PID)` + `GenerateConsoleCtrlEvent(CTRL_C_EVENT)` não pode ser tratada como canal SAFE_STOP válido sem prova de console compartilhado.

Regras canônicas:

```text
CREATE_NO_WINDOW_CTRL_EVENT_CHANNEL=FORBIDDEN_UNLESS_TARGET_HAS_PROVEN_CONSOLE
CONSOLE_CTRL_CHANNEL_REQUIRES_SHARED_CONSOLE_PROOF=YES
PROCESS_CONTROL_CHANNEL_TOPOLOGY_COMPATIBILITY_PROBE=MANDATORY
SAFE_STOP_CHANNEL_MUST_NOT_DEPEND_ON_UNPROVEN_CONSOLE_ATTACHMENT=YES
NAMED_KERNEL_EVENT_SAFE_STOP_CHANNEL=ALLOWED_WHEN_HASH_BOUND_AND_AUTHENTICATED_BY_GATE
```

Aplicação TICKSTORE V004R1:

```text
safe_stop_event_name=Global\TICKSTORE_V004R1_STOP_<32 HEX MAIUSCULO>
```

O evento manual-reset é criado pelo master orchestrator antes do lançamento. O engine abre apenas um nome previamente validado e o usa como sinal cooperativo; SIGINT permanece caminho secundário, não autoridade primária do operador.

Provas obrigatórias no Windows alvo:
1. nome inválido fail-closed;
2. evento ausente bloqueia antes do writer lock;
3. sinal do evento alcança o supervisor;
4. exit 130 + SAFE_STOP=YES;
5. lock ausente e árvore limpa;
6. kill-on-close permanece apenas fallback de fatal stall.


---

## ANEXO H — DELTA V005R6: escapes entre linguagens, ingestão de parecer e objetos Win32 nomeados

### H.1 Descobertas físicas do CP2

A revisão CP2 comprovou três classes de falha transversal:

1. um regex correto em JSON foi transcrito literalmente para uma string raw Python, preservando escapes de JSON que não pertenciam ao domínio da regex;
2. uma mudança de contrato obrigatória (`safe_stop_event_name`) não foi propagada para uma fixture RECOVER existente;
3. o orquestrador aceitava parecer externo por busca de substrings, o que poderia transformar um parecer `BLOCKED` que apenas citasse texto de aprovação em falso PASS.

A revisão também exigiu que a criação de evento Win32 nomeado recuse `ERROR_ALREADY_EXISTS=183` para evitar reutilizar um objeto residual ou criado por terceiro.

### H.2 Regras canônicas novas

```text
CROSS_LANGUAGE_ESCAPE_COPY_WITHOUT_SEMANTIC_VECTOR_TEST=FORBIDDEN
JSON_ESCAPE_SYNTAX_IS_NOT_PYTHON_RAW_STRING_SYNTAX=YES
REGEX_CONTRACT_REQUIRES_ACCEPT_AND_REJECT_VECTORS=YES
CONTRACT_FIELD_ADDITION_REQUIRES_ALL_FIXTURES_UPDATED=YES
EXTERNAL_REVIEW_SUBSTRING_ACCEPTANCE=FORBIDDEN
EXTERNAL_REVIEW_AUTHORITATIVE_BLOCK_PARSE=MANDATORY
EXTERNAL_REVIEW_DUPLICATE_KEYS=BLOCKED
EXTERNAL_REVIEW_HASH_EQUALITY=MANDATORY
BLOCKED_REVIEW_MAY_CONTAIN_APPROVAL_TEXT_WITHOUT_BECOMING_PASS=YES
NAMED_KERNEL_OBJECT_PREEXISTENCE_CHECK=MANDATORY
CREATEEVENT_ERROR_ALREADY_EXISTS=BLOCKED_UNLESS_EXPLICIT_REUSE_PROTOCOL
TEST_CARDINALITY_IS_NOT_TEST_EXECUTION_EVIDENCE=YES
PHYSICAL_TEST_RUN_RECEIPT_REQUIRED_FOR_RELEASE=YES
```

### H.3 Regra de escapes entre serializações

Ao transportar uma expressão entre JSON, PowerShell, Python, regex ou outra gramática:

1. identificar a sequência semântica desejada;
2. escrever a representação própria de cada linguagem separadamente;
3. executar vetores positivos e negativos no runtime alvo;
4. nunca copiar uma representação escapada de uma linguagem como se fosse literal da outra.

Exemplo:

```text
SEMÂNTICA: Global\TICKSTORE...
JSON:     "Global\\TICKSTORE..."
PY RAW:   r"Global\TICKSTORE..." para texto literal
REGEX RAW:r"^Global\\TICKSTORE..." para uma barra literal no alvo
```

A autoridade é o comportamento dos vetores, não a semelhança textual.

### H.4 Ingestão de parecer externo

Pareceres externos usados como gates devem ser lidos por estrutura:

- localizar apenas o bloco autoritativo declarado;
- parsear linha por linha `CHAVE=VALOR`;
- recusar chaves duplicadas;
- comparar valores por igualdade exata;
- vincular hashes aos bytes locais;
- não pesquisar por `contains`, `in`, regex ampla ou frases soltas no documento.

Um parecer `BLOCKED` continua `BLOCKED` mesmo que sua fundamentação contenha frases como `APPROVED=YES` a título de exemplo ou condição futura.

### H.5 Objetos Win32 nomeados

Ao usar `CreateEventW`, `CreateMutexW`, `CreateFileMappingW` ou primitiva equivalente como autoridade de coordenação:

- zerar/ler `GetLastError` da chamada crítica;
- quando a política exige objeto novo, `ERROR_ALREADY_EXISTS` é bloqueante;
- reutilização só é permitida por protocolo explícito de identidade, ownership e estado;
- nome aleatório não substitui a verificação de preexistência.

### H.6 Evidência de testes

Não é permitido concluir:

```text
TESTS_PASS=YES
```

a partir de:

```text
AST_COUNT=N
DISCOVERED_COUNT=N
```

ou apenas da presença dos arquivos.

É obrigatório, quando o gate exige execução:

```text
TARGET_RUNTIME_EXECUTION=YES
TESTS_RUN=N
FAILURES=0
ERRORS=0
UNEXPECTED_SKIPS=0
EXIT_CODE=0
```

e o receipt deve vincular os hashes dos bytes testados.

### H.7 Aplicação TICKSTORE CP2R1

A revisão CP2 pré-selou exatamente:

```text
CORRECTED_CANDIDATE_SHA256=0A4147134C64C18EF296825A9DCADCE1F54421D3CB3D7647789EE8D608FC427C
CORRECTED_RELEASE_SHA256=178A588E88C03721F8146C19C571698CC69B907BA0A31BEFF869798257321276
NEW_EXTERNAL_REVIEW_REQUIRED_FOR_CP2R1=NO
```

desde que:

- o engine mude apenas a linha de regex pré-selada;
- R-01/T-E1..T-E6 esteja presente;
- R-02 e R-03 estejam implementados;
- A2 e B2 passem fisicamente no Windows/Python 3.14.7;
- nenhum skip inesperado ocorra.

Qualquer outro byte do engine exige nova revisão CP2.


---

## ANEXO I — DELTA V005R7: gramática obrigatória de hashes antes do binding

### I.1 Descoberta física

Um SHA-256 transcrito em evidência narrativa foi aceito como valor de binding apesar de possuir somente **63 caracteres hexadecimais**.

Valor narrativo malformado:

```text
71A9BA7B417A2E4D6A230EC937B9F11CF270C6F28532654A0E1D03E94527036
```

Valor físico medido pelo Windows `Get-FileHash`:

```text
71A9BA7BD417A2E4D6A230EC937B9F11CF270C6F28532654A0E1D03E94527036
```

O resultado corretivo físico e o conteúdo do receipt permanecem coerentes; o defeito foi exclusivamente de **transcrição/binding do hash esperado**.

### I.2 Regras canônicas novas

```text
SHA256_EXPECTED_GRAMMAR=^[0-9A-F]{64}$
SHA256_GRAMMAR_GATE_BEFORE_COMPARISON=MANDATORY
NARRATIVE_HASH_CANNOT_OVERRIDE_PHYSICAL_HASH=YES
PHYSICAL_HASH_REMEASUREMENT_REQUIRED_WHEN_NARRATIVE_HASH_IS_MALFORMED=YES
MALFORMED_EXPECTED_HASH=PRE_EFFECT_BLOCKED
HASH_BINDING_SOURCE_PRIORITY=PHYSICAL_BYTES_THEN_MACHINE_MANIFEST_THEN_NARRATIVE
```

Antes de qualquer comparação de identidade:

1. validar que o hash esperado é string;
2. validar exatamente 64 hexadecimais maiúsculos;
3. só então medir o arquivo físico;
4. validar também a gramática do hash medido;
5. comparar;
6. em divergência com evidência narrativa, preservar ambos e privilegiar o hash físico ou manifesto de máquina devidamente autenticado.

### I.3 Aplicação TICKSTORE

O A0 do master orchestrator passa a rejeitar configuração com qualquer campo `*_sha256` malformado antes de criar estado operacional relevante ou tocar no workspace.

O binding correto do receipt da qualificação contratual é:

```text
71A9BA7BD417A2E4D6A230EC937B9F11CF270C6F28532654A0E1D03E94527036
```

O estado anterior `A0=FAIL REASON=CORRECTIVE_RECEIPT` é classificado como:

```text
PRE_EFFECT_FAIL=YES
WORKSPACE_MUTATION=NO
CANARY_EFFECT=NO
PRODUCTION_EFFECT=NO
RECONCILIATION_REQUIRED=NO
SAFE_TO_START_FRESH_CONTROL_ROOT=YES
```


---

## ANEXO J — DELTA V005R8: Python isolated mode e resolução explícita de módulos

### J.1 Descoberta física

No Windows/Python 3.14.7, o master executou:

```text
python.exe -I -S -B -m unittest <module names>
```

com `cwd` apontando para o workspace.

Resultado físico:

```text
ModuleNotFoundError: No module named 'test_native_rename_v004r2r1'
ModuleNotFoundError: No module named 'test_precanary_completeness_v005'
ModuleNotFoundError: No module named 'test_publisher_recovery_v004'
```

Os quatro arquivos do workspace possuíam exatamente os hashes esperados; a falha ocorreu exclusivamente na resolução de módulos sob `-I`.

### J.2 Regras canônicas novas

```text
PYTHON_ISOLATED_MODE_CWD_IMPORT_ASSUMPTION=FORBIDDEN
PYTHON_I_FLAG_REQUIRES_EXPLICIT_MODULE_ROOT=YES
TEST_MODULE_ORIGIN_BINDING=MANDATORY
CWD_IS_NOT_MODULE_AUTHORITY=YES
EXPLICIT_AUTHORIZED_SYS_PATH_INSERTION=ALLOWED_IN_PHYSICAL_RUNNER
UNITTEST_MODULE_FILE_IDENTITY=EXACT_PATH_REQUIRED
```

Quando `python -I` for usado:

1. nunca presumir que `cwd` será adicionado a `sys.path`;
2. usar um runner Python físico, não `python -c`;
3. o runner deve adicionar explicitamente o diretório autorizado ao `sys.path`;
4. cada módulo carregado deve ter `__file__` igual ao arquivo físico esperado;
5. qualquer import resolvido para outro diretório é BLOCKED;
6. o `cwd` pode permanecer útil para arquivos relativos, mas não é autoridade de importação.

### J.3 Aplicação TICKSTORE

A2/B2 passam a usar `modules/unittest_path_runner.py` sob:

```text
python.exe -I -S -B <runner.py> <workspace> <3 módulos exatos>
```

O runner:
- admite apenas nomes de módulo simples;
- exige cada `<workspace>\<module>.py`;
- insere somente o workspace autorizado no início de `sys.path`;
- importa cada módulo;
- valida `Path(module.__file__).resolve() == expected`;
- executa a suíte via `unittest` sobre os três módulos explícitos.

O estado físico anterior fica classificado:

```text
A0=PASS
A1=PASS
A2=FAIL_IMPORT_RESOLUTION
WORKSPACE_BYTES=EXACT_EXPECTED
CANARY_EFFECT=NO
PRODUCTION_EFFECT=NO
RESUME_POINT=A2
```


---

## ANEXO K — DELTA V005R9: testes de gates encadeados devem satisfazer gates anteriores

### K.1 Descoberta física

No release TICKSTORE, um teste pretendia provar que a admissão bloqueia antes de qualquer I/O:

```text
dispatch_bootstrap({})
```

esperando `RUNTIME_CONTRACT`.

No runtime físico Windows/Python 3.14.7 com `-I -S`, o `RUNTIME_CONTRACT` já estava satisfeito. O fluxo real prosseguiu para:

```text
anchor = payload["anchor"]
```

e o teste falhou com `KeyError('anchor')`.

O engine não falhou; o teste modelou incorretamente a ordem real dos gates.

### K.2 Regras canônicas novas

```text
CHAINED_GATE_TEST_MUST_SATISFY_ALL_PRIOR_GATES=YES
DOWNSTREAM_GUARD_TEST_WITH_EMPTY_FIXTURE=FORBIDDEN_IF_PRIOR_GATES_CAN_PASS
TEST_EXPECTED_FAILURE_MUST_MATCH_ACTUAL_GATE_ORDER=YES
PRE_IO_TEST_MUST_PATCH_OR_SUPPLY_EARLIER_RUNTIME_CONTRACTS=YES
TEST_FAILURE_IN_RELEASE_DOES_NOT_IMPLY_ENGINE_DEFECT_WITHOUT_ENGINE_PATH_EVIDENCE=YES
```

Ao testar um gate `G_n`:

1. enumerar a ordem real dos gates `G_1..G_n`;
2. satisfazer explicitamente `G_1..G_(n-1)` por fixture ou patch controlado;
3. induzir a falha somente em `G_n`;
4. manter um sentinel que prove ausência de I/O ou efeito posterior;
5. nunca usar payload vazio para testar um gate posterior se o fluxo pode acessar campos do payload antes do gate pretendido.

### K.3 Aplicação TICKSTORE

O teste de release passa a:
- fornecer um `sys` falso que satisfaz Python 3.14.7 + isolated + no_site;
- forçar `job_members()` a conjunto vazio;
- manter `Win32Store` com sentinel de erro caso qualquer I/O seja alcançado;
- esperar `JOB_ASSIGNMENT_REQUIRED_BEFORE_STARTUP`.

Assim o teste prova o comportamento pretendido sem depender do ambiente ou de payload incompleto.


---

## ANEXO L — DELTA V005R10: namespace VSS GLOBALROOT e parent pinning

### L.1 Descoberta física

O probe B6 criou uma geração VSS e falhou ao abrir o caminho do snapshot com:

```text
OPEN_PROTECTED:WINERROR=123
```

A causa é topológica. O device object VSS tem forma:

```text
\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopyN
```

A Microsoft define esse `DeviceObject` como **a raiz do volume shadow**. `GLOBALROOT` é um acesso ao namespace global do Object Manager; os pseudo-ancestrais:

```text
\\?\GLOBALROOT
\\?\GLOBALROOT\Device
```

não devem ser tratados como diretórios normais do volume shadow.

O `Win32Store.open` anterior abria todos os `path.parents` para pinning e, portanto, tentava `CreateFileW` nesses pseudo-ancestrais.

### L.2 Regras canônicas novas

```text
VSS_DEVICE_OBJECT_IS_FILESYSTEM_FLOOR=YES
GLOBALROOT_PSEUDO_ANCESTORS_ARE_NOT_FILESYSTEM_PARENTS=YES
VSS_PARENT_PINNING_STARTS_AT_HARDDISKVOLUMESHADOWCOPY=YES
ORDINARY_PATH_PARENT_PINNING_UNCHANGED=YES
VSS_SHADOW_PATH_GRAMMAR_MUST_BE_EXACT=YES
ARBITRARY_GLOBALROOT_BYPASS=FORBIDDEN
B6_OPEN_SHADOW_ROOT_PHYSICAL_PROOF=MANDATORY
```

Para targets da forma:

```text
\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy<digits>\...
```

o primeiro parent handle permitido é:

```text
\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy<digits>
```

Todos os diretórios reais abaixo dele continuam pinados. `GLOBALROOT` e `GLOBALROOT\Device` são omitidos apenas dessa cadeia de parent handles.

Para qualquer path que não corresponda exatamente à gramática acima, o comportamento anterior permanece inalterado.

### L.3 Aplicação TICKSTORE

O delta adiciona funções puras:

```text
vss_shadow_volume_root(path)
protected_parent_is_real(target,parent)
```

e um único filtro no loop de parent pinning de `Win32Store.open`.

A autoridade final é:
- candidate/release suites físicas no Windows;
- B6 físico completo;
- revisão externa CP2 restrita ao delta após A/B completos.


---

## ANEXO M — DELTA V005R11: abertura da raiz VSS exige separador final

### M.1 Descoberta física

Após remover `GLOBALROOT` e `GLOBALROOT\Device` da cadeia de parent pinning, o B6 avançou de:

```text
OPEN_PROTECTED:WINERROR=123
```

para:

```text
FILE_INFORMATION:WINERROR=87
```

O handle da raiz `HarddiskVolumeShadowCopyN` passou a ser criado, mas a consulta de metadados falhou.

A documentação VSS define `m_pwszSnapshotDeviceObject` como a raiz do volume shadow e deixa explícito que o device object **não contém barra final**. Para acessar caminhos do shadow, o requester concatena o device object, `\` e o caminho relativo.

### M.2 Regras canônicas novas

```text
VSS_DEVICE_OBJECT_CANONICAL_IDENTITY_HAS_NO_TRAILING_SLASH=YES
VSS_ROOT_DIRECTORY_CREATEFILE_PATH_HAS_TRAILING_SLASH=YES
VSS_ROOT_TRAILING_SLASH_ONLY_FOR_PHYSICAL_DIRECTORY_OPEN=YES
VSS_SUBDIRECTORY_OPEN_PATH_UNCHANGED=YES
ORDINARY_DIRECTORY_OPEN_PATH_UNCHANGED=YES
LOGICAL_PATH_IDENTITY_MUST_NOT_CHANGE_FOR_OPEN_SYNTAX=YES
```

A barra final é uma propriedade da **sintaxe física de abertura da raiz**, não da identidade lógica persistida.

Portanto:
- `ProtectedFile.path`, `norm(path)`, anchors e bindings continuam sem barra final;
- somente o argumento de `CreateFileW` recebe exatamente uma `\` quando:
  1. `directory=True`; e
  2. o path é exatamente `\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy<digits>`.
- arquivos, subdiretórios VSS e paths ordinários são passados a `CreateFileW` sem alteração.

### M.3 Aplicação TICKSTORE

O delta adiciona:

```text
vss_directory_open_path(path,directory)
```

e troca somente:

```text
CreateFileW(str(path), ...)
```

por:

```text
CreateFileW(vss_directory_open_path(path,directory), ...)
```

A autoridade continua sendo B6 físico completo (criação, abertura dos dois roots e cleanup), precedido por 79/79 candidate e 79/79 release no Windows.


---

## ANEXO N — DELTA V005R12: resolução de caminho final em handles VSS e microprobe antes de regressão cara

### N.1 Descoberta física

Após corrigir:
1. pseudo-ancestrais GLOBALROOT/Device; e
2. trailing slash na abertura física da raiz shadow;

o B6 avançou para:

```text
FINAL_PATH_FAILED
```

O `ProtectedFile.info()` usava:

```text
GetFinalPathNameByHandleW(..., dwFlags=0)
```

`dwFlags=0` significa `VOLUME_NAME_DOS | FILE_NAME_NORMALIZED`.

Snapshots VSS são acessados por device object e não necessariamente possuem representação DOS/Mount Manager. A documentação Microsoft de `GetFinalPathNameByHandleW` registra que consultas DOS/GUID podem falhar quando a unidade não possui letra/mount point e que `VOLUME_NAME_NT` retorna o NT device object.

### N.2 Regras canônicas novas

```text
VSS_FINAL_PATH_QUERY_MODE=VOLUME_NAME_NT
ORDINARY_FINAL_PATH_QUERY_MODE=VOLUME_NAME_DOS
VSS_FINAL_PATH_COMPARISON=NT_DEVICE_OBJECT_IDENTITY
VSS_LOGICAL_GLOBALROOT_IDENTITY_PRESERVED=YES
FINAL_PATH_FAILURE_MUST_INCLUDE_FLAGS_AND_WINERROR=YES
EXPENSIVE_REGRESSION_AFTER_CAPABILITY_CODE_DELTA_REQUIRES_MICROPROBE=YES
```

Para qualquer path VSS com floor exato `HarddiskVolumeShadowCopy<digits>`:
- consultar `GetFinalPathNameByHandleW` com `VOLUME_NAME_NT (0x2)`;
- transformar apenas para comparação a identidade lógica
  `\\?\GLOBALROOT\Device\...`
  em
  `\Device\...`;
- manter a identidade persistida/original em `ProtectedFile.path`.

Para paths ordinários, manter `dwFlags=0` e o comportamento anterior.

### N.3 Microprobe obrigatório

Quando um blocker de capability como B6 já exigiu múltiplos code deltas, o próximo candidato deve executar um microprobe físico do capability **antes** da suíte A/B completa.

No TICKSTORE, o microprobe:
1. usa exatamente o novo release;
2. cria VSS real;
3. abre shadow DEST e SCRATCH usando o mesmo `Win32Store`;
4. executa a mesma identidade `ProtectedFile.info`;
5. remove o snapshot;
6. confirma ausência;
7. somente após PASS permite A0→B9.

Esse microprobe não substitui B6; apenas evita repetir regressão cara com um capability ainda defeituoso.


---

## ANEXO O — DELTA V005R13: paridade de dependências em microprobes

### O.1 Descoberta física

O primeiro microprobe B6 pré-A0 falhou antes de criar snapshot:

```text
AttributeError: module 'tickstore_b6_microprobe_engine' has no attribute 'volume_guid'
```

A função `volume_guid()` não pertence ao engine; ela pertence ao orquestrador. O B6 oficial obtém o GUID por:

```text
GetVolumeNameForVolumeMountPointW("D:\\", ...)
```

Portanto o erro foi exclusivamente do harness do microprobe.

### O.2 Regras canônicas novas

```text
MICROPROBE_DEPENDENCY_PARITY=MANDATORY
PROBE_MUST_NOT_INVENT_ENGINE_API=YES
PROBE_HELPER_ORIGIN_MUST_BE_PHYSICALLY_VERIFIED=YES
CAPABILITY_PROBE_FAILURE_BEFORE_CAPABILITY_CALL_IS_HARNESS_FAILURE=YES
HARNESS_FAILURE_MUST_NOT_BE_CLASSIFIED_AS_ENGINE_FAILURE=YES
NATIVE_STDERR_CAPTURE_MUST_NOT_DEPEND_ON_PS51_2_TO_1_WITH_STOP=YES
```

Antes de executar um microprobe:
1. cada símbolo chamado deve ser comprovadamente exportado pelo módulo correspondente, ou implementado fisicamente no próprio probe;
2. helpers de infraestrutura devem reproduzir a mesma API nativa e os mesmos argumentos do caminho oficial;
3. falha ocorrida antes da chamada do capability sob teste é falha do harness, não do capability;
4. em Windows PowerShell 5.1, stdout/stderr de executáveis nativos devem ser capturados por redirecionamento de processo quando `$ErrorActionPreference='Stop'`, evitando `NativeCommandError` prematuro.

### O.3 Aplicação TICKSTORE

`b6_vss_microprobe.py` passa a implementar localmente `volume_guid()` com o mesmo:

```text
GetVolumeNameForVolumeMountPointW("D:\\", ...)
```

usado pelo orquestrador B6.

Candidate, release e as suítes 81/81 permanecem byte a byte inalterados.


---

## ANEXO P — DELTA V005R14: adaptador runtime de núcleo congelado, cleanup VSS e B6X

### P.1 Incidente técnico corrigido

A revisão externa B6 V004 comprovou dois blockers reais:

```text
B-01=CORE_FROZEN_VSS_FILE_IO_INCOMPATIBLE
B-02=FAILED_VSS_PROBE_GENERATIONS_NOT_RECONCILED
```

O núcleo congelado autenticado permanece correto como artefato de proveniência, mas duas funções internas presumem paths DOS/vivos:
- `_windows_final_handle_path(..., flags=0)`;
- `assert_no_link_chain(...)` iniciando no pseudo-ancestral `\\?\GLOBALROOT\`.

Quando essas funções são chamadas sobre arquivos dentro de um shadow VSS, reproduzem as mesmas classes de defeito já corrigidas na camada `Win32Store`.

### P.2 Regra de imutabilidade do núcleo

```text
CORE_B64_MUTATION=FORBIDDEN
CORE_SHA_MUTATION=FORBIDDEN
REFERENCE_B64_MUTATION=FORBIDDEN
REFERENCE_SHA_MUTATION=FORBIDDEN
RUNTIME_CORE_ADAPTER_ALLOWED=YES_ONLY_AFTER_HASH_VERIFICATION
RUNTIME_CORE_ADAPTER_SYMBOL_SCOPE=EXACTLY_TWO_SYMBOLS
RUNTIME_CORE_ADAPTER_INSTALLATION=EXACTLY_ONCE
```

O adaptador só pode ser instalado:
1. depois de `base64.b64decode(..., validate=True)`;
2. depois de `sha(raw)==CORE_SHA/REFERENCE_SHA`;
3. depois do `exec` do módulo autenticado;
4. antes de expor o módulo por `frozen_core()`.

Somente estes símbolos podem ser substituídos no namespace em memória:
- `_windows_final_handle_path`;
- `assert_no_link_chain`.

Os objetos originais devem ser preservados e paths não-VSS devem delegar integralmente a eles.

### P.3 Semântica obrigatória para VSS

Para `_windows_final_handle_path` em paths VSS:
- usar somente `VOLUME_NAME_NT (0x2)`;
- validar que o resultado pertence ao mesmo `HarddiskVolumeShadowCopy<digits>`;
- rejeitar outro device/path;
- devolver forma `\\?\GLOBALROOT + NT_RESULT` para que a validação original do núcleo permaneça autoridade;
- falhas devem registrar `FLAGS=0x2` e `WINERROR`.

Para `assert_no_link_chain` em paths VSS:
- iniciar no próprio `HarddiskVolumeShadowCopyN`;
- consultar o floor fisicamente com barra final;
- nunca consultar `\\?\GLOBALROOT` ou `\\?\GLOBALROOT\Device`;
- manter as mesmas regras de reparse/link e `allow_missing_tail`;
- paths não-VSS delegam ao original.

### P.4 Testes transversais obrigatórios

```text
CORE_VSS_ADAPTER_TEST_IDS=T-V1,T-V2,T-V3,T-V4,T-V5,T-V6,T-V7,T-V8
CORE_VSS_ADAPTER_TESTS_CANDIDATE=MANDATORY
CORE_VSS_ADAPTER_TESTS_RELEASE=MANDATORY
```

Os oito IDs devem cobrir:
- delegação idêntica de paths vivos;
- flag NT no shadow;
- rejeição de outro device/path;
- mensagem de falha com flags/WinError;
- floor/reparse/missing-tail;
- hashes congelados + instalação única;
- cleanup de probe em falha preservando erro primário;
- provenance/oracle inalterados.

### P.5 Cleanup de geração VSS

```text
VSS_STARTUP_PROBE_OWN_GENERATION_CLEANUP_ON_SUCCESS=MANDATORY
VSS_STARTUP_PROBE_OWN_GENERATION_CLEANUP_ON_FAILURE=MANDATORY
VSS_PRIMARY_ERROR_PRESERVED_IF_CLEANUP_FAILS=YES
VSS_PREEXISTING_SNAPSHOT_DELETE_WITHOUT_OWNER_APPROVAL=FORBIDDEN
```

Cada probe só pode remover a geração que ele próprio criou pelo `snapshot_id`, exigindo `count==1` e confirmação de ausência.

Snapshots preexistentes são apenas inventariados e classificados até autorização explícita do owner.

### P.6 B6X — prova física de leitura dentro do shadow

Antes de C1, após A/B completos, é obrigatório executar `B6X` com efeito SYS controlado.

PASS exige:
1. inventário read-only dos shadows D: antes;
2. criar uma geração contexto 25;
3. abrir roots shadow DEST/SCRATCH;
4. manifest shadow igual ao B4;
5. `validate_pair` em C0 menor, mediano e maior;
6. `prep` do S0 `20210304`;
7. `scan_s0` completo = 1399 dias / 2798 objetos;
8. `Win32Store.inventory` DEST = 303 arquivos e igualdade B4;
9. cleanup da própria geração em `finally`;
10. inventário read-only depois;
11. conjunto de snapshots antes/depois idêntico.

### P.7 Reconcile de snapshots preexistentes

```text
ORPHAN_SNAPSHOT_RECONCILIATION=READ_ONLY_CLASSIFICATION_FIRST
ORPHAN_SNAPSHOT_REMOVAL_REQUIRES_EXPLICIT_OWNER_APPROVAL=YES
B6X_MUST_NOT_DELETE_PREEXISTING_SNAPSHOTS=YES
```

Reconcile significa inventariar, registrar IDs/propriedades, correlacionar com receipts históricos e declarar retenção/ausência.
Não significa autorização automática para exclusão.

### P.8 Gate externo e canário

```text
B6_V005_EXTERNAL_REVIEW_BEFORE_C1=MANDATORY
CANARY_ROOT_CREATION_BEFORE_B6_V005_REVIEW_PASS=FORBIDDEN
```

O pack externo deve conter stdout/stderr físicos do B6X, resultados/receipts A0–B8/B6X, inventários antes/depois, reconcile e diff V004→V005.

Canary roots só podem ser criados depois do PASS externo em C1.
