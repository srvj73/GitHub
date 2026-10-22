# PEGASUS FULL 2026 — ENGENHARIA FINAL V008 — campanha única no Windows do titular

**Base:** Codex V003 físico (`CC37261C…`), byte-idêntico. **Pacote:** `PEGASUS_FULL_2026_ENGINEERING_FINAL_V008_20261022.zip` — SHA-256 `31713EBFE68EA046C16C2D5AD58036A5C35A192DB96C4A2A63136B8D26599510` (87.349.074 bytes). **Bootstrap:** `BOOTSTRAP_PEGASUS_FULL_2026_V008_PS51.ps1` — SHA-256 `DFBEC3C15218CFD6245E9CEAC1DA8BB77A481EB4C1EF4CD1A267A9086E7233B0`. **Manifesto interno:** `57250071B9B8FBB99F7EE7C8AEC5876BF7C0D4F72B32A3269A293AE021289EF5`.

Fronteiras: `G4=FROZEN · QS4=NO · FULL_ECONOMIC=NO · PHASE_C=FORBIDDEN · RESELECTION_2026=FORBIDDEN · RUN_RELEASED=NO · FULL_RELEASED=NO`. Nenhum modo executa economia; B/C/FULL bloqueiam antes de efeitos.

## Passo 1 — salvar os dois arquivos em `C:\Users\silvi\Downloads` (fora do OneDrive)

## Passo 2 — conferir os SHA (no `PS C:\Users\silvi>`)

```powershell
(Get-FileHash -LiteralPath C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008_PS51.ps1 -Algorithm SHA256).Hash -ceq 'DFBEC3C15218CFD6245E9CEAC1DA8BB77A481EB4C1EF4CD1A267A9086E7233B0'
(Get-FileHash -LiteralPath C:\Users\silvi\Downloads\PEGASUS_FULL_2026_ENGINEERING_FINAL_V008_20261022.zip -Algorithm SHA256).Hash -ceq '31713EBFE68EA046C16C2D5AD58036A5C35A192DB96C4A2A63136B8D26599510'
```

As duas linhas devem imprimir `True`. Se alguma imprimir `False`, não prossiga.

## Passo 3 — G0 (sem elevação)

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008_PS51.ps1 -Mode Verify
```

Confere PowerShell 5.1 Desktop, Python 3.14.7 pinado (SHA `4942B86A…`), ZIP e manifesto; autoextrai em pasta nova; executa `verify` do supervisor e do entrypoint V003, o probe de argv/exit (37) e prova que `run-b`, `run-c` e `run-full` bloqueiam (exit 2).

## Passo 4 — qualificação nativa integrada (pede UAC uma vez)

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008_PS51.ps1 -Mode QualifyNative
```

Cria `venv314` dentro da pasta da execução, instala numpy 2.4.6 **offline** pela wheel do próprio pacote (`--require-hashes`), e roda sob o supervisor, com Job e W04 reais, a qualificação sintética Q01–Q09 (A/B mono×multi, SAFE_STOP com Ctrl+C real no console privado do coordenador, retomada exactly-once, duas lacunas, `RUN.lock` órfão, journal duplicado, porta de evidência) e os negativos nativos Q10a–f (escritor externo, renomeação, escritor pré-existente, mapeamento gravável, novo nome, stream alternado, hardlink) e Q11 (linhagem do Job e breakaway negado). Elevação é necessária para o diário USN e o census de handles.

## Passo 5 (opcional, após PASS) — instalação controlada e rollback não destrutivo

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008_PS51.ps1 -Mode Install
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\silvi\Downloads\BOOTSTRAP_PEGASUS_FULL_2026_V008_PS51.ps1 -Mode Rollback
```

`Install` cria somente a raiz nova `C:\ProgramData\PEGASUS_FULL_2026_V008_57250071B9B8FBB9` (nunca sobrescreve), com DACL protegida, e verifica a árvore instalada. `Rollback` apenas renomeia essa raiz para `..._RETIRED_<data>`; nada é apagado e a raiz V007 não é tocada.

## Logs e retorno

Cada execução grava em `C:\Users\silvi\Downloads\PEGASUS_FULL_2026_RUNS\<MODO>_<yyyyMMdd_HHmmss_fff>_<PID>\RUN_LOG.txt`, qualquer que seja a pasta atual; a instância elevada usa a mesma pasta. Ao final é gerado `C:\Users\silvi\Downloads\PEGASUS_FULL_2026_RUNS\<MODO>_..._RESULT.zip`. Em falha, não repita automaticamente: a evidência fica preservada.

Devolva este resultado ao ChatGPT, no projeto 'Pegasus Original', conversa 'Implementação Runner Paralelo 14'. Anexe as evidências existentes (os `..._RESULT.zip` de Verify e QualifyNative) e cole a resposta.

`RESULT_RETURN_TO=ChatGPT | PROJECT=Pegasus Original | THREAD=Implementação Runner Paralelo 14`
