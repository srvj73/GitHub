# CDT21 — G5 V003: causa raiz da parada, correção R2 e launcher final

**Papel:** implementador (Opus 5.5). Não é parecer B06.
**Candidato único:** V003 `69DA2D59…7E50`, código `D59BC4EE…3953`. **Inalterado.**

## 1. Evidência recebida

| Item | Valor |
|---|---|
| Dois volumes de transporte | Verificados (`830FC643…`, `85799BA0…`) |
| `RECONSTRUIR_EVIDENCIAS_OPUS.py` (`733B0D1B…`) | Executado num diretório novo, com `-I` |
| Reconstrução | `PASS COLLECTED_SHA_59_OF_59` |
| `R08_RETURN.zip` | Exato: `5835A841…02EF` |
| Coletor de origem | `D319EC71…` (o qualificado); manifesto `94729DBD…` |

## 2. Causa raiz (comprovada)

**Cadeia de falha:**
- `SUPERVISOR_RESULT`: `phase=CAMPAIGN`, `exit_code=3`, `campaign_exit_code=3`, `owned_processes_at_end=0`, 28,4 s.
- `ENGINEERING_RESULT`: `BLOCKED`, com `PRE_G06_LAB_UNIT_PROCESS_EXIT:SUITE_test_b2d_origin_decision_binder.py:2`.
- Log da unidade: 29/29 `ERROR` no `setUp`, linha 52, com `G5_FIXTURE_RUNROOT_CONTRACT_NOT_MET`.
- **COMMITTED antes da parada (5):**
  - `G5_PS51_INSTALL_MENU`
  - `G5_STAGE_B_REAL_ISOLATED_PATH_NATIVE`
  - `G5_D4_REAL_ISOLATED_PATH_NATIVE`
  - `SUITE_test_cdt17_final_g5_complete_proof_gate.py`
  - `SUITE_test_cdt18_stage_proof_integrated_reconcile.py`

**O contrato congelado.** A suíte `tests/test_b2d_origin_decision_binder.py` (`D19EF3BA…`, idêntica no V002 e no V003) exige, só no Windows, que o código testado esteja em `…\CURRENT_G5_DELTA_*\EXTRACTED\implementation_v001`. O caminho também precisa ser canônico, sem alias.

**O defeito.** O supervisor externo R1 (`7B482A4B…`) extraiu em `<raiz>\PACKAGED`. Foi uma obrigação de lançador que eu não identifiquei: o lançador CDT20 da origem a cumpria, e por isso a mesma suíte passou nativamente no V002.

| Aspecto | Conclusão |
|---|---|
| Tipo do defeito | Do supervisor externo, não do V003 |
| Correção no candidato | Desnecessária |
| Sucessor do V003 | Nenhum |

## 3. Reprodução determinística e controles

**Linux, bytes congelados:** a suíte congelada é carregada em cada layout com `os.name='nt'` aplicado só ao módulo de teste (`B2D_LAYOUT_CONTROLS`).

| Layout | Resultado |
|---|---|
| A — `<raiz>\PACKAGED` (R1) | 29/29 `CONTRACT_NOT_MET`: reproduz a falha nativa |
| B — `CURRENT_G5_DELTA_*\EXTRACTED` | 29/29 OK |
| C — `EXTRACTED` sem prefixo | Recusado |
| D — alias | Recusado |

**Windows (no launcher, fase Q):** a mesma suíte é executada **nativamente** nos layouts B (deve passar 29/29) e A (deve falhar 29/29 por `CONTRACT_NOT_MET`). Sem os dois resultados, a retomada não começa.

## 4. Correção mínima: supervisor R2 (`99704BA5…C0CC`)

O R2 deriva do R1 por substituições exatas e revisáveis (`make_r2.py` e `make_r2_q.py`; diff anexo).

1. **Layout.** Extrai o V003 em `%LOCALAPPDATA%\CDT21_G5_V003\CURRENT_G5_DELTA_<carimbo>\EXTRACTED` e aplica o mesmo predicado da fixture antes de usar.
2. **Retomada da MESMA raiz** `R08_Q1_20261020210605_856fea523791`, com reconciliação somente leitura:
   - `OWNER` idêntico na raiz e no laboratório D:;
   - witness determinístico;
   - pacote único em `INPUTS`;
   - `ENGINEERING_RESULT` em `BLOCKED`;
   - ausência de `SAFE_STOP`;
   - cada COMMIT fechado e vinculado ao V003, com artefatos re-hasheados.
