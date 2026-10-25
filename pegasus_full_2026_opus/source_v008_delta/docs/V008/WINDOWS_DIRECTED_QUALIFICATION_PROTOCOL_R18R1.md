# Protocolo de qualificação dirigida Windows — V008R18R1 (classe reparse/alias, semântica nativa)

Prova nativa, no PC do titular, da semântica de **reparse points / junctions / aliases** do Windows que
não pode ser demonstrada em sandbox POSIX. Processos **exclusivamente sintéticos**, hash-bound, sem
economia, **sem kill não autorizado**, **D4 não autorizado**. Complementa (não substitui) os protocolos
R16/R17/R18 e a campanha R9 (23/23, MET) preservada. **Não se declara PASS nativo a partir do Linux.**

## Contexto
No POSIX a correção R18R1 lê de forma **race-free** (`openat`+`O_NOFOLLOW` por componente). No Windows
`os.open` não aceita `dir_fd`; a cadeia é provada livre de reparse por `is_symlink()`/`is_junction()`
(lexical) antes de qualquer resolução, e a leitura é feita em seguida. Os alvos abaixo confirmam a
semântica nativa de aliases do Windows que o Linux não exercita.

## Alvos (fixtures sintéticos, isolados)

| # | Propriedade | Fixture sintético (Windows) | Observação esperada |
|---|---|---|---|
| W1 | symlink de arquivo (módulo/bundle) | `mklink` para o arquivo real | recusa `*_REPARSE_OR_ALIAS` antes de qualquer uso |
| W2 | **junction** de diretório ancestral | `mklink /J` num ancestral do caminho | recusa `*_REPARSE_OR_ALIAS_COMPONENT` |
| W3 | symlink de diretório ancestral | `mklink /D` num ancestral | recusa por reparse ancestral |
| W4 | nome curto 8.3 / alias de nome | acesso por nome 8.3 do mesmo arquivo | a identidade física é a mesma; SHA sobre os bytes lidos governa |
| W5 | escape do pacote selado | caminho que saia da árvore selada | recusa `*_INSIDE_SEALED_PACKAGE_FORBIDDEN` (bundle/módulo) ou `OUTSIDE_BUNDLE` (gate) |
| W6 | SHA incorreto / troca de identidade | arquivo cujo conteúdo ≠ SHA fixado | recusa `*_IDENTITY_MISMATCH_OR_CONCURRENT_SWAP`; não executa/usa |
| W7 | bytes autênticos | arquivo correto, fora do selado, SHA batendo | lê/executa os bytes autenticados (admissão sintética prossegue) |

## Salvaguardas
- Nenhum arquivo externo pode residir dentro do pacote selado.
- O módulo externo é **compilado e executado a partir dos bytes autenticados**, nunca reaberto por caminho.
- Cada recibo primário é hash-bound; nada é promovido a PASS sem a observação exigida.

## Retorno
Recibos primários (`*_DIRECTED_R18R1_*.json`) com SHA-256 dos bytes e observações. Enquanto a prova
dirigida não for executada, a semântica nativa de reparse/junction é **TARGET_RUNTIME_PENDING** — a
robustez lógica da classe está fechada e testada no POSIX; a confirmação nativa é do titular/origem.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 15`
