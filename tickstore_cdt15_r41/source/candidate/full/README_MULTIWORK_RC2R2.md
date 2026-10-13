# TICKSTORE FULL MULTIWORK RC2R2

Não execute este pacote ainda sem o gate MULTIWORK autorizado e a validação Windows final.

Arquivos novos:

- `tickstore_full_multiwork.py` — parent/worker multi-process.
- `run_tickstore_full_multiwork_r9.ps1` — launcher.
- `FULL_MULTIWORK_OWNER_GATE_TEMPLATE_DO_NOT_USE.json` — template fechado.
- `SPEC_FULL_MULTIWORK_RC2R2.md` — contrato.
- `test_full_multiwork.py` — testes da camada nova.
- `static_multiwork_preaudit.py` — scanner estático.

A RC1 original permanece byte a byte congelada e continua sendo o core/oráculo.

## Recursos

- AUTOCPU com teto de 22 workers por padrão.
- alvo de RAM 60%.
- multiprocessing `spawn`.
- um mês por worker.
- publicação single-writer.
- resume por row-group.
- recuperação de transação serial interrompida antes de iniciar o paralelo.
- Ctrl+C cooperativo no row-group.
- barra textual, percentual, rows/s, ETA, RAM e espaço D:.
- `BUILT`, `REUSED`, `RESUMED`.

## Gate

São necessários dois gates:

1. o owner gate RC1 que vincula core/path/volumes;
2. um owner gate MULTIWORK independente que vincula wrapper SHA, core SHA, SHA do gate RC1, roots, volumes e limites máximos de workers/RAM.

O template entregue permanece `authorized=false`.

- Em máquinas com 24 CPUs lógicas, AUTO reserva 2 CPUs e pode chegar a 22 workers se o orçamento de RAM de 60% permitir.


## RC2R2 hardening

- explicit worker counts cannot bypass CPU/RAM budgets;
- clean worker exit without a terminal event blocks instead of hanging forever;
- error/stop paths wait for workers to terminate cooperatively before releasing pins/lock;
- production launcher no longer calls `exit`, so it does not intentionally close the caller PowerShell host;
- Windows preflight includes a real 22-process concurrent synthetic build/resume/pin test.
