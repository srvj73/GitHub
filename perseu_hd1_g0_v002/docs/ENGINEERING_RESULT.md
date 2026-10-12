# ENGINEERING_RESULT — PERSEU HD1 G0 (sucessor V002)

**Projeto:** Perseu MT5 (Astra) · **Conversa:** PERSEU_C2_DISK_SPACE_RECONCILIATION · **Subfrente:** PERSEU_HD1_ARCHIVE_RECONCILIATION
**Papel:** `IMPLEMENTER/G0_ENGINEER` — engenharia, **não** auditoria independente. Nenhuma autocertificação.
**Superfície real:** Claude Code (sessão remota em contêiner Linux), modelo configurado Claude Opus 5.5. Sem acesso ao Windows do titular.
**Data:** 2026-10-12.

## 0. Aceitação do handoff

| Verificação | Resultado |
|---|---|
| SHA-256 físico do ZIP recebido vs. testemunha externa (`package_zip_sha256`) | `435FA919…BBA72` = **PASS**; tamanho 77604 = **PASS** |
| `MANIFEST_SHA256.json` (SHA `7C9E56FD…43284`) vs. testemunha | **PASS** |
| 14 membros: SHA e tamanho | **14/14 PASS**; contagem 15 com o manifesto = testemunha |
| Captura da política: MASTER `5B135DA0…B302`, HEAD `2DA2939C…5BA9`, `HEAD.master_sha256` igual, revisão `20261012T070600-0300-5B135DA0CA7C3BFE`, `FROZEN`, cardinalidade 1+1 | **PASS_DELEGATED_OFFLINE** (Biblioteca viva não consultada; nenhum `LIVE_POLICY_PASS` alegado) |
| Extração | somente como dados, em diretório novo e isolado; nenhum script extraído foi executado |

Observação de roteamento: a mensagem do titular continha um trecho colado de outra frente (launcher `RUN_PEGASUS_FULL_2026.ps1`, `BOOTSTRAP_QS4_HARNESS.ps1`). Esses bytes **não** estão nesta sessão e não fazem parte do handoff Perseu; nada foi produzido para o PEGASUS. A correção posterior do titular confirmou o escopo Perseu.

## 1. Causa raiz: por que o V001 não podia ser promovido

Leitura estática do probe legado `PERSEU_HD1_READONLY_GATE_ZERO_PROBE_V001.py` (SHA `C53BBA63…4CE6`, **não alterado**):

| # | Defeito no V001 | Consequência | Tratamento no V002 |
|---|---|---|---|
| L1 | `POLICY_SHA256_AT_BUILD` de 10/10 (`B114CFA4…`) | identidade de política vencida | nova identidade vinculada a MASTER `5B135DA0…` e HEAD de 12/10 |
| L2 | inventário via `powershell -EncodedCommand` inline lançado pelo Python; stdout do filho na code page do console (OEM), decodificado como UTF-8 estrito | launcher inline proibido; risco de falso BLOCKED/erro com caracteres não ASCII | o inventário passa ao wrapper PS 5.1 (`-File`), gravado em arquivo UTF-8 sem BOM; o Python não lança PowerShell |
| L3 | sem heartbeat durante a espera do subprocesso | viola 10.0A | heartbeat em stderr (Python) e no log (wrapper), cadência 30 s |
| L4 | binding não verificava `OperationalStatus`, `IsOffline`, duplicidade de DiskNumber, colisão de letra entre discos, nem o HD2 | disco offline ou letra ambígua tratados de forma imprecisa | 21 controles negativos explícitos, guarda HD2 por serial |
| L5 | `int()` aceitava `bool`/`str` em `DiskNumber` | coerção silenciosa | tipos estritos (`type(x) is int`) |
| L6 | reparse detectado só por `is_symlink`/`is_junction` | outros reparse points do NTFS passariam | atributo `FILE_ATTRIBUTE_REPARSE_POINT` (0x400) |
| L7 | censo global apenas (1530 / 414020605824) | um conjunto faltante compensado por excedente em outro passaria | censo **por conjunto** (contagem, bytes, cardinalidade 0/1/N, aninhamento) |
| L8 | `PASS_PROBE_ONLY` emitido mesmo com censo divergente | falso PASS possível | divergência de metadados, manifesto ausente/divergente ou contagem de linhas ≠ 1530 → `BLOCKED` (exit 2), com censo completo preservado |
| L9 | exceções não previstas (ex.: `IndexError`) escapavam com traceback e exit 1, sem JSON | fail-open de formato | captura final registra tipo e mensagem como `BLOCKED` (detectado pelo próprio selftest durante esta engenharia) |
| L10 | resultado só em stdout; sem recibo, sem log, sem pasta de evidência | sem recibo hash-bound | wrapper grava recibo, log e snapshots em pasta absoluta nova por execução |
| L11 | sem estabilidade do volume durante o probe | troca de disco no meio do run passaria | `st_dev` antes/depois + snapshot PRE/POST com comparação de binding |
| L12 | nenhum comprovante procurado no próprio HD1 | perderia a chance de achar `HD500_V003_COPY_RESULT_*` | listagem limitada de raiz, `ARQUIVO_FRIO` e `TOP4_V001`, com SHA de arquivos ≤ 16 MiB (máx. 64 arquivos / 256 MiB) |

