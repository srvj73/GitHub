# CDT21 — G5 V004: investigação física do bloqueio `QUAL_q_no_effect_on_foreign_roots`

**Papel:** implementador. Este documento não é parecer B06. MASTER/HEAD não foi consultado; a custódia normativa permanece na origem.

## 1. Retorno nativo examinado

O retorno `289A064EA65235CEA2EF8EB1E80970C5415C2022C26D78781F8EF8CFBE4A7EC2` foi lido sem executar nada dele.

| Item | Resultado |
|---|---|
| Launcher | R1 `E3F83D0A…` |
| Supervisor | `273E6207…` |
| `QUALIFICATION_RESULT.json` | `966F33CD…`, igual ao log |
| Logs b2d | conferem com os SHA do resultado |
| UAC e árvore própria | o pai `23632` aparece em `ARVORE_PROPRIA` com o mesmo instante de criação: **premissa do R1 confirmada nativamente** |
| Verificações | 16/17 PASS. Falha: `q_no_effect_on_foreign_roots`, com `detail` vazio |
| `production_unchanged_during_q` | **não avaliada**, porque a Q parou antes |
| Janela da Q | 18:39:59–18:40:14 UTC (15,53 s) |
| Raízes preexistentes | 26: 2 do V003, 20 de outros donos, 4 arquivos `CURRENT_*.json` |
| Efeitos | campanha não iniciada; nenhuma raiz criada |

**Lacuna de evidência:** a Q compara apenas o dicionário inteiro. Ela não guarda o “depois” nem as linhas por entrada, por isso o retorno não permite saber qual raiz mudou nem como. É uma deficiência de observabilidade do supervisor. Será corrigida junto com a correção causal, se houver uma, para gerar uma única revisão do executor.

## 2. Causas descartadas sem repetir testes nativos

**Replay Linux auditado** (`q_replay_audit.py`). Todos os passos que a Q executa entre os dois digests rodaram sob `sys.addaudithook`, no supervisor e nos filhos b2d:
- extração;
- contrato do layout;
- importação do plano de 38 unidades;
- `verify_package` congelado (código `D2C626FD…`);
- b2d no layout corrigido e no layout R1.

As raízes estrangeiras eram cópias reais da raiz V003 coletada.

**Resultado:**
- 0 escritas em raízes estrangeiras;
- digest e linhas por entrada idênticos antes e depois;
- b2d 29/29.

**Importação sem efeitos.** Nenhum dos 17 módulos que a Q importa executa E/S na importação. A importação do supervisor também é inerte.

**Conclusão:** o código executado pela Q não escreve nas raízes preexistentes. As causas remanescentes são:

| Hipótese | Causa | Natureza |
|---|---|---|
| (a) | escritor externo nas raízes durante a janela: processo remanescente, ferramenta de sincronização ou limpeza, ou o mesmo agente do incidente de perda no D: | não é defeito do supervisor |
| (b) | vista instável do digest: o supervisor usa os dados do índice de diretório (FindFirstFile / `DirEntry.stat`), que a Microsoft documenta como possivelmente não atualizados em NTFS. A primeira enumeração pode atualizá-los sem escrita de conteúdo | **defeito material do supervisor** |
| (c) | falha transitória de leitura em `owner_binding` ou `scandir` | defeito de robustez |

O R2 do V003 passou a verificação análoga sobre a raiz V003 com o mesmo tipo de digest. Isso torna (b) menos provável para aquela raiz, mas não para as outras 24 entradas.

## 3. Coleta nativa somente leitura (a executar pelo titular)

**Launcher:** `RUN_CDT21_G5_V004_DIAG_RAIZES_READONLY_20261021.ps1`, SHA-256 **`DE3938EFBD45014A7F53BEBB0818878E2845ABEC6743CA093DDF61F8B71B8D3A`** (108.410 bytes). Parser com 0 erros, sem tokens exclusivos do PS 7, ASCII, CRLF, sem cmdlets destrutivos. As únicas escritas vão para a pasta de log.

**Embutidos:**
- `CDT21_G5_V004_DIAG_RAIZES.py` (`42166FA72DB4FD2A0C51EA58D6B04CDCDCC9C62B24A529381335ED578E7B0FC3`);
- supervisor `273E6207…`, apenas para reutilizar `foreign_roots` e `production_fingerprint` byte a byte.

