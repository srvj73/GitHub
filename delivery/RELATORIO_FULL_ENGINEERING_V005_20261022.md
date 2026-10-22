# CDT21 — Entrega definitiva do FULL de engenharia (V005), 2026-10-22

**Origem:** missão consolidada “entrega definitiva do FULL de engenharia”.
**Papel:** implementador, não B06.
**Retorno:** ChatGPT, projeto Base de Dados CSV / Tickstore, conversa Compressão De Ticks 21.

## 1. Resultado

Entrego **um único pacote FULL de engenharia**, `CDT21_FULL_ENGINEERING_V005_20261022.zip` (SHA-256 `99C77F4603E3547E34D4513782B5590E10E5B33159F08CB0A1E08E46B6B77662`, 122 membros). Ele contém:
- o código integrado (candidato V005 congelado);
- os executores, inclusive o instalador congelado;
- os manifestos;
- o mapa de componentes e consumidores;
- as evidências e os controles negativos;
- o MISSION_LOCK, a matriz de pré-entrega, o recibo dos cinco critérios e o estado dos gates;
- os procedimentos de execução e de recuperação.

**Não há bloqueio corrigível internamente em aberto.** O único impedimento físico desta etapa é a campanha G5 nativa do V005, que só pode rodar no Windows do titular. Ela tem procedimento único, vinculado por hash e delimitado: o **P1**, com retorno direto ao Opus.

## 2. Por que existe o V005

A revisão integrada percorreu os caminhos completos sobre os bytes do V004, não apenas a existência dos módulos. Resultado: a cadeia FULL estava **interrompida no D4**.

| Achado | Defeito no V004 | Correção no V005 |
|---|---|---|
| GAP-01 (crítico) | O recibo D4 nunca era publicável: `FULL_STAGE_EVIDENCE.publish` exigia testemunhas de nó que o D4 não tem | O produtor espelha o consumidor `validate_chain`: testemunhas somente de D5 a FULL_ADMISSION |
| GAP-02 (crítico) | O `FULL_RUNNER` não passava `-G5StageReceiptPath`/`-G5InstancePath`, exigidos pelo wrapper D4 selado | Os dois saem da cadeia admitida e são obrigatórios |
| GAP-03 (alto) | O launcher adaptado fixava uma entrada inline inexistente. **Foi regressão do meu delta V003** | O pin passa a ser a entrada vinculada; os bindings acompanham |
| GAP-04 (alto) | O ZIP sucessor do D4 tinha duas identidades | Identidade única `8A05E761…`; a Q do P1 lê, somente para leitura, o arquivo físico |
| GAP-09 (médio) | O `SOURCE_MANIFEST` omitia o `RUNTIME_CODE_MANIFEST.json` (**veio das minhas montagens V003/V004**) | Manifesto fechado; o verificador do próprio candidato passa |

**Prova:** 7 testes de regressão, em suítes do plano G5, **falham no V004 e passam no V005**. Ambos os ZIPs foram extraídos do zero para essa verificação.

Na varredura Linux, 77 módulos foram comparados um a um. Somente as duas suítes com testes novos diferem, ambas OK (705 → 712 testes). Os testes que não rodam no Linux falham da mesma forma nos dois e não contam como aprovação.

O V004 foi preservado byte a byte como pai, com todas as suas evidências. Os documentos de operação também foram corrigidos (GAP-06, GAP-07 e GAP-11).

## 3. Achados A1–A6

| Achado | Estado | Base |
|---|---|---|
| A1 | Fechado no código (R4) e levado ao G5 V005 | Reconciliação COMMIT→livro-razão por prova de proveniência. R4: 52/52 e 11/11 mutantes. Supervisor V005: 53/53 (inclui NR14, COMMIT do pai V004 recusado) e 11/11 mutantes. A Q nativa do censo do Job ocorre no P1 |
| A2 | Fechado no código do V005; prova nativa no P1 | Cadeia percorrida caminho a caminho; mapa de 163 componentes revinculado aos bytes finais (6 alterados) |
| A3 | Impedimento físico (Windows do titular) | P1 pronto. Os deltas do V005 rodam nativamente dentro das suítes do plano G5 |
| A4 | Fechado para os executores novos; raiz congelada justificada | Logs em `C:\Users\silvi\Downloads\CDT21_G5_V005_RUNS\G5V5_<stamp>`; instalador por `-WitnessPath`; prova nativa → Opus, consolidado → origem, B06 → Work |
| A5 | Fechado | `RUNTIME_CODE_MANIFEST` do V005 (163 arquivos) verificado membro a membro; papéis, consumidores e dependências externas por gate |
| A6 | Fechado | Pacote único; um sucessor congelado em lugar de patches isolados |

## 4. O que fica fora do alcance interno (estado explícito em `09_ESTADO_DOS_GATES.json`)

- **G5 nativo do V005:** P1, no Windows do titular.
- **B06:** Work independente.
- **Decisões e registros da origem:** decisão G5, decisão B07, recibo de admissão de política D4, pacote de revisão D4 e reconciliação corrente.
- **GAP-10:** 2 overlays derivados aprovados pela origem para a B07 (`E74F3701…`, `40B396FC…`). Não existem em nenhum artefato disponível, e fabricá-los seria forjar entrada.
- **GAP-05:** observação nativa do predecessor D4 (no máximo 300 s antes da admissão). Não há produtor em nenhum artefato. A observação descreve a produção no instante do D4; o Opus prepara o observador somente leitura na preparação do D4.
- **GAP-17 (só testes):** duas suítes fora de qualquer gate dependem de capturas MASTER/HEAD históricas, que só existem dentro de um arquivo empacotado. Copiá-las para `tests/fixtures` é decisão de custódia da origem.
- **Queda física de energia:** `NOT_TESTED_PHYSICAL_POWERLOSS`.

## 5. Não declarado

Não declaro como concluídos:
- G5 nativo do V005;
- B06, B07, D4, D5, canário, FULL_PREP, FULL_ADMISSION e FULL;
- execução nativa do launcher adaptado (só ocorre no D4).

Também não apresento como aprovação nativa do V005:
- o G0 nativo do V004;
- o G5 nativo do V003;
- a qualificação Linux.

## 6. Próximo passo único

O titular executa o **P1**, a partir de `PS C:\Users\silvi>`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\Downloads\RUN_CDT21_G5_V005_20261022.ps1" -AutorizoLabD
```

**Pré-requisitos em `C:\Users\silvi\Downloads`:**
- `CDT21_FINAL_PACKAGE_V005_20261022.zip` (`E3F1F479…`);
- `RUN_CDT21_G5_V005_20261022.ps1` (`2767A823…`).

**Log:** `C:\Users\silvi\Downloads\CDT21_G5_V005_RUNS\G5V5_<stamp>\RUN_LOG.txt`.

**Retorno:** `ENVIAR_AO_OPUS_CDT21_G5_V005_<stamp>.zip`, enviado diretamente ao Opus.