Achados do wrapper durante a própria engenharia (corrigidos antes da entrega): acesso direto a `$PSVersionTable.CLRVersion` sob StrictMode (passou a ser opcional via `PSObject.Properties`), falha de recibo registrada apenas no console (agora também no log, preservando a causa primária) e ausência da causa do filho no recibo (`child_reason` adicionado).

## 2. Artefatos do candidato

| Caminho | Bytes | SHA-256 | Papel |
|---|---:|---|---|
| `dist/PERSEU_HD1_RECON_PROBE_V002.ps1` | 83499 | `3F78E1A2704DD82C52947061F842AAF72DC9D3F2004BE225FA306DA04FA6E8D5` | entrypoint único entregue ao Windows |
| `src/PERSEU_HD1_RECON_PROBE_V002.py` | 38171 | `2FE0174AFB117209C02A77278BCE2FA1549A1933ECD2259D0D823B6FB84CD675` | payload (idêntico ao embutido) |
| `dist/PERSEU_C2_SOURCE_LOCATOR_V001.ps1` | 38640 | `07F665511BEF201BF363F418846174840ECA6E3EEEE385FD71BC4B19E82D935D` | localizador C2 somente leitura (frente C2; ver seção 9) |

Demais arquivos e SHAs: `MANIFEST_SHA256.json` do candidato. O delta completo legado→V002 está em `delta/IMPLEMENTED_DELTA.patch`.

Arquitetura: `PS1 (-File) → gates de ambiente → pasta de run nova → Python pinado (existência + SHA do exe) → materialização do payload (SHA embutido = SHA físico, revalidado antes de cada lançamento) → snapshot Get-Disk/Get-Partition/Get-Volume → payload (--inventory-check | --probe | --selftest) → JSON de resultado (arquivo, UTF-8 estrito, sem BOM) → classificação (allowlist, coerência exit×RESULT×EXIT_CODE, série 3.14) → recibo + resumo key=value + rodapé`.

Mapa de autoridade: exit code nativo = autoridade de PASS/não-PASS; o arquivo `OUT_*.json` = dados; o stdout do Python = espelho humano. O JSON é lido de arquivo (e não por redirecionamento de stdout com `ReadToEndAsync`), substituição prevista em 10.0A que elimina o risco de deadlock de pipe.

## 3. Matriz G0

| Gate | Resultado | Evidência |
|---|---|---|
| `G0_STATIC` | **PASS_SANDBOX** | compile dos bytes exatos em CPython 3.14.6 e 3.13.16; `codecs.lookup` de `utf-8`, `utf-8-sig`, `ascii`; payload e wrapper ASCII, sem BOM; parser externo pwsh 7.4.6: 0 erros, 0 achados (variáveis automáticas em parâmetros/atribuições/foreach, aliases, sombra de cmdlet, token-glue de `return`, CRLF); controle negativo do auditor detectou 8/8 defeitos plantados. **Parse em Windows PowerShell 5.1: pendente** (a execução no alvo constitui a prova). |
| `G0_NEGATIVE` | **PASS_SANDBOX** | 21 casos de binding + 3 de inventário; 14 de censo/listagem/manifesto/escrita atômica (inclusive valores > 2³² e symlink recusado); 8 casos de probe sobre volume esparso sintético (positivo, 1 byte a menos, arquivo extra, symlink, manifesto não provado, conjunto ausente, restauração, payload ausente); matriz de 7 fixtures no wrapper (pass, blocked, contradição, malformado, sem arquivo, BOM, watchdog). Nenhum teste de escrita em alvo protegido. |
| `G0_INTEGRATION` | **PASS_SANDBOX** (pwsh/Linux) | bytes entregues: bloqueio fail-closed fora do Windows, sem criar arquivos, cabeçalho `RESULT_CONTEXT` e rodapé presentes. Cópia patchada **rotulada** (gates de ambiente neutralizados, cmdlets de disco simulados, rótulos `PASS_WINDOWS_*` reescritos para `SANDBOX_PATCHED_COPY_NOT_WINDOWS_*`): SelfTest exit 0, Inventory exit 0, Probe exit 2 com `child_reason=WINDOWS_TARGET_REQUIRED`; argv físico 7/7 (espaços, barra final, aspas, vazio, tab, não-ASCII); vetor Int64 419168089472; watchdog sem kill com término natural reconciliado; cwd intocado. |
| `G0_TARGET_RUNTIME` | **TARGET_RUNTIME_PENDING** | requer Passo 2 do README no PC alvo (PS 5.1 Desktop, Python 3.14 pinado, propriedades reais de `Get-Disk`/`Get-Partition`/`Get-Volume`). |
| `G0_TESTED_PACKAGED_DELIVERED` | tested = packaged **PASS_SANDBOX**; delivered **NOT_MEASURED** | SHA do fonte testado = embutido decodificado = pinado = materializado em cada run (`2FE0174A…`). O SHA do `.ps1` recebido no Windows depende do Passo 1. |
| `G0_RELEASE_DECISION` | **BLOCKED** → artefato `SOURCE_ONLY` | blockers B1–B4 abaixo |
| `CANDIDATE_COMPLETENESS` | **NOT_PROVEN** | depende de `G0_TARGET_RUNTIME` e da igualdade delivered |
| `FORMAL_AUDIT_DISPATCH` | **NOT_DISPATCHED** | proibido para candidato incompleto |
| `C2_FULL_STARTED` | **NO** | — |

