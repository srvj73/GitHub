# CDT15 G4 — remoção da rota legada de ativação (SOURCE_ONLY)

Delta mínimo sobre o pacote SHA-256 0F5AAF9E0751610DDBF5B5924E5CF6D19CAE74B189D12CEDF4DCBE509936D34E.
Installer anterior SHA-256 E59280D6B661D83D8E1AB9F55BE7B4E6DFA83D1256649BD636F88F7AB3514247.
Installer modificado SHA-256 8D7B93D34858A1BDA10238E87C9B2FA0582F6A3A6C7F547486DA61957E93217F.

O `-ActivateMenu` continua **bloqueado ANTES de qualquer escrita**.
Foi removido o bloco legada inacessível que substituía `ACTIVE_DEPLOYMENT.json`
sem um escritor de MENU com journal COMMITTED e recuperação. O modo de
instalação **inativa** com `MENU_INSTALL_INTENT.json` permanece no código.

Nenhuma conexão oficial com o coordenador e nenhuma ativação está implementada.
A alteração não libera G4, G5, B06, B07, D4, D5 nem FULL.
A prova atual é análise estática dirigida, não PS 5.1 nativo nem execução do instalador.
O PRODUTIVO do usuário NÃO foi acessado ou modificado.
