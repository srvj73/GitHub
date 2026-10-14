# TICKSTORE CDT15 — Retorno do engenheiro (R44 / B2-G5-01 / B2C / B2D)

**RESULT_RETURN_TO:** ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compressão De Ticks 15
**PAPEL:** ENGINEER_ONLY (produtor candidato). Nenhum gate foi emitido. B06 não realizado. Nenhuma execução produtiva.
**Estado:** G4=INCOMPLETE; G5=NOT_PROVEN; B06=NOT_STARTED; B07=NOT_STARTED; FULL_STARTED=NO; PRODUCTION_MODIFIED=NO.
**Política:** captura R40 do handoff, não autoritativa (MASTER `695DCD64…`, HEAD `B3B41959…`, revisão `20261013T070500-0300-695DCD6495E549B1`). A Biblioteca viva não foi consultada.

## 1. B2-G5-01: corrigido no produtor e no consumidor (SOURCE, com controles negativos)

- **Consumidor** (`candidate/control/FULL_QUALIFICATION_CONTRACT.py`):
  - Quando o contrato exige as seis provas tipadas (contrato real `9AF1C840…`), passa a exigir `delta.native_provenance` e **relê ele mesmo os bytes físicos**:
    - o RETURN ZIP nativo fechado: CRC, membros seguros e únicos, e `RETURN_MANIFEST.json` exato e recursivo;
    - dentro dele, `EVIDENCE/B1_HARNESS/RESULT.json`: 126 registros exatamente uma vez, todos PASS, `success=true`, `totals` iguais a 126/0/0/0, `tested_code_unchanged`, plataforma `Windows*` e Python `MSC`;
    - `TESTS.log`: cada ID uma única vez com `... ok`, `Ran 126 tests` e `OK` final;
    - `QUAL_RECEIPT` V003: precheck nativo PS 5.1, NTFS, elevação e privilégio de symlink, vinculado ao FINAL ZIP e ao manifesto de código;
    - `B1_RESULT` R44 PASS.
  - O FINAL ZIP também é relido: `PACKAGE_MANIFEST` exato e `RUNTIME_CODE_MANIFEST` não vazio, fechado (igual a todos os membros `candidate/`) e com SHA idêntico ao `code_manifest_sha256`.
  - Cada prova precisa de um recibo tipado (`TICKSTORE_G5_TARGET_PROOF_RECEIPT_V001`) que atenda a todos os requisitos abaixo:
    - tenha o `kind` próprio da prova;
    - tenha sido gerado pela função nomeada do executor **empacotado** `g5proof/G5_PROOF_RUNNERS.py`, com SHA conferido no manifesto de código;
    - contenha exatamente as checagens nomeadas da prova, todas PASS;
    - aponte artefatos não vazios dentro de `EVIDENCE/PROOFS/<PROVA>/`;
    - pertença ao mesmo `run_id` e aos mesmos bytes.
  - Evidência reutilizada entre provas é rejeitada, também no modo genérico.
  - `CHECKPOINT_POWERLOSS_RECOVERY` não tem executor aceito: só sai de PENDENTE quando a origem especificar a prova física, e `POWERLOSS_EMULATED` nunca a satisfaz.
  - As fixtures dos 11 IDs `tests_resume_delta.QualificationContract` e dos 22 IDs `TransactionTests` continuam PASS, sem alteração.
- **Produtor** (`G5_EVIDENCE_BUILDER.py`):
  - Constrói somente a partir do RETURN ZIP fechado e do FINAL ZIP, que são copiados para o pacote como `INPUTS/`, e reutiliza as funções do próprio consumidor como fonte única.
  - Entradas JSON soltas (a interface anterior) são analisadas, mas nunca chegam a COMPLETE.
  - Nunca emite PASS de gate; o rascunho G5 permanece `PENDING_ORIGIN_DECISION`.
- **Controles:**
  - `tests/test_g5_evidence_builder.py` tem **34/34 PASS**.
  - Cada condição adversarial da origem bloqueia o produtor **e** o consumidor: manifesto vazio, 127 registros, `success=false`, `tests_run=0`, plataforma só declarada, mesmo recibo nas seis provas, recibo genérico, artefato ausente, executor não empacotado, outro run, ZIP adulterado, membro fora do manifesto, log incompleto e não elevado.
  - O reprodutor da origem, byte a byte (`1AB62404…`), agora resulta em `INCOMPLETE/REJECTS` com bloqueios explícitos.
  - O produtor aplicado ao RETURN do R43 rejeita, e aplicado a um RETURN offline do R44 rejeita com bloqueios granulares.

## 2. R44: runner nativo para o titular (não executado aqui)

- `RUN_TICKSTORE_CDT15_R44_QUAL.ps1`:
  - Na **primeira** execução não elevada, abre a si mesmo como Administrador (UAC) e encerra com código 3; a janela elevada é a que executa a qualificação.
  - O driver bloqueia se não houver elevação ou se o privilégio de symlink falhar (R43-E1).
