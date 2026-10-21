# CDT21 — G5 V004 R1: launcher corrigido (classificação de campanhas concorrentes)

**Papel:** implementador. Este documento não é parecer B06. A custódia normativa permanece na origem; MASTER/HEAD não foi consultado.

## 1. Achado da origem e confirmação

**Launcher afetado:** `RUN_CDT21_G5_V004_20261021.ps1` (`54C5ED1991AE3BEDAC656E96772DB4DF41E5D99A7385B22405AAB39B82393372`).

O achado está **confirmado**:
- nas linhas 798–804, o pai não elevado pede o UAC e permanece vivo, aguardando;
- nas linhas 822–826, o filho elevado exclui apenas `$PID` e procura `CDT21_G5_V00` nas linhas de comando;
- o comando documentado (`-File "…\RUN_CDT21_G5_V004_20261021.ps1"`) põe esse marcador na linha de comando do pai.

**O falso `LIVE_G5_CAMPAIGN_PROCESS` é determinístico no caminho UAC.** Foi reproduzido com os fragmentos do launcher sobre snapshot no formato Windows (S01) e com processos reais (R01).

**Efeito:**
- bloqueio com exit 2 antes de qualquer efeito: nenhum stage, raiz ou laboratório e nenhuma escrita em D:;
- não há risco à produção, mas a campanha G5 V004 não poderia ser executada pelo comando documentado.

**Causa:** fui eu que introduzi o defeito, na derivação do R2 (V003) para o V004.
- O R2 filtrava `CDT21_G5_V003_SUPERVISOR`, que não aparece no nome do launcher.
- No V004, o filtro foi ampliado para `CDT21_G5_V00`, que casa também com o nome do próprio launcher.

## 2. Correção (exclusivamente a classificação)

**Launcher corrigido:** `RUN_CDT21_G5_V004_R1_20261021.ps1`, SHA-256 **`E3F83D0A76E4B372C02C4F7AFD28243CE7DB568A8B242810AECEE86396CED2C8`** (87.904 bytes).

O R1 é derivado do launcher defeituoso por 7 substituições contadas, com o SHA do pai conferido. A reprodução byte a byte foi verificada. O diff tem 8 linhas removidas, todas no escopo da classificação.

**Árvore própria por PID e identidade de criação:**
1. **Pai não elevado.** Antes do UAC, lê a própria identidade em `Win32_Process`: PID e `CreationDate`, convertida em ticks UTC. Entrega-a ao filho por `-LauncherParentPid` e `-LauncherParentCreation`. O log registra `IDENTIDADE_PAI=<PID>@<criação>`.
2. **Filho elevado.** Num único snapshot, exige:
   - `ParentProcessId` real do filho = PID informado;
   - exatamente um processo com esse PID;
   - instante de criação idêntico ao informado;
   - pai mais antigo que o filho.
   
   Só então exclui exatamente o par (PID, criação) do pai e o próprio processo. O log registra `ARVORE_PROPRIA=`.
3. **Qualquer divergência** bloqueia antes de qualquer efeito com um código `OWN_TREE_*`:
   - `OWN_TREE_PARENT_PID_MISMATCH`
   - `OWN_TREE_PARENT_CREATION_MISMATCH`
   - `OWN_TREE_PARENT_NOT_ALIVE`
   - `OWN_TREE_PARENT_NEWER_THAN_CHILD`
   - `OWN_TREE_PARENT_IDENTITY_MISSING`
   - `OWN_TREE_PARENT_ARGS_WITHOUT_ELEVATED_CHILD`
   - `OWN_TREE_SELF_*`
4. **Prompt já elevado (sem UAC):** comportamento idêntico ao V004, com a árvore própria igual ao próprio processo.

**Inalterados:**
- os marcadores e a comparação sem distinção de caixa;
- a mensagem de bloqueio;
- as fases Q/E, os caminhos e a regra de log;
- o pacote V004, o supervisor `273E6207…` e a revisão `E84E5C39…`, embutidos byte a byte iguais.

## 3. Qualificação

Ambiente: Linux, pwsh 7.4. Os fragmentos do launcher rodam sem alteração.

