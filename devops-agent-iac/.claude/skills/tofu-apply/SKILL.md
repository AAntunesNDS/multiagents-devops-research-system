---
name: tofu-apply
description: Aplica um plano OpenTofu ja revisado (Abordagem 1). Cria recursos reais com custo. So use apos o usuario ter visto o plano (via skill tofu-plan) e confirmado explicitamente nesta conversa que quer aplicar.
allowed-tools: Bash(tofu apply*), Bash(tofu output*), Bash(aws ssm get-parameter*)
---

# tofu-apply

Pre-condicoes, verifique antes de prosseguir:
- Existe um `tfplan` recente em `envs/dev/` (ou `envs/prod/`)? Se não, pare e
  peça para rodar a skill `tofu-plan` primeiro.
- O usuário confirmou explicitamente nesta conversa, depois de ver o plano?
  Se a confirmação foi genérica ("pode seguir com tudo"), pare e peça
  confirmação específica para este apply.
- Se o ambiente é `prod`: pare e exija confirmação adicional nomeando o
  ambiente explicitamente.

Execução:
1. `export AGENT_IAC_CONFIRMED=yes` (necessário para o hook `guard-destructive.sh` liberar o comando).
2. `tofu apply tfplan` dentro de `envs/<env>/`.
3. Ao concluir: `tofu output -json | jq` e `aws ssm get-parameter --name /agentes-devops/<env>/base-infra --query Parameter.Value --output text | jq` para confirmar o contrato publicado.
4. Reporte tempo de apply e quaisquer warnings.

Se o apply falhar, NÃO tente "consertar e reaplicar" sozinho em recursos de
IAM/KMS sem mostrar o diff da mudança proposta primeiro — essas são as
armadilhas documentadas no RUNBOOK (seção 3.4).
