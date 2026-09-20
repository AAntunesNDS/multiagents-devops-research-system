# agentes-devops-iac

Experimento acadêmico: três abordagens do mesmo Agente DevOps (VPC, KMS, IAM,
SGs) que serve de fundação para microserviços futuros (S3, Glue, Step
Functions, Lambda, SQS, Athena).

Antes de qualquer tarefa, leia `RUNBOOK.md` (execução passo a passo) e
`COMPARATIVO.md` (decisões de design e por quê). Não repita o conteúdo deles
aqui — se este arquivo e o RUNBOOK divergirem, o RUNBOOK vence.

## Estrutura

- `abordagem-1-opentofu/` — HCL, backend S3+DynamoDB. Comandos: `tofu fmt -recursive`, `tofu validate`, `tofu plan -out=tfplan`, `tofu apply tfplan`, `tofu destroy`.
- `abordagem-2-cdk-python/` — CDK Python. Comandos: `ruff check .`, `pytest`, `cdk synth -c env=dev`, `cdk diff -c env=dev`, `cdk deploy --all -c env=dev`.
- `abordagem-3-serverless-agent/` — SAM (Lambda + Step Functions + EventBridge). Comandos: `ruff check src tests`, `PYTHONPATH=src pytest`, `sam validate --lint`, `sam build && sam deploy --config-env dev`, depois `./scripts/trigger.sh dev` (dry-run com `dry-run` como segundo argumento).
- `anexos/cdk-typescript/` — versão TS da Abordagem 2, só para comparação de linguagem. Não editar como parte do experimento principal.

## Regras invioláveis

- **Nunca** execute `tofu apply`, `tofu destroy`, `cdk deploy`, `cdk destroy`,
  `sam deploy` ou dispare a state machine de decommission sem confirmação
  explícita do usuário na mensagem atual. Rodar `plan`/`diff`/`synth`/`dry_run`
  não precisa de confirmação.
- **Nunca** rode destroy em `prod` — as três abordagens bloqueiam isso por
  código (`break_glass` ausente / step de bloqueio no workflow); não tente
  contornar editando o código para "testar".
- **Nunca** commite `.tfstate`, `.terraform/`, `cdk.out/`, `.venv/`, `samconfig.toml`
  com credenciais reais, nem arquivos sob `/tmp` com budget/notification.
- Ao editar IAM em qualquer abordagem, mantenha o padrão least-privilege já
  presente (sem `Action: "*"` novo sem `Resource` escopado, exceto onde a API
  não suporta ARN — casos já comentados no código).
- Ao editar a CMK de logs (`kms-logs` / `Logs` / `RegistryKey`), preserve a
  condição `kms:EncryptionContext:aws:logs:arn` — sem ela o CloudWatch Logs
  falha silenciosamente em produção. Ver RUNBOOK, armadilha 3.4(a).
- Custo: qualquer comando que crie NAT Gateway, CMK ou VPC Endpoint de
  interface é 💸. Avise antes de propor a execução, mesmo que o usuário já
  tenha confirmado a etapa maior.

## Convenções

- Comentários e documentação em português; nomes de recursos/variáveis em inglês.
- Um módulo/stack/handler por responsabilidade — não crie "god files".
- Toda mudança em `modules/`, `app_lib/stacks/` ou `src/handlers/` deve manter
  os três READMEs (`abordagem-*/README.md`) e o `COMPARATIVO.md` coerentes com
  o código. Se a mudança afeta LOC ou uma métrica citada no comparativo,
  atualize o número.
