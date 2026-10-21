# CDT21 — Reconciliação da última execução G5 V003 (20/10/2026, 21:06)

**Papel:** implementador (Opus 5.5). Não é parecer B06.
**Candidato:** V003 `69DA2D59…7E50`, código `D59BC4EE…3953`, intocado.
**Resultado:** `NOT_READY_SINGLE_BLOCKER`. A causa primária ainda não foi determinada e **não foi presumida**.

## 1. Fontes e seu valor probatório

| Fonte | Natureza | Conteúdo |
|---|---|---|
| Handoff `3B8DA8B4…2E4D`, reconstruído byte a byte dos 3 volumes | Física, 15/15 itens conferidos com o manifesto | Estado da origem, candidato, G0, launcher R1 forense |
| `CDT21_G5_V003_RUNNER_ORIGEM_R1_PS1_FORENSIC_ONLY.ps1` (`ED0D7035…`) | Física, somente análise | Modificação da origem sobre o meu launcher: autoelevação por UAC e `C:\Users\silvi\Downloads`. O supervisor embutido (`7B482A4B…`) e a revisão (`BB2BDE03…`) são idênticos aos qualificados. |
| Log do pai `…\G5_20261020_210602_767_19736\RUN_LOG.txt` | Relatado pela origem; não recebido | `ELEVATED_CHILD_PID=5076`, `ELEVATED_CHILD_EXIT_CODE=3` |
| `RUN_LOG` do diagnóstico V1 do D:, 20/10 21:11 (`D835F352…`) | Física, Windows do titular, recebida nesta conversa | Pastas e horários da execução (§2) |
| `SUPERVISOR_RESULT.json`, log do filho, `ENGINEERING_RESULT.json`, `COMMITS`, `R08_RETURN.zip` | **Ausentes** | Causa, unidade e estado COMMITTED |

## 2. Fatos físicos da execução

- **Estágio do filho:** `C:\Users\silvi\AppData\Local\CDT21_G5_V003\STAGE_20261020_210605_565_5076`. O sufixo `_5076` é o `$PID` do filho elevado.
- **Pasta de log do filho:** pelo código do R1, é `C:\Users\silvi\Downloads\CDT21_G5_V003_RUNS\G5_20261020_210605_565_5076`.
- **Raiz da campanha:** `C:\Users\silvi\AppData\Local\CDT20_R08\R08_Q1_20261020210605_856fea523791`. Última criação direta às 21:06:33.
- **Laboratório no D::** `D:\TICKSTORE_CDT19_PRE_G06_LABS\R08_Q1_20261020210605_856fea523791`, às 21:06:07. Isso indica que o bootstrap do supervisor foi concluído.
- **Prova PS51:** os logs `TICKSTORE_RUNS\INSTALL_*` e `MENU_OFFICIAL_WRITER_*`, de 21:06:08 a 21:06:28, mostram que ela executou com `layout_kind=QUALIFICATION`. Os backups ficaram dentro do laboratório.
- **Processo filho:** inexistente às 21:11, portanto encerrado.

## 3. O que o código permite concluir

1. No ramo do filho do R1, o código de saída é o `$LASTEXITCODE` do supervisor; o ramo `catch` daria 2. Logo, **3 veio do supervisor**.
2. No supervisor `7B482A4B…`, o código 3 só ocorre em dois casos:
   - falha na fase `CAMPAIGN`: campanha com código ≠ 0, status diferente de PASS ou `R08_RETURN` não selado;
   - processos órfãos após um PASS.
3. O plano de 38 unidades tem base nativa de 712 s. Um término cerca de 28 s após o início **não pode ser um PASS**; portanto, o caso de órfãos após PASS fica excluído.

**Indeterminados:**
- a unidade que falhou;
- o texto do blocker e o traceback;
- quais unidades ficaram COMMITTED;
- se o `R08_RETURN.zip` foi selado;
- se a causa está no ambiente, no supervisor externo ou no candidato.

Sem essas peças, qualquer correção ou nova campanha seria cega e, por isso, não foi feita.

## 4. Recuperação do trabalho COMMITTED

O `run_unit` congelado reaproveita `COMMITS/<chave>.json` somente da **mesma** raiz e com o mesmo pacote e código (`REUSE_COMMITTED`). Unidades não COMMITTED são preservadas em `INTERRUPTED_ATTEMPTS`, nunca promovidas.

Depois de conhecida e corrigida a causa, a raiz `R08_Q1_20261020210605_856fea523791` pode ser **retomada** sem reexecutar o que já foi COMMITTED. Nenhuma unidade será repetida por falta de leitura do recibo.

## 5. Próximo ato mínimo: uma coleta somente leitura

O coletor é `RUN_CDT21_G5_V003_COLLECT_READONLY_20261021.ps1` (`D319EC71…0A89`):
- roda em PowerShell 5.1 comum, **sem UAC**;
- nunca acessa o D:, nunca executa arquivos coletados e nunca segue links ou junctions;
- grava apenas em `C:\Users\silvi\Downloads\CDT21_G5_V003_COLLECT_RUNS\COLLECT_<carimbo>\`.

**O que ele seleciona:**
- `G5_*` em `Downloads\CDT21_G5_V003_RUNS` (pai e filho);
- `STAGE_*`;
- raízes `R08_Q1_*` que contêm `CDT21_SUPERVISOR_BOOTSTRAP.json` ou são citadas por `SUPERVISOR_RESULT.run_root`. As raízes V002 ficam fora.
- `TICKSTORE_RUNS`, apenas na janela temporal dessas raízes.

**Tratamento por tipo de conteúdo:**

| Conteúdo | Tratamento |
|---|---|
| `PACKAGED`, `WORK`, `TEMP`, `QUAL_C` | Apenas listados |
| Pacote em `INPUTS` e duplicatas | Apenas hash |
| Arquivos acima dos limites (250 MB por arquivo, 600 MB no total) | Apenas hash |

**Qualificação (Linux, pwsh 7.4.6, `-TestRoot`):** 31/31.
- Casos 0, 1 e N.
- Sentinelas `.ps1`, `.py`, `.bat`, `.cmd` não executados.
- Origem imutável, comparada por SHA e mtime antes e depois.
- Escritas apenas na pasta de coleta.
- Hashes coletados iguais aos da origem.
- Limites de tamanho por arquivo e total.
- Links não seguidos.
- ZIP de retorno íntegro.
- Checagem estática pela AST: 0 comandos fora da lista permitida, 0 usos do operador de invocação e 0 membros perigosos.

**Não coberto no Linux:** ACLs do Windows (o filho elevado roda com o mesmo usuário; arquivos ilegíveis viram `ERROR` no manifesto, sem abortar) e o runtime do PowerShell 5.1 (sintaxe conservadora).

## 6. Condição para qualquer execução com efeitos posterior

Retomada ou nova campanha grava no laboratório do D:. Só deve ocorrer depois de:
- identificada a causa primária;
- esclarecido o incidente de perda de dados no D: relatado pelo titular, cujo diagnóstico V2 está pendente.

A coleta em si não toca o D:.

RESULT_RETURN_TO=ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compressão De Ticks 21
