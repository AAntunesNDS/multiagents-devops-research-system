# Abordagem 3 — Agente DevOps Serverless (Lambda + Step Functions + EventBridge)

O "cérebro" do agente é efêmero: não existe control plane de longa duração, nem
runner segurando um processo de `apply`. O provisionamento é uma **execução de
state machine** dentro da AWS, disparada por evento.

---

## 1. Visão geral da arquitetura

```
 GitHub Actions ──put-events──▶ EventBridge Bus (agentes-devops-agent-bus)
        │                              │ rule: base-infra.provision-requested
        │                              ▼
        │                   Step Functions (STANDARD) — provisioning
        │                     Plan ──▶ IsDryRun? ──▶ [Succeed]
        │                       │
        │                       ▼
        │                   Encryption (λ) ──▶ Network (λ) ──▶ WaitForNat ⟲ CheckNat (λ)
        │                                                          │
        │                                                          ▼
        │                                                      Routing (λ)
        │                                                          │
        │                                            ┌─────────────┴─────────────┐
        │                                     SecurityGroups (λ)          Identity (λ)
        │                                            └─────────────┬─────────────┘
        │                                                          ▼
        │                                                 PublishContract (λ)
        │                                                          │
        │                                        Catch ──▶ Rollback (λ) ──▶ SNS ──▶ Fail
        │
        └──dispatch──▶ Step Functions — decommission ──▶ Destroy (λ) ⟲ até remaining=0

  Estado: DynamoDB ResourceRegistry (1 item por recurso lógico, PITR, SSE-KMS)
  Drift:  EventBridge Scheduler (rate 1 day) ──▶ Drift (λ) ──▶ evento drift-detected
  Saída:  SSM /agentes-devops/<env>/base-infra-serverless  (mesmo contrato das outras abordagens)
```

## 2. Justificativa da escolha do modelo

1. **Sem peça de computação de longa duração.** Não há EC2 de control plane, runner self-hosted nem agente residente. O custo ocioso tende a zero e a superfície de ataque some junto com a execução.
2. **A orquestração é o artefato de governança.** O histórico da execução do Step Functions é um log imutável, por estado, com input e output de cada transição — auditoria mais rica que o log de um `apply` em terminal.
3. **Retry e compensação são declarativos.** `Retry`/`Catch` no ASL substituem try/except espalhado pelo código; o backoff exponencial para throttling da API EC2 é configuração, não código.
4. **Reação a eventos, não só a commits.** O mesmo agente responde a `provision-requested`, a schedule de drift e — se necessário — a eventos de CloudTrail sobre mudança manual. Nenhuma das outras abordagens reage sem um pipeline rodando.
5. **Contraste metodológico.** É a única das três que é imperativa: cada recurso é uma chamada de API explícita. Isso expõe, de forma mensurável, tudo o que o modelo declarativo entrega de graça.

## 3. Estrutura de pastas

```
abordagem-3-serverless-agent/
├── template.yaml                     # SAM: funções, state machines, bus, registry, IAM
├── samconfig.toml                    # parâmetros por ambiente
├── statemachine/
│   ├── provisioning.asl.json         # fluxo de criação (Plan → ... → Contract)
│   └── decommission.asl.json         # fluxo de destruição com confirmação
├── src/
│   ├── common/
│   │   ├── aws_clients.py            # boto3 com retry adaptativo, cache de cold start
│   │   ├── registry.py               # substituto do state file (DynamoDB)
│   │   ├── tagging.py                # identidade dos recursos (LogicalId)
│   │   ├── errors.py                 # RetryableError / FatalError / NotReadyError
│   │   └── logging_conf.py           # log JSON correlacionado por execution_id
│   ├── handlers/
│   │   ├── planner.py                # equivalente ao `tofu plan`
│   │   ├── encryption.py             # CMKs
│   │   ├── network.py                # VPC, IGW, subnets, NAT, EIP
│   │   ├── nat_poller.py             # polling do NAT (evita Lambda ociosa)
│   │   ├── routing.py                # route tables + gateway endpoints
│   │   ├── security_groups.py        # SGs com egress restrito
│   │   ├── identity.py               # roles de workload
│   │   ├── contract.py               # publica SSM + evento de conclusão
│   │   ├── rollback.py               # compensação da execução corrente
│   │   └── drift.py                  # detecção agendada
│   └── requirements.txt
├── scripts/{trigger.sh,destroy.sh}
└── tests/test_registry.py
```

## 4. Decisões de design

### 4.1 Tratamento de estado (o ponto central)

Não há state file. O registro vive em **DynamoDB**, um item por recurso lógico:

```
pk = "<env>#<logical_id>"
├── physical_id   vpc-0a1b2c3d
├── resource_type ec2:vpc
├── status        PENDING | CREATED | FAILED | DELETED
├── spec_hash     sha256(spec desejada)[:16]
├── order         20        → define a ordem inversa do destroy
└── execution_id  quem criou
```

