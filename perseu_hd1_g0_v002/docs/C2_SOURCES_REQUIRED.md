# C2 — Fontes indispensáveis, caminhos exatos no Windows e recuperação somente leitura

**Projeto:** Perseu MT5 (Astra) · **Conversa:** PERSEU_C2_DISK_SPACE_RECONCILIATION
**Revisão:** atualizada após o Complemento de Fontes V001 (substitui a versão anterior deste documento, que não chegou a ser entregue).

Caminhos derivados **dos próprios bytes recuperados** (constantes `ROOT`, `REPORT`, `ZIP_NAME`, `DOWNLOADS`) e da evidência terminal original de 22/09 — não inferidos.

## 1. Raízes físicas

| Raiz | Origem da informação |
|---|---|
| `C:\Users\silvi\OneDrive\Downloads\` | `DOWNLOADS[0]` de todos os preparadores; ZIP R4R9 observado aqui em 22/09 |
| `C:\Users\silvi\Downloads\` | `DOWNLOADS[1]` dos preparadores; busca secundária explicitamente pedida pela origem |
| `C:\Users\silvi\OneDrive\Downloads\PACOTE_PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R9_20260921_CONFIRMATORY\` | `ROOT` de todos os scripts R4R9 recuperados (raiz de instalação) |
| `D:\PerseuRuns\PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R9_CONFIRM_C1_202502\`, `…_CONFIRM_C2_202608\`, `…_R4R9_SEP2026\` | `OUT` dos wrappers; somente existência e contagem de primeiro nível |

## 2. Indispensáveis (bloqueiam a frente C2)

| # | Arquivo | Caminho exato esperado | Identidade | Situação |
|---|---|---|---|---|
| C2-01 | `PACOTE_PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R9_20260921.zip` | `C:\Users\silvi\OneDrive\Downloads\` (alternativa `C:\Users\silvi\Downloads\`) | `70D6E13125EDCA3FC0AC5049ADBE0FD605AA5111598030EBFDE8A35030C0F69F` | ausente no handoff; **recuperável do Windows** se ainda existir |
| C2-02 | runner `perseu_parallel_auto.py` | raiz de instalação | `28DF85A4BF87B859230C931042C493CD6B4E57FE8698135C3D771C56E466E68C` | ausente; recuperável (instalação ou ZIP) |
| C2-03 | `perseu_r4r9_accel.py` | raiz de instalação | `042FA9CB7DB2DE26BD64F82B41B2A1977B05C65509E2038239BDC972E766F2E5` | ausente; recuperável |
| C2-04 | `test_parallel_auto.py`, `test_r4r9_gate.py` | raiz de instalação | `5D3DB8FD…AB7E`, `B8E1417E…E8B8` | ausentes; recuperáveis |
| C2-05 | `RUN_WINDOWS_R4R9_CONFIRM_C2_202608.ps1` | raiz de instalação | `53C8A1FBAA0C836DCB616789BD0C1D7264CCA6E97C8780E364FA05204E088ADD` | ausente; recuperável |
| C2-06 | `perseu_r4r9_telemetry_v4.py` e `RUN_WINDOWS_R4R9_CONFIRM_C2_202608_TELEMETRY_V4.ps1` **instalados** | raiz de instalação | shim: REENVIO esperado `8BF0BFBB…4710` (CRLF, derivado) ou `882C90AF…B7FD` (LF); outro SHA = variante desconhecida (possivelmente o original) | ausentes; recuperáveis; ver achados F1/F2 |
| C2-07 | Prep **V004 original** da telemetria (nome provável `PREP_PERSEU_R4R9_C2_TELEMETRY_V004.py` ou ZIP `*TELEMETRY_V004*` sem `REENVIO`) | raízes de Downloads | sem SHA conhecido | **W-LOC**: o localizador lista todos os `*TELEMETRY_V004*` e rotula o REENVIO |
| C2-08 | Prerregistro H1/H3 **V004** corrigido | raízes de Downloads (padrões `*PREREG*V004*`, `*H1_H3*V004*`) | sem SHA conhecido | **W-LOC**; a origem precisa fixar a identidade |
| C2-09 | Certificado D1 com SHA `93092E9A8FB656CF5696087CE863C1F7B5F1601B52621993081A98A49B2F628D` | raízes de Downloads (padrão `D1_HOMOLOGATION_CERT_*`; o R4R8 usava `D1_HOMOLOGATION_CERT_V001_20260919.json`, SHA `CBA5B927…`) | `93092E9A…` | **W-HASH** |
| C2-10 | Recibos de aplicação do hotfix | `C:\Users\silvi\OneDrive\Downloads\PERSEU_R4R9_INMEMORY_RESUME_HOTFIX_R3_PREP_V003.json`; logs `PERSEU_R4R9_*.log`; recibos `PERSEU_R4R9_CONFIRMATORY_C1_C2_RECEIPT_*.json` | sem SHA | **W-LOC** |

## 3. Apoio e proveniência (não bloqueiam isoladamente)

Raiz de instalação: `MANIFEST_SHA256.json` (102 arquivos), `RUN_WINDOWS_R4R9_SEP2026.ps1`, `RUN_WINDOWS_R4R9_LOCAL_TESTS.ps1`, `RUN_WINDOWS_R4R9_CONFIRM_C1_202502.ps1` (`78830B5A…`), módulos/wrappers de hotfix R1 (`23AAE257…`/`6D6A7547…`), R2 (`07562BD1…`/`DE7506A9…`), R3 (`6F77DFA4…` derivado / wrapper sem SHA), telemetria V1–V3 (falhadas conhecidas; SHAs fixados).
Raiz `OneDrive\Downloads`: `PERSEU_R4R9_CONFIRMATORY_CAPABILITY_AUDIT_V002.json`, `PERSEU_R4R9_CONFIRMATORY_PREP_C1_C2_V001.json`, `PERSEU_R4R9_FIXTURE_FIX_AND_CONFIRMATORY_PREP_V002.json`, `PERSEU_R4R9_INMEMORY_RESUME_HOTFIX_R1_PREP_V001.json`, `…_R2_PREP_V002.json`, `PERSEU_R4R9_HOTFIX_IDENTITY_MIGRATION_PREFLIGHT_V001.json`, `PREP_PERSEU_R4R9_C2_TELEMETRY_V004.json`, `AUDIT_PERSEU_R4R9_TELEMETRY_GAPS_V001.json` + `_CONTEXT.txt`, `AUDIT_PERSEU_R4R9_TELEMETRY_SEMANTICS_V002.json` + `_CONTEXT.txt`.

## 4. Já fechados por este delta

- Identidades de 7 membros do R4R9 e de wrappers, hotfixes e telemetrias V1–V3 (constantes dos recuperados + evidência original).
- 3 membros do R4R9 com bytes recuperados por igualdade de SHA com o R4R8 (`perseu_exploratorio.py`, `test_perseu_exploratorio.py`, `BASELINE_R4R8/perseu_parallel_auto.py`).
- Identidade derivada e validada do módulo hotfix R3 (`6F77DFA4…`).
- Identidade exata do REENVIO e do shim que ele instala (derivada).
- Prerregistro V003 e a cadeia de auditoria/código vinculada a ele.

## 5. Recuperação somente leitura preparada

`dist/PERSEU_C2_SOURCE_LOCATOR_V001.ps1` (ver `README_WINDOWS_TARGET.md`, seção 6) verifica exatamente os itens acima: caminhos exatos, listagem apenas de primeiro nível das duas raízes de Downloads com padrões fixos, inventário limitado da raiz de instalação (sem seguir links/reparse), existência das pastas de run em `D:\PerseuRuns`, SHA-256 apenas de arquivos locais (nunca de placeholders de nuvem), rótulo de cada SHA contra o mapa de identidades conhecidas e veredito `C2_SOURCE_GATE`. Não move, não extrai, não executa e não grava fora da sua pasta de run.

Para itens W-LOC encontrados, o titular anexa à conversa de origem os bytes e o `LOCATOR_RESULT_LOCATE.json`; a origem fixa as identidades antes de qualquer sucessor.

---

Devolva este resultado ao ChatGPT, no projeto “Perseu MT5 (Astra)”, conversa “PERSEU_C2_DISK_SPACE_RECONCILIATION”. Anexe as evidências existentes e cole esta resposta.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Perseu MT5 (Astra) | THREAD=PERSEU_C2_DISK_SPACE_RECONCILIATION`
