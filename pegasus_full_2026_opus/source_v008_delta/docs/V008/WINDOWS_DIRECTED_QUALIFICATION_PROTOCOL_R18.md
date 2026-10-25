# Protocolo de qualificação dirigida Windows — V008R18 (rota I-03, processos sintéticos)

Prova nativa, no PC do titular, das propriedades da rota de admissão de produção concluída na R18 que
não podem ser demonstradas em sandbox POSIX. Processos **exclusivamente sintéticos**, hash-bound, sem
instalação produtiva, **sem economia**, **sem kill não autorizado**. Complementa (não substitui) a
campanha R9 (23/23, MET) preservada, e os protocolos dirigidos R16/R17. **D4 não autorizado.**

## Pré-condições
- `-Mode Verify` do bootstrap R18 PASS (identidade do pacote e dos pais conferida).
- Python fixado (SHA pelo bootstrap). Nenhum efeito fora do diretório sintético de trabalho.

## Alvos (cada um com árvore/bundle sintético próprio, isolado)

| # | Propriedade (invariante R18) | Fixture sintético | Observação esperada | NO_KILL |
|---|---|---|---|---|
| P1 | **I-03A** prova física dos gates | bundle externo com arquivos de gate reais | `ADMITTED_GATES_PHYSICALLY_VERIFIED` (re-hash bate) | n/a |
| P2 | **I-03A** negativos físicos | SHA inventado / arquivo ausente / status falso / mismatch / stale / reparse / escape / mutação concorrente | `BLOCKED` com a causa exata; nenhum gate promovido | n/a |
| P3 | **I-03B** decisão reservada | entry congelado real (`RELEASE_STATE=QUALIFICATION_ONLY`) | `RESERVED_OWNER_RELEASE_DECISION`; execução econômica real **não** alcançada | n/a |
| P4 | **I-03B** módulo externo | pacote com `external_admission_module` cujo SHA **não** bate | `EXTERNAL_ADMISSION_MODULE_IDENTITY_MISMATCH` | n/a |
| P5 | **I-03C** E2E sintético | entry-fixture que sinaliza `DEFER` + módulo externo sintético SHA-bound + runtime sintético | admissão positiva condicional; `_run_supervised` executa o plano `SYNTHETIC_ISOLATED` sob supervisão; **sem economia**, nunca aponta `CODE/` | sim |
| P6 | **I-03C** isolamento de espécie | plano `SYNTHETIC_ISOLATED` cujo argv tente apontar `CODE/` | `ECONOMIC_RUN_PLAN_NOT_ISOLATED` | n/a |

> **Importante.** P5 é **sintético e isolado**: o entry-fixture, o módulo externo e o runtime são
> sintéticos; o V003 real **não** é tocado. Uma admissão positiva simulada **não** é um release real.
> Para o artefato congelado real, o resultado correto é **P3** (decisão reservada). Nenhuma credencial,
> recibo de release ou `RUN_RELEASED` é fabricado.

## Salvaguardas
- O pacote de autorização e o módulo externo **nunca** podem residir dentro do pacote selado.
- **D4 operacional (término forçado do próprio supervisor) NÃO autorizado.** O supervisor nunca mata.
- Cada recibo primário retorna hash-bound; nenhum resultado é promovido a PASS sem a observação exigida.

## Retorno
Recibos primários (`*_DIRECTED_R18_*.json`) com SHA-256 dos bytes, identidades e observações. Enquanto a
prova dirigida não for executada, a qualificação nativa da rota R18 é honestamente
**TARGET_RUNTIME_PENDING** — e a execução econômica real permanece **decisão reservada do titular**.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 15`
