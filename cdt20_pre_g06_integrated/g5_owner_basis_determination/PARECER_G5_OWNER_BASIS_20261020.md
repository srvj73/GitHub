# CDT20 — Parecer técnico do implementador sobre `G5_OWNER_BASIS_FINDING`

Papel: implementador revisando a própria engenharia. **Não é B06, não é decisão G5 e não é auditoria normativa.** Nenhum arquivo de política, captura, MASTER/HEAD foi lido, comparado ou hasheado (os campos `policy` do registro histórico não foram usados).

## Veredito

**`NOT_DEFECT` — classificação `INTENTIONAL_SCOPED_CONTRACT` (e, cumulativamente, `NONBLOCKING_FOR_PRE_B06`).** Nenhuma alteração de código. Candidato original preservado: pacote interno `6C952BD9…C064`, transporte `61C0EFFA…3C13`, lançador `E1EB62A4…EB48`, binder `DC6182C9…23AB`.

## Fundamentação física

1. **Semântica do campo.** No fixture histórico imutável (`CDT17_G5_OWNER_R2_SCOPED_IMMUTABLE_REFERENCE.zip`, `3C5A99EF…`), o `README_FIRST.txt` diz: *"The OWNER/RELEASE_AUTHORITY … is the G5 stage issuer per the explicit user declaration in this conversation"*; o `MISSION_LOCK.json` registra `owner_stage_issuer=OWNER_RELEASE_AUTHORITY_USER_DECLARED_NO_EXTERNAL_CERTIFICATE`. A decisão de 16/10 separa dois conceitos em campos distintos: `issuer_basis` (base do **papel** de emissor) e `scope_limit` (`G5_EVIDENCE_STAGE_ONLY_NO_FULL_COMPLETENESS_OR_B06_RELEASE`, alcance **daquela** decisão). Na linha 100 o binder verifica apenas a base do papel, junto com `owner_is_independent_b06_auditor is False` — ambos são atributos de identidade do emissor, não de data ou alcance da decisão.
2. **A decisão de 16/10 não pode ser revinculada aos bytes atuais.** Isso já é barrado por hash, independentemente de `issuer_basis`:
   - o binder (linhas 107–109) exige `code_manifest_sha256`, `final_package_sha256` e `instance_sha256` atuais;
   - o SHA da decisão é fornecido separadamente pelo operador (linha 96);
   - o consumidor final `FULL_G5_COMPLETE_PROOF_GATE.validate_g5_complete_proof` exige decisão vinculada ao código, instância e pacote final atuais e ao retorno nativo (`ORIGIN_DECISION_OLD_OR_WRONG_CODE`, `ORIGIN_DECISION_NATIVE_RETURN_BINDING`), com o comentário explícito *"A historical G5 scoped owner decision is not re-issued for the final package."*
3. **Uma decisão FINAL nova sobre os bytes atuais é exprimível.** Um registro novo (novo `decision_id`, hashes atuais, SHA fornecido separadamente) que cite a base de papel existente é aceito pelo verificador. O que o probe da origem chamou de "aceite do label histórico" é exatamente isso: a base de autoridade do emissor, não uma autorização. A autorização é o próprio registro novo, ancorado pelo pino de segundo canal e pelos vínculos de hash.
4. **A recusa de `…_20261020` é intencional.** Ela impede que um rótulo arbitrário de "base de emissor" seja aceito, o que é controle anti-falsificação de papel (`test_07_owner_basis_required`, que passou nativamente em 29/29 `SUITE_test_b2d_origin_decision_binder.py`). Adotar uma nova base de papel seria um ato de governança do titular/origem, não um defeito de engenharia.
5. **Alcance.** O binder é ponto de entrada manual do operador. Não é invocado pela campanha PRE-G06 nem pela completude; o retorno nativo declara `g5=NOT_ISSUED`. Ele está vinculado por hash no `G5_INTEGRATION_MANIFEST` da evidência FINAL_G5 nativa, de modo que alterá-lo invalidaria a completude 5/5 obtida e exigiria nova campanha.
6. **Proveniência.** O binder `DC6182C9…` é byte-idêntico no pai `40FB01…`: não foi tocado pela integração PRE-G06.

