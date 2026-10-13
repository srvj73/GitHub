# CDT15 G4 — Critical section unificada, SOURCE_ONLY

O parent é `TICKSTORE_CDT15_G4_INSTALLER_LEGACY_ACTIVATION_PRUNE_SOURCE_ONLY_20261013.zip`.
Este delta **não altera o instalador, MENU nem os componentes históricos**.

Foi adicionada uma API de engenharia `locked_stage_commit_sandbox()` exclusivamente
para `CDT15_G4_TXN_SANDBOX_INTENT` com sentinela físico. O mesmo lock do kernel
permanece adquirido da verificação de `MENU_INSTALL_INTENT.json` até a confirmação
`COMMITTED` e readback do MENU/deployment. Se houver erro, conserva journal, locks
e evidência para recuperação explícita `locked_reconcile`; nunca cria successor cego.

O módulo não possui CLI nem destino instalável. Não concede autoridade effectful,
não substitui o MENU oficial, não prova ACL/TOCTOU de produção nem durabilidade
por perda de energia. Os resultados locais qualificam apenas fixtures isoladas.

Não encaminhar para auditoria formal; `G4=INCOMPLETE`, `G5=NOT_PROVEN`,
`B06=BLOCKED_INCOMPLETE`, `FULL_STARTED=NO`.

O launcher de diagnóstico Windows executa apenas 18 casos novos, com lock real
entre processos e diretórios temporários. Não repete o conjunto anterior de 17
casos já aprovado.
