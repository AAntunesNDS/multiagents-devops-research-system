# RUNBOOK — Provisionamento das três abordagens

Sequência de execução, verificação e armadilhas. Sem conceitos básicos.

## Etapa 0 — Usando este repositório com Claude Code

O repositório já traz `CLAUDE.md` + `.claude/` (settings, hooks, skills,
subagents). Isso é o que carrega o contexto deste chat para o Claude Code
local — memória de conversa não atravessa, arquivo sim.

```bash
cd devops-agent-iac
claude                    # a conta logada na CLI é irrelevante; o contexto vem dos arquivos
```

- `.claude/settings.json` — permissions (allow/ask/deny) e o hook `PreToolUse`
  que bloqueia `apply`/`deploy`/`destroy`/`start-execution` sem
  `AGENT_IAC_CONFIRMED=yes` na sessão. `permissions.deny` sozinho tem bugs
  documentados com comandos compostos; o hook é o bloqueio de verdade.
- `.claude/skills/` — `tofu-plan`, `tofu-apply`, `cdk-diff`, `serverless-trigger`,
  `serverless-destroy`, `cost-check`. Invoque por nome ("rode a skill
  tofu-plan") ou deixe o Claude descobrir pela descrição.
- `.claude/agents/` — `iac-security-reviewer` e `cost-reviewer`, subagents
  somente-leitura que rodam isolados antes de qualquer operação com 💸.
- `.claude/settings.local.json.example` — copie para `settings.local.json`
  (gitignored) e ponha seu `AWS_PROFILE` pessoal ali, não no `settings.json`
  compartilhado.

Se quiser usar a **mesma conta** deste chat na CLI (não obrigatório):
`CLAUDE_CONFIG_DIR=~/.claude-agentes-devops claude` isola credenciais em um
diretório à parte, sem afetar sua configuração padrão.

**Convenção de custo:** comandos marcados com 💸 criam recursos cobrados.
Cada abordagem provisionada custa ≈ **US$ 1,20/dia** (NAT Gateway + 3 CMKs).
As três juntas são três VPCs com NAT — rode uma de cada vez.

---

## Etapa 1 — Pré-requisitos

| Ferramenta | Versão mínima | Instalação | Usada em |
|---|---|---|---|
| OpenTofu | 1.8.0 | `brew install opentofu` / `snap install --classic opentofu` | Abordagem 1 |
| AWS CLI | v2.15 | instalador oficial v2 | Todas |
| Python | 3.11 | pyenv / distro | Abordagens 2 e 3 |
| Node.js | 20 LTS | `nvm install 20` | Abordagem 2 (CDK CLI roda em Node mesmo com app Python) |
| AWS SAM CLI | 1.120 | `brew install aws-sam-cli` | Abordagem 3 |
| jq | 1.6 | gerenciador do SO | Todas |
| TFLint | 0.52 | `brew install tflint` | Abordagem 1 |
| Checkov | 3.2 | `pipx install checkov` | Todas |
| cfn-lint | 1.8 | `pipx install cfn-lint` | Abordagem 3 |
| Infracost | 0.10 | `brew install infracost` + `infracost auth login` | Abordagens 1 e 2 |

```bash
tofu version && aws --version && python3.11 -V && node -v && sam --version && jq --version
```

**CDK CLI não deve ser global em versão divergente.** O projeto Python fixa
`aws-cdk-lib==2.150.0`; instale o CLI exatamente igual
(`npm install -g aws-cdk@2.150.0`) ou terá `Cloud assembly schema version
mismatch` — erro nº 1 de CDK.

---

## Etapa 2 — Configuração AWS mínima

### 2.1 Identidade

Conta sandbox isolada. Não rode em conta com workloads.

```bash
aws configure sso --profile lab-devops
aws sso login --profile lab-devops
export AWS_PROFILE=lab-devops
export AWS_REGION=us-east-1
aws sts get-caller-identity      # validação obrigatória antes de qualquer apply
```

**Permissões:** `AdministratorAccess` na sessão de bootstrap das três abordagens
(criam OIDC provider, CMKs, roles e policies). Depois do bootstrap, o deploy usa
as roles OIDC criadas pelo próprio código.

### 2.2 O que muda em relação ao template corporativo

| Responsabilidade | Template corporativo | Aqui |
|---|---|---|
| Backend de state | Provisionado pela plataforma | Abordagem 1: você cria. Abordagem 2: não existe. Abordagem 3: você **projeta** o modelo de estado |
| Permission boundary / SCP | Aplicado na conta | Ausente nas Abordagens 1 e 2; implementado manualmente na 3 |
| Naming e tagging | Enforced por policy | `default_tags` / `Tags.of(app)` / `common/tagging.py` |
| Registry de módulos aprovados | Módulos golden versionados | Módulos locais, sem versionamento semântico |
| Drift detection | Job central | `tofu plan`, `detect-stack-drift`, ou Lambda agendada |
| Guardrails de custo | Budget da unidade | Você cria o budget abaixo |

### 2.3 Budget alert (sem custo — faça antes do primeiro apply)

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

cat > /tmp/budget.json <<EOF
{ "BudgetName": "lab-devops-monthly",
  "BudgetLimit": { "Amount": "80", "Unit": "USD" },
  "TimeUnit": "MONTHLY", "BudgetType": "COST" }
EOF

cat > /tmp/notifications.json <<EOF
[{ "Notification": { "NotificationType": "ACTUAL", "ComparisonOperator": "GREATER_THAN",
     "Threshold": 50, "ThresholdType": "PERCENTAGE" },
   "Subscribers": [{ "SubscriptionType": "EMAIL", "Address": "SEU-EMAIL@dominio.com" }] }]
EOF

aws budgets create-budget --account-id "$ACCOUNT_ID" \
  --budget file:///tmp/budget.json \
  --notifications-with-subscribers file:///tmp/notifications.json
```

### 2.4 Quotas que mordem

```bash
# EIPs: default 5/região. Três abordagens + resíduos estouram facilmente.
aws service-quotas get-service-quota --service-code ec2 --quota-code L-0263D0A3
# VPCs: default 5/região.
aws service-quotas get-service-quota --service-code vpc --quota-code L-F678F1CE
```

**Cada abordagem usa um CIDR distinto** (10.20, 10.22, 10.23) justamente para
poderem coexistir sem conflito de peering futuro.

---

## Etapa 3 — Abordagem 1 (OpenTofu)

### 3.1 Preparação

```bash
cd devops-agent-iac/abordagem-1-opentofu
```

Ajuste antes de qualquer comando:
- `envs/dev/terraform.tfvars` → `github_repository` real.
- `bootstrap/main.tf` → `project_name`, se `<project>-tfstate-<account_id>` passar de 63 caracteres.

### 3.2 Bootstrap do backend 💸 (~US$ 1,07/mês)

```bash
cd bootstrap
tofu init && tofu plan        # esperado: 8 a 10 recursos
tofu apply                    # 💸
tofu output                   # anote state_bucket e lock_table
```

O `terraform.tfstate` local do bootstrap é um ativo: não commitar, não perder.

### 3.3 Init, validação e apply 💸

```bash
cd ../envs/dev
tofu init \
  -backend-config="bucket=<state_bucket>" \
  -backend-config="dynamodb_table=<lock_table>" \
  -backend-config="region=us-east-1"

cd ../.. && tofu fmt -recursive && tflint --recursive --minimum-failure-severity=error
checkov -d . --framework terraform --compact

cd envs/dev
tofu plan -out=tfplan
tofu show -json tfplan | jq '.resource_changes | length'   # ~90 recursos
infracost breakdown --path tfplan --format table
tofu apply tfplan                                          # 💸 6 a 9 min
```

**O que observar no plan, em ordem de importância:**
1. `aws_nat_gateway` = 1 em dev. Se aparecer 2+, `single_nat_gateway` não foi lido.
2. `aws_vpc_endpoint.interface` = 0 em dev (cada um custa ~US$ 7,30/mês/AZ).
3. `aws_kms_key` = 3. Cada CMK: US$ 1/mês e **7 dias mínimos** para exclusão.
4. `aws_iam_role_policy` — leia o JSON renderizado. É onde o least privilege vive ou morre.
5. `aws_ssm_parameter.platform_contract` — o contrato dos próximos agentes.

### 3.4 Armadilhas de IAM / KMS / policies

**(a) CMK de logs × CloudWatch Logs — falha mais provável do primeiro apply.**
O CW Logs exige, na key policy, condição sobre o contexto de criptografia.
A policy do módulo usa `aws:SourceAccount` e pode falhar com:

```
InvalidParameterException: The specified KMS key does not exist or is not allowed to be used with LogGroup
```

Correção em `modules/kms/main.tf`, no statement `AllowServiceUse` da chave de logs:

```hcl
condition {
  test     = "ArnLike"
  variable = "kms:EncryptionContext:aws:logs:arn"
  values   = ["arn:aws:logs:${var.region}:${data.aws_caller_identity.current.account_id}:log-group:*"]
}
```

Desbloqueio rápido para validar o resto: `flow_logs_kms_key_arn = null` no módulo `vpc`.
As Abordagens 2 e 3 já nascem com a condição correta — compare os três arquivos,
é um bom exemplo de "o que a abstração lembra por você".

**(b) OIDC provider já existente** → `EntityAlreadyExists`. Ajuste:
```hcl
github_oidc = { enabled = true, create_oidc_provider = false, ... }
```

**(c) Dependência circular KMS ⇄ IAM.** Não adicione `additional_role_arns = module.iam.workload_role_arns` no módulo KMS: fecha ciclo no grafo. O design resolve pelo lado IAM de propósito.

**(d) PassRole.** Ao adicionar serviço novo (ex.: `ecs-tasks.amazonaws.com`), o apply falha com `AccessDenied ... iam:PassRole`. Ponto único: statement `PassRoleToServices` em `modules/iam/main.tf`.

**(e) Alias de KMS órfão** após apply parcial → `AlreadyExistsException`. Resolva com `aws kms delete-alias --alias-name alias/<nome>`.

### 3.5 Validação e destroy

```bash
tofu output -json | jq
aws ssm get-parameter --name /agentes-devops/dev/base-infra --query Parameter.Value --output text | jq
tofu destroy                 # ~5 min
```

`DependencyViolation` na subnet/SG = ENI órfã. Liste com
`aws ec2 describe-network-interfaces --filters Name=vpc-id,Values=$VPC` e delete.
Lock preso após Ctrl+C: `tofu force-unlock <LOCK_ID>`.

---

## Etapa 4 — Abordagem 2 (AWS CDK Python)

### 4.1 Preparação

```bash
cd ../../abordagem-2-cdk-python
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
npm install -g aws-cdk@2.150.0
```

Ajuste `cdk.json`:
- `environments.dev.account` → account ID real (o placeholder `111111111111` faz o synth falhar com `Need to perform AWS calls for account 111111111111`).
- `githubRepository` → seu `owner/repo`.

### 4.2 Bootstrap 💸 (~US$ 1,10/mês)

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
cdk bootstrap aws://$ACCOUNT_ID/us-east-1
```

Cria a stack `CDKToolkit`: bucket de assets, ECR, CMK e 5 roles `cdk-hnb659fds-*`.
É o análogo do `bootstrap/` da Abordagem 1, com a diferença de que o ciclo de
vida é da AWS — você não versiona nem revisa esse código.

### 4.3 Build, teste e synth (sem custo)

```bash
ruff check .
PYTHONPATH=. pytest -v
cdk synth -c env=dev --quiet
```

**Gotcha previsível: `cdk-nag` falha o synth.** Erros esperados: `AwsSolutions-IAM4`
(managed policy `AWSLambdaVPCAccessExecutionRole`), `AwsSolutions-IAM5` (wildcards
nas ações de ENI), `AwsSolutions-S3-1` (server access logs). Comportamento
correto — trate com supressão documentada:

```python
from cdk_nag import NagSuppressions

NagSuppressions.add_resource_suppressions(
    self.lambda_role,
    [
        {"id": "AwsSolutions-IAM4", "reason": "Managed policy AWS para ENI em VPC"},
        {"id": "AwsSolutions-IAM5", "reason": "ec2:*NetworkInterface nao suporta ARN"},
    ],
    apply_to_children=True,
)
```

Para destravar e seguir: comente `cdk.Aspects.of(app).add(...)` em `app.py`,
conclua o deploy, reative e trate as supressões uma a uma.

### 4.4 Diff e deploy 💸

```bash
cdk diff -c env=dev
cdk deploy --all -c env=dev --outputs-file cdk-outputs.json    # 💸 9 a 14 min
```

Ordem observada: `Encryption` → `Network` + `Data` (paralelas) → `Iam`. Você não
declarou isso; veio do grafo de referências.

Revise IAM no template sintetizado, não no Python:

```bash
jq '.Resources | to_entries[] | select(.value.Type=="AWS::IAM::Policy")
    | .value.Properties.PolicyDocument.Statement' cdk.out/BaseInfra-dev-Iam.template.json
```

### 4.5 Erros comuns

| Erro | Causa | Resolução |
|---|---|---|
| `Cloud assembly schema version mismatch` | CLI ≠ `aws-cdk-lib` | `npm i -g aws-cdk@2.150.0` |
| `Need to perform AWS calls for account X` | `account` do `cdk.json` errado | corrija o `cdk.json` |
| `This stack uses assets, so the toolkit stack must be deployed` | bootstrap ausente | `cdk bootstrap` |
| `UPDATE_ROLLBACK_FAILED` | falha durante update | `aws cloudformation continue-update-rollback --stack-name <s>` |
| `jsii.errors.JSIIError: Value is not a ...` | enum errado (ex.: `RetentionDays`) | confira o mapeamento em `network_stack.py` |
| Deploy travado em `DELETE_IN_PROGRESS` de ENI | Lambda `auto_delete_objects` em VPC | aguarde até 20 min; limitação do CFN |

### 4.6 Validação e destroy

```bash
aws ssm get-parameter --name /agentes-devops/dev/base-infra-cdk-py \
  --query Parameter.Value --output text | jq
cdk destroy --all -c env=dev
```

Em `prod` buckets e CMKs são `RETAIN` — destroy deixa recursos cobrando.

---

## Etapa 5 — Abordagem 3 (Agente Serverless)

Aqui há **duas operações distintas**, e confundi-las é o erro conceitual mais
comum: (a) implantar o agente e (b) executar o agente.

### 5.1 Preparação

```bash
cd ../abordagem-3-serverless-agent
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
```

### 5.2 Qualidade (sem custo)

```bash
ruff check src tests
PYTHONPATH=src pytest -v      # idempotência do registry, ordem do destroy
sam validate --lint --region us-east-1
cfn-lint template.yaml
```

Os testes usam `moto`; nada toca a AWS.

### 5.3 Deploy do agente 💸 (~US$ 0,60/mês ocioso)

```bash
sam build
sam deploy --config-env dev --guided    # informe AlertEmail
```

Confirme a inscrição do SNS no e-mail, senão alertas de falha somem silenciosamente.

O que é criado: 9 Lambdas (arm64), 2 state machines, EventBridge bus, DynamoDB
`agentes-devops-agent-registry` (PITR + SSE-KMS), CMK, SNS, DLQ, permissions
boundary e a spec em SSM. **Nenhuma infraestrutura de rede ainda.**

### 5.4 Plan (dry-run) — não cria nada

```bash
SM=$(aws stepfunctions list-state-machines \
  --query "stateMachines[?name=='agentes-devops-provisioning'].stateMachineArn | [0]" --output text)

aws stepfunctions start-execution --state-machine-arn "$SM" \
  --input '{"environment":"dev","dry_run":true}'
```

O output traz `summary` com contagem de CREATE / NOOP / DRIFT. É o equivalente
mais próximo do `tofu plan` — e deliberadamente mais fraco: compara hash de spec
contra o registry, não o estado real na AWS.

### 5.5 Provisionamento real 💸 (VPC + NAT + CMKs ≈ US$ 36/mês)

```bash
./scripts/trigger.sh dev           # publica evento e acompanha até terminar
```

**O que observar no console do Step Functions** (é o artefato mais didático das
três abordagens — vale um print para o trabalho):

1. `Encryption` → `Network` → loop `WaitForNat` ⟲ `CheckNat` (2 a 5 min de polling)
2. `ParallelPolicies`: SGs e roles criadas concorrentemente
3. `PublishContract` → `Success`
4. Input/output de cada estado no histórico — auditoria por transição

```bash
aws ssm get-parameter --name /agentes-devops/dev/base-infra-serverless \
  --query Parameter.Value --output text | jq

aws dynamodb scan --table-name agentes-devops-agent-registry \
  --query 'Items[].{id:logical_id.S,status:status.S,phys:physical_id.S}' --output table
```

Esse `scan` é o "state file" desta abordagem. Compare com
`tofu state list` — a diferença de granularidade fica evidente.

### 5.6 Erros comuns e como resolver rápido

| Sintoma | Causa | Resolução |
|---|---|---|
| Execução falha em `Encryption` com `AccessDenied` em `kms:CreateKey` | Policy da função no `template.yaml` | `CreateKey` não aceita ARN; confira se o statement está com `Resource: '*'` |
| `AddressLimitExceeded` no `Network` | Quota de 5 EIPs | libere EIPs órfãos (`describe-addresses`) ou peça aumento |
| `FatalError: spec divergente` | Você mudou `vpc_cidr` na spec após criar | o agente **não faz update in-place**: destrua e recrie explicitamente |
| `FatalError: Execucao concorrente detectada` | Duas execuções simultâneas | é o comportamento correto do `claim()`; aguarde a primeira terminar |
| NAT fica em `PENDING` além de 10 min | Subnet pública sem rota para IGW, ou capacidade da AZ | verifique o IGW; o `CheckNat` devolve `FAILED` e dispara `Rollback` |
| `Rollback` roda mas recursos permanecem | Compensação é best-effort por design | use `./scripts/destroy.sh dev DESTROY-dev` |
| Nada acontece após `put-events` | Regra do EventBridge não casou o `DetailType` | confira `base-infra.provision-requested` exato; teste com `start-execution` direto |
| Lambda `identity` falha com `AccessDenied` em `iam:CreateRole` | Nome da role fora de `<env>-role-*` | o escopo é proposital; ajuste o padrão de nome, não a policy |

Diagnóstico padrão (correlação por `execution_id`):

```bash
aws logs start-query \
  --log-group-name /aws/lambda/agentes-devops-agent-network \
  --start-time $(date -d '1 hour ago' +%s) --end-time $(date +%s) \
  --query-string 'fields @timestamp, logical_id, action, physical_id | sort @timestamp desc | limit 50'
```

### 5.7 Destruição controlada

```bash
./scripts/destroy.sh dev DESTROY-dev
```

A state machine percorre o registry em ordem inversa de `order` e repete com
backoff enquanto houver `DependencyViolation` (ENIs órfãs). CMKs entram em
exclusão agendada de 7 dias — continuam custando US$ 1/mês nesse período.

Para remover também o agente:

```bash
sam delete --stack-name agentes-devops-serverless-agent-dev
# A tabela do registry tem DeletionPolicy: Retain — remova manualmente se quiser:
aws dynamodb delete-table --table-name agentes-devops-agent-registry
```

---

## Etapa 6 — Ordem recomendada e verificação de resíduos

1. Budget alert + `aws sts get-caller-identity`
2. Abordagem 1: bootstrap → apply → inspecionar SSM → **destroy**
3. Abordagem 2: bootstrap → deploy → inspecionar SSM → **destroy**
4. Abordagem 3: `sam deploy` → dry-run → provision → inspecionar registry e SSM → **destroy**
5. Só então rode duas em paralelo, se quiser comparar tempos (💸 dobrado)

Conferência final — NAT Gateway e EIP não associado continuam cobrando após
destroy incompleto:

```bash
aws ec2 describe-nat-gateways --query 'NatGateways[?State==`available`].[NatGatewayId,VpcId]'
aws ec2 describe-addresses --query 'Addresses[?AssociationId==null].[AllocationId,PublicIp]'
aws ec2 describe-vpcs --filters Name=tag:Project,Values=agentes-devops --query 'Vpcs[].VpcId'
aws kms list-aliases --query 'Aliases[?starts_with(AliasName, `alias/agentes-devops`) || starts_with(AliasName, `alias/dev-`)].AliasName'
aws s3 ls | grep agentes-devops
aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
  --query 'StackSummaries[?contains(StackName, `agentes-devops`)].StackName'
```

---

## Etapa 7 — O que medir para o trabalho acadêmico

Colete durante as execuções acima; os três pipelines já instrumentam os tempos:

| Métrica | Onde obter |
|---|---|
| Tempo de plan/diff/dry-run | Comentário do PR (os três workflows publicam) |
| Tempo de apply/deploy/provision | Job summary do GitHub Actions |
| Nº de recursos criados | `tofu show -json`, `cdk.out/*.template.json`, `dynamodb scan` |
| LOC por abordagem | `wc -l` (valores de referência no COMPARATIVO.md) |
| Falhas até o primeiro sucesso | Contagem manual — é a métrica que mais diferencia a Abordagem 3 |
| Custo real | Cost Explorer filtrado por tag `Project=agentes-devops`, agrupado por `ManagedBy` |

A tag `ManagedBy` tem valor distinto em cada abordagem (`OpenTofu`,
`AWS-CDK-Python`, `serverless-devops-agent`), então o Cost Explorer separa os
custos das três automaticamente — use isso para substituir as estimativas do
COMPARATIVO por números medidos.
