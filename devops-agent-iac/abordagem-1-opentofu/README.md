# Abordagem 1 — Agente DevOps com OpenTofu (HCL)

> Camada de infraestrutura base na AWS provisionada via OpenTofu, com backend
> remoto S3 + DynamoDB e esteira de CI/CD em GitHub Actions.

---

## 1. Visão geral da arquitetura

```
                          ┌──────────────────────────────────────────┐
                          │            AWS Account (dev)             │
                          │                                          │
  GitHub Actions          │   ┌─────────── VPC 10.20.0.0/16 ──────┐  │
  (OIDC, sem chaves) ────▶│   │  AZ-a                AZ-b         │  │
          │               │   │  ┌─────────┐        ┌─────────┐   │  │
          │ AssumeRole    │   │  │ public  │        │ public  │   │  │
          ▼               │   │  │  + NAT  │        │         │   │  │
  ┌────────────────┐      │   │  └────┬────┘        └─────────┘   │  │
  │ gha-deploy role│      │   │       │ rota 0.0.0.0/0            │  │
  └────────────────┘      │   │  ┌────▼────┐        ┌─────────┐   │  │
                          │   │  │ private │        │ private │   │  │
  ┌────────────────┐      │   │  └─────────┘        └─────────┘   │  │
  │ S3 tfstate     │◀─────┤   │   VPC Endpoints: S3, DynamoDB (GW)│  │
  │ DynamoDB lock  │      │   │   + interface endpoints (opcional)│  │
  └────────────────┘      │   └───────────────────────────────────┘  │
                          │                                          │
                          │   KMS (data / messaging / logs)          │
                          │   IAM (lambda, glue, stepfunctions)      │
                          │   SG (lambda, glue, microservices)       │
                          │   S3 (raw, curated, athena-results)      │
                          │   SSM /agentes-devops/dev/base-infra ────┼──▶ próximos agentes
                          └──────────────────────────────────────────┘
```

**Camadas entregues**

| Componente | Recursos |
|---|---|
| Rede | VPC, subnets públicas/privadas multi-AZ, IGW, NAT Gateway(s), route tables, VPC Endpoints (S3/DynamoDB gateway + 10 interface endpoints opcionais), Flow Logs criptografados |
| Criptografia | 3 CMKs (`data`, `messaging`, `logs`) com rotação anual e key policy restrita por `aws:SourceAccount` |
| IAM | Roles de execução para Lambda, Glue e Step Functions; managed policy para analistas Athena; role de deploy GitHub Actions via OIDC |
| Segurança de rede | SGs de Lambda, Glue (com self-reference exigido pela AWS) e microserviços — egress limitado a 443 |
| Armazenamento | Buckets `raw`, `curated` e `athena-results` (SSE-KMS + bucket key, versionados, public access bloqueado, lifecycle) |
| Contrato | Parâmetro SSM com IDs/ARNs consumidos pelos próximos agentes |

## 2. Justificativa da escolha da ferramenta

1. **Neutralidade de licença.** O Terraform migrou para a BUSL 1.1 em agosto/2023. O OpenTofu é um fork sob MPL 2.0 mantido pela Linux Foundation — elimina o risco jurídico de uso comercial/automação de uma ferramenta proprietária, o que é um *custo de risco* mensurável.
2. **Declaratividade pura.** HCL não permite laços arbitrários nem efeitos colaterais; o que está escrito é o que existe. Isso reduz a distância entre o código revisado no PR e o recurso criado.
3. **`plan` como artefato auditável.** O plano binário é gerado, comentado no PR, aprovado e só então aplicado — o `apply` usa exatamente o plano revisado, não um recálculo.
4. **Multi-cloud readiness.** O mesmo motor e a mesma linguagem servem para AWS, GCP, Azure, Cloudflare, Datadog e GitHub. A arquitetura do experimento não fica presa à AWS.
5. **Superfície de estado explícita.** O state é um arquivo versionado sob controle da equipe, com locking em DynamoDB — permite `import`, `state mv`, `taint` e recuperação manual em incidentes.

