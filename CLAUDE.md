# Regras do titular para este repositório

- Responder em língua portuguesa formal.
- Scripts PowerShell assumem que o usuário os executa a partir de `PS C:\Users\silvi>`; não exigir `cd`.
- **Regra de log (registrada a pedido do titular):** todo script grava o log em uma pasta **absoluta e fixa definida pelo próprio script**, criada nova a cada execução, **independentemente da pasta atual** de onde o script é chamado. Nunca derivar o caminho do log do cwd (`Get-Location`, caminhos relativos). Padrão adotado na frente Perseu HD1:
  `C:\Users\silvi\OneDrive\Downloads\<FAMILIA>_RUNS\<MODO>_<yyyyMMdd_HHmmss_fff_PID>\RUN_LOG.txt`
- Para o projeto Perseu MT5 (Astra), a política capturada em `perseu_hd1_g0_v002/` (via handoff) rege codificação, BOM, exit codes, recibos e rota de retorno ao ChatGPT.
