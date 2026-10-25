# Auditoria interna — V008R18 (conclusão de engenharia do I-03)

Continuação da **mesma engenharia** (não nova auditoria, não novo marco). Resposta ao parecer de
retomada sobre a R17, que apontou dois fatos técnicos corretos:

1. A rama econômica B→C→FULL do R17 estava apenas **sintaticamente encadeada**: `ProductionReleaseAdmission.admit` terminava sempre em `entry.release_admission(...)` + `raise SupervisorBlocked`, e `_run_supervised` recusava `plan['economic']` incondicionalmente. A rama econômica não era **atingível**.
2. `production_admission_verdict` fazia **prova sintática** — aceitava um gate com SHA hexadecimal de 64 e `status=PASS` sem ler/re-hashear o arquivo físico apontado, sem proveniência e integridade.

A R18 conclui o I-03 fechando os dois pontos e **classificando honestamente** o que resta como decisão reservada. Nenhum núcleo econômico V003, census ou G4 foi tocado; R17 (I-01/I-02), R16 (N1/N2/N3), R15 (A01–A04/INT), F01–F04, R11/R12/R13-ORIGIN e R9 (23/23 MET) preservados. **Nenhuma execução econômica foi iniciada; nenhum gate foi liberado.**

## I-03A — prova FÍSICA dos gates

`production_admission_verdict(bundle, *, phase, bundle_root)` agora **lê e re-hasheia** o arquivo de cada gate técnico sob `bundle_root` (fora do pacote selado). `verify_gate_file` confere o SHA real do conteúdo, a existência, o tipo (arquivo regular), a **proveniência** (`release_id` do gate == do bundle) e o `status=PASS`; `_safe_under` resolve o caminho **sem** seguir aliases/reparse e recusa escape (`..`), caminho absoluto e resolução fora do bundle. Negativos fechados (com teste): SHA inventado, arquivo ausente, status falso, mismatch, reparse/alias, **stale** (release_id divergente), fase fora de ordem, **manipulação concorrente** (o re-hash no momento da verificação difere do SHA declarado) e bundle dentro do ZIP.

## I-03B — rota externamente autorizável REAL + decisão reservada

`release_admission_signal` **lê o sinal** do `release_admission` congelado do V003 **sem burlá-lo**:

- `G00_RUN_RELEASE_DISABLED` (RELEASE_STATE != RUN_RELEASED — o caso do artefato congelado, e virar isso dentro do pacote selado seria **forjar**, proibido) ⇒ **`RESERVED_OWNER_RELEASE_DECISION`**: a liberação legítima exige uma **nova decisão do titular**, não é erro de código e não se resolve renomeando recibo ou instalando flag.
- `G00_EXTERNAL_RELEASE_ADMISSION_NOT_INSTALLED` (com RUN_RELEASED, por **desenho** do V003: "a reviewed release must supply its separately authorized, physically bound admission module") ⇒ o supervisor carrega o **módulo de admissão externo** autorizado, **fisicamente vinculado por SHA** (`load_external_admission_module`), e delega-lhe a admissão, que devolve o RunPlan econômico com o **recibo de release**.

`_run_supervised` passou a **executar** um plano econômico — porém **só** com um `release_admission_receipt` concedido (`granted=True`), e com `economic_plan_isolation_verdict` validando a espécie. `make_run_plan` recusa um plano econômico sem esse recibo. Nada é forjado; nenhum bypass de `release_admission`; QS4/Phase B/C não antecipados; nenhum Owner Gate.

**Prova da reserva (arquitetural).** O entry V003 congelado (`F77B5266…`) levanta `G00_RUN_RELEASE_DISABLED` enquanto `RELEASE_STATE=QUALIFICATION_ONLY` e, mesmo com `RUN_RELEASED`, exige um módulo de admissão externo separadamente autorizado e fisicamente vinculado — **inexistente** neste artefato e que **não pode ser fabricado** sem decisão do titular. Logo a execução econômica real **não é alcançável** aqui: é uma **decisão reservada**, e assim é declarada (`cmd_run`/`cmd_run_full` devolvem `RESERVED_OWNER_RELEASE_DECISION`).

## I-03C — E2E SINTÉTICO isolado (sem efeito econômico)

Com uma fixture **sintética** (um entry que sinaliza `DEFER`, um módulo externo sintético vinculado por SHA e um runtime sintético), a admissão positiva **condicional** é demonstrada de ponta a ponta: o módulo externo produz um RunPlan econômico de espécie `SYNTHETIC_ISOLATED` e `_run_supervised` o **executa sob supervisão plena** (W04/Job/SAFE_STOP/recibo) **sem tocar o V003 real**. `economic_plan_isolation_verdict` garante que a espécie `SYNTHETIC_ISOLATED` nunca aponte `CODE/` nem módulos econômicos reais. **Uma admissão positiva simulada nunca é confundida com release real de V003.**

## Evidência

`receipts/V008/offline_final/r18_origin_fixes/` (`ORIGIN_FIXES_CLOSURE_V008R18.json`, `all_closed=true`: I-03A, I-03B, I-03C, PRIOR_PRESERVED; `FALSE_COMPLETENESS_SEARCH_V008R18.json` = `NO_MANDATORY_ENGINEERING_INTEGRATION_UNIMPLEMENTED_REAL_RELEASE_RESERVED_TO_OWNER`). Regressões `R18ProductionAdmissionPhysicalGates`, `R18ReservedOwnerReleaseDecision`, `R18ExternalRouteSyntheticE2E` falham na R17 congelada (prova apenas sintática; rama não atingível) e PASS nos bytes R18. A efetividade Win32 das rotas fica na qualificação dirigida (processos sintéticos; **D4 não autorizado**): `TARGET_RUNTIME_PENDING`.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 15`
