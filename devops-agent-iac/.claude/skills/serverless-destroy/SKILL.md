---
name: serverless-destroy
description: Executa a destruicao controlada da Abordagem 3 (agente serverless). So use apos confirmacao explicita do usuario com a string DESTROY-<ambiente>.
allowed-tools: Bash(./scripts/destroy.sh*), Bash(aws stepfunctions*), Bash(aws dynamodb scan*)
---

# serverless-destroy

1. Exija que o usuário forneça literalmente `DESTROY-dev` (ou `DESTROY-prod`,
   o que é bloqueado por design — avise disso).
2. `export AGENT_IAC_CONFIRMED=yes`
3. `./scripts/destroy.sh dev DESTROY-dev`
4. Acompanhe até `SUCCEEDED`. Se `remaining > 0` ao final, a state machine já
   está reagendando — não intervenha manualmente, apenas informe o usuário.
5. Confira resíduos:
   ```
   aws dynamodb scan --table-name agentes-devops-agent-registry \
     --query 'Items[?status.S!=`DELETED`]'
   ```
   Itens restantes com `status=FAILED` precisam de investigação manual, não
   de novo destroy automático.