**O que a coleta produz:**
1. **Comparação por raiz e por campo** com o “antes” da Q, linhas por entrada atuais e entradas modificadas a partir de 10 min antes da Q.
2. **Vista do índice x vista do handle** para cada entrada.
3. **Controle** em árvores que a Q nunca percorreu: índice, depois handle, depois índice de novo.
4. **Repetição imediata e observação de 2 min** sem nenhuma atividade, com a diferença por entrada se algo mudar.
5. **`D:\Base CSV`** comparado com o “antes” da Q, porque essa verificação não foi feita na Q.
6. **Diário USN de C: e D:**, somente leitura (`GENERIC_READ`, `FSCTL_QUERY_USN_JOURNAL` e `FSCTL_READ_USN_JOURNAL`; nada é criado nem alterado). Cobre a janela da Q e o período posterior, restrito aos diretórios das raízes, de `D:\Base CSV` e da própria Q (controle de cobertura), e inclui todo o D: na janela.
7. **Processos vivos, Defender** (detecções e eventos da janela) **e `disablelastaccess`.**

**Qualificação Linux da coleta: 11/11.** Os testes usam um kernel32 falso que produz registros USN V2 no formato real. Cobrem o retorno real fixado, a comparação por raiz, a consistência com o digest do supervisor, o D: com diário inativo, o parse e a classificação USN, um escritor real flagrado por entrada, o índice desatualizado e a prova de somente leitura.

**Execução**, a partir de `PS C:\Users\silvi>`. Requer que a pasta `C:\Users\silvi\Downloads\CDT21_G5_V004_RUNS\G5V4_20261021_153955_137_23632` continue presente.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\Downloads\RUN_CDT21_G5_V004_DIAG_RAIZES_READONLY_20261021.ps1"
```

- **UAC:** necessário, porque a leitura do diário USN exige administrador.
- **Duração:** 3 a 6 min.
- **Log:** `C:\Users\silvi\Downloads\CDT21_G5_V004_RUNS\DIAGQ_<carimbo>\`.
- **Retorno:** `ENVIAR_AO_OPUS_CDT21_G5_V004_DIAGQ_<carimbo>.zip`, enviado diretamente a esta conversa.

**Execute logo.** O diário USN de C: é circular, e sua cobertura da janela das 15:40 diminui com o tempo.

## 4. Decisão de engenharia após a coleta

| Achado | Conclusão | Ação |
|---|---|---|
| (a) registros USN nas raízes durante a janela | a proteção funcionou e o supervisor está correto | identificar o escritor e propor a contenção operacional antes de nova Q |
| (b) leitura move o digest sem registro USN | defeito material do supervisor | correção mínima: digest pela vista do handle e detalhe por entrada na falha, mantendo a exigência de imutabilidade. Qualificar e entregar **somente** o launcher afetado |
| (c) nenhuma diferença persistente nem registro USN | causa transitória | correção de observabilidade e nova Q |

**Em qualquer caso:**
- a proteção não é enfraquecida nem suprimida;
- a campanha G5, B06, B07, D4/D5, canário e FULL não são iniciados;
- os testes já aprovados não são repetidos.

## 5. Arquivos

| Arquivo | SHA-256 |
|---|---|
| `RUN_CDT21_G5_V004_DIAG_RAIZES_READONLY_20261021.ps1` | `DE3938EFBD45014A7F53BEBB0818878E2845ABEC6743CA093DDF61F8B71B8D3A` |
| `CDT21_G5_V004_DIAGQ_EVIDENCE_20261021.zip` (70.933 bytes, 11 membros, `MANIFESTO.json` `E664B2F9…2291`) | `2EFCD6F5C537FC73A66DCF2953CFF78A6EB77646A99EE209D15CEE6F2797EA92` |
| `WITNESS_CDT21_G5_V004_DIAGQ_20261021.json` | registrado no commit |
| `RELATORIO_G5_V004_DIAGQ_20261021.md` (este) | registrado no commit |

## 6. Preservado

| Item | Situação |
|---|---|
| V004 `AD334869…99DD` e código `D2C626FD…66FF` | intactos |
| Supervisor `273E6207…`, launcher R1 `E3F83D0A…` e recibos anteriores | inalterados |
| Diretórios existentes | não tocados |
| G0 V004 | não repetido |

RESULT_RETURN_TO=ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compressão De Ticks 21