## 3. Estrutura de pastas

```
abordagem-1-opentofu/
├── bootstrap/
│   └── main.tf                  # S3 + DynamoDB + CMK do state (rodado 1x, state local)
├── modules/
│   ├── vpc/
│   │   ├── main.tf              # VPC, subnets, IGW, NAT, RTs, endpoints, flow logs
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   └── versions.tf
│   ├── kms/                     # N CMKs via for_each + key policy least privilege
│   ├── iam/                     # roles de workload + OIDC GitHub
│   └── security_groups/         # SGs de lambda, glue e microserviços
└── envs/
    ├── dev/
    │   ├── backend.tf           # backend S3 parcial (config vem do CI)
    │   ├── main.tf              # composição dos módulos + buckets + contrato SSM
    │   ├── variables.tf
    │   ├── outputs.tf
    │   └── terraform.tfvars
    └── prod/                    # mesma composição, valores de HA e retenção maiores
```

**Princípio:** módulos não conhecem ambientes; ambientes não contêm lógica. Toda condicional de custo/HA (`single_nat_gateway`, `enable_interface_endpoints`) é um *input*, não um `if` espalhado pelo código.

## 4. Decisões de design e justificativas

| Decisão | Justificativa |
|---|---|
| Separação `modules/` × `envs/` | Permite promover dev → prod alterando apenas `.tfvars`, mantendo o código idêntico. |
| Backend parcial (`-backend-config` no CI) | O nome do bucket de state não fica versionado no repositório e o mesmo código serve a várias contas. |
| KMS não referencia as roles IAM na key policy | Evita dependência circular KMS ⇄ IAM. As roles recebem `kms:Decrypt/GenerateDataKey` pelo lado IAM, o que é suficiente porque a key policy delega à conta. |
| `bucket_key_enabled = true` | Reduz em até ~99% o número de chamadas ao KMS em cargas de leitura intensa (Glue/Athena) — decisão explicitamente de custo. |
| Gateway endpoints sempre ligados; interface endpoints por flag | Gateway endpoints são gratuitos e cortam tráfego de S3/DynamoDB do NAT. Interface endpoints custam ~US$ 7,30/mês por AZ e só compensam com volume. |
| `map_public_ip_on_launch = false` | Nenhum recurso recebe IP público por acidente. |
| Egress dos SGs restrito a 443 | Elimina o `0.0.0.0/0` all-ports padrão, controle cobrado por Checkov/CIS. |
| Flow Logs com CMK e retenção por ambiente (14d dev / 90d prod) | Auditabilidade sem inflar o custo de CloudWatch em dev. |
| Contrato publicado em SSM em vez de `terraform_remote_state` | Os próximos agentes (Glue, Lambda, Step Functions) leem um JSON estável, sem acoplamento ao formato do state nem permissão de leitura sobre ele. |
| `lifecycle` de expiração nos resultados do Athena (30 dias) | Resultados de query são descartáveis; sem isso o bucket cresce indefinidamente. |

## 5. Como executar

### Localmente

```bash
# Pré-requisitos: OpenTofu >= 1.8, AWS CLI v2, credenciais com permissão de admin na conta sandbox
tofu --version && aws sts get-caller-identity

# 1) Bootstrap do backend (uma única vez por conta)
cd abordagem-1-opentofu/bootstrap
tofu init && tofu apply            # anote os outputs state_bucket e lock_table

# 2) Ambiente de desenvolvimento
cd ../envs/dev
tofu init \
  -backend-config="bucket=<state_bucket>" \
  -backend-config="dynamodb_table=<lock_table>" \
  -backend-config="region=us-east-1"

tofu fmt -recursive ../..
tofu validate
tofu plan  -out=tfplan
tofu apply tfplan

# 3) Conferir o contrato publicado para os próximos agentes
aws ssm get-parameter --name /agentes-devops/dev/base-infra --query Parameter.Value --output text | jq

# 4) Remover tudo (apenas dev)
tofu destroy
```

