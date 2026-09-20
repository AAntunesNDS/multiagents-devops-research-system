# Experimento Acadêmico — Agente DevOps: três abordagens de IaC na AWS

Implementação e comparação de **três abordagens** para o mesmo Agente DevOps,
responsável por provisionar a camada de infraestrutura base que será consumida
pelos próximos agentes (microserviços).

## Conteúdo

| Caminho | Descrição |
|---|---|
| [`RUNBOOK.md`](RUNBOOK.md) | Pré-requisitos, configuração AWS, passo a passo de execução das três abordagens e armadilhas |
| [`abordagem-1-opentofu/`](abordagem-1-opentofu/README.md) | IaC declarativa em OpenTofu (HCL), backend S3 + DynamoDB, módulos reutilizáveis |
| [`abordagem-2-cdk-python/`](abordagem-2-cdk-python/README.md) | IaC declarativa em AWS CDK (Python), constructs L2/L3, cdk-nag, testes de template |
| [`abordagem-3-serverless-agent/`](abordagem-3-serverless-agent/README.md) | Orquestração imperativa efêmera: Lambda + Step Functions + EventBridge, estado em DynamoDB |
| [`.github/workflows/`](.github/workflows) | Três pipelines: `tofu-base-infra.yml`, `cdk-python-base-infra.yml`, `serverless-agent.yml` |
| [`COMPARATIVO.md`](COMPARATIVO.md) | Tabela comparativa ponderada, métricas de custo e recomendação final |
| [`anexos/cdk-typescript/`](anexos/cdk-typescript) | Versão TypeScript da Abordagem 2 — isola o efeito da linguagem dentro da mesma ferramenta |

## Escopo provisionado (idêntico nas três)

- **VPC**: subnets públicas e privadas multi-AZ, Internet Gateway, NAT Gateway(s), route tables, VPC Endpoints, Flow Logs criptografados
- **KMS**: três CMKs (dados, mensageria, logs) com rotação anual
- **IAM**: roles de execução para Lambda, Glue e Step Functions; role de deploy via OIDC do GitHub (sem chaves estáticas)
- **Security Groups**: Lambda, Glue e microserviços, com egress restrito a 443
- **Contrato de plataforma**: JSON em SSM Parameter Store para os próximos agentes (S3, Glue, Step Functions, Lambda, SQS, Athena)

CIDRs distintos por abordagem (`10.20`, `10.22`, `10.23`) para que possam
coexistir na mesma conta.

## Resultado resumido

| | 1. OpenTofu | 2. CDK Python | 3. Serverless |
|---|---|---|---|
| Paradigma | Declarativo, state próprio | Declarativo, state na AWS | Imperativo, estado próprio em DynamoDB |
| LOC | 1.123 | 671 | 1.787 |
| Pontuação ponderada | 86,5 | **89,0** | 63,0 |
| Melhor em | Auditabilidade, portabilidade, velocidade de feedback | Produtividade, IAM gerado, manutenção | Custo ocioso, reatividade, postura de credencial no CI |

**Recomendação:** base em OpenTofu, camadas de serviço em CDK, e o padrão
serverless como orquestrador das duas — não como provisionador direto.
Justificativa completa em [`COMPARATIVO.md`](COMPARATIVO.md).

## Ordem de leitura sugerida

1. `RUNBOOK.md` (etapas 1 e 2: pré-requisitos e AWS)
2. `abordagem-1-opentofu/README.md`
3. `abordagem-2-cdk-python/README.md`
4. `abordagem-3-serverless-agent/README.md`
5. `COMPARATIVO.md`

## Aviso

O código segue boas práticas de produção e foi validado estaticamente (sintaxe,
lint, testes unitários), mas **não foi aplicado em conta AWS real**. Antes de
executar: ajuste `account`/`region`, o repositório do GitHub, os nomes de bucket
e o e-mail de alerta, e confirme os preços na calculadora oficial da AWS.
