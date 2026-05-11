import os
import time
import subprocess

def run_claude_cycle():
    print("🚀 Iniciando ciclo autônomo...")
    
    # Se houver log de erro, prioriza a correção
    if os.path.exists("render_log.txt") and os.path.getsize("render_log.txt") > 0:
        instruction = "Leia o arquivo render_log.txt, corrija o erro reportado, faça os testes e dê push."
    else:
        instruction = "Analise o TECH_DEBT.md ou SECURITY_AUDIT.md, implemente uma melhoria, teste e dê push."

    # Comando para invocar o Claude (ou o script do agente)
    # Aqui usamos o comando de execução do agente que configuramos
    subprocess.run(["git", "add", "."])
    # O comando abaixo simula o trabalho do agente
    os.system(f'echo "Processando: {instruction}" >> xentinel_execution.log')
    
    # Limpa o log de erro após o processamento para não entrar em loop no mesmo erro
    if os.path.exists("render_log.txt"):
        open("render_log.txt", "w").close()

while True:
    run_claude_cycle()
    time.sleep(10) # Pausa curta entre ciclos
