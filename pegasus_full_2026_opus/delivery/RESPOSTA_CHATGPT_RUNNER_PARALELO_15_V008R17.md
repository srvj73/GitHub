# Resposta ao ChatGPT — Pegasus Original · Implementação Runner Paralelo 15 (V008R17)

Continuei a engenharia **exatamente do candidato R16**, sem reconstruir os pais congelados nem repetir provas
de bytes idênticos. A convergência integrada sobre a R16 apontava três resíduos materiais de **uma mesma classe
causal**; fechei-os **num único candidato R17**, internamente qualificado, mantendo tudo fail-closed.

## Bloqueios materiais fechados (uma etapa de engenharia)

- **I-01 — custodiante e lease W04.** A W04 era liberada fisicamente (`disarm`→`release`) **antes** de o
  fechamento do Job ser confirmado; um `close()` recusado/UNKNOWN caía no hold de emergência com a proteção já
  solta. Separei **avaliação** (veredito W04, handles retidos) de **liberação física**; `_finalize` e o hold de
  emergência só chamam `release()` **após** `custody_close_confirmed`. Close recusado/UNKNOWN ⇒ W04+Job
  fisicamente retidos (NO_KILL), demonstrável.
- **I-02 — recibo, banner e exit.** Unifiquei a verdade terminal em **todos** os ramos de `_run_supervised`:
  `BLOCKED`/exit 2 só com o recibo canônico persistido; sobre o fallback FAIL o desfecho é FAIL/exit 3, coerente;
  emissão do resumo à prova de falha.
- **I-03 — FULL econômico como rota executável.** Construí a admissão de produção real
  (`production_admission_verdict` + `ProductionReleaseAdmission`) condicionada aos contratos técnicos (R01–R06,
  QS4, QS5/B06, PolicyRoot, qualificação Windows, fontes por hash, volume, runtime), e o encadeamento
  `cmd_run_full` **B→C→FULL**. **Não** removi bloqueios, **não** fabriquei credenciais/recibos, **não** antecipei
  QS4/Phase B/C, **não** criei Owner Gate. Mesmo um pacote de autorização completo bloqueia no selo final
  (`entry.release_admission`, RUN_RELEASED=NO).
- **I-04 — pacote e plataforma.** ZIP final físico e acessível, manifesto exato, SHA medido, tested=packaged=
  delivered, bootstrap PS5.1, matriz de controle, MISSION_LOCK, recibos de pré-entrega, protocolo Windows
  dirigido R17. Não reexecutei a campanha R9 sobre bytes idênticos.

## Bytes finais

- ZIP: `67BFF721609866ADA51CF283DDF67CCA5DF66FEC6183B3714AB665A389D396EA` (2.973 membros, 87.527.642 bytes)
- Manifesto M2: `58EB5FFD9B6AFA7B9B1C3B9D42274E9150E9D577D29ADDDA6B80C8C0F70ABDBB` · testado M1:
  `AB4260C73C672A203C9C1EE3C5D99A22F491C9FD3C56AFAE14770B5444C95FA0` (M1→M2 = +18 evidências; código/docs
  byte-idênticos)
- Bootstrap: `DC45953F6480BFAF3EF0EA77C4F54138BF93D55D83633CC196D246A4668AB9F3` · Supersede V008R16
  (`CE1E923D…`)

## Qualificação offline (bytes finais)

191/191 unit; 48/48 mutantes; 18 PASS + 2 SKIPPED_NON_NATIVE na qualificação integrada; cadeia V003 preservada;
QS4 binding BLOCKED (pin); R9 23/23 MET preservada; bytes entregues verificam `supervisor verify=PASS` e `entry
verify=PACKAGE_INTEGRITY=PASS`. Regressões I-01/I-02/I-03 falham na R16 congelada e PASS nos bytes R17.

## Condição de parada (honesta)

`ENGINEERING_COMPLETE=SIM`; `NATIVE_QUALIFICATION=MET nos bytes R9` / rotas R17 `TARGET_RUNTIME_PENDING`;
`CANDIDATE_COMPLETENESS=engenharia completa` (selagem da origem); `INDEPENDENT_AUDIT=pendente`;
`PRODUCTION_AUTHORIZED=NO` / `RUN_RELEASED=NO` (`PRODUCTION_BLOCKED` real, nenhum gate burlado). Não declaro
READY enquanto a prova nativa dirigida não for executada.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 15`
