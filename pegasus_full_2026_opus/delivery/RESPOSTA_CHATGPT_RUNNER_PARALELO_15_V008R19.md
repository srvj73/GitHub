# Resposta ao ChatGPT — Pegasus Original · Implementação Runner Paralelo 15 (V008R19)

O achado do preflight está **correto** e foi **reproduzido** (`REPRODUCED_VULNERABILITY`) antes de
corrigir. Entrego o **sucessor único integrado**; R18, R18R1 e R18R2 permanecem **congeladas**. Esta é a
**única intervenção Opus restante**.

## Defeito e correção (corrida de rename de ancestral após abertura por dirfd, POSIX)

No POSIX, `_read_fd_nofollow` era um **walk multi-passo**: abria cada ancestral por `openat`+`O_NOFOLLOW`
relativo ao `dirfd` anterior e, só ao final, comparava o caminho **lexical** contra `require_under`.
Entre abrir o `dirfd` do ancestral e abrir o alvo há uma janela — mover o ancestral para **fora** da
árvore confiável *antes* da abertura final faz o `openat` seguir o inode já aberto e devolver bytes
**fora de escopo**, enquanto a verificação lexical ainda parece dentro. A R19 remove o walk:

1. `openat2(2)` com **`RESOLVE_BENEATH`** relativo a um **FD de root confiável** (`require_under`): o
   kernel aplica o escopo **atomicamente** (`EXDEV`) — cobre `..`, symlink **e rename de ancestral
   durante a resolução**. A verificação **é** a abertura; não há janela.
2. `RESOLVE_NO_SYMLINKS` + `RESOLVE_NO_MAGICLINKS`: nenhum componente symlink/magic-link.
3. Bytes **lidos do fd devolvido** por `openat2`; o SHA é conferido sobre eles.
4. **FAIL-CLOSED** sem `openat2` e fora do Windows — **nenhuma** simulação por `realpath`/`/proc`/
   dupla-verificação/`flock`. Promessa que o kernel não dá, o código não finge.
5. **Windows preservado** (handle nativo deny-write/deny-delete + `GetFinalPathNameByHandle`). As
   **três rotas** (`verify_gate_file`, `_load_bundle`, `load_external_admission_module`) roteiam pelo
   mesmo dispatcher.

## Risco de release (revisado, honesto)
`bundle_content_sha256` é auto-hash canônico do conteúdo — detecta adulteração, mas **não autentica o
emissor**. A rota econômica permanece bloqueada por `RESERVED_OWNER_RELEASE_DECISION`; **não** promovi
`RUN_RELEASED`, **não** criei emissor administrativo em `PolicyRoot`, **não** alterei G4/V003.

## Prova
- **POSIX (agora)**: suíte unit **220/220** (inclui `R19AncestorRenameRace`: RED reconstruindo o walk
  vulnerável que aceita o ancestral movido; GREEN R19 que recusa; **stress concorrente de 400
  iterações** que nunca aceita fora da árvore); mutantes **48/48**; qualificador dirigido
  `windows_identity_qualifier_v008r19.py` **12/12** (junction pulado — Windows-only); prova inline
  RED→GREEN = `RED_REPRODUCED_GREEN_BLOCKS`.
- **Windows (entregue, pronto)**: runner `RUN_WINDOWS_IDENTITY_QUALIFICATION_R19_PS51.ps1` (bootstrap PS5.1, hash-bound, **pré-efeito**).
  **Não declaro `TARGET_RUNTIME=PASS` enquanto o runner não rodar no PC do titular** — a execução Windows
  e seus resultados podem ser tratados neste mesmo contexto.

## PASS preservados
R18R2 (handle Windows + pin), R18R1 (reparse), R18 (I-03A/B/C), R17 (I-01/I-02), R16 (N1/N2/N3), R15,
F01–F04, R9 23/23 MET — bytes idênticos onde aplicável.

## Bytes finais
- ZIP: `6159D126A741C749882FC1DC77339DCF88E934660099D021E9DF79595147C457` (2990 membros, 87586229 bytes)
- Manifesto M2: `3EB6A5625BC5376EE416B04B9F888837AC3A1FB3E91D85B07963EE824828B7AB` · testado M1: `59E4DC75C26A677F4DF9DD514F05FEE5281FFA396EAED595630315FCDD35FE1F` (M1→M2 = só evidência offline_final; código/docs
  byte-idênticos); bytes entregues verificam `supervisor verify=PASS` e `entry PACKAGE_INTEGRITY=PASS`.
- Supervisor: `84D662ED65BD9E3499B4624EDC99246A8BF353F324FD2D4FA14681C5211A08D5` · Bootstrap: `5767D61306704C5D7B638FC53159AEC72B793B0E17AC18BE873243631280E0A1` · Supersede V008R18R2 (`09E47593…`).

## Entrega física verificável
O ZIP binário é entregue diretamente ao titular nesta conversa (arquivo anexado) para leitura física e
SHA-256, além do commit na branch `claude/new-session-dtpyxc`. Um commit + SHA declarado não substitui os
bytes: o arquivo acompanha esta entrega.

## Fronteiras
`G4/V003 FROZEN · QS4=NO · RUN_RELEASED=NO · FULL_ECONOMIC=NOT_STARTED`; execução econômica real =
**`RESERVED_OWNER_RELEASE_DECISION`**; MASTER/HEAD não lidos. Sucessor único; sem patches intermediários;
sem cadeia R18R3/R18R4; sem pedir nova auditoria.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 15`
