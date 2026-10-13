# TICKSTORE R9 — FULL MULTIWORK RC2R2

## Objetivo

Camada produtiva de orquestração paralela sobre a RC1 homologada, sem editar `tickstore_serial_runner.py`.

## Invariantes

- Core RC1 congelado por SHA-256.
- Fonte CSV somente leitura.
- Nenhuma exclusão de CSV.
- Formato/codec inalterados (`PTS2G001` / `ZSTD9`).
- Publicação canônica e manifesto permanecem **single-writer**.
- Parsing + construção + compressão são **multi-process**.
- Um worker processa um mês por vez, sequencialmente dentro do mês.
- Cada worker mantém `FullSerialMonth` aberto do hash inicial ao hash final do mês.
- Worker nunca publica em `D:\TICKSTORE`; produz `partial+journal` validados no scratch.
- Pai valida e publica uma data por vez usando a state machine RC1.
- Owner gate RC1 continua obrigatório.
- Gate adicional MULTIWORK, com trusted SHA externo, é obrigatório.

## AUTOCPU

`--workers AUTO` calcula concorrência a partir de:

- CPUs lógicas menos reserva de 2;
- teto configurável (`--max-workers`, default 22);
- alvo de RAM (`--ram-target-percent`, default 60%);
- orçamento conservador de ~1.25 GiB por worker e 2 GiB para o parent/OS.

O número efetivo é impresso como `WORKERS_EFFECTIVE=N`.

## Resume

Há duas camadas de resume:

1. transações canônicas deixadas por RC1/execução anterior são normalizadas antes do multiwork por `run_one_day`;
2. trabalho multiwork interrompido fica em `D:\TICKSTORE_GATE_B_SCRATCH\FULL_MULTIWORK_RC2R2\<month>\<date>`, usando o mesmo journal durable por row-group.

O coordinator JSON é informativo; a autoridade de resume continua sendo journal/artefatos canônicos.

## SAFE_STOP

Workers ignoram SIGINT direto; o parent recebe Ctrl+C, seta `stop_event` e os workers param **após o row-group corrente ter sido journalado**.

O parent espera todos os workers fecharem seus month pins; não usa terminate/kill como fluxo normal.

Marcadores:

```text
SAFE_STOP=YES
SAFE_STOP_GRANULARITY=ROW_GROUP
RESUME=YES
```

## Progresso/ETA

O parent agrega progresso por rows:

```text
PROGRESS [########----------------------] 26.1234% DAYS=... MONTHS=... WORKERS=... RATE_ROWS_S=... ETA=d.hh.mm.ss BUILT=... REUSED=... RESUMED=... RAM_AVAILABLE_GIB=... D_FREE_GIB=...
```

A atualização ocorre no máximo a cada ~5 s e também após cada publicação.

## Fluxo por mês

1. worker abre `FullSerialMonth` (hash inicial + pin write/delete denial);
2. envia identidade ao parent;
3. parent reconcilia/reutiliza dias canônicos já existentes;
4. worker constrói apenas dias ausentes no scratch;
5. ao final de cada row-group, journal atômico + evento de progresso;
6. quando o dia está `VALIDATED_PENDING_PUBLISH`, worker espera;
7. parent transfere journal/partial para a transação canônica e publica com RC1;
8. parent ACK;
9. worker segue para o próximo dia;
10. ao fim do mês, `FullSerialMonth` refaz hash completo e fecha pin.

## Fronteira terminal

Após todos os 1550 dias:

1. final source seal abre as 75 fontes;
2. `reconcile_full_readonly` integral;
3. release do writer lock;
4. final binding verification;
5. fechamento do final seal;
6. somente então `TICKSTORE_FULL_MULTIWORK_STATUS=PASS`.

## Proibições

```text
LEGACY_FULL_HISTORY=NO
CSV_DELETION=NO
FORMAT_PROMOTION=NO
CODEC_PROMOTION=NO
THREAD_POOL=NO
MULTIPLE_CANONICAL_WRITERS=NO
```


## RC2R2 additional fail-closed requirements

1. Explicit `--workers N` is bounded by the same CPU and RAM budgets as AUTO; it cannot bypass the 60% target policy.
2. A worker that exits without a structured terminal event is a blocking error.
3. On parent error/SAFE_STOP, the parent does not intentionally release canonical lock/pins while workers are still alive; it waits cooperatively for worker termination.
4. The launcher must return control to the invoking PowerShell host and must not call `exit $LASTEXITCODE`.
5. Windows release preflight must prove 22 concurrently alive/pinned worker processes, 22 synthetic builds and 22 synthetic resumes.
