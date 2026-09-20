---
name: serverless-trigger
description: Roda o dry-run (plan) do Agente Serverless (Abordagem 3) e, se confirmado, dispara o provisionamento real via evento. Use para "testar", "planejar" ou "provisionar" a infraestrutura da abordagem serverless.
allowed-tools: Bash(ruff:*), Bash(pytest:*), Bash(sam validate*), Bash(cfn-lint*), Bash(aws stepfunctions*), Bash(aws ssm get-parameter*), Bash(./scripts/trigger.sh*)
---

# serverless-trigger

Dentro de `abordagem-3-serverless-agent/`:

1. Qualidade: `ruff check src tests`, `PYTHONPATH=src pytest -v`, `sam validate --lint`, `cfn-lint template.yaml`.
2. Se o agente ainda não foi implantado (`aws stepfunctions list-state-machines`
   não retorna `agentes-devops-provisioning`), pare e informe que é preciso
   `sam build && sam deploy --config-env dev` primeiro — isso NÃO é coberto
   por esta skill porque é deploy do próprio agente, não da infraestrutura.
3. Dry-run:
   ```
   aws stepfunctions start-execution --state-machine-arn <arn> \
     --input '{"environment":"dev","dry_run":true}'
   ```
   Acompanhe até `SUCCEEDED`/`FAILED` e resuma o `summary` (create/noop/drift).
4. Só dispare o provisionamento real (`export AGENT_IAC_CONFIRMED=yes` +
   `./scripts/trigger.sh dev`) se o usuário confirmou explicitamente depois
   de ver o resultado do dry-run.

Ao concluir com sucesso, valide o contrato:
```
aws ssm get-parameter --name /agentes-devops/dev/base-infra-serverless \
  --query Parameter.Value --output text | jq
```

Se a execução falhar, use `aws stepfunctions get-execution-history
--execution-arn <arn> --reverse-order --max-items 20` para localizar o
estado que falhou antes de propor qualquer correção — as causas mais comuns
estão na tabela do RUNBOOK, seção 5.6.
