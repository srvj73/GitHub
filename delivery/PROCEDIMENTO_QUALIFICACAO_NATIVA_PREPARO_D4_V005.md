# Procedimento nativo único — qualificação do produtor da observação do predecessor D4 (GAP-05), V005 congelado

**Executor:** titular, no próprio Windows.
**Retorno:** diretamente ao Opus.
**Escopo:** somente laboratório próprio.

Neste procedimento:
- **não** se lê nem se escreve a produção;
- **não** se executam B06, B07, D4/D5, canário nem FULL;
- **não** se instala nada.

## Arquivos (em `C:\Users\silvi\Downloads`)

| Arquivo | SHA-256 |
|---|---|
| `RUN_CDT21_V005_PREPARO_D4_20261022.ps1` (lançador único, autoextraível) | `40D8961B75B5385E42F9312A008D2B46E297ED8F00E7E59DADB55BDA3EA6488F` |
| `CDT21_FINAL_PACKAGE_V005_20261022.zip` (já presente; não alterado) | `E3F1F4790D6AE6E5639F137FAEE3E91B2B8E6FFB51A95F18078DF734553CB145` |

O produtor `CDT21_D4_PREDECESSOR_OBSERVER.py` está embutido no lançador, com SHA-256 `D724908C82573A6618DD365CFFECF8CCC4502FAEFEE00EB8D446422F4DC8EF1F`.

O código congelado que o produtor usa é extraído do ZIP do V005. Cada membro é conferido contra o `RUNTIME_CODE_MANIFEST` do pacote e contra o pin do lançador.

## Antes de executar

- Feche **todos** os programas Python: VS Code com extensão Python, Jupyter, ferramentas próprias e afins.
- Feche janelas e editores cuja linha de comando cite TICKSTORE.

O consumidor congelado recusa outro processo Python e qualquer processo com o marcador. A qualificação prova justamente essas recusas, mas o caso positivo exige o ambiente limpo.

## Execução

A partir de `PS C:\Users\silvi>`:

```powershell
Get-FileHash -Algorithm SHA256 "C:\Users\silvi\Downloads\RUN_CDT21_V005_PREPARO_D4_20261022.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\Downloads\RUN_CDT21_V005_PREPARO_D4_20261022.ps1"
```

A etapa padrão é `Qualificar`. O lançador pede elevação por UAC e leva cerca de 1 minuto. Ele cria um laboratório em `%LOCALAPPDATA%\CDT21_PREPARO_D4_V005\LAB_<stamp>` e executa:

| Caso | O que prova (nativamente) | Esperado |
|---|---|---|
| Q1 | Observação completa sobre um predecessor sintético do laboratório. Os consumidores congelados admitem a evidência: `reconcile` e `fresh_predecessor` do bootstrap, com leituras Win32 e a checagem real do mutex de censo | `PASS_FRESH_PREDECESSOR_EVIDENCE` |
| Q2 | Lock `TICKSTORE_WRITER.lock` presente | recusa `WRITER_LOCK_ABSENCE_NOT_PROVEN` |
| Q3 | Outro processo Python vivo (o próprio lançador inicia um processo de 2 minutos e o encerra) | recusa `UNCLASSIFIED_PYTHON_PROCESS` |
| Q4 | Processo com o marcador na linha de comando (idem) | recusa `RECOVERY_PROCESS_OBSERVED` |
| Q5 | Raiz recriada (outra identidade de arquivo NTFS) | recusa `ROOT_IDENTITY` |

Na mesma execução, o lançador também verifica a autoextração do instalador congelado, sem instalar.

**Resultado esperado:** `OBSERVER_STATUS=PASS_NATIVE_LAB_QUALIFICATION` e `EXIT_CODE=0`.

## Log e retorno

- **Log:** `C:\Users\silvi\Downloads\CDT21_PREPARO_D4_V005_RUNS\QUALIFICAR_<yyyyMMdd_HHmmss_fff_PID>\RUN_LOG.txt` (e `RUN_LOG_ELEVATED.txt`).
- **Retorno:** `ENVIAR_AO_OPUS_CDT21_PREPARO_D4_V005_<stamp>.zip`, na mesma pasta, enviado diretamente ao Opus junto com o log colado.

O retorno contém:
- os logs;
- o recibo de qualificação;
- as três evidências do caso Q1 (observação do laboratório).

Por minimização, a lista de processos traz a linha de comando completa somente dos interpretadores e dos processos com o marcador; dos demais, apenas o SHA-256 e o tamanho.

## Uso operacional futuro (não executar agora)

- **Momento:** no D4, depois da B07 e a menos de 5 minutos da admissão.
- **Pasta:** `-EvidenceDir` deve ser igual ao `PredecessorEvidenceDir` da INSTANCE. Precisa ser absoluta, fora de `D:\Base CSV` e sem a palavra TICKSTORE. Sugestão: `C:\Users\silvi\AppData\Local\CDT21_D4_PREDECESSOR_EVIDENCE`.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\Downloads\RUN_CDT21_V005_PREPARO_D4_20261022.ps1" -Etapa Observar -EvidenceDir "<PredecessorEvidenceDir>" -AutorizoLeituraProducao
```

A produção é lida somente para leitura. Evidências anteriores na pasta são movidas para `HISTORICO_OBSERVACOES`, nunca apagadas.

- **Antes da observação:** se o último boot for anterior ao `STARTED` do predecessor, o consumidor recusa (`LATER_BOOT_NOT_PROVEN`). Use **Reiniciar**, e não Desligar: com a Inicialização Rápida, Desligar não reinicia o kernel.

**Instalação (substitui a extração manual do P4):**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\silvi\Downloads\RUN_CDT21_V005_PREPARO_D4_20261022.ps1" -Etapa Instalar
```
