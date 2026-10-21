# CDT21 — G5 V004: launcher final qualificado (campanha nativa nova)

**Papel:** implementador. Este documento não é parecer B06 nem admissão. A custódia de MASTER/HEAD permanece exclusivamente na origem.

**Decisão da origem (21/10/2026):** é exigida uma nova campanha G5 nativa, vinculada ao manifesto completo do V004. O G5 do V003 continua válido apenas para os bytes do V003. Seus 38 COMMITs **não** recebem a identidade do V004.

## 1. Identidades preservadas

| Item | SHA-256 | Estado |
|---|---|---|
| Candidato V004 `CDT21_FINAL_PACKAGE_V004_20261021.zip` | `AD33486954F1248AF28A78677377E83AB979AB86EDD5F71F5B7D108CBA8F99DD` | congelado, inalterado |
| Manifesto de código do V004 | `D2C626FD2819B86D472433CB2B26C6688B1688E5E5474402162B67C5048666FF` | inalterado |
| Manifesto do pacote V004 | `F6225EA6720FCA558F8BBAD70B3ED46687103374873439E0FADDB4FEA9D3A813` | inalterado |
| G0 V004 (bundle / retorno) | `1A5C8E51…2702` / `AB710D82…ECA8` | aprovado pela origem; **não repetido** |
| Plano G5 integrado | 38 unidades lidas das constantes congeladas | mesmas chaves do V003 |

A máquina G5 do V004 é idêntica, byte a byte, à do V003:

| Arquivo | Prefixo SHA |
|---|---|
| `PRE_G06_CAMPAIGN` | `347767D1` |
| `PRE_G06_COMPLETENESS` | `15B10B10` |
| `FULL_G5_COMPLETE_PROOF_GATE` | `EC6D9B2D` |
| `G5_FINAL_COMPLETENESS_PRODUCER` | `34CA561C` |
| `test_b2d_origin_decision_binder` | `D19EF3BA` |

## 2. Supervisor G5 V004

**Arquivo:** `CDT21_G5_V004_SUPERVISOR.py` (`273E620746FD5293D87858847CEBE035328B2A354F4371BBB18D82195A410126`).

Ele é derivado do supervisor R2 já comprovado no V003 (`99704BA5965294204D6FE1BBD348C423EA70204B5C104D4D19C5150217F1C0CC`). A derivação é feita por um compositor que confere o SHA do R2 e copia blocos de linhas literais.

**Preservado byte a byte do R2 (23 funções; prova por comparação de AST):**
- extração byte a byte no layout `CURRENT_G5_DELTA_*\EXTRACTED`, o mesmo que a suíte b2d congelada exige;
- verificação desse contrato e plano de 38 unidades;
- Job kill-on-close (supervisão de processos);
- impressão digital somente leitura de `D:\Base CSV`;
- isolamento das raízes de escrita;
- runner b2d nativo, `verify_extract` e `validate_review`.

**Removido:** o modo de retomada inteiro (`resume_precheck`, `preserve_prior_terminal`, `checkpoint_consistency`, `prior_processes_dead`, `lock_probe`). Nenhum argumento de retomada é aceito. Portanto, não há caminho para reabrir a raiz do V003 ou de qualquer outra execução.

**Acrescentado:**
1. **Fase Q nativa para campanha nova.** Não cria raiz nem laboratório. Verifica:
   - SHA do pacote V004 e vínculo da revisão ao V004;
   - elevação, `LOCALAPPDATA` canônico, NTFS em C: e D:, espaço livre (C: 4 GiB; D: 1 GiB);
   - Job aninhado com kill-on-close;
   - extração de qualificação, manifesto, fontes congeladas, plano 38 e `verify_package` congelado;
   - isolamento de escrita.
   
   Em seguida, executa o b2d nativo no layout corrigido (29/29 OK) e no layout R1, onde a falha deve ser reproduzida. Por fim, registra **somente leitura** cada raiz e laboratório preexistentes com o seu dono (V003, V004, outro ou ilegível).
2. **Fase E admitida só com Q=PASS** do mesmo supervisor e da mesma pasta de log, emitido há menos de 2 h. A fase E:
   - cria raiz e laboratório **novos** (`mkdir` sem `exist_ok`);
   - executa as 38 unidades congeladas e o fechamento de cinco partes;
   - recusa qualquer `REUSE_COMMITTED`.
