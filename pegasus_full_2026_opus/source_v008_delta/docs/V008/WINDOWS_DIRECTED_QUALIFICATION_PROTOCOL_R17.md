# Protocolo de qualificação dirigida Windows — V008R17 (rotas I-01/I-02/I-03, processos sintéticos)

Prova nativa, no PC do titular, das propriedades das **rotas efetivamente modificadas na R17** que não podem
ser demonstradas em sandbox POSIX. Processos **exclusivamente sintéticos**, hash-bound, sem instalação
produtiva, sem economia, **sem kill não autorizado**. Complementa (não substitui) a campanha R9 (23/23, MET)
preservada, o protocolo dirigido R16 (N1/N2/N3) e os controles negativos offline. O Opus coordena diretamente
com o titular.

## Pré-condições
- `-Mode Verify` do bootstrap R17 PASS (identidade do pacote e dos pais conferida).
- Python fixado (SHA conferido pelo bootstrap). Elevação só onde o USN exige; nenhum efeito fora do diretório
  sintético de trabalho.

## Alvos (cada um com árvore sintética própria, curta, controlada)

| # | Propriedade (invariante R17) | Processo sintético | Observação esperada | NO_KILL |
|---|---|---|---|---|
| D1 | **I-01** W04 retida até prova de close | árvore drenada; `close()` do Job **recusa** uma vez (ativo>0 simulado) e depois confirma | na recusa: lease W04 **não** liberada (handles abertos), `w04_held_pending_close=True`, hold; na confirmação: `release()` só então | sim |
| D2 | **I-01** close confirmado | árvore drenada; `close()` prova `closed=True, active=0` | `CUSTODIAN_CLOSED`; `guard.release()` depois do close; `evaluate` antes de `release` (ordem JIT) | sim |
| D3 | **I-02** pré-spawn + recibo canônico falho | lease incompleta (sem spawn) + diretório de evidência somente-leitura | exit **3** e `result=FAIL_PRESPAWN_RECEIPT_NOT_PERSISTED`; fallback coerente; banner = mesmo desfecho (nunca exit 2) | n/a |
| D4 | **I-02** pré-spawn + recibo canônico OK | lease incompleta (sem spawn) + evidência gravável | exit **2** e `result=BLOCKED_PRESPAWN_NO_EFFECT`; recibo canônico presente | n/a |
| D5 | **I-03** admissão de produção incompleta | `--authorization` apontando pacote sem um gate | `PRODUCTION_ADMISSION_BLOCKED:GATE_MISSING…`; não chega ao selo final | n/a |
| D6 | **I-03** admissão completa + selo final | `--authorization` com pacote completo (SHA de recibos sintéticos do titular) | chega ao selo final `entry.release_admission` e **bloqueia** (RUN_RELEASED=NO); exit 2, `effects=NONE` | n/a |
| D7 | **I-03** encadeamento FULL | `run-full` com a admissão default | `FULL_CHAIN_BLOCKED blocked_at=B`; cadeia registra B→C→FULL; sem efeito | n/a |

> **Importante:** D1–D7 são sintéticos. O pacote de autorização de D6 usa **recibos sintéticos do próprio
> titular** (não fabricados por este artefato) apenas para exercitar a rota; como o selo final bloqueia, nenhum
> efeito econômico ocorre. Nenhuma credencial/recibo de produção é criado aqui.

## Salvaguardas
- Prazo e condição de parada por alvo; nenhuma espera infinita não observável (CUSTODY_STATE a cada heartbeat).
- **D4 operacional (término forçado do próprio supervisor) NÃO está autorizado** por este protocolo (não
  confundir com o alvo D4 acima, que é um teste de recibo). Nenhum teste mata processo real sem autorização
  específica e salvaguardas. O supervisor nunca mata por iniciativa própria.
- O pacote de autorização de produção **nunca** pode residir dentro do pacote selado (recusa
  `AUTHORIZATION_BUNDLE_INSIDE_SEALED_PACKAGE_FORBIDDEN`).
- Cada recibo primário retorna hash-bound; nenhum resultado é promovido a PASS sem a observação exigida.

## Retorno
Recibos primários (`*_DIRECTED_R17_*.json`) com SHA-256 dos bytes, identidades e observações. Enquanto a prova
dirigida não for executada, a qualificação nativa das rotas R17 é honestamente **TARGET_RUNTIME_PENDING** —
não se declara READY.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 15`