Diferenças em relação ao state do OpenTofu:

| Aspecto | State file (Abordagem 1) | Registry (Abordagem 3) |
|---|---|---|
| Granularidade | Arquivo único por ambiente | Item por recurso |
| Concorrência | Lock global em DynamoDB | Escrita condicional por item — execuções paralelas em recursos distintos não se bloqueiam |
| Corrupção | Arquivo inteiro em risco | Impacto isolado a um item |
| Dependências | Grafo calculado pela ferramenta | Ordem codificada manualmente (`order`) |
| "O que existe agora" | `refresh` automático | Nenhum — precisa de `describe_*` escrito à mão (é o que faz `drift.py`) |

**Idempotência** é resolvida por `claim()`: se o recurso já está `CREATED` com o
mesmo `spec_hash`, a etapa vira NOOP; se o hash divergiu, o agente falha em vez
de tentar um replace silencioso. Se a spec mudou e o replace é desejado, ele é
explícito — destruir e recriar. Isso é uma limitação assumida: **o agente não
implementa update in-place**, que é exatamente a funcionalidade mais cara de se
escrever à mão e a que o modelo declarativo entrega de graça.

**Adoção de recursos órfãos:** se uma execução morre entre o `create_*` e o
`commit`, o recurso existe na AWS mas não no registro. Dois mecanismos cobrem
isso: `EntityAlreadyExists` tratado como adoção (ver `identity.py`) e tags
obrigatórias (`LogicalId`, `ManagedBy`) que permitem descoberta por
`describe_* --filters`.

### 4.2 Execução efêmera e o limite de 15 minutos

NAT Gateway leva 2–5 minutos. Segurar uma Lambda esperando é desperdício e
arriscado. O fluxo usa `Wait` + `Choice` + poller: a Lambda de rede cria e
retorna; a state machine faz o polling a cada 30 s. Custo de espera ≈ 0
(transições de Standard Workflow são cobradas, não o tempo parado).

### 4.3 IAM do próprio agente

| Função | Escopo |
|---|---|
| `encryption` | `kms:CreateKey` (não aceita ARN) + alias restrito ao prefixo do ambiente |
| `network` / `routing` / `security_groups` | APIs de criação do EC2 exigem `Resource: "*"`; mitigado por `Condition: aws:RequestedRegion` |
| `identity` | `iam:CreateRole`/`PutRolePolicy` restritos a `arn:aws:iam::<acct>:role/<env>-role-*` **e** com `PermissionsBoundary` anexada |
| `destroy` | Ações de delete, DLQ em SQS, `kms:ScheduleKeyDeletion` |
| Step Functions | Apenas `lambda:InvokeFunction` nas 9 funções + `sns:Publish` |

O `PermissionsBoundary` é o único mecanismo das três abordagens que impede,
estruturalmente, a role criada de escalar privilégio (nega `iam:CreateUser`,
`iam:CreateAccessKey`, `organizations:*`). É o análogo mais próximo do que a
plataforma corporativa aplica automaticamente nas contas.

### 4.4 Logging, retry e falhas

- Log JSON por evento, com `execution_id`, `logical_id` e `action` — consultável por CloudWatch Logs Insights.
- `Retry` no ASL com backoff exponencial para throttling da API; `RetryableError` e `NotReadyError` separam transitório de definitivo.
- `Catch` → `Rollback` → SNS → `Fail`. **Não existe rollback transacional**: a compensação é manual e best-effort, diferença estrutural relevante frente ao CloudFormation.
- X-Ray habilitado; alarme CloudWatch sobre `ExecutionsFailed`; DLQ na função de destroy.

### 4.5 Destruição controlada

State machine dedicada, com três barreiras: `confirm == "DESTROY-<env>"`,
`break_glass` obrigatório em prod e aprovação no GitHub Environment. O destroy
percorre o registro em ordem inversa de `order` e trata `DependencyViolation`
como `NotReadyError` — ENIs órfãs de VPC endpoint resolvem-se com espera, então
o ASL repete com backoff até `remaining == 0`.

## 5. Como executar

### Localmente

```bash
cd abordagem-3-serverless-agent
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

ruff check src tests
PYTHONPATH=src pytest -v          # testes de idempotência do registry (moto)
sam validate --lint
cfn-lint template.yaml

# Deploy do agente 💸 (custo ocioso ≈ US$ 0,60/mês: DynamoDB + CMK + logs)
sam build
sam deploy --config-env dev --guided   # informe AlertEmail; confirme a inscrição no SNS

# Plan (dry-run) — não cria nada
aws stepfunctions start-execution \
  --state-machine-arn <ProvisioningStateMachineArn> \
  --input '{"environment":"dev","dry_run":true}'

# Provisionamento real 💸 (VPC + NAT + CMKs ≈ US$ 36/mês)
./scripts/trigger.sh dev

# Contrato para os próximos agentes
aws ssm get-parameter --name /agentes-devops/dev/base-infra-serverless \
  --query Parameter.Value --output text | jq

# Destruição
./scripts/destroy.sh dev DESTROY-dev
```

