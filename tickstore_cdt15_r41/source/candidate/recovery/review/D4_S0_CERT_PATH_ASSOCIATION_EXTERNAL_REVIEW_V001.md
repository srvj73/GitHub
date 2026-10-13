ASTRA_D4_CODE_DELTA_REVIEW=PASS
SOURCE_PACKAGE_INTEGRITY=PASS
POLICY_SNAPSHOT_COHERENCE=PASS
D4_ROOT_CAUSE_SUPPORTED=YES
OLD_RELEASE_DEFECT_CONFIRMED=YES
MICROFIX_MINIMALITY=PASS
REGRESSION_COVERAGE=PASS
CANDIDATE_RELEASE_FUSE_ONLY=PASS
AB_CANDIDATE_CORE=PASS_93
AB_CANDIDATE_C3=PASS_8
AB_RELEASE_CORE=PASS_93
AB_RELEASE_C3=PASS_8
TEST_SUPPORT_DEPENDENCY_PARITY=PASS
PROTECTED_IDENTITIES_UNCHANGED=YES
PROMOTION_PREP_ELIGIBLE=YES
D4_RERUN_AUTHORIZED=NO
D5_AUTHORIZED=NO
FULL_AUTHORIZED=NO
CRITICAL_FINDINGS=0
MAJOR_FINDINGS=0
MINOR_FINDINGS=4
REQUIRED_CORRECTIONS=PRE_D4_ADMISSION_ONLY(not blocking promotion prep): bind invs0() excerpt from modules/orchestrator.py SHA A01DB3955B44… and read-only extract OWNER_GATE.json s0_inventory from preserved CERTIFY_SCRATCH bundle SHA 9404F23C798A…, proving 1399/1399 nested {path,sha256,bytes} entries whose path grammar equals scan_s0 POSIX shadow-root-relative form; offline-replay the corrected S0_CERT_PATH_ASSOCIATION predicate over that real inventory; add partial-path drift assertion to the regression in the promotion-candidate qualification; echo per-side installed engine SHA and pre/post protected-identity values in the promotion qualification output

---

## Racional (somente evidência física do ZIP)

### Integridade e política
- 29/29 arquivos de `99_MANIFEST_SHA256.json` conferem em bytes e SHA-256; nenhum ausente, nenhum extra. Todos os SHAs de `01_REVIEW_FACTS.json` conferem com os arquivos físicos.
- 12/12 arquivos promovidos (20, 21, 23, 24, 30–37) conferem com as entradas de `22_OLD_PROMOTED_manifest.json`; `package_manifest_sha256` do recibo do wrapper D4 em `50` = `3BE959EE…` = SHA de `22`.
- `10` → `master_sha256` = SHA físico de `11` (`A2D8289E…`), `state=FROZEN`; `previous_master_sha256=A97D969B…` = `BASE_MASTER_SHA256` da §0R de `11` (L320) e L2517. Os documentos 51–56 declaram a mesma base.

### Questões 1–9

