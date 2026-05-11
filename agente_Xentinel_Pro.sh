#!/bin/bash
CLAUDE_BIN="/usr/local/nvm/versions/node/v24.15.0/bin/claude"
export CLAUDE_CONFIG_DIR="/home/asafetork/.claude"
export TERM=xterm-256color

while true
do
  echo "--- [$(date)] Xentinel-AI: Iniciando Ciclo de Autonomia Total ---"
  
  # A flag mágica que resolve tudo:
  $CLAUDE_BIN --dangerously-skip-permissions -c "Siga o protocolo /home/asafetork/CLAUDE.md. Corrija o tests/conftest.py, execute os testes e atualize o progresso." < /dev/null

  echo "--- [$(date)] Ciclo finalizado. Reiniciando em 30s... ---"
  sleep 30
done
