#!/bin/bash
while true; do
  echo "--- ⚠️ MODO DANGEROUSLY-SKIP-PERMISSIONS ATIVADO: $(date) ---"
  
  # Garante permissões totais no diretório
  chmod -R 777 ~/Xentinel-AI-1
  
  # O Claude agora opera sem travas e sem perguntas
  claude --dangerously-skip-permissions "Analise render_log.txt primeiro. Se vazio, busque dívida técnica em 'services/' e 'models/'. Corrija, teste, atualize o PROJECT_PROGRESS.md e dê git push. Repita até a perfeição. Não pare por nada."

  # Reseta o log de erro
  > render_log.txt
  
  echo "--- ✅ Ciclo concluído com sucesso total. Reiniciando... ---"
  sleep 5
done
