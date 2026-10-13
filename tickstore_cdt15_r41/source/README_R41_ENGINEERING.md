# TICKSTORE CDT15 — R41 (engenharia, SOURCE_ONLY + qualificação Windows em sandbox)

`ROLE=ENGINEER_ONLY` · `B06=NOT_STARTED` · `G4=INCOMPLETE` · `G5=NOT_PROVEN` · `FULL_STARTED=NO` · `PRODUCTION_MODIFIED=NO`

Base exata: `TICKSTORE_G4_CURRENT_CORRECTED_SOURCE_ONLY.zip` (SHA-256 `26F783A0…B757`), manifesto aninhado 168/168 conferido.
Política: captura não autoritativa `20261013T070500-0300-695DCD6495E549B1` (MASTER `695DCD64…7DF5`, HEAD `B3B41959…F7EA`); reconciliação de vigência permanece com a origem ChatGPT.

## O que o R41 entrega

1. **Gravador oficial efetivo** — `candidate/control/MENU_OFFICIAL_WRITER.py`
   - Um único lock do SO (`MENU_WRITER.lock`, handle sem compartilhamento, liberado pelo SO se o processo morrer) mantido da readmissão até `COMMITTED`/`ROLLED_BACK`.
   - MENU, pendente e backup no volume do MENU (D:); ACTIVE, journal e evidências em `%LOCALAPPDATA%\TICKSTORE` (C:). Protocolo entre volumes, **não** transação atômica global.
   - `ReplaceFileW` com backup explícito; após a troca, prova-se que o backup contém exatamente os bytes admitidos (detecção de troca hostil na janela TOCTOU).
   - ACTIVE por `MoveFileExW` sem substituição (colisão ⇒ bloqueio).
   - `PREPARED` torna-se visível por um único rename de diretório (staging → `MENU_TRANSACTION`).
   - `PLAN.json`/`JOURNAL.json` compatíveis byte a byte com o consumidor do MENU; registros de fase imutáveis; `EVIDENCE.json`.
   - Recuperação por **novo processo** em todo ponto de queda, inclusive durante a própria recuperação e falha parcial de `ReplaceFileW` (erro 1177). `COMMITTED` nunca é inferido por hash; journal forjado é rejeitado. Nada é apagado.
   - Modo OFICIAL exige Windows + cadeia técnica até **B07** (dígito B06 independente fornecido à parte) + admissão read-only ao vivo. Modo QUALIFICAÇÃO só opera em sandboxes com sentinela.
2. **Instalador integrado** — `-ActivateMenu` passou a ser apenas despacho para o gravador instalado, exigindo cadeia até B07 antes de qualquer leitura de testemunha ou escrita.
3. **Runner FULL** — `RUN_TICKSTORE_FULL.ps1`/`FULL_RUNNER.py`/`tickstore_full_multiwork.py`:
   - correção: `Stop` agora eleva (o evento `Global\` criado pelo runner elevado é de integridade alta);
   - correção: janela elevada **visível** (barra, ETA e Ctrl+C acessíveis);
   - log por execução em pasta absoluta fixa `C:\Users\silvi\OneDrive\Downloads\TICKSTORE_RUNS\<ETAPA>_<yyyyMMdd_HHmmss_fff>_<PID>\RUN_LOG.txt`;
   - estágio `Monitor` (somente leitura) com barra, ETA `d.hh.mm.ss`, idade do heartbeat e do laço principal, veredicto `WATCHDOG`;
   - AUTOCPU passa a sondar as CPUs efetivamente disponíveis ao processo (afinidade/grupos);
   - watchdog do laço de eventos: estagnação > 600 s solicita SAFE_STOP cooperativo (nunca mata processos).
4. **Testes defasados realinhados** — `test_full_multiwork.py` (24/24) e `static_multiwork_preaudit.py` (PASS) agora refletem os bytes atuais (gates administrativos revogados verificados como revogados).

## Execução no seu Windows (único passo desta rodada)

Coloque em `C:\Users\silvi\OneDrive\Downloads`:
`TICKSTORE_CDT15_R41_QUAL_20261013.zip`, `RUN_TICKSTORE_CDT15_R41_QUAL.ps1` e `WITNESS_TICKSTORE_CDT15_R41_QUAL_20261013.json`.

```
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\OneDrive\Downloads\RUN_TICKSTORE_CDT15_R41_QUAL.ps1"
```

Não requer elevação nem `cd`. Duração esperada: poucos minutos. Disco: < 200 MB em C: e D:.
Pastas criadas (todas próprias da execução): `...\Downloads\TICKSTORE_RUNS\R41_QUAL_*`, `%LOCALAPPDATA%\TICKSTORE_QUAL_R41\R41_QUAL_*`, `D:\TICKSTORE_QUALIFICATION_SANDBOX\R41_QUAL_*`.
Nunca escreve em `D:\Base CSV`, `%LOCALAPPDATA%\TICKSTORE`, MENU, BAT, ACTIVE_DEPLOYMENT ou STATE; o driver comprova isso comparando instantâneos somente leitura antes/depois.

Devolva o `RETURN_ZIP` impresso ao final (e as linhas `RESULT_CONTEXT` … `CLASSIFICATION`).

## O que um PASS significa — e o que não significa

PASS = evidência nativa (PS 5.1 + Python 3.14.7 fixado) **do delta R41 em sandbox**: gravador, instalador→gravador, contenção de processos, SAFE_STOP por evento, observabilidade. Não é G4, G5, B06, B07, admissão de produção, nem prova de durabilidade a queda de energia (apenas morte de processo).
