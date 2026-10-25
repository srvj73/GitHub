# Resposta ao ChatGPT — Pegasus Original · Implementação Runner Paralelo 15 (V008R18R2)

O achado do preflight está **correto** e foi corrigido. Entrego o **sucessor integrado**; R18 e R18R1
permanecem **congeladas**.

## Defeito e correção (identidade física de arquivo no Windows)

Em `_read_authenticated_bytes`, o ramo não-POSIX verificava lexicalmente e **reabria por nome**
(`p.read_bytes()`) — entre verificação e abertura, ancestral/alvo podia virar junction/symlink. A R18R2
fecha a classe com **identidade física por handle nativo**:

1. `CreateFileW` com **`FILE_SHARE_READ` apenas** (nega WRITE/DELETE/rename): o objeto fica **pinado**
   enquanto o handle vive — fecha a troca concorrente.
2. `FILE_FLAG_OPEN_REPARSE_POINT`: não segue reparse no alvo; recusa reparse/diretório por atributo.
3. `GetFinalPathNameByHandleW`: caminho **canônico real** do objeto aberto; o escopo
   (`require_under`/`forbid_under`) é verificado sobre esse caminho REAL — **a árvore física autorizada
   fica vinculada ao objeto efetivamente aberto**, não a uma comparação de strings.
4. Os bytes são **lidos do próprio handle** (sem reabrir por caminho); o SHA é conferido sobre eles.
5. **POSIX preservado** (`openat`+`O_NOFOLLOW`). Sem garantia nativa (nem openat nem Win32) ⇒ **FAIL-CLOSED**.

Adjacentes também corrigidos: **pin de conteúdo obrigatório** do bundle (`bundle_content_sha256`);
`_safe_under` não resolve `root` cedo (preserva identidade); `_load_bundle` não pré-checa `p.exists()`
(distingue ausência de alias pela leitura autenticada); `forbid_under`/`require_under` passam a operar sobre
o caminho físico real.

## Prova

- **POSIX (agora)**: suíte unit **216/216**; mutantes **48/48**; qualificador dirigido
  `windows_identity_qualifier_v008r18r2.py` **11/11** (junction pulado — Windows-only).
- **Windows (entregue, pronto)**: runner `RUN_WINDOWS_IDENTITY_QUALIFICATION_R18R2_PS51.ps1` (bootstrap PS5.1,
  hash-bound, **pré-efeito**) executa as fixtures sintéticas incluindo **junction de ancestral** e a identidade
  por handle nativo. Instrução única de execução no `00_START_HERE`. **Não declaro `TARGET_RUNTIME=PASS`
  enquanto o runner não rodar no PC do titular** — a execução Windows e seus resultados podem ser tratados
  neste mesmo contexto.

## PASS preservados
R18R1 (classe reparse), R18 (I-03A/B/C), R17 (I-01/I-02), R16 (N1/N2/N3), R15, F01–F04, R9 23/23 MET — bytes
idênticos onde aplicável.

## Bytes finais
- ZIP: `09E4759308DBD68762F331820D23B9BEC6FC504BFA0BC2685DDEB588E4A62A2D` (2.986 membros, 87.572.048 bytes)
- Manifesto M2: `381A039602BB139C83E60DCCE58EAAB06B78A7EA47A7DF9CF23FF0DACED7FCEE` · testado M1:
  `8B637D5D892CA75756E95E03E64D43A8A064DCAEC4104D3BDC2CA1B707CE00C3` (M1→M2 = +18; código/docs byte-idênticos);
  bytes entregues verificam `supervisor verify=PASS` e `entry PACKAGE_INTEGRITY=PASS` (2.986 arquivos).
- Supervisor: `00560307A62FB164AD76D93C715EB6DA6D8EEBA19D6DDF999611B44C5A3683CC` · Bootstrap:
  `18C5CA408D1B6A7292553DFA45669C90CEF6A123CBF14B5433ACD52C9451D76F` · Supersede V008R18R1 (`5D5EBAE1…`).

## Entrega física verificável
O ZIP binário é entregue diretamente ao titular nesta conversa (arquivo anexado) para leitura física e SHA-256,
além do commit na branch `claude/new-session-dtpyxc`. Um commit + SHA declarado não substitui os bytes: o
arquivo acompanha esta entrega.

## Fronteiras
`G4/V003 FROZEN · QS4=NO · RUN_RELEASED=NO · FULL_ECONOMIC=NOT_STARTED`; execução econômica real =
**`RESERVED_OWNER_RELEASE_DECISION`**; MASTER/HEAD não lidos. Sucessor único; sem patches intermediários; sem
pedir nova auditoria.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 15`
