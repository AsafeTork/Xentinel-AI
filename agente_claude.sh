#!/bin/bash

# Adiciona os caminhos comuns de binários ao PATH do script
export PATH=$PATH:/home/asafetork/.local/bin:/home/asafetork/.npm-global/bin:/usr/local/bin

while true
do
  echo "--- Iniciando Ciclo de Evolução: $(date) ---"
  
  # Tentativa de rodar o claude
  if command -v claude >/dev/null 2>&1; then
    claude "Analise o projeto Xentinel-AI-1. Implemente melhorias autônomas, evolua o código, faça commit e tente o deploy se houver um script configurado. Não pare por erros menores, tente corrigi-los."
  else
    echo "ERRO: O comando 'claude' ainda não foi encontrado no PATH."
    echo "Tentando rodar via npx como alternativa..."
    npx @anthropic-ai/claude-code "Analise o projeto Xentinel-AI-1 e evolua o código autonomamente."
  fi

  echo "--- Ciclo Finalizado em $(date). Reiniciando em 5 minutos... ---"
  sleep 300
done
