# PEGASUS FULL 2026 — ENTREGA DE ENGENHARIA V008R18R1 (Opus, 25/10/2026)

**Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 15 · **Papel:** implementador integrado. **Sucessor corrigido da R18 (que permanece congelada), não nova auditoria.**

## O que é esta entrega — correção do defeito material do preflight

O **preflight independente reprovou a R18** por defeito material (nenhuma auditoria formal iniciada), reproduzido
nos bytes do ZIP R18 (`1A2DED4C…`): em `load_external_admission_module` e `_load_bundle`, `Path(x).resolve()`
era chamado **antes** de `is_symlink()`/`is_junction()`; a resolução apaga a identidade do link e o check morre,
aceitando módulo/bundle **por alias**. A R18R1 corrige **a classe inteira** nas **três** rotas de leitura de
arquivo externo (gate, bundle, módulo de admissão), incluindo **ancestrais** e **proteção TOCTOU**.
**Nenhuma economia iniciada; nenhum gate liberado; nada forjado; política não lida; D4 não autorizado.**

### Correção (família de helpers)
- `_reparse_free_chain` — prova, componente a componente e **sem resolver**, que nenhum ancestral nem o alvo é
  symlink/junction (a verificação ocorre **antes** de qualquer `resolve()`).
- `_read_fd_nofollow` (POSIX) — `openat`+`O_NOFOLLOW` por componente relativo ao descritor anterior: recusa
  symlink em qualquer componente de forma **race-free**; lê os bytes do descritor final.
- `_read_authenticated_bytes` — cadeia livre de reparse → (opcional) fora do pacote selado → leitura race-free →
  SHA conferido **sobre os mesmos bytes lidos** (fecha a substituição entre verificação e uso). **Retorna os
  bytes autenticados.** O módulo externo é **compilado/executado desses bytes**, nunca reaberto por caminho.

As três rotas migraram: `verify_gate_file` (gate), `ProductionReleaseAdmission._load_bundle` (bundle),
`load_external_admission_module` (módulo). No Windows a semântica nativa de **reparse/junction** é qualificada na
prova dirigida do alvo (`WINDOWS_DIRECTED_QUALIFICATION_PROTOCOL_R18R1.md`) — **não se declara PASS nativo a
partir do Linux**; no POSIX a leitura é race-free.

### Bytes finais (fora do ZIP)

| Artefato | SHA-256 |
|---|---|
| ZIP `…_FINAL_V008R18R1_20261024.zip` (2.981 membros, 87.554.597 bytes) | `5D5EBAE1A2DB734FBA37A2610C41290F0EED197B241BC253F0DC313F243FFEC1` |
| Manifesto final (M2) | `8535A10EF380B05C87A57230EB89369AF039F0751F7F9A290BB2AF4C8C214772` |
| Manifesto testado (M1) | `6A89BB15C801C0DAD98E171ECB49031F4ABAAAF8F703F1A379D045ADD0598168` |
| Bootstrap `BOOTSTRAP_…_V008R18R1_PS51.ps1` | `D8B81529775C6C734E456D37A4B60B213B1F856F401FDF8C3E60DFB7C7F8482F` |
| Supervisor `supervisor/pegasus_supervisor_v008.py` | `36700BD589D03FB70E2F3548D46B455159DC3D63A0C9C80358D8BEE0508784FB` |
| Entry `CODE/pegasus_entry.py` (V003, inalterado) | `F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB` |

**tested=packaged=delivered:** M1→M2 difere só por **18** arquivos de evidência; **código e docs byte-idênticos**
(0 alterados, 0 removidos). Os bytes **entregues** (ZIP extraído) verificam `supervisor verify=PASS_PACKAGE_VERIFIED`,
`entry verify=PACKAGE_INTEGRITY=PASS`, 2.981 arquivos, manifesto = M2. Unit **208/208**; mutantes **48/48**;
qualificação **18 PASS (incl. Q16, Q17) + 2 SKIPPED_NON_NATIVE**; cadeia V003 preservada; QS4 binding `BLOCKED`
(pin). `pwsh` indisponível no sandbox (template PS5.1 byte-validado). Supersede V008R18 (`1A2DED4C…`), que
permanece congelada.

### Controles negativos dirigidos (teste)
`R18R1ReparseHardening`: módulo por symlink direto, alias ancestral, dentro do pacote selado, SHA incorreto,
troca concorrente de identidade e bytes autênticos executam; bundle por symlink direto e alias ancestral;
ausência genuína → veredito `ABSENT` (distinguida de alias por `errno`). Junctions nativos ficam para o Windows.

## Estado honesto dos cinco eixos

| Eixo | Estado |
|---|---|
| ENGINEERING_COMPLETE | **SIM** — R18-PREFLIGHT-01 (classe TOCTOU/alias) + I-03A/B/C + I-01/I-02 + N1/N2/N3 + A01–A04/INT + F01–F04 |
| NATIVE_QUALIFICATION | **MET nos bytes R9** (23/23); semântica nativa reparse/junction = **TARGET_RUNTIME_PENDING** |
| CANDIDATE_COMPLETENESS | **engenharia completa**; selagem `=PASS` é da origem |
| INDEPENDENT_AUDIT | **pendente** — da origem |
| PRODUCTION_AUTHORIZED / RUN_RELEASED | **NO** — execução econômica real = **DECISÃO RESERVADA do titular** |

Fronteiras: `G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO`. **Não declaro
READY** nem a execução econômica alcançável.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 15`