3. **Preservação:**
   - os terminais anteriores são **copiados** para `INTERRUPTED_ATTEMPTS\PRIOR_TERMINAL_*`;
   - o `R08_RETURN.zip` anterior é copiado byte a byte para o estágio;
   - a tentativa b2d é **movida** pelo próprio `run_unit` congelado para `INTERRUPTED_ATTEMPTS`; nada é apagado.
4. **Sem reexecução das 5 COMMITTED.** O `run_unit` congelado as reutiliza (`REUSE_COMMITTED`). O R2 registra as reutilizações e bloqueia se o conjunto reutilizado não for exatamente o das 5.
5. **Fase Q, qualificação nativa, obrigatória antes de qualquer efeito.** A retomada recusa iniciar sem um `QUALIFICATION_RESULT` PASS, recente, dos mesmos bytes, raiz e log. A Fase Q:
   - prova kill-on-close aninhado (Job object);
   - reconcilia processos (`R.dead` congelado sobre todas as identidades registradas), lock (`CAMPAIGN.lock` adquirível e liberado) e checkpoints (`LIVE_STATUS` igual aos COMMITs; SHA do `R08_RETURN` anterior);
   - prova o isolamento dos caminhos de escrita (canônicos, sem reparse, fora de `D:\Base CSV`);
   - tira a impressão digital somente leitura de `D:\Base CSV`;
   - executa o b2d nativo positivo e negativo;
   - prova que ela própria não alterou nada na raiz nem no laboratório D:.
6. **Produção.** A impressão digital de `D:\Base CSV` é verificada antes e depois da campanha e precisa coincidir com a da Fase Q; qualquer diferença bloqueia.

## 5. Qualificação Linux (não basta para executar; a execução exige a Fase Q nativa)

| Suíte | Resultado |
|---|---|
| Controles de layout b2d | 4/4 |
| R2 sobre a raiz nativa real reconstituída | 21/21 |
| Regressão das verificações do R1 sobre o R2 | 20/20 |
| Funções da Fase Q | 18/18 |
| Controles negativos do montador B06 | 4/4 |

**Destaques do R2:**
- reutiliza as 5 COMMITs nativas pelo `run_unit` congelado;
- preserva a tentativa b2d;
- recusa 9 estados inválidos.

**Destaques da Fase Q:**
- recusa qualificação bloqueada, de outro supervisor, de outra raiz ou log, ou vencida;
- falha fechada sem efeitos.

**Destaques do montador B06:** recusa o retorno BLOCKED genuíno, um rótulo PASS forjado e um índice forjado; este último é barrado pelo gate congelado.

**Somente no runtime Windows (Fase Q):** elevação, NTFS, Job aninhado, lock `msvcrt` real, censo de processos e b2d negativo nativo.

## 6. Classificação de efeitos

- **Fase Q:** grava apenas em C:, nas pastas de log, estágio, `CURRENT_G5_DELTA_QUAL_*` e `QUAL_NEG_*`. Somente lê a raiz, o laboratório D: e `D:\Base CSV`.
- **Fase E:** grava na raiz da campanha, no laboratório D: (`WRITER_EFFECTFUL`, da ordem de centenas de KB) e no log fixo do V003, `C:\Users\silvi\OneDrive\Downloads\TICKSTORE_RUNS`, que está fixado no código congelado. `D:\Base CSV` permanece somente leitura, com impressão digital antes e depois.

## 7. Launcher final único

`RUN_CDT21_G5_V003_FINAL_R2_20261021.ps1` (`DF8FF518…5C1F`), em Windows PowerShell 5.1, executado a partir de `C:\Users\silvi`.

**Log:** `C:\Users\silvi\Downloads\CDT21_G5_V003_RUNS\G5R2_<carimbo>\`. Pai e filho elevado gravam na **mesma** pasta, e o pai empacota um único `ENVIAR_AO_OPUS_…zip`.

**Modos:**
- Sem `-AutorizoLabD`: só a Fase Q (código 10).
- Com `-AutorizoLabD`: Fase Q e, se PASS, Fase E.

## 8. Após o retorno nativo

O montador `build_b06_dispatch.py` aplica, ao retorno:
- o gate congelado;
- a **reexecução independente de `PRE_G06_COMPLETENESS.close` no Linux**, com comparação byte a byte ao `FINAL_G5` do Windows;
- a releitura física das cinco partes.

Só então monta `CDT21_V003_B06_INDEPENDENT_DISPATCH_READY.zip`, com testemunha externa. Se algo falhar, emite `NOT_READY` com a causa. B06 segue `NOT_STARTED` e o despacho é exclusivo da origem.