3. **Admissão do resultado (fail-closed).** Todas as condições abaixo são exigidas:
   - exatamente os 38 COMMITs do plano, todos vinculados ao pacote e ao código do V004;
   - status PASS, exit 0, sem descendentes órfãos e artefatos re-hasheados;
   - um COMMIT vinculado ao V003 é recusado com `COMMIT_BOUND_TO_V003`;
   - `LIVE_STATUS`, `R08_RETURN.sha256` e `RETURN_LOCK_SCOPE` consistentes, sem arquivo parcial;
   - raízes preexistentes inalteradas: só podem surgir `run/<própria>` e `d_lab/<própria>`;
   - `D:\Base CSV` com impressão digital idêntica em Q, antes, depois e no fechamento.
4. **Digest das raízes estrangeiras.** Nunca segue symlink, junction ou reparse point. Diretórios ilegíveis são registrados pelo nome. Um link remanescente de outra execução não gera laço, travessia externa nem bloqueio espúrio.

**Revisão de fonte do V004:** `CDT19_IMPLEMENTER_SOURCE_REVIEW_V004.json` (`E84E5C39F37E73C08DE913403D41045F622916063190638DEA308F668C86C802`). É a entrada exigida por `PRE_G06_COMPLETENESS.close` e está vinculada ao pacote e ao código do V004. A revisão do V003 é recusada.

## 3. Pré-qualificação e controles negativos (Linux)

A qualificação Linux não substitui a Fase Q nativa, que é obrigatória.

**Validação do supervisor: 41/41 PASS.** Os casos rodam sobre a raiz real coletada do V003, cujos COMMITs reais estão vinculados ao V003.

| Grupo | Resultado |
|---|---|
| Composição | as 23 funções do R2 são idênticas; retomada ausente; guarda `NEW_RUN_REUSED_A_COMMIT` presente |
| Identidade | constantes V004; layout corrigido aceito, layout R1 recusado; plano 38; `verify_package` congelado devolve o código do V004 |
| Revisão | V004 aceita; V003 recusada |
| Raízes estrangeiras | dono V003 registrado; tocar a raiz V003 → `FOREIGN_ROOT_CHANGED`; irmão inesperado → `FOREIGN_ROOT_ADDED`; laço e link externo não seguidos |
| `run_unit` congelado | **recusa um COMMIT do V003 sob a identidade V004** (`PRE_G06_LAB_COMMITTED_INPUT_DRIFT`), sem `REUSE_COMMITTED` e sem executar nada |
| COMMITs | 38 vinculados ao V004 aceitos; COMMIT V003, ausente, artefato adulterado e órfão recusados |
| Checkpoints | consistentes aceitos; chaves divergentes do `LIVE_STATUS` e SHA divergente do `R08_RETURN` recusados |
| Qualificação | Q PASS admite E; Q bloqueada, de outro supervisor, do R2, de outra pasta de log, de outro modo ou vencida é recusada |
| Falha fechada sem efeito | `--qualify-only`, E sem Q e E fora do Windows não deixam efeito no disco |

**Controles de layout b2d sobre os bytes do V004: 4/4.**
- Layout R1: 29 `CONTRACT_NOT_MET`.
- Layout corrigido: 29/29 OK.
- Sem prefixo: recusado.
- Alias: recusado.

## 4. Launcher único `RUN_CDT21_G5_V004_20261021.ps1`

**SHA-256:** `54C5ED1991AE3BEDAC656E96772DB4DF41E5D99A7385B22405AAB39B82393372` (84.874 bytes).

| Propriedade | Comportamento |
|---|---|
| Formato | PowerShell 5.1, só ASCII, CRLF, 0 erro de parser, sem cmdlets destrutivos, sem argumentos de retomada |
| Conteúdo embutido | supervisor e revisão em base64 com SHA fixado; os bytes são conferidos ao desembrulhar |
| Verificações prévias | SHA do pacote V004 e do Python 3.14.7 (`4942B86A…9AC9`) |
| Isolamento | recusa iniciar se houver outra campanha G5 viva (`LIVE_G5_CAMPAIGN_PROCESS`); `TEMP` isolado no stage próprio |
| Elevação | autoeleva por UAC; pai e filho escrevem na mesma pasta de log |
| Falha fechada | qualquer exceção resulta em `G5_V004_BLOCKED=<motivo>` e código 2 |

**Modos:**

| Execução | O que acontece | Código de saída |
|---|---|---|
| sem `-AutorizoLabD` | somente a Fase Q; nada é gravado no D: | 10 |
| com `-AutorizoLabD` | Fase Q e, se Q=PASS, Fase E | 0 = PASS |