### Via CI/CD

`.github/workflows/tofu-base-infra.yml`

| Gatilho | Jobs executados |
|---|---|
| Pull Request | `static-analysis` (fmt, validate, TFLint, Checkov→SARIF) → `plan` + Infracost comentados no PR |
| Push em `main` | `static-analysis` → `plan` → `apply` (com *required reviewers* no GitHub Environment) |
| `workflow_dispatch` | escolha de ambiente e ação `plan` / `apply` / `destroy` |

Secrets necessários: `AWS_DEPLOY_ROLE_ARN`, `TF_STATE_BUCKET`, `TF_LOCK_TABLE` e
`INFRACOST_API_KEY` (opcional — sem ele o passo de custo é pulado).
Environments: `dev`, `prod`, `dev-destroy`, `prod-destroy`.
Autenticação exclusivamente por **OIDC** — nenhuma access key estática no repositório.
O job de qualidade roda sem credencial AWS; só `plan`, `apply` e `destroy` assumem a role.
O `plan` ainda tem uma guarda de custo: em `dev`, mais de um NAT Gateway falha o job.
O `destroy` exige três barreiras: ação explícita no dispatch, string `DESTROY-<ambiente>` e aprovação no Environment `<ambiente>-destroy`; produção é bloqueada por código.

## 6. Vantagens e desvantagens

**Vantagens**
- Plano legível por humanos e auditável antes de qualquer mudança; o artefato aprovado é o artefato aplicado.
- Ecossistema de segurança maduro e barato (TFLint, Checkov, tfsec, Infracost lê `plan.json` nativamente).
- Estado manipulável: `import`, `state mv`, `state rm` resolvem drift sem recriar recursos.
- Sem dependência do CloudFormation: erros e limites de serviço (500 recursos/stack, rollbacks demorados) não se aplicam.
- Licença MPL 2.0 e governança em fundação — risco jurídico próximo de zero.

**Desvantagens**
- Verbosidade: o módulo de VPC tem ~230 linhas para o que o CDK resolve em ~20.
- HCL não tem tipos algébricos nem testes unitários de primeira classe; validação depende de `validation {}`, TFLint e Checkov.
- O state é um ativo crítico: corrompê-lo ou perder o lock causa incidente operacional.
- Least privilege é totalmente manual — cada ARN de policy é escrito à mão e pode divergir da realidade.
- Não há recuperação automática: um `apply` interrompido deixa recursos parcialmente criados (sem rollback transacional).

## 7. Análise crítica

A abordagem OpenTofu privilegia **controle e previsibilidade** sobre velocidade. O ganho principal é epistêmico: quem revisa o PR enxerga exatamente a mudança de infraestrutura, recurso por recurso, antes que ela ocorra. Esse atributo é decisivo em ambientes regulados e em times com rotatividade, porque a revisão não exige conhecimento do framework — apenas de AWS.

O preço é o esforço inicial e a superfície de erro humano em IAM. Nada no HCL impede escrever `Action: "*"`; a rede de proteção vem de ferramentas externas (Checkov) e de disciplina de revisão. Em um experimento acadêmico com poucos serviços, isso é administrável; em uma plataforma com dezenas de microserviços, o custo marginal de manter policies manuais cresce linearmente, enquanto no CDK ele é quase constante.

A modularização adotada minimiza esse custo: `envs/prod` é uma cópia da composição de `dev` com valores diferentes, e a diferença de arquitetura entre ambientes é expressa por três variáveis. Isso torna a comparação dev/prod trivial de auditar — ponto forte que raramente aparece em códigos Terraform reais, onde ambientes divergem silenciosamente.
