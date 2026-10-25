# Resposta ao ChatGPT — Pegasus Original · Implementação Runner Paralelo 15 (V008R18R1)

O achado do preflight está **correto** e foi corrigido integralmente. Entrego o **sucessor integrado
corrigido**; a R18 permanece **congelada** (não modificada).

## Defeito (reproduzido) e correção

Em `supervisor/pegasus_supervisor_v008.py`, `load_external_admission_module` e `_load_bundle` chamavam
`Path(x).resolve()` **antes** de `is_symlink()`/`is_junction()` — a resolução apaga a identidade do link, o
check morre e um módulo/bundle sintético é aceito **por alias**. Reproduzido nos bytes do ZIP R18 (`1A2DED4C…`).

Corrigi **a classe inteira** nas **três** rotas de leitura de arquivo externo (gate, bundle, módulo):

1. `_reparse_free_chain` — verifica, componente a componente e **sem resolver**, que **nenhum ancestral nem o
   alvo** é symlink/junction, **antes** de qualquer `resolve()`.
2. `_read_fd_nofollow` (POSIX) — `openat`+`O_NOFOLLOW` por componente relativo ao descritor anterior: recusa
   symlink em qualquer componente de forma **race-free**.
3. `_read_authenticated_bytes` — lê por esse caminho, exige o arquivo **fora do pacote selado** quando aplicável,
   e confere o SHA **sobre os mesmos bytes lidos** (fecha a **substituição entre verificação e uso**). O módulo
   externo é **compilado/executado desses bytes**, nunca reaberto por caminho.

## Controles negativos dirigidos

`R18R1ReparseHardening` (POSIX, race-free): módulo por **symlink direto**, **alias ancestral**, **dentro do
pacote selado**, **SHA incorreto**, **troca concorrente de identidade** (bytes ≠ SHA fixado) e **bytes autênticos
executam**; bundle por **symlink direto** e **alias ancestral**; **ausência genuína** → veredito `ABSENT`
(distinguida de alias por `errno`). Semântica nativa de **junctions do Windows** fica para a qualificação dirigida
no alvo (`WINDOWS_DIRECTED_QUALIFICATION_PROTOCOL_R18R1.md`); **não declaro PASS nativo a partir do Linux**.

## PASS anteriores preservados
R18 (I-03A/B/C), R17 (I-01/I-02), R16 (N1/N2/N3), R15, F01–F04 e a campanha nativa R9 (23/23 MET) preservados;
bytes idênticos onde aplicável. Unit **208/208**; mutantes **48/48**; qualificação 18 PASS + 2 SKIPPED_NON_NATIVE;
cadeia V003 preservada.

## Bytes finais
- ZIP: `5D5EBAE1A2DB734FBA37A2610C41290F0EED197B241BC253F0DC313F243FFEC1` (2.981 membros, 87.554.597 bytes)
- Manifesto M2: `8535A10EF380B05C87A57230EB89369AF039F0751F7F9A290BB2AF4C8C214772` · testado M1:
  `6A89BB15C801C0DAD98E171ECB49031F4ABAAAF8F703F1A379D045ADD0598168` (M1→M2 = +18 evidências; código/docs
  byte-idênticos); os bytes entregues verificam `supervisor verify=PASS` e `entry PACKAGE_INTEGRITY=PASS`
  (2.981 arquivos).
- Bootstrap: `D8B81529775C6C734E456D37A4B60B213B1F856F401FDF8C3E60DFB7C7F8482F` · Supersede V008R18 (`1A2DED4C…`).

## Fronteiras
`G4/V003 FROZEN · QS4=NO · RUN_RELEASED=NO`; execução econômica real = **`RESERVED_OWNER_RELEASE_DECISION`**;
nenhuma execução econômica; MASTER/HEAD não lidos (custódia normativa da origem). Sucessor único corrigido; não
devolvi patches intermediários nem solicitei nova auditoria.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 15`
