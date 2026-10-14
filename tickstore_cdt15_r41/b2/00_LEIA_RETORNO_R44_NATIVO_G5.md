# TICKSTORE CDT15 — Retorno nativo R44 e pacote de evidência G5 (engenheiro)

**RESULT_RETURN_TO:** ChatGPT | PROJECT=Base de Dados CSV / Tickstore | THREAD=Compressão De Ticks 15
**PAPEL:** ENGINEER_ONLY. Nenhum gate emitido; B06 não realizado; nenhuma execução produtiva.
**Estado:** G4=INCOMPLETE; G5=NOT_PROVEN; B06=NOT_STARTED; B07=NOT_STARTED; FULL_STARTED=NO; PRODUCTION_MODIFIED=NO.
**Complementa:** `TICKSTORE_CDT15_R44_B2_RETORNO_ORIGEM_20261014.zip` (SHA-256 `BF87A341CD0DAFECDA6F11EFDCA6A14E219DD6282271254DB2C6F05B7B5FB22D`).

## 1. Execução nativa do titular (Windows 11, PS 5.1.26100.9444, Python 3.14.7 fixado, elevado)

- RUN `R44_QUAL_20261014_065214_300_41492`, `CLASSIFICATION=R44_WINDOWS_SANDBOX_QUALIFICATION_PASS`, `EXIT_CODE=0`, `PRODUCTION_MODIFIED=FALSE`.
- RETURN ZIP `02036B1EA45370BE570865E281F8F5FC4C5D1C5364171680E2EE493EC7C5BB6D`, 48 membros, `RETURN_READBACK=PASS`. O SHA recalculado aqui coincide com o do log.
- FINAL `0FBB6C36B840F2EF228DB3B160AA50D733FE5293C80BB4060AFFD4C074F8A48D`; manifesto de código com 133 arquivos.
- Precheck: `ELEVATED=YES` e `SYMLINK_PRIVILEGE=PASS`. A causa do R43-E1 foi fechada.

| Item | Resultado |
|---|---|
| S8 produtor/consumidor G5 | 34/34 |
| S9 contrato executor↔consumidor | 3/3 |
| **126 IDs contratuais** (B1A + B1B aprovados) | **126/126 PASS**, microprobes 5/5 |
| PROCESS_TREE_CRASH_CONTAINMENT | PASS: filho e neto no Job; contenção em 0,004 s após TerminateProcess do coordenador |
| SAFE_STOP_RESUME_ROW_GROUP | PASS: dia de 5 grupos; STOP nomeado de outro processo com 2 grupos duráveis; retomada de 1 para 2 workers (REUSED=2, RESUMED=2); contêineres byte a byte iguais ao controle |
| PS51_INSTALL_MENU | PASS: instalação inativa, readback, ativação sem cadeia bloqueada, MENU oficial intocado, writer em layout QUALIFICATION com crash e recuperação |
| D4_CLOSURE_NATIVE_1399 | PASS: 1399 entradas, `ALL_CHUNKS_COMMITTED`, leitura Win32Store em NTFS; entrada ausente, espelho ausente e recibo adulterado bloquearam |
| STAGE_B_FULL_CHAIN_NATIVE | PASS: 49/49, sem skips |
| POWERLOSS_EMULATED (separado) | EMULATED_PASS: 5 mortes abruptas (duas no meio da publicação canônica), reinício fail-closed, recuperação com contêineres iguais. **Não é prova física.** |

## 2. Produtor G5 sobre os bytes nativos devolvidos

`G5_EVIDENCE_BUILDER` foi aplicado ao RETURN ZIP fechado e ao FINAL ZIP. A saída está em `G5_EVIDENCE_PACK/`, que contém `INPUTS/` com os bytes e `PROOF_RECEIPTS/`.

- `provenance_mode=CLOSED_NATIVE_RETURN_ZIP`; `windows_qualification=PASS`; `delta_test_totals` 126/0/0/0; `tested_code_equals_packaged_code=PASS`.
- As cinco provas factíveis estão PASS, cada uma com recibo tipado do executor empacotado e SHA conferido no manifesto de código.
- **`ENGINEERING_COMPLETENESS.status=INCOMPLETE`**, com **um único** bloqueio: `CHECKPOINT_POWERLOSS_RECOVERY:PHYSICAL_PROOF_NOT_SPECIFIED_BY_ORIGIN`.
- O consumidor retorna `REJECTS`, e o rascunho G5 permanece `PENDING_ORIGIN_DECISION`.
- Reverificação independente: o consumidor releu o pacote **realocado**, com os caminhos absolutos originais invalidados, e encontrou apenas o mesmo bloqueio (`CONSUMER_RECHECK.txt`).

## 3. Decisões necessárias da origem (nenhuma tomada pelo engenheiro)

1. **CHECKPOINT_POWERLOSS_RECOVERY:** especificar o experimento físico seguro em mídia sacrificial, ou deliberar formalmente sobre a prova, sem relaxar a política. Enquanto isso, G5 não pode fechar.
2. **R44-B2C:** aprovar ou rejeitar, byte a byte, as duas derivações de fixture contratual (ver o pacote B2).
3. Após G5 (decisão da origem materializada pelo B2D) vem o B06 independente. O produtor técnico B07 (SOURCE_ONLY) será implementado a seguir, e sua execução só ocorre após B06 PASS.
