# Regras do titular para este repositório

- Responder em língua portuguesa formal.
- Scripts PowerShell assumem que o usuário os executa a partir de `PS C:\Users\silvi>`; não exigir `cd`.
- **Pasta padrão de downloads do titular (registrada a pedido do titular em 2026-10-21):** `C:\Users\silvi\Downloads`. É nela que o titular salva os scripts e pacotes e de onde os executa. `C:\Users\silvi\OneDrive\Downloads` é o local anterior; scripts novos não devem mais usá-lo, salvo para ler artefatos antigos.
- **Regra de log (registrada a pedido do titular):** todo script grava o log em uma pasta **absoluta e fixa definida pelo próprio script**, criada nova a cada execução, **independentemente da pasta atual** de onde o script é chamado. Nunca derivar o caminho do log do cwd (`Get-Location`, caminhos relativos). Padrão vigente:
  `C:\Users\silvi\Downloads\<FAMILIA>_RUNS\<MODO>_<yyyyMMdd_HHmmss_fff_PID>\RUN_LOG.txt`
- Para o projeto Perseu MT5 (Astra), a política capturada em `perseu_hd1_g0_v002/` (via handoff) rege codificação, BOM, exit codes, recibos e rota de retorno ao ChatGPT.
