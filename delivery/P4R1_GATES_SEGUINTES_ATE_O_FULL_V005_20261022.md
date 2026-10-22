# P4R1 — Gates seguintes, do G5 operacional ao FULL (preparado; não executado)

**Revisão R1 (adendo GAP-05, 22/10):** este documento substitui o P4 do pacote FULL. As mudanças são duas:
- a instalação deixa de usar extração manual e passa a usar o lançador autoextraível `RUN_CDT21_V005_PREPARO_D4_20261022.ps1 -Etapa Instalar`;
- a observação nativa do predecessor D4 passa a ter um produtor qualificado, que roda na etapa `Observar` do mesmo lançador.

O restante é idêntico ao P4. O P4 original continua no pacote FULL como histórico. O V005 não foi alterado.

**Fonte normativa:** `implementation_v001/procedures/PROCEDIMENTO_OPERACIONAL_GATES.md` do V005. A seção “CDT21 V005 — correções de integração da cadeia” prevalece sobre o texto anterior a ela. Este P4 resume a ordem, os pré-requisitos e quem executa cada etapa; ele não autoriza etapa alguma.

**Convenções do procedimento congelado:**
- execução a partir de `PS C:\Users\silvi>`, sem `cd`;
- `PY` = Python 3.14 fixado por SHA;
- `CAND` = `implementation_v001\candidate` da instalação ativa;
- todo digest marcado como “à parte” é digitado separadamente pelo operador.

## Ordem e responsáveis

| # | Etapa | Quem | Pré-requisito | Observação V005 |
|---|---|---|---|---|
| 0 | G5 técnico nativo do V005 | titular (P1) → Opus (P3) | — | única prova nativa desta entrega |
| — | Instalação do V005 (não é admissão) | titular | P1 PASS (recomendado) | `RUN_CDT21_V005_PREPARO_D4_20261022.ps1 -Etapa Instalar` (ver “Instalação” abaixo); resultado `INSTALLED_NOT_PRODUCTION_ADMISSION` em `%LOCALAPPDATA%\TICKSTORE\Candidates\<sha do pacote>` |
| 2 | `INSTANCE.json` operacional | titular | — | `FULL_INSTANCE_PREPARE.py prepare` |
| 1 | Completude G5 V003 sobre a instância operacional | titular | P1 PASS + etapa 2 | comando `G5_FINAL_COMPLETENESS_PRODUCER.py` da seção V005, item 1 |
| 3 | Decisão G5 | **origem** | completude + pacote G5 | `TEMPLATE_ORIGIN_STAGE_DECISION.json` |
| 3b | Recibo de estágio G5 | titular | decisão + reconciliação de política corrente (origem) | `ORIGIN_DECISION_BINDER.py --stage G5` |
| 4 | B06 | **Work independente** | despacho do Opus (P3) | veredito exatamente no `TEMPLATE_B06_VERDICT.txt` |
| 4b, 5 | Conformidade B06 e cadeia até B06 | titular | B06 | `B06_RECEIPT_CHECK.py`; `FULL_INSTANCE_PREPARE.py chain --until B06` |
| 6 | Verificações nativas B07 | titular no Windows | cadeia até B06; **2 overlays derivados fornecidos pela origem** (`E74F3701…`, `40B396FC…`, GAP-10); launcher B07 montado pelo Opus no despacho | o pacote QUAL está em `B1_APPROVED_INPUTS` do V005 |
| 7, 7b, 8 | Decisão B07 (origem), recibo B07 e cadeia até B07 | origem + titular | B07 técnico | — |
| — | Ativação oficial do menu | titular | cadeia até B07 | `INSTALL_TICKSTORE_FULL.ps1 -ActivateMenu -ChainFile … -ChainSha256 … -B06Sha256 …` |
| — | LEGACY_ENTRY_FENCE | titular | cadeia até B07 | `PROCEDIMENTO_CDT21_LEGACY_ENTRY_FENCE.md` |
| 8b | Migração do sucessor D4 (V002R22 → V002R24) | titular | cadeia até B07 | ZIP com identidade única `8A05E76189E63379A60E2447DAA313765D30A2EAB78EAF4E9D91AA19CBFE3E73`; a Q do P1 já informa o arquivo físico |
| — | Entradas do D4 emitidas pela origem | **origem** | B07 | recibo `TICKSTORE_D4_POLICY_ADMISSION_RECEIPT_V001` (`TEMPLATE_D4_POLICY_ADMISSION_RECEIPT.json`), pacote de revisão D4 e reconciliação corrente |
| — | Observação nativa do predecessor D4 (no máximo 300 s antes da admissão) | titular | B07 + entradas da origem para o D4 | `RUN_CDT21_V005_PREPARO_D4_20261022.ps1 -Etapa Observar -EvidenceDir "<PredecessorEvidenceDir>" -AutorizoLeituraProducao`, imediatamente antes de iniciar o D4 (ver “Observação nativa do predecessor D4” abaixo) |
| 9 | D4 | titular | todas as linhas acima | MENU opção 10 ou `RUN_TICKSTORE_FULL.ps1 -Stage D4`; o `FULL_RUNNER` passa ao wrapper o recibo G5 e a instância da cadeia (GAP-02); `D4Close` publica o recibo D4 (GAP-01) |
| 10–12 | D5, CANARY, FULL_PREP | titular | recibo anterior + reconciliação | `MENU` → etapa |
| 13 | Revisão Stage B + `FULL_GO` | revisor/origem | FULL_PREP | `inbox\STAGE_B_REVIEW_V001.txt`, `inbox\FULL_GO.txt` |
| 14 | FULL_ADMIT | titular | FULL_PREP + revisão | recibo válido por 300 s; `FULL_READMIT` reemite |
| 15 | FULL | titular | FULL_ADMISSION fresca | MULTIWORK/AUTOCPU, heartbeat, ETA, Monitor somente leitura, `Stop` cooperativo |

