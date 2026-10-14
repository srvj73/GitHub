# TICKSTORE CDT15 — Retorno R44D2 + R45 à origem

Papel: ENGINEER_ONLY. Nenhuma alteração produtiva, FULL, B06, B07, corte de energia ou crédito pago adicional.

## 1. R44D2 (delta da admissão física de `D:`) — corrige R44D-ORIGIN-01

- O bootstrap **nunca cria** `D:\TICKSTORE_QUALIFICATION_SANDBOX`. Se a pasta não existir, a execução bloqueia com `D_SANDBOX_ROOT_ABSENT_NOT_CREATED`. Se existir, é admitida antes de qualquer escrita: sem reparse em nenhum componente, caminho final igual ao caminho e volume NTFS.
- Admissão presa a handle (`HeldChain`): cada componente é aberto sobre o próprio objeto (`OPEN_REPARSE_POINT`, sem `FILE_SHARE_DELETE`) e permanece retido. O diretório de ensaio é criado de forma exclusiva sob a raiz retida e passa a ser retido também. A identidade (volume, índice de arquivo, caminho final) é verificada **imediatamente antes e depois** dos controles negativos.
- Testes adversariais: ancestral redirecionado (sem escrita), raiz em junction, raiz ausente não criada, diretório de ensaio pré-existente (pasta comum e junction), rename da raiz retida recusado e caminho feliz.
- Os 126 do R44 **não** são executados nem repetidos. O R44D original (PS1 `0AED17FA…`) fica fora de uso.

## 2. R45 (FINAL novo; o FINAL R44 `0FBB6C36…` permanece intocado)

- RC1 byte-idêntico (`D3A15572…`).
- B2C, B2D e B07 integrados ao candidato. B07 continua SOURCE_ONLY e só executa depois de B06 independente PASS (`ReleaseChain(..., until='B06')`).
- As fixtures B2C aprovadas entram como overlays hash-bound, com os bytes exatos (`E74F3701…`, `40B396FC…`) e os pais do arquivo R3. Os 126 IDs rodam sobre os bytes R45, que são novos; não se trata de repetição do R44.
- Entradas legadas FULL_SERIAL, piloto e full-history isoladas comprovadamente: ver `R45/LEGACY_ENTRY_ISOLATION.md`. O risco residual está declarado e a decisão cabe à origem.
- Admissão just-in-time com leitura de retorno: o driver retém a raiz de trabalho e a raiz `D:` antes de qualquer escrita, cria o diretório de execução `D:` de forma exclusiva sob handle e revalida a mesma identidade retida no POSTCHECK.
- `R45_B2C_NATIVE_PROBE`: verificação da captura R40 pelo leitor selado; bloqueio exatamente na reconciliação `NOT_ISSUED`; recusa de V38, de arquivo extra e de MASTER adulterado; negação de escrita, exclusão e rename com o handle retido (com controle positivo após a liberação); `d4_command` exige reconciliação corrente.
- `R45/R45_POLICY_RECONCILIATION_REQUEST.json` é uma **solicitação**, não um recibo: `POLICY_RECONCILIATION_FOR_R45=NOT_ISSUED`.

## 3. Estado dos gates

G4 INCOMPLETE · G5 INCOMPLETE (bloqueador único: `CHECKPOINT_POWERLOSS_RECOVERY`, prova física não especificada; POWERLOSS_EMULATED não substitui) · B06 NOT_STARTED (independente) · B07 SOURCE_ONLY.

## 4. Ordem de execução no Windows (`PS C:\Users\silvi>`)

1. `CHECK_PS51_SYNTAX.ps1`: parser PS5.1, somente leitura.
2. `RUN_TICKSTORE_CDT15_R44D2_DROOT.ps1`: delta de `D:`.
3. Somente se o R44D2 der PASS: `RUN_TICKSTORE_CDT15_R45_QUAL.ps1`, elevado.

Os logs ficam sempre em `C:\Users\silvi\OneDrive\Downloads\TICKSTORE_RUNS\<MODO>_<timestamp>_<PID>\RUN_LOG.txt`.