### Via CI/CD

`.github/workflows/serverless-agent.yml` tem cinco jobs, refletindo a separação
que só existe nesta abordagem:

| Job | O que faz |
|---|---|
| `quality` | ruff, pytest, validação das ASL, `sam validate --lint`, cfn-lint, Checkov |
| `deploy-agent` | `sam build` + `sam deploy` — publica o **agente**, não a infraestrutura |
| `plan` | executa a state machine em `dry_run` e comenta o plano no PR |
| `provision` | publica o evento no EventBridge e acompanha a execução até `SUCCEEDED` 💸 |
| `destroy` | dispara a state machine de decommission com confirmação textual |

Secrets: `AWS_AGENT_DEPLOY_ROLE_ARN` (deploy do agente), `AWS_AGENT_INVOKE_ROLE_ARN`
(apenas `events:PutEvents` + `states:StartExecution`/`DescribeExecution`, mais as
leituras `states:ListStateMachines`/`ListExecutions` que o workflow usa para
descobrir o ARN da state machine).
Environments: `dev`, `prod`, `dev-provision`, `prod-provision`, `dev-destroy`,
`prod-destroy`.

O job `plan` exercita o agente **já implantado** no ambiente, não o código do PR —
consequência direta de separar "implantar o agente" de "executar o agente".

**Diferença de segurança relevante:** o runner do GitHub nunca recebe permissão
de criar VPC, KMS ou IAM. Ele só publica um evento. As permissões de
provisionamento vivem nas roles das Lambdas, dentro da conta — impossível
vazá-las por um workflow comprometido.

## 6. Vantagens e desvantagens

**Vantagens**
- Sem control plane de longa duração; custo ocioso ≈ US$ 0,60/mês.
- Menor superfície de credencial no CI: o runner só emite evento.
- Auditoria nativa: histórico de execução por estado, com input/output.
- Retry e backoff declarativos, resistentes a throttling da API.
- Reage a eventos e a schedule, não apenas a commits.
- Permissions boundary e escopo de IAM por função — granularidade que as outras duas não têm por padrão.
- Extensível para ações que nenhuma IaC declarativa cobre (validações de negócio, integração com ITSM, aprovação humana via `waitForTaskToken`).

**Desvantagens**
- **Reinventa a roda.** Dependências, idempotência, drift, ordem de destruição e adoção de órfãos são código seu. São ~1.400 linhas para fazer o que o `tofu plan/apply` já faz.
- **Sem update in-place.** Mudança de spec exige destroy + recreate explícito.
- **Sem rollback transacional.** A compensação é best-effort.
- **Sem `plan` fiel.** O planner compara hashes de spec, não o estado real da AWS — é mais fraco que `tofu plan` e que `cdk diff`.
- **Cobertura manual.** Cada novo tipo de recurso exige escrever create, delete e check de drift.
- **Paradoxo do bootstrap.** O agente serverless precisa de IaC declarativa (SAM/CloudFormation) para nascer — ele não se autoprovisiona.
- **Depuração distribuída.** Um erro atravessa Step Functions → Lambda → boto3 → API; correlacionar exige disciplina de log.

## 7. Análise crítica

Esta abordagem é a mais interessante academicamente e a menos recomendável como
ferramenta de IaC de propósito geral — e as duas coisas têm a mesma causa. Ao
escrever à mão o que Terraform e CloudFormation fazem internamente, ela expõe o
custo real do modelo declarativo: grafo de dependências, reconciliação, plano,
rollback e detecção de drift são exatamente os cinco itens que consumiram a
maior parte das 1.400 linhas — e, mesmo assim, entregues em versão reduzida.

O que ela entrega e as outras não: **ações**. Um agente serverless não está
limitado a criar recursos. Ele pode validar uma política de negócio antes de
provisionar, consultar um CMDB, pausar aguardando aprovação humana via
`waitForTaskToken`, remediar um drift automaticamente ou reagir a um evento de
CloudTrail em segundos. Nada disso tem expressão em HCL ou em CDK.

Daí a leitura correta do seu papel na arquitetura: **não é substituto do
OpenTofu/CDK — é a camada de automação em volta deles**. O desenho mais defensável
em produção é o agente serverless orquestrando execuções de IaC declarativa
(Step Functions chamando CodeBuild que roda `tofu apply`), combinando a
reconciliação madura de uma ferramenta pronta com a reatividade e a auditoria da
orquestração serverless. Implementá-lo como provisionador direto, via boto3,
como foi feito aqui, é a escolha certa para o experimento — porque é o que torna
a diferença entre os paradigmas mensurável — e a escolha errada para uma
plataforma real.
