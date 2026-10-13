# Especificação — `C2_SOURCE_LOCK_V001.json`

Documento emitido **pela origem** depois de recuperar e conferir as fontes exatas. É consumido por `PERSEU_C2_FULL_LAUNCHER_V001.ps1` (modos `Install`, `Preflight` e `Run`). A autoridade do lock é o SHA-256 que a origem informa e que o titular passa em `-SourceLockSha256`; um lock com SHA diferente é recusado.

## Invariantes compilados no lançador (o lock não pode alterá-los)

| Item | Valor |
|---|---|
| runner `perseu_parallel_auto.py` | `28DF85A4BF87B859230C931042C493CD6B4E57FE8698135C3D771C56E466E68C` |
| accel `perseu_r4r9_accel.py` | `042FA9CB7DB2DE26BD64F82B41B2A1977B05C65509E2038239BDC972E766F2E5` |
| core `perseu_exploratorio.py` | `A331F308182766C299B067BE2035EB071E01019C28A6C20DD6DF09B1AB92607F` |
| wrapper C2 simples `RUN_WINDOWS_R4R9_CONFIRM_C2_202608.ps1` | `53C8A1FBAA0C836DCB616789BD0C1D7264CCA6E97C8780E364FA05204E088ADD` |
| certificado D1 | `93092E9A8FB656CF5696087CE863C1F7B5F1601B52621993081A98A49B2F628D` |
| prerregistro proibido (V003) | `76833706F5E87F386071F35328D362FA0C5ABB124AC52CA1AA0840A603D7C408` |
| OUT | `D:\PerseuRuns\PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R9_CONFIRM_C2_202608` (deve estar ausente ou vazio) |
| faixa | `2026-08-01` .. `2026-08-31` (verificada também no texto do wrapper) |
| espaço livre na unidade do OUT | ≥ 100 GiB (ou o valor do lock, se maior) |

## Esquema

```json
{
  "schema": "PERSEU_C2_SOURCE_LOCK_V001",
  "install_root": "C:\\Users\\silvi\\OneDrive\\Downloads\\PACOTE_PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R9_20260921_CONFIRMATORY",
  "entry_wrapper": "RUN_WINDOWS_R4R9_CONFIRM_C2_202608.ps1",
  "out": "D:\\PerseuRuns\\PERSEU_EXPLORATORIO_V001R3_AUTOCPU_R4R9_CONFIRM_C2_202608",
  "range": ["2026-08-01", "2026-08-31"],
  "files": { "<caminho relativo à instalação>": "<SHA-256>", "...": "conjunto completo da instalação" },
  "d1_cert": { "path": "<caminho absoluto idêntico ao $D1Cert do wrapper>", "sha256": "93092E9A...", "restore_from_rel": "<opcional: relativo a -SourceDir>" },
  "prereg": { "version": "V004", "path": "<absoluto>", "sha256": "<SHA do V004 corrigido>" },
  "min_free_gb_out_drive": 100
}
```

Regras:

- `entry_wrapper` = `RUN_WINDOWS_R4R9_CONFIRM_C2_202608.ps1` (SHA invariante) **ou** `RUN_WINDOWS_R4R9_CONFIRM_C2_202608_TELEMETRY_V4.ps1`. Neste segundo caso, `files` deve fixar também `perseu_r4r9_telemetry_v4.py` e o wrapper V4, e a escolha entre a variante original e o REENVIO é decisão exclusiva da origem (achados F1/F2).
- `files` deve listar **o conjunto completo** de que o runner precisa (por exemplo, as 102 entradas do manifesto do ZIP R4R9 mais os wrappers derivados e eventuais hotfix/shim efetivamente aplicados). O modo `Install` copia exatamente esse conjunto e recusa qualquer caminho com `..` ou absoluto.
- O `$D1Cert` declarado dentro do wrapper deve ter exatamente uma atribuição, com caminho igual a `d1_cert.path`.
- O lançador nunca altera o lock, o wrapper ou o runner; após o `Run`, revalida todas as identidades.

---

Devolva este resultado ao ChatGPT, no projeto “Perseu MT5 (Astra)”, conversa “PERSEU_C2_DISK_SPACE_RECONCILIATION”. Anexe as evidências existentes e cole esta resposta.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Perseu MT5 (Astra) | THREAD=PERSEU_C2_DISK_SPACE_RECONCILIATION`
