# CDT21 — G5 V004 R2: fechamento causal do bloqueio da Fase Q e correção mínima do supervisor

**Papel:** implementador. Este documento não é parecer B06.
- MASTER/HEAD não foi consultado; a custódia normativa permanece na origem.
- A B06 independente continua reservada ao Work da irmã do titular, depois de a completude ser demonstrada.

## 1. Retorno DIAGQ examinado

**Retorno:** `4FEBE2F7B2AFAB06DE422F779340A748B462C619BB59EE760155E3B7CBD89B38`.
- Os 8 membros têm o hash conferido.
- O launcher registrado é `DE3938EF…`. Os scripts devolvidos correspondem aos SHA fixados (`42166FA7…` e `273E6207…`).
- `DIAG_RESULT.json` = `A0164CD9…`.

| Fato | Valor |
|---|---|
| Raízes alteradas em relação ao “antes” da Q | 2 (raiz e laboratório V003 `R08_Q1_20261020210605_856fea523791`), com **as mesmas contagens** (3.116 e 339). As outras 24 estão iguais |
| Diário USN | C: (registro mais antigo às 17:03 UTC) e D: (registro mais antigo em 07/10) cobrem a janela. C: tem 2.236 registros das gravações da própria Q na janela |
| Registros USN nas raízes protegidas | **0** na janela e depois dela, em C: e em D: |
| `D:\Base CSV` | igual ao “antes” da Q (`1FD27FDB…`, 14.514 entradas) |
| Repetição imediata e observação de 2 min | estáveis |
| Controle `CDT21_G5_V003` (nunca percorrido pela Q) | 86 diretórios com índice atrasado em relação à entrada (de 1 a 150 ms), havia 10,4 h. A segunda leitura do índice coincide com a entrada |
| Controles G0 | sem atraso e estáveis |
| `DisableLastAccess` | 0 (atualização de último acesso habilitada) |

**Correção de leitura:** as “11 divergências índice x handle” são as junctions `Base CSV/Scripts` dos laboratórios. Nelas o mtime é idêntico nas duas vistas; a diferença era apenas o código de tamanho atribuído pela minha coleta (-2 x -1). **A divergência real nas raízes protegidas é 0.**

## 2. Causa física

1. A retomada R2 do G5 V003 (fase E, 07:28–07:40 locais) foi o último escritor das duas raízes.
2. Em alguns diretórios, o tamanho e o mtime guardados no **índice do diretório-pai** (FindFirstFile, lido pelo `DirEntry.stat`) ficaram atrasados em relação à própria entrada. É o comportamento documentado do NTFS para a informação duplicada no índice.
3. O primeiro digest da Q leu o índice atrasado. Essa enumeração atualizou o índice, o que é reforçado pela atualização de último acesso habilitada.
4. O segundo digest, 15 s depois, leu o índice atualizado.
5. **Nenhum byte, nome ou metadado de arquivo foi alterado:** o USN prova isso nas duas unidades. Mesmo assim, o supervisor recusou, porque o digest dependia de uma vista que a leitura altera.

**Conclusão:** era um **defeito material do supervisor** — instabilidade da fonte dos metadados —, e não uma alteração real. A proteção agiu de forma fechada, como devia, mas pelo motivo errado.

**Agravante latente, demonstrado no modelo (caso E5):** o mesmo índice atrasado pode **mascarar** uma alteração real de tamanho ou mtime ainda não propagada ao índice. O digest antigo não a detecta; o corrigido detecta.

## 3. Correção mínima

**Supervisor:** `CDT21_G5_V004_SUPERVISOR.py` R2 = **`2A5F4B7138C950D320F7787540F98FF912D1AFB6C86C59E0F562887DB671029F`**.
- Derivado de `273E6207…` por counted replacements, com 9 linhas removidas e 47 acrescentadas.
- O composer e o diff estão no pacote de evidências.

**Mudanças:**
- **Metadados da própria entrada:** `os.lstat`, vista do handle, em `link_safe_digest` (raízes e laboratórios preexistentes), nos arquivos de topo de `foreign_roots` e em `tree_digest` (impressão digital de `D:\Base CSV`). A vista do índice deixa de ser lida para metadados.
- **Evidência:** quando a checagem de raízes recusa, Q e E gravam `foreign_roots_difference`, por raiz e por entrada. Isso supre a lacuna apontada pela origem.

**Inalterado:**
- nomes, tipos e campos comparados;
- todas as exigências e os mesmos códigos de bloqueio;
- a exigência de imutabilidade (nada preexistente pode mudar; só podem surgir a própria raiz e o próprio laboratório).

Sem atraso no índice, o digest R2 é idêntico ao antigo.

## 4. Qualificação

**Digest R2: 22/22.** O modelo reproduz o fenômeno observado na DIAGQ: o índice atrasado é atualizado quando o diretório é enumerado.