## Instalação (autoextração segura do instalador congelado)

A partir de `PS C:\Users\silvi>`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\Downloads\RUN_CDT21_V005_PREPARO_D4_20261022.ps1" -Etapa Instalar
```

**Pré-requisitos em `C:\Users\silvi\Downloads`:**
- `CDT21_FINAL_PACKAGE_V005_20261022.zip`;
- `WITNESS_TICKSTORE_FULL_FINAL_V005_20261022.json`.

**O que o lançador faz:**
1. Confere o SHA-256 do ZIP (`E3F1F479…`) e o da testemunha (`A3A616DA…`).
2. Extrai `control/INSTALL_TICKSTORE_FULL.ps1` para uma pasta própria e nova em `%LOCALAPPDATA%\CDT21_PREPARO_D4_V005\STAGE_<stamp>`, sem sobrescrever nada. O membro é conferido contra o `RUNTIME_CODE_MANIFEST` do pacote e contra o pin `BB245FCF…`.
3. Executa o instalador congelado com `-WitnessPath`. Isso evita o padrão legado `OneDrive\Downloads` e o bloqueio por cardinalidade de testemunhas.

**Logs:**
- do lançador: `C:\Users\silvi\Downloads\CDT21_PREPARO_D4_V005_RUNS\INSTALAR_<stamp>\RUN_LOG.txt`;
- do instalador: a raiz congelada `OneDrive\Downloads\TICKSTORE_RUNS` (GAP-08).

A ativação do menu (`-ActivateMenu`) continua exigindo a cadeia até B07.

## Observação nativa do predecessor D4 (GAP-05)

O produtor `CDT21_D4_PREDECESSOR_OBSERVER.py` está embutido no lançador e qualificado: Linux 23/23, mutantes 15/15, laboratório nativo 5/5. Ele grava em `<PredecessorEvidenceDir>`:
- `predecessor_observer\predecessor_evidence\OBSERVATION.json`;
- `predecessor_observer\PREDECESSOR_SYSTEM.json`;
- `D4_ROOTS_REPORT.json`, gerado pelo produtor congelado `D4_ROOTS_EVIDENCE`.

Esses são os arquivos que `D4_FIRST_ADMISSION_BOOTSTRAP.fresh_predecessor` lê.

1. **Na preparação da INSTANCE (etapa 2):** escolha um `PredecessorEvidenceDir` absoluto, fora de `D:\Base CSV` e sem a palavra TICKSTORE. Sugestão: `C:\Users\silvi\AppData\Local\CDT21_D4_PREDECESSOR_EVIDENCE`.
2. **Antes da observação:**
   - feche todos os programas Python e janelas que citem TICKSTORE;
   - se o último boot for anterior ao `STARTED` do predecessor, use **Reiniciar**, e não Desligar (com a Inicialização Rápida, Desligar não reinicia o kernel).
3. **No momento do D4,** com a cadeia até B07 e as entradas da origem prontas, execute:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\Downloads\RUN_CDT21_V005_PREPARO_D4_20261022.ps1" -Etapa Observar -EvidenceDir "<PredecessorEvidenceDir>" -AutorizoLeituraProducao
```

   - A produção é lida somente para leitura e a escrita ocorre só na pasta de evidência.
   - Evidências anteriores são movidas para `HISTORICO_OBSERVACOES`, nunca apagadas.
   - O resultado esperado é `OBSERVER_STATUS=PASS_FRESH_PREDECESSOR_EVIDENCE`.
   - O próprio produtor roda os consumidores congelados sobre o que gravou e informa `valid_until_utc`.
4. **Logo em seguida, inicie o D4** (MENU opção 10 ou `RUN_TICKSTORE_FULL.ps1 -Stage D4`). O bootstrap verifica a observação duas vezes, antes da materialização e no `revalidate()`; nas duas, ela precisa ter no máximo 300 s. Se passar disso, repita o passo 3.
5. **Se a observação for recusada,** o recibo informa o motivo exato do consumidor congelado, por exemplo:
   - outro Python vivo;
   - lock presente;
   - boot anterior ao `STARTED`;
   - identidade de raiz divergente.

   Corrija a condição (nunca a evidência) e repita. Uma recusa não autoriza contornar o D4.

## Regras

- **Retornos:**
  - prova nativa → Opus;
  - fechamento consolidado → ChatGPT (origem);
  - B06 → Work independente.
- **Parada em bloqueio:** qualquer `*_BLOCKED=<motivo>` encerra a etapa; nada é inferido e nada é repetido por conta própria.
- **Escritas:** nenhuma etapa antes do D4 escreve em `D:\Base CSV`. A migração 8b, a cerca legada e a ativação do menu têm efeitos próprios e documentados; executam-se somente com a cadeia até B07.