## 4. Custódia do HD1 — decisão

As evidências existentes **não fecham** a custódia:

- `ARCHIVE_SOURCE_MANIFEST_SHA256.csv` com SHA `416A385C…` prova a identidade do manifesto de origem, não a cópia.
- O recibo 77/77 de 30/09 prova as **origens** JAN e SEP naquela data. Reconciliação aritmética: ele cobre 38 + 39 = 77 arquivos (230022103779 bytes), ao passo que o TOP4 lista 45 + 44 = 89 arquivos (230022182406 bytes) para os mesmos conjuntos; **12 arquivos / 78627 bytes** dos conjuntos TOP4 estão fora dos manifestos de run. C1 e MINOTAURO não fazem parte desse recibo. Portanto o readback deve se vincular ao CSV TOP4 de 1530 linhas, nunca aos manifestos de 77 membros.
- O ZIP localizado (`…PREDELIVERY_QUALIFICATION_ONLY…`, SHA `A86A3C63…`) é qualificação, não cópia concluída.
- `HD500_V003_COPY_RESULT_*.zip` não foi encontrado nos dois Downloads varridos.
- As pastas originais em `D:` estão ausentes (`ORIGINAL_D_PATH_ABSENT`); não se afirma perda nem que o HD1 contenha os dados.

**Conclusão:** o readback SHA integral do HD1 contra o CSV TOP4 é **indispensável**, salvo se o probe V002 localizar no HD1 um recibo completo de cópia+readback vinculável — decisão que retorna à origem.

## 5. Plano em estágios (nenhum estágio é iniciado por este artefato)

| Estágio | Ação | Pré-condições / gates | Efeito |
|---|---|---|---|
| E0 | `-Mode SelfTest` com HD1 desconectado | Passo 1 (SHA do `.ps1`) | só evidência em C: |
| E1 | decisão de conexão (D1–D3 do README) | HD2 quiescente; sem jobs em D:/E:/F:; autorização do titular | conexão física |
| E2 | `-Mode Inventory` | HD1 Online por si; binding único | só evidência |
| E3 | `-Mode Probe` | E2 PASS | leitura de metadados + SHA de arquivos pequenos |
| E4 | runner de readback SHA (sucessor a construir, nova identidade e G0 próprio) | E3 PASS; esquema do CSV fixado a partir do cabeçalho relatado em E3; preflight de saúde read-only; espaço de evidência em C: (< 10 MiB); checkpoint por arquivo commitado, resume, SAFE_STOP, heartbeat 30–60 s, ETA; leitura sequencial single-reader (HDD) | leitura integral de 414020605824 bytes; ETA ≈ 55 min a 120 MiB/s, ≈ 82 min a 80 MiB/s |

E4 não foi implementado nesta entrega porque depende do esquema físico do CSV (bytes no Windows, não no handoff); implementá-lo agora exigiria presumir colunas, o que a política proíbe.

## 6. Blockers

- **B1** `G0_TARGET_RUNTIME_PENDING` — execução do Passo 2 no PC alvo.
- **B2** `DELIVERED_SHA_NOT_MEASURED` — Passo 1 no PC alvo.
- **B3** `HD1_OFFLINE` — conexão física sujeita às decisões D1–D3.
- **B4** Fase B (C2) — após o complemento, permanece `BLOCKED` apenas nas verificações que dependem dos itens C2-01 a C2-10 de `C2_SOURCES_REQUIRED.md` (R4R9 original, prerregistro V004, telemetria V004 original, recibo de aplicação do hotfix, certificado D1 `93092E9A…`).
- **B5** Localizador C2: `G0_TARGET_RUNTIME_PENDING` e SHA delivered não medido (Passos C1–C2 do README).