| Caso | Resultado |
|---|---|
| Composição e códigos | somente as funções pretendidas mudam; os códigos de bloqueio são idênticos; não resta leitura de metadados pelo índice |
| Sem atraso | digest antigo = digest R2 |
| Mecanismo | o antigo reproduz a falha da Q (as mesmas duas raízes, contagens iguais); o R2 fica estável e igual à verdade, sem nenhuma leitura de metadados pelo índice; o mesmo vale para a impressão digital de produção |
| Proteção preservada (alteração detectada, com evidência por entrada) | mudança de tamanho; mudança só de mtime; criação, exclusão e renomeação de arquivo; diretório novo no laboratório D:; link novo; `CURRENT_*.json` alterado; raiz irmã nova (`FOREIGN_ROOT_ADDED`); arquivo de produção alterado |
| Alteração real mascarada pelo índice | o antigo **não** detecta; o R2 detecta |
| Fase E | a própria raiz nova é admitida sem ruído; a alteração estrangeira é recusada com evidência por entrada; a falta da própria raiz é recusada |
| Fase Q | registra a diferença por raiz e por entrada |

**Mutantes: 5/5 mortos.** Cada enfraquecimento falha exatamente nos casos que o protegem.

| Mutante | Enfraquecimento |
|---|---|
| M1 | índice nas raízes |
| M2 | índice em produção |
| M3 | sem evidência |
| M4 | evidência vazia |
| M5 | checagem engolida |

**Validação V004 anterior (41 checagens) reexecutada no R2: 40/41.** A única diferença é esperada: `r2_functions_byte_identical`, porque `tree_digest` mudou de propósito. As outras 22 funções do R2 do V003 continuam idênticas, e todas as checagens de raízes, links, COMMITs, checkpoints, qualificação e falha fechada passam.

**Prova nativa da nova fonte (já obtida pela DIAGQ, sem nova execução):**
- `os.lstat`, com o mesmo Python 3.14.7, leu todas as entradas das 22 raízes protegidas com 0 erros e 0 divergências reais, e 1.761 entradas do controle.
- O valor lido foi o atualizado mesmo quando o índice estava atrasado.
- Nas junctions, `os.lstat` não seguiu o link.

**Não reaberto, porque não é afetado:** o b2d (extração e layout idênticos), o G0 V004, a classificação de processos R1 e o V004.

## 5. Executor afetado — único arquivo a substituir

**Launcher:** `RUN_CDT21_G5_V004_R2_20261021.ps1` = **`8CC1ACB6B093020D4CFC94B3EB618A624243A3F8B3E9E1E991EA7B9E9C1B8DA2`** (92.376 bytes).
- Derivado do R1 `E3F83D0A…`. Fora do supervisor embutido, mudam só o cabeçalho (3 linhas) e o SHA fixado.
- A classificação R1, a revisão `E84E5C39…`, os caminhos, o log, as fases e o retorno são idênticos.
- Parser com 0 erros, ASCII e CRLF.
- **Os launchers `54C5ED19…` e `E3F83D0A…` ficam substituídos.**

**Não é necessária uma execução Windows só para qualificar a correção:** a fonte de metadados já foi provada nativamente pela DIAGQ. A próxima execução Windows é a própria campanha G5 V004, que é indispensável para os 38 recibos. Ela começa pela Fase Q, que reverifica nativamente as raízes e a produção antes de qualquer efeito. A campanha deve ser executada quando a origem autorizar:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\Downloads\RUN_CDT21_G5_V004_R2_20261021.ps1" -AutorizoLabD
```

- **Log:** `C:\Users\silvi\Downloads\CDT21_G5_V004_RUNS\G5V4_<carimbo>\`
- **Retorno:** `ENVIAR_AO_OPUS_CDT21_G5_V004_<carimbo>.zip`, direto a esta conversa.

**Resíduo declarado:** se o Windows negar a abertura de uma entrada só para atributos (acesso negado), o `os.lstat` do CPython volta ao índice para essa entrada. A DIAGQ não encontrou nenhum caso desses nas raízes protegidas.

## 6. Arquivos

| Arquivo | SHA-256 |
|---|---|
| `RUN_CDT21_G5_V004_R2_20261021.ps1` | `8CC1ACB6B093020D4CFC94B3EB618A624243A3F8B3E9E1E991EA7B9E9C1B8DA2` |
| `CDT21_G5_V004_R2_SUPERVISOR_FIX_EVIDENCE_20261021.zip` (118.175 bytes, 20 membros, `MANIFESTO.json` `D99C742D…E948`) | `FDCB9FEBCDFBE4033693D131CDD2A30095358A564992DCF3C7A5E0CCCF2FFB6C` |
| `WITNESS_CDT21_G5_V004_R2_20261021.json` | registrado no commit |
| `RELATORIO_G5_V004_R2_CAUSA_E_CORRECAO_20261021.md` (este) | registrado no commit |

## 7. Preservado e não iniciado

| Item | Situação |
|---|---|
| V004 `AD334869…99DD` e código `D2C626FD…66FF` | intactos |
| Revisão `E84E5C39…` | intacta |
| Recibos e diretórios existentes | intactos |
| G0 | não repetido |
| Campanha G5, B06, B07, D4/D5, canário, FULL e produção | não iniciados |

RESULT_RETURN_TO=ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compressão De Ticks 21