**Log (regra do titular):** `C:\Users\silvi\Downloads\CDT21_G5_V004_RUNS\G5V4_<yyyyMMdd_HHmmss_fff_PID>\`. A pasta é absoluta, fixa e nova a cada execução, independentemente da pasta atual. O pai grava `RUN_LOG.txt` e o filho elevado grava `RUN_LOG_ELEVATED.txt`.

**Efeitos permitidos:** somente laboratório próprio.
- `C:\Users\silvi\AppData\Local\CDT20_R08\<raiz nova>`
- `C:\Users\silvi\AppData\Local\CDT21_G5_V004\`
- `D:\TICKSTORE_CDT19_PRE_G06_LABS\<raiz nova>\WRITER_EFFECTFUL`, com arquivos pequenos
- o log que o código congelado do V004 grava em `C:\Users\silvi\OneDrive\Downloads\TICKSTORE_RUNS`. Esse caminho está fixado nos bytes congelados e não pode ser alterado sem novo pacote.

**Nenhuma escrita em `D:\Base CSV`.**

## 5. Instruções de execução (titular)

1. Confirme que `C:\Users\silvi\Downloads\CDT21_FINAL_PACKAGE_V004_20261021.zip` está presente. É o mesmo arquivo usado no G0 V004; o launcher confere o SHA.
2. Salve `RUN_CDT21_G5_V004_20261021.ps1` em `C:\Users\silvi\Downloads\`.
3. Em `PS C:\Users\silvi>`, no Windows PowerShell 5.1, execute:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\Downloads\RUN_CDT21_G5_V004_20261021.ps1" -AutorizoLabD
   ```

4. Aceite o UAC. Não feche nenhuma das duas janelas.
   - **Tempo estimado:** Fase Q de 1 a 3 min; Fase E de 15 a 25 min.
   - **Parada segura, se necessária:** crie o arquivo indicado na linha `SAFE_STOP=` do log.
5. Ao final, o log mostra estas linhas:
   - `ENVIE_O_RETORNO=…\ENVIAR_AO_OPUS_CDT21_G5_V004_<carimbo>.zip`
   - `ENVIE_O_RETORNO_SHA256=…`
6. Envie esse ZIP ao implementador e cole o texto do `RUN_LOG.txt`.

## 6. Após o retorno nativo (pendente)

O implementador fará, somente leitura:
- verificação do retorno;
- conferência dos 38 recibos e do vínculo físico de cada COMMIT ao V004 (`AD334869…` / `D2C626FD…`, sem `REUSE_COMMITTED`);
- conferência das cinco provas de completude e dos quatro achados pré-B06;
- execução do gate congelado;
- reexecução independente de `PRE_G06_COMPLETENESS.close` com comparação de bytes.

Em seguida, montará o fechamento integrado para a admissão B06 independente. Esse pacote recusa o retorno do V003 por construção.

**Não iniciados:** B06, B07, D4/D5, canário, FULL e produção.

## 7. Arquivos desta entrega

| Arquivo | SHA-256 |
|---|---|
| `RUN_CDT21_G5_V004_20261021.ps1` | `54C5ED1991AE3BEDAC656E96772DB4DF41E5D99A7385B22405AAB39B82393372` |
| `CDT21_G5_V004_SUPERVISOR_EVIDENCE_20261021.zip` (113.860 bytes) | `072BD47B44DA5DA375C4674C4BE67CD73CC63C4013C407C0008C64F82BFEFB3E` |
| `WITNESS_CDT21_G5_V004_LAUNCHER_20261021.json` | `4DD13DC9BEE7E05561A55A6EEDEBF826CDDB6FB1BFB8734ABA469F13FBCD6974` |
| `RELATORIO_G5_V004_LAUNCHER_20261021.md` (este) | registrado no commit |

O pacote de evidências contém:
- `01_SUPERVISOR`: supervisor e revisão V004;
- `02_DERIVACAO`: diff R2→V004, compositor, seções novas, gerador do launcher e R2 parent;
- `03_QUALIFICACAO_LINUX`: validador, resultado 41/41 e controles b2d 4/4;
- `04_LAUNCHER`: launcher e checagem de parser e embutidos.

Um `MANIFESTO.json` interno lista o SHA de cada membro.

RESULT_RETURN_TO=ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compressão De Ticks 21
