# PEGASUS FULL 2026 — ENTREGA DE ENGENHARIA V008R8 (Opus, 22/10/2026)

**Projeto:** Pegasus Original · **Conversa:** Implementação Runner Paralelo 14 · **Papel:** implementador integrado (não auditor independente).

## O que mudou da R7 para a R8

Na campanha nativa R7 a cadeia parou em **Q10a**, caso que havia **passado na R6**. A prova primária do kernel funcionou (escritor externo negado; rename negado com `winerror=32`), mas o veredito W04 ficou `BLOCKED` por `CENSUS_TRUNCATED`: o census de handles do sistema — apenas **corroboração** — veio incompleto. O backend pinado (`8FEF1313…`, não alterável) declara a enumeração truncada quando mais de 8 consultas de nome travam numa mesma chamada; é intermitente e depende da carga de handles do Windows no momento. O contador é por chamada. Q11 (contenção real de breakaway, corrigida na R7) não chegou a rodar.

**Correção R8** (em `_census`; backend e V003 intocados): **nova tentativa limitada** do census (até 3). Se **todas** truncarem, o resultado segue truncado e o W04 continua **bloqueando** — nada foi afrouxado. As tentativas ficam registradas na evidência (`census.attempts`).

### Bytes finais (fora do ZIP)

| Artefato | SHA-256 |
|---|---|
| ZIP `…_FINAL_V008R8_20261022.zip` (2.946 membros) | `17A9FB12168F88CBF5CFC4454D211AB773C30E63AEEB95E529899597693DF411` |
| Manifesto final (M2) | `3BA34A1D1C6F6B1D2C55D6AFE53564E38813F2D1DFD988CFA7C93BE90A1B396C` |
| Manifesto testado (M1) | `9B5F91DC21BD98554FAA9B968BCBB02542AE046D0EA4C0538F054CD976E4C66A` |
| Bootstrap `BOOTSTRAP_…_V008R8_PS51.ps1` | `F499D48C0A93065E273D564ABEF8768CEAACEE5DC87A12B7CB79DFA120F56E0C` |
| Entry `CODE/pegasus_entry.py` | `F77B52669FF5D98BD9D8AC7AFBFB1483BF8CAE3AA7CB61F5242830BF3E43A7FB` |

**tested=packaged=delivered:** M1→M2 difere só por 31 arquivos de evidência sob `receipts/V008/offline_final/`; código e docs byte-idênticos. O extrato reconfere 2.945/2.945 arquivos; verify e 71/71 unit passam sobre os bytes entregues. Supersede V008R7 (`FDFCEDB5…`).

## Re-execução — a mesma campanha única (bootstrap R8)

A partir de `PS C:\Users\silvi>`, com o ZIP e o bootstrap R8 em `C:\Users\silvi\Downloads`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R8_PS51.ps1 -Mode Verify
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008R8_PS51.ps1 -Mode QualifyNative
```

Esta campanha precisa confirmar, numa mesma execução, Q10a–f (W04 nativo) e Q11 (contenção de breakaway). Se tudo passar, a `QualifyNative` termina com exit 0 e `native_completeness_evaluation=MET`. Devolva o `..._RESULT.zip`.

## Estado honesto dos gates

| Gate | Estado |
|---|---|
| G1 | PASS |
| G2 W04 full | Q10a–f nativos PASS na R6; census com nova tentativa (R8); confirmar na re-run |
| G3 W04 JIT/Job | 22/23 nativos PASS na R6; Q11 com contenção real (R7) pendente de execução nativa |
| G4 SAFE_STOP/retomada | Q03/Q04 nativos PASS (R6, R7) |
| G5 Windows nativo | re-run para confirmar 23/23 numa mesma execução |
| G6 CANDIDATE_COMPLETENESS | **NOT_PASS** — único bloqueio externo: re-execução nativa |

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