| # | Questão | Resposta | Evidência |
|---|---|---|---|
| 1 | Causa-raiz `CERTIFY_SCRATCH → S0_CERT_PATH_ASSOCIATION` | **SIM** | `50`: anchor `recovery_source_sha256=38B2D162…` (= `21`); stdout do bundle `REASON=S0_CERT_PATH_ASSOCIATION`; todos os `require` anteriores de `certify_scratch` (`21` L1981–1992) passaram, logo o inventário tem as mesmas 1399 chaves observadas e a falha ocorreu no primeiro par ordenado. |
| 2 | String-vs-dict em journal e partial | **SIM** | `21` L1993. Lado esquerdo é string por construção (`scan_s0`, L1625: `relative_to(root).as_posix()`); o lado direito é o valor inteiro da entrada, cuja forma aninhada é o modelo S0 do próprio engine (L1151, L1172, L1996; fixtures `31` L25–30, `32` L23–33). Observação: pelo curto-circuito do `and`, a D4 exercitou fisicamente apenas a metade journal. |
| 3 | Microfix exato e semântica preservada | **SIM** | `diff 20↔41` e `21↔42`: somente L1993. `40_DELTA.patch` aplicado a 20 e 21 reproduz 41 e 42 byte a byte (`E1CE7EA6…`, `186F865A…`); +16 bytes = 2×`["path"]`; mesmo reason code; ordem dos gates e conjunção `and` inalteradas. |
| 4 | Regressão fiel e bidirecional | **SIM** (limites m2/m3) | `43` L9–37: 1399 entradas `{namespace, contract, journal{path,sha256,bytes}, partial{…}}`; positivo afirma `PASS_1399_1399` (L53–55); drift afirma `S0_CERT_PATH_ASSOCIATION` (L57–66). Execução suplementar isolada (apenas `43` + `24`, sem código novo): antigo candidate/release → `ERROR Blocked: S0_CERT_PATH_ASSOCIATION`; novo → `OK`. Red→green comprovado. |
| 5 | Candidate/release apenas fusível | **SIM** | `diff 41↔42`: somente L30 `IMPLEMENTATION_READY = False/True`, ocorrência única em cada arquivo; relação idêntica a `20↔21`. |
| 6 | A/B físico | **SIM** | `51`: quatro blocos unittest com `Ran 93`/`Ran 8`, `OK`, exit code 0. Nomes executados = conjunto AST dos fontes, 1:1 (candidate 30+31+32+43; release 34+35+36+43; C3 33/37), com 0 FAIL/ERROR/skip. 93 = 92 (`23` `physical_test_count`) + 1. Parity: manifestos de cópia = fonte (`803EF41B…`, `A071B3A8…`) nos dois lados; `TEST_SUPPORT_SOURCE_IMMUTABILITY=PASS`; `POST_AB_PROTECTED_IDENTITIES=UNCHANGED`; `POST_RUN_RESIDUAL_PROCESS_COUNT=0`. |
| 7 | Mutação durante as qualificações | **Nenhuma evidência** | `51`: `MODE=DRY_RUN_ONLY`, `FAILED_D4_STATE=PASS_UNCHANGED_FAIL_NEXT_D4_NO_CERT`, fronteira effectful restrita à extração run-owned com `DELIVERY_EXTRACTION_CLEANUP=PASS`; `50`: `MUTATIONS_PERFORMED=NO`; 52/54/55/56: falhas anteriores de harness, sem mutação e com payload idêntico (hashes iguais em 01/51/52). |
| 8 | Elegível para PREPARAÇÃO sob CODE_DELTA_PATH | **SIM** | Delta mínimo; fail-closed em todas as hipóteses alternativas (dict → correto; string plana → `TypeError` → BLOCKED; formato divergente → mesmo reason code); regressão discriminante; A/B 202/202. |
| 9 | D4 rerun autorizado agora | **NÃO** | `00`, `01`, `52`, `53` negam; nenhum pacote imutável novo foi produzido nem qualificado. |

### Achados (todos MINOR)

- **m1 — Proveniência do produtor ausente.** A forma aninhada atribuída a `modules/orchestrator.py::invs0()` consta apenas da narrativa de `53` (seção "Root cause"). O fonte (`22`, entrada `modules/orchestrator.py`, SHA `A01DB395…`, 77.291 bytes; `23` `orchestrator_py_sha256`) e o `OWNER_GATE.json` real dentro de `CERTIFY_SCRATCH_…_D8706756.zip` (SHA `9404F23C…`, listado em `50`, "D4 RUN INVENTORY") não estão no ZIP. A causa-raiz é corroborada por consistência (Q1/Q2), não por bytes do produtor.
- **m2 — Paridade de formato nunca exercitada.** No caso positivo de `43`, observado e inventário derivam da mesma variável `path` (L20, L25, L33); a igualdade é tautológica quanto ao formato. Como o predicado antigo era sempre falso, ele mascarava tudo após `21` L1993: (a) a paridade do path de `invs0()` com a gramática POSIX relativa à raiz shadow de `scan_s0` (L1625); (b) `prep()` por dia sobre o shadow (`41` L1998; substituído por mock em `43` L47/L61). A correção é necessária; sua suficiência para o inventário real de 1399 dias ainda não está provada.
- **m3 — Drift apenas no journal.** `43` L59 altera somente `bad[first]["journal"]["path"]`; um mutante que removesse a conjunção partial sobreviveria. A presença dessa conjunção está provada estaticamente (`41`/`42` L1993) e o acesso aninhado partial é coberto pelo caso positivo.
- **m4 — Fechamentos A/B apenas por rótulo.** `51` reporta `POST_AB_PROTECTED_IDENTITIES=UNCHANGED`, `TEST_SUPPORT_SOURCE_IMMUTABILITY=PASS` e `PROCESS_TREE_RECONCILIATION=PASS` sem valores pré/pós; o runner V001R2 (delivery `C4401626…`) não está no ZIP; o SHA do `tickstore_publisher_recovery_v004.py` instalado em cada workspace não é ecoado. A identidade por lado fica provada indiretamente: testes específicos do fusível (`test_implementation_fuse_stays_false…` / `…_is_true…`, `test_candidate_remains_blocked…` / `test_release_fuse_true…`) e a regressão verde, que é vermelha no código antigo.

### Observações não contabilizadas (para a preparação)
- `44_ab_static_audit.py` L5–7 usa os nomes `04_/05_/06_` do layout de entrega; a correspondência com 41/42/43 é estabelecida pela igualdade de hash no stdout de `51`.
- O novo candidate de promoção deverá atualizar `physical_test_count` (92→93), `delta_candidate/release_source_sha256` e as listas `tests/` e `tests_release/` com a regressão.
- A correção de harness registrada em `53` (o parent imprime `BLOCKED_PRE_EFFECT` após exit 3 do filho elevado) permanece pendente no sucessor do runner D4.