| Bloco | Resultado | Conteúdo |
|---|---|---|
| Estática | **PASS** | parser 0 erros; nenhum token exclusivo do PS 7; ASCII; CRLF; embutidos idênticos ao `54C5ED19`; sem cmdlets destrutivos; sem retomada; diff restrito |
| Pai/filho com UAC (formato Windows) | **PASS** | S01: V004 lista o próprio pai (defeito). S02: R1 passa com árvore filho + pai. S24: o pai entrega PID + criação |
| Pai/filho com UAC (processos reais) | **PASS** | R01: V004 bloqueia pelo próprio pai. R02: R1 passa; árvore própria igual ao PID e à criação lidos do kernel de forma independente |
| Campanha concorrente verdadeira | **PASS** | S03–S10 e R04–R07 bloqueiam, sem listar o próprio pai (detalhe abaixo) |
| Identidade de processo incorreta | **PASS** | S12–S23 e R08–R12 bloqueiam (detalhe abaixo) |
| Escopo da exclusão | **PASS** | S25–S27: nenhum ancestral ou wrapper é liberado |
| Equivalência | **0 divergências** | em 400 snapshots aleatórios, R1 = V004 menos o pai validado |
| Mutantes | **6/6 mortos** | sem checagem do pai real; sem igualdade de criação; sem pai mais antigo; sem identidade de criação; comportamento V004; exclusão só por PID |

**Campanhas concorrentes verdadeiras que bloqueiam:**
- outra instância inteira (pai, filho, supervisor e `PRE_G06_CAMPAIGN`);
- `PRE_G06_CAMPAIGN` órfão;
- supervisor do V003;
- marcador em caixa baixa;
- processo sem instante de criação legível;
- `PRE_G06_CAMPAIGN` e supervisor reais;
- segunda instância real do launcher com a primeira viva: a segunda lista o pai e o filho da primeira.

**Identidades incorretas que bloqueiam:**
- criação adulterada;
- PID reutilizado com PPID obsoleto;
- identidade forjada mais nova que o filho;
- identidade exata de um launcher ou `PRE_G06_CAMPAIGN` real concorrente informada como pai;
- pai ausente, ambíguo ou encerrado;
- argumentos ausentes, inválidos ou indevidos;
- processo próprio ausente ou sem instante.

Totais: snapshots 28/28; processos reais 13/13; mutantes 6/6.

**Limite declarado.** UAC e WMI não existem no Linux. O filho é iniciado com a mesma string de argumentos produzida pela linha do launcher, e o snapshot vem de `/proc`.

**Premissa nativa:** no Windows, o processo elevado por runas tem como pai o processo que pediu a elevação. Se ela falhar, o R1 bloqueia com `OWN_TREE_PARENT_PID_MISMATCH` antes de qualquer efeito, sem liberar concorrentes. A primeira linha nativa `ARVORE_PROPRIA=` confirma a premissa.

## 4. Execução pelo titular (quando a origem autorizar)

O pacote V004 e o local de log são os mesmos da entrega anterior. O launcher `54C5ED19…` fica **substituído; não deve ser executado**.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\Downloads\RUN_CDT21_G5_V004_R1_20261021.ps1" -AutorizoLabD
```

- **Log:** `C:\Users\silvi\Downloads\CDT21_G5_V004_RUNS\G5V4_<carimbo>\`
- **Retorno:** `ENVIAR_AO_OPUS_CDT21_G5_V004_<carimbo>.zip`

## 5. Arquivos

| Arquivo | SHA-256 |
|---|---|
| `RUN_CDT21_G5_V004_R1_20261021.ps1` | `E3F83D0A76E4B372C02C4F7AFD28243CE7DB568A8B242810AECEE86396CED2C8` |
| `CDT21_G5_V004_R1_LAUNCHER_QUALIFICATION_20261021.zip` (153.898 bytes, 81 membros, `MANIFESTO.json` `B76E3F73…56DD`) | `0DAD3D59F3FBDA12605C214923491024262F4B742320BDDAE0E4B349EACF64E8` |
| `WITNESS_CDT21_G5_V004_R1_LAUNCHER_20261021.json` | `A7A871CD84BC6F0FEC8BCD6DDD65D6A6DD5FBAA249E1C46800706D6C9D6448B9` |
| `RELATORIO_G5_V004_R1_LAUNCHER_20261021.md` (este) | registrado no commit |

## 6. Preservado e não executado

| Item | Situação |
|---|---|
| V004 `AD334869…99DD` e código `D2C626FD…66FF` | intactos |
| PASS do G0 V004 (bundle `1A5C8E51…`, retorno `AB710D82…`) | preservados; G0 não repetido |
| Supervisor (validação 41/41, b2d 4/4) | não tocado |
| COMMITs do V003 reutilizados | nenhum |
| Campanha G5 | não executada |
| B06, B07, D4/D5, canário, FULL e produção | não iniciados |

RESULT_RETURN_TO=ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compressão De Ticks 21
