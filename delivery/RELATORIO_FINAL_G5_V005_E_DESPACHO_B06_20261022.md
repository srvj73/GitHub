# CDT21 — G5 nativo do V005 verificado e despacho B06 pronto (2026-10-22)

**Papel:** implementador, não B06. **Retorno:** ChatGPT, projeto Base de Dados CSV / Tickstore, conversa Compressão De Ticks 21.

## 1. Resultado

A campanha G5 nativa do V005 foi executada pelo titular com o P1 e verificada fisicamente pelo Opus com o P3. Resultado: **`PASS_NATIVE_V005_G5_TECHNICAL_FIVE_PART`**.

| Item | Valor |
|---|---|
| Candidato | `CDT21_FINAL_PACKAGE_V005_20261022.zip` `E3F1F4790D6AE6E5639F137FAEE3E91B2B8E6FFB51A95F18078DF734553CB145` |
| Código runtime | `63CBA7065A719CBCF58F1EB1F088D090B87AE7ABBAF37BE03856619CE1D0D74E` |
| Retorno nativo (original do Windows) | `ENVIAR_AO_OPUS_CDT21_G5_V005_20261022_063004_747_43284.zip` `AB0E34CFA12212B9E333D1618429A9336AE778567B0486CDC765CDD88696B07C` (56.901.872 bytes; recebido em 3 partes e remontado byte a byte) |
| `R08_RETURN.zip` | `F7E5E879395768ECE664D1FF757FABBCE74D622B928D85943814B53A5898089A` (run `R08_Q1_20261022063029_348b83753194`, 711,7 s) |
| Completude de engenharia (Windows) | `8BA377D498DF904536C8C295B0DB6C28BF74F461D6F386DE1E94F2631D6FFB95` |

## 2. O que a verificação física comprovou (32/32, com o código congelado do V005)

**Supervisor e campanha**
- O supervisor `363D1654…` e a revisão `CA8E5252…` são exatamente os entregues.
- Campanha nova: **38 COMMITs novos, 0 reutilizados**, nenhum do V003, do V004 ou de outra campanha.
- Nenhum processo órfão ao final.

**Código congelado**
- `verify_final_zip` confirmou o código.
- `verify_native_campaign` retornou `PASS_NATIVE_INTEGRATED_PRE_B06`, com 31 papéis.
- Os 38 COMMITs estão fechados, vinculados ao V005 e com artefatos físicos.
- Não há tentativas interrompidas.

**Proveniência (lógica R4)**
- Livro-razão 38/38 com base `OBSERVED_COMMITTED_LINE`; nenhuma reconciliação foi necessária.
- Diário com uma única tentativa deste supervisor.
- Censo do Job em 38 unidades, cada uma listando o dono do seu COMMIT.

**Delta V005 em execução nativa**
- Os 7 testes de regressão constam como `ok` nos logs nativos: `test_v005_01` a `05` e os `test_06`/`test_07` do recibo D4.

**Cinco partes**
- Todas PASS e fisicamente presentes no retorno.
- Os quatro achados pré-B06: `PASS_NATIVE_REGRESSION`.
- A reexecução de `PRE_G06_COMPLETENESS.close` no Linux reproduziu exatamente o fechamento do Windows.

**Efeitos**
- `D:\Base CSV`: impressão digital idêntica antes, depois e após o fechamento.
- As 26 raízes preexistentes ficaram inalteradas; foram acrescentadas somente as 2 raízes próprias.
- Fase Q desta execução: 19/19, com o censo do Job nativo enxergando o filho aninhado.

**Controles negativos do verificador: 5/5 recusados.** Mesmo com os hashes externos recalculados pelo atacante, foram recusados:
- o candidato trocado pelo V004;
- o COMMIT adulterado;
- o log nativo com `ok`→`FAIL` (recusado pelo gate congelado);
- a prova de cinco partes forjada;
- o COMMIT revinculado ao V004.

**Divulgações:**
- **Unidade diagnóstica pulada:** `DELTA_test_cdt19_r06_integrated_contract.py` (16 testes). O contrato congelado só permite isso em extra diagnóstica, e os `REQUIRED_DELTA` não foram pulados.
- **ZIP sucessor do D4 ausente em `D:`:** é o estado esperado antes da migração 8b. A fonte do arquivo `8A05E761…` deve ser confirmada antes da 8b.
- **`D:\Base CSV`:** `MENU.py` e o `.bat` constam ausentes, como já registrado no incidente em diagnóstico com o titular. Não decorre da campanha.
- **Execuções:** uma primeira execução rodou só a Fase Q (sem `-AutorizoLabD`, PASS 19/19). A campanha veio na segunda execução.

## 3. Despacho B06 (pronto para a origem; o implementador não despacha nem audita)

`CDT21_V005_B06_INDEPENDENT_DISPATCH_READY.zip`: SHA-256 `C43805B8D6187449458897C9B01EC34806407850BBECFF3A7CA8913734C09ED0`, 97.959.775 bytes, 37 membros. O pacote contém:
- o candidato;
- o retorno nativo original e a execução só com a Fase Q;
- o pacote FULL de engenharia;
- o histórico dos pais (G0 do V003 e do V004);
- as ferramentas de verificação;
- o recibo, a matriz, o checklist das cinco partes e as instruções ao auditor independente.

**Transporte em 4 partes**, cada uma menor que 30 MB, com `RECONSTRUIR_PACOTE_B06_V005.py` (`B55ABA2E…`). A reconstrução foi testada (`PASS_BYTES_EXACT`, 36 membros conferidos) e recusa a falta de uma parte.

| Parte | SHA-256 |
|---|---|
| `CDT21_V005_B06_DISPATCH_PARTE_01_DE_04.zip` | `DA0B8598258A2F766D64439AF7B2B097CEC7155089D778F89D979FA7A9B37772` |
| `CDT21_V005_B06_DISPATCH_PARTE_02_DE_04.zip` | `3B061C0C162A3279ABA8225E2F8506A8D174BF54E0D8771658644616C5CCCFB9` |
| `CDT21_V005_B06_DISPATCH_PARTE_03_DE_04.zip` | `E0F62087892FE3908D7258247E08E88862886D936355DF1CE0CF2A9B4C90DF57` |
| `CDT21_V005_B06_DISPATCH_PARTE_04_DE_04.zip` | `A4B083BA44EA0767A1D6AAC09FA1EA80BF1E85E6A94103135B09077833CBBD36` |

## 4. Estado dos gates após este recibo

| Gate | Estado |
|---|---|
| G5 técnico nativo do V005 | **PASS_NATIVE_V005_G5_TECHNICAL_FIVE_PART** (recibo do implementador) |
| Decisão G5 e recibo de estágio G5 | NOT_ISSUED (origem) |
| B06 | NOT_STARTED. A origem revalida a política, emite `INDEPENDENCE_PRE_DISPATCH` e despacha ao Work independente |
| B07, D4, D5, canário, FULL_PREP, FULL_ADMISSION, FULL | NOT_STARTED. Pré-requisitos e entradas reservadas estão no P4 e em `09_ESTADO_DOS_GATES.json` do pacote FULL |
| Queda física de energia | NOT_TESTED_PHYSICAL_POWERLOSS |

O veredito B06 deve usar exatamente `implementation_v001/procedures/TEMPLATE_B06_VERDICT.txt`: cabeçalho único e as chaves listadas. A B07 e o motor D4 leem o mesmo arquivo.