## Prova reprodutível

`g5_owner_basis_probe.py`, executado sobre o binder original, deu 14/14 casos conforme esperado (`G5_OWNER_BASIS_PROBE_RESULT.json`):

| Caso | Resultado |
|---|---|
| Bytes da decisão de 16/10 contra identidades atuais | `DECISION_BINDING:code_manifest_sha256` |
| Registro de 16/10 reeditado com o SHA antigo | `DECISION_SHA256_SUPPLIED_SEPARATELY` |
| Decisão nova atual (base de papel vigente) | aceita pelo verificador puro |
| Mesma decisão com base relabelada para 20/10 | `G5_OWNER_SCOPE_AND_NO_FAKE_INDEPENDENCE` |
| Base ausente; dono alegando independência B06 | `G5_OWNER_SCOPE…` |
| Origem ChatGPT como emissora G5 | `DECISION_SCHEMA_ISSUER` |
| Implementador como emissor | `DECISION_IMPLEMENTER_CANNOT_ISSUE` |
| Decisão REJECT | `ORIGIN_DECISION_REJECT` |
| Pacote 2A52… | `DECISION_BINDING:final_package_sha256` |
| Instância errada | `DECISION_BINDING:instance_sha256` |
| Bloqueador aberto | `DECISION_BLOCKERS` |
| Checks incompletos | `DECISION_CHECKS` |
| Pino SHA errado | `DECISION_SHA256_SUPPLIED_SEPARATELY` |

Os registros usados são sintéticos, nunca gravados como autoridade. Os valores de política são marcadores sintéticos.

## Condições que dependem do titular/origem (não emitidas aqui)

- A emissão de uma decisão G5 FINAL para `6C952BD9…`, se e quando o titular decidir, como registro novo com hashes atuais e SHA entregue por segundo canal.
- Se o titular entender que a designação de 16/10 do papel de emissor G5 **não** se estende a decisões FINAL, isso é decisão normativa da origem. Só nesse caso caberia uma alteração do binder, com nova identidade e nova qualificação nativa, dado o vínculo por hash na evidência FINAL_G5.

## CONTRIBUTION_TO_TICKS21_HANDOFF

- **Estado técnico:** PRE-G06 integrado `PASS_NATIVE_INTEGRATED_PRE_B06` no run `R08_Q1_20261020145036_6735ed63d3a4`.
  - Retorno nativo `9B565CF3…F205`: 38 commits, 479 referências, completude 5/5 `PASS` e quatro achados `PASS_NATIVE_REGRESSION`.
  - `FINAL_ENGINEERING_STATUS.status=EVIDENCE_READY_ORIGIN_G5_NOT_ISSUED`.
- **Hashes vigentes:**

  | Artefato | SHA-256 |
  |---|---|
  | Pacote final | `6C952BD9D0C0B7E13D7B5AD01E1563DA8AFC2FB641262835A0AABBC49778C064` |
  | Manifesto de código | `CC7726742DD5DD72788AC6FD6D4CC1860DB7123F88599188E0A2B559F7FA3ECA` |
  | Instância | `EBCC5F39F627C3AF26532ACBB625B20A829B15F00AA1AF6A6E2269FDE0A375FD` |
  | Transporte | `61C0EFFA358D9CB04E90114CA5A7B544493B4DC5DB2B8E90DDDC6FB72B333C13` |
  | Lançador | `E1EB62A4EFCCEDBBFB9D37322DC616A41A1ADC5E730BB79EAE5D79B3432AEB48` |
  | Binder | `DC6182C9CA339EECCA63EFDEAAC9EDF0FBCBA0F8C762E29B4D7410F2D13F23AB` |

- **Bloqueadores reais restantes**, nenhum de engenharia:
  1. decisão G5 do titular para os bytes atuais (`G5=NOT_ISSUED`);
  2. B06 por auditor realmente independente (`NOT_STARTED`).
- **Fora de escopo:** B07, D4/D5 produtivos, canário e FULL, todos `NOT_STARTED`. Registra-se `NOT_TESTED_PHYSICAL_POWERLOSS`.
- **Não há patch pendente.** O sucessor experimental `DB1C7205…` (ChatGPT) **não** é parent e não deve ser usado.