## 7. Efeitos físicos reais

Nenhum efeito no Windows, em D:, E:, F:, HD1 ou HD2. Efeitos desta sessão: arquivos no contêiner/repositório da sessão e diretórios temporários de teste (removidos pelos próprios testes). `SOURCE_DELETE=NO`.

## 8. RESOURCE_USAGE

Uso incluído da sessão Claude Code; consumo exato `UNKNOWN` (não visível). Ferramentas baixadas apenas para teste em sandbox: CPython 3.14.6 (uv) e PowerShell 7.4.6 (parser externo). Nenhum crédito pago, compra ou recarga.

## 9. Complemento de Fontes V001 (delta)

Aceitação: ZIP `DF5192F6…A907` = testemunha; pai e testemunha pai vinculados; 21/21 membros e exact-set PASS (detalhe em `C2_STATIC_ENGINEERING_DELTA.md`). A engenharia HD1 V002 **não foi refeita**: seus bytes e evidências permanecem idênticos.

Avanços com as fontes recuperadas (estáticos, sem executar código recuperado):

1. Raiz de instalação do R4R9 no Windows fixada a partir dos próprios scripts: `C:\Users\silvi\OneDrive\Downloads\PACOTE_PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R9_20260921_CONFIRMATORY`; caminho físico do ZIP R4R9 em 22/09 fixado pela evidência terminal original.
2. Identidades de 7 membros do R4R9; 3 com bytes recuperados por igualdade de SHA com o R4R8 (core, testes do core, runner baseline R4R8). Runner, accel e testes R4R9 continuam ausentes.
3. Cadeia do hotfix C1 R1→R2→R3: método de derivação validado 2/2 contra constantes independentes; módulo R3 esperado `6F77DFA4…BB13` (`DERIVED_STATIC`).
4. Telemetria: REENVIO identificado exatamente; causa estrutural da confusão V004×REENVIO localizada (escritas sem guarda de colisão com a mesma `VERSION`; sidecar com SHA LF versus arquivo CRLF no Windows) — achados F1/F2.
5. Prerregistro: código confirmatório V001R2 vinculado ao V003; um V004 exige novo vínculo; D1 `93092E9A…` ausente de todos os recuperados.
6. Localizador somente leitura `PERSEU_C2_SOURCE_LOCATOR_V001.ps1` construído para os itens ausentes.

| Gate (localizador C2) | Resultado | Evidência |
|---|---|---|
| `G0_STATIC` | **PASS_SANDBOX** | parser externo pwsh 7.4.6: 0 erros, 0 achados (`evidence_sandbox/11_*`) |
| `G0_NEGATIVE` | **PASS_SANDBOX** | 15 verificações sintéticas: SHA divergente, ausente, sem SHA fixado, padrões em cada raiz, pasta de run vazia/ausente, link não seguido, gate fail-closed, Int64; placeholder Offline **pulado no Linux** (exercido no Windows) |
| `G0_INTEGRATION` | **PASS_SANDBOX** | bytes entregues bloqueiam fora do Windows sem criar arquivos; cópia patchada rotulada: SelfTest exit 0, Locate exit 0 com `C2_SOURCE_GATE=BLOCKED`; JSON sem BOM; cwd intocado (`evidence_sandbox/12_*`) |
| `G0_TARGET_RUNTIME` | **TARGET_RUNTIME_PENDING** | Passo C2 do README |
| `G0_TESTED_PACKAGED_DELIVERED` | tested = packaged **PASS_SANDBOX**; delivered **NOT_MEASURED** | Passo C1 |
| `G0_RELEASE_DECISION` | **BLOCKED** → `SOURCE_ONLY` | B5 |

Defeitos encontrados e corrigidos no localizador antes da entrega: parâmetro `[string]` convertia `$null` em `''` (todo alvo sem SHA fixado seria falsamente `FOUND_MISMATCH`); o selftest aceitava a criação de junction sem verificar o link físico (no pwsh/Linux o cmdlet retorna sem criar nada); diretórios com reparse passam a nunca ser seguidos. O wrapper HD1 V002 foi verificado quanto ao mesmo padrão e não o contém.

## 10. POLICY_DRIFT_DEFERRED_TO_ORIGIN

O V002 foi preparado sob MASTER `5B135DA0…` / HEAD `20261012T070600-0300-5B135DA0CA7C3BFE`, por captura delegada. A origem deve reler o par vivo e reconciliar eventual drift (10.Z) antes de autorizar E1 ou qualquer sucessor.

---

Devolva este resultado ao ChatGPT, no projeto “Perseu MT5 (Astra)”, conversa “PERSEU_C2_DISK_SPACE_RECONCILIATION”. Anexe as evidências existentes e cole esta resposta.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Perseu MT5 (Astra) | THREAD=PERSEU_C2_DISK_SPACE_RECONCILIATION`