- Execução, sempre sobre os bytes extraídos do FINAL `TICKSTORE_FULL_FINAL_CDT15_R44_20261014.zip`:
  - S8 (34) e S9 (3);
  - os **126 IDs** com as sobreposições aprovadas B1A (`29981D15…`) e B1B (`2E95CADE…`, patch `84E32FA3…`), mais as microprobes B1A (5);
  - as provas tipadas em sandbox:
    - árvore de processos (TerminateProcess do coordenador com filho e neto no Job);
    - SAFE_STOP com retomada em **row group** real: um dia de 1.100.000 linhas (5 grupos de 262.144), STOP nomeado vindo de outro processo durante BUILDING e retomada com outro número de workers; contêineres byte a byte iguais aos de um build de controle sem interrupção;
    - instalação PS 5.1 inativa, sem ativar o MENU oficial;
    - fechamento D4 sintético com **1399** entradas em NTFS, com controles de entrada ausente ou adulterada;
    - cadeia Stage B sintética (49 testes, leitura nativa protegida);
  - `POWERLOSS_EMULATED` em separado: mortes abruptas da árvore em instantes semeados, reinício *fail-closed* (`WRITER_LOCK_EXISTS`), reconciliação no sandbox e recuperação do produto até contêineres iguais aos do controle. Isso **não** é queda física de energia.
- Ao final, o driver relê os bytes extraídos e gera um RETURN ZIP fechado com `RETURN_MANIFEST.json` recursivo e verificação de leitura (*readback*).
- Preflight offline (POSIX) do pacote: cadeia completa, B1 portátil 106/106 e microprobes 5/5. As provas offline nunca valem PASS.

## 3. R44-B2C (SOURCE_ONLY, fora dos bytes R44): `b2c/`

- `POLICY_CAPTURE_BINDING.py`:
  - Identidade derivada dos bytes da captura: cardinalidade 1+1; HEAD vincula MASTER; estado FROZEN; revisão estruturalmente ligada ao SHA do MASTER; escopo TICKSTORE.
  - V37 e V38 aparecem **apenas** como proveniência histórica e são rejeitados como atuais.
  - Além disso, exige um **registro de reconciliação emitido pela origem** (`TICKSTORE_ORIGIN_POLICY_RECONCILIATION_V001`), cujo SHA é fornecido separadamente, com validade máxima de 72 h.
  - Não há nenhum literal da revisão R40: uma mudança legítima futura da Biblioteca é aceita sem alterar o código, mediante nova reconciliação.
- TRANSACTION, PREP, BOOTSTRAP, FULL_STAGE_CONTINUATION, FULL_INSTANCE_PREPARE, FULL_RUNNER, RUN_TICKSTORE_FULL e o wrapper efetivo passaram a consumir a captura verificada. Cada estágio com efeito exige a reconciliação **vigente**, e há verificação de drift durante a admissão.
- **Achado:** o motor congelado (`RELEASE_SHA BFC44DA9…`, `POLICY_ADMISSION_SCOPE`) exige, no recibo de política, `project=PEGASUS_TICKSTORE` e `thread=Compressão De Ticks 7`. Esses campos foram mantidos como *proveniência/ABI*; o roteamento atual foi para `routing_project`/`routing_thread` da reconciliação.
- **OWNER_GATE:**
  - O caminho FULL atual não consome aprovação administrativa.
  - `RECOVERY_OWNER_GATE_V004` é descritor/ABI calculado por código.
  - Foram **revogados** os caminhos legados vivos `tickstore_serial_runner --mode FULL_SERIAL`, `--pilot-date`/`--pilot-gate-file` e `--full-history`, que consumiam um gate humano.
  - Foram removidos do wrapper o caminho e o SHA do gate histórico de 20260930.
- Testes: `b2c/tests` tem 19/19 PASS.
- **Impacto contratual** (`B2C_CONTRACT_IMPACT.json`):
  - Sem derivação de fixture, 38 dos 106 IDs portáteis falham, porque as fixtures referenciam `T.POLICY_*`, `P.MASTER_SHA` e `B.policy_v38`.
  - Com a derivação proposta (`proposed_contract_fixture/*.patch`), o resultado é **106/106 PASS**.
  - **Decisão da origem necessária:** aprovar ou rejeitar, byte a byte, as duas derivações. Enquanto isso, o B2C permanece fora dos bytes qualificados.

## 4. R44-B2D (SOURCE_ONLY): `b2d/`

- `ORIGIN_DECISION_BINDER.py`:
  - Materializa `TICKSTORE_STAGE_RECEIPT_V001` para G5 ou B07 **somente** a partir de `TICKSTORE_ORIGIN_STAGE_DECISION_V001`, cujo emissor é `CHATGPT_ORIGIN` e cujo SHA é fornecido separadamente.
  - Verifica decisão PASS e todos os vínculos: estágio, política e reconciliação, manifesto de código, pacote FINAL, instância, evidências relidas e conferidas semanticamente, *blockers* vazios, cadeia de predecessores e, em B07, o B06 independente.
  - Não sobrescreve recibos existentes (*no-clobber*).
  - Nunca decide, não cria OWNER_GATE e recusa implementador como emissor.
- Testes: 11/11 PASS. Os recibos produzidos são validados pelo `FULL_RELEASE_CHAIN.validate_chain` sem modificação.

## 5. Pendências e pedidos à origem

1. O titular deve executar o R44 elevado e devolver o RETURN ZIP. O engenheiro então roda o produtor G5 sobre esse RETURN e esse FINAL e entrega o pacote; o resultado continuará INCOMPLETE enquanto houver o item 2.
2. `CHECKPOINT_POWERLOSS_RECOVERY`: especificação da prova física (mídia sacrificial) ou deliberação formal. Não há proxy unilateral.
3. B2C: decisão sobre as duas derivações de fixture contratual.
4. Produtor técnico do recibo B07 (10 checks): ainda não iniciado, em SOURCE_ONLY; a execução só ocorre após B06 independente PASS.
