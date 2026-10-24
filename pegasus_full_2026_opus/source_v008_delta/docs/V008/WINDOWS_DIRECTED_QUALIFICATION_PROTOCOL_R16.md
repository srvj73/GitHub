# Protocolo de qualificação dirigida Windows — V008R16 (rotas N1/N2/N3, processos sintéticos)

Prova nativa, no PC do titular, das propriedades das **rotas efetivamente modificadas na R16** que não
podem ser demonstradas em sandbox POSIX. Processos **exclusivamente sintéticos**, hash-bound, sem instalação
produtiva, sem economia, **sem kill não autorizado**. Complementa (não substitui) a campanha R9 (23/23, MET)
preservada e os controles negativos offline. O Opus coordena diretamente com o titular.

## Pré-condições
- `-Mode Verify` do bootstrap R16 PASS (identidade do pacote e dos pais conferida).
- Python fixado (SHA conferido pelo bootstrap). Elevação só onde o USN exige; nenhum efeito fora do diretório
  sintético de trabalho.

## Alvos (cada um com árvore sintética própria, curta, controlada)

| # | Propriedade (invariante R16) | Processo sintético | Observação esperada | NO_KILL |
|---|---|---|---|---|
| E1 | **N1** efeitos pós-resume | neto que retoma ≥1 thread e sai rápido com código ≠0 | `effects_started=True`; FAIL exit 3 (nunca BLOCKED exit 2); histórico de efeitos | sim |
| E2 | **N1** sem efeito provado | criação suspensa com Assign/Resume falho antes da 1ª thread | rollback do próprio suspenso; exit 2 sem efeito | término só do suspenso próprio |
| E3 | **N2** fechamento recusado | árvore viva no instante do `close()` | `close()` prova `closed=False`/`active>0`; handles RETIDOS; sem `CUSTODIAN_CLOSED`; hold observável | sim |
| E4 | **N2** fechamento provado | árvore drenada antes do `close()` | `close()` prova `closed=True, active=0`; `CUSTODIAN_CLOSED`; W04 disarm só então | sim |
| E5 | **N3** recibo canônico falho | diretório de evidência somente-leitura | exit 3 e `result=FAIL…`; recibo fallback coerente; banner = mesmo desfecho | n/a |
| E6 | **N3** emissão de resumo falha | stdout fechado/redirecionado para falhar | exit preservado; sem crash; aviso em stderr | n/a |

## Salvaguardas
- Prazo e condição de parada por alvo; nenhuma espera infinita não observável (CUSTODY_STATE a cada heartbeat).
- **D4 (término forçado do próprio supervisor) NÃO está autorizado** por este protocolo. Nenhum teste mata
  processo real sem autorização específica e salvaguardas. O supervisor nunca mata por iniciativa própria.
- Cada recibo primário retorna hash-bound; nenhum resultado é promovido a PASS sem a observação exigida.

## Retorno
Recibos primários (`*_DIRECTED_R16_*.json`) com SHA-256 dos bytes, identidades e observações. Enquanto a prova
dirigida não for executada, a qualificação nativa das rotas R16 é honestamente **TARGET_RUNTIME_PENDING** —
não se declara READY.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
