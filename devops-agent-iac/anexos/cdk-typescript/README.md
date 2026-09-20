# Abordagem 2 — Agente DevOps com AWS CDK (TypeScript)

> Mesma camada de infraestrutura base, expressa como programa TypeScript que
> sintetiza CloudFormation, com verificação de compliance (cdk-nag) e testes
> unitários sobre o template.

---

## 1. Visão geral da arquitetura

```
  bin/app.ts
     │
     └── Stage BaseInfra-<env>            (unidade de deploy de um ambiente)
            ├── EncryptionStack   ──▶ 3 CMKs (data / messaging / logs)
            ├── NetworkStack      ──▶ VPC multi-AZ, NAT, endpoints, flow logs, 3 SGs
            ├── DataStack         ──▶ SecureBucket x3 (raw, curated, athena-results)
            └── IamStack          ──▶ roles Lambda/Glue/StepFunctions, OIDC GitHub
                    └── PlatformContract ──▶ SSM /agentes-devops/<env>/base-infra-cdk
```

A ordem de deploy **não é declarada**: o CDK a infere do grafo de referências
entre stacks (`encryption.logsKey` usado em `NetworkStack` cria a dependência).
Cada stack vira uma stack de CloudFormation independente, com rollback próprio.

## 2. Justificativa da escolha da ferramenta

1. **Least privilege gerado, não escrito.** `bucket.grantReadWrite(role)` emite as ações de S3 *e* as de KMS da chave do bucket, com os ARNs corretos. A principal fonte de erro de segurança em IaC — policy escrita à mão — é removida do caminho crítico.
2. **Abstrações que codificam boas práticas.** `ec2.Vpc` já implementa o padrão AWS de subnets por AZ, tabelas de rota e NAT; `SubnetType.PRIVATE_WITH_EGRESS` é uma decisão arquitetural expressa em uma palavra.
3. **Testabilidade real.** `Template.fromStack()` permite asserções (`rotação de chave habilitada`, `nenhuma subnet pública com IP automático`) executadas em segundos no CI, sem tocar na AWS.
4. **Compliance como aspecto.** `cdk-nag` com `AwsSolutionsChecks` roda em todo `synth` e falha o build — verificação embutida, não etapa opcional.
5. **Tipagem estática.** Um ID de subnet trocado por um ID de SG não compila; em HCL, falharia só no `apply`.
6. **Gestão de estado terceirizada.** O estado é a própria stack de CloudFormation: sem bucket de state, sem tabela de lock, sem risco de corrupção.

## 3. Estrutura de pastas

```
abordagem-2-cdk/
├── bin/
│   └── app.ts                       # entrypoint: 1 Stage por ambiente + Aspects globais
├── lib/
│   ├── config.ts                    # tipos do contexto de ambiente
│   ├── base-infra-stage.ts          # composição das 4 stacks
│   ├── encryption-stack.ts          # CMKs
│   ├── network-stack.ts             # VPC, endpoints, flow logs, security groups
│   ├── data-stack.ts                # buckets de dados
│   ├── iam-stack.ts                 # roles de workload + OIDC GitHub
│   └── constructs/
│       ├── secure-bucket.ts         # L3 reutilizável: baseline de segurança de bucket
│       └── platform-contract.ts     # publicação do contrato em SSM
├── test/
│   └── base-infra.test.ts           # asserções sobre o template sintetizado
├── cdk.json                         # contexto: ambientes, feature flags
├── package.json
├── tsconfig.json
└── jest.config.js
```

## 4. Decisões de design e justificativas

| Decisão | Justificativa |
|---|---|
| Quatro stacks em vez de uma monolítica | Reduz o blast radius (um erro em IAM não faz rollback da VPC) e contorna o limite de recursos por stack. |
| `Stage` por ambiente | Instancia o conjunto inteiro com um único objeto de configuração; elimina divergência acidental entre dev e prod. |
| Configuração em `cdk.json` (context) e não em código | Mantém valores de ambiente fora da lógica, equivalente ao `.tfvars` da Abordagem 1 — comparabilidade metodológica entre as duas abordagens. |
| Construct L3 `SecureBucket` | Encapsula KMS + bucket key + versionamento + block public access + TLS obrigatório. Um bucket inseguro passa a exigir esforço deliberado. |
| `allowAllOutbound: false` em todos os SGs | O padrão do CDK é egress liberado; a decisão explícita fecha esse desvio. |
| `AwsSolutionsChecks` via `Aspects` | Compliance verificada em toda a árvore, inclusive em constructs criados por terceiros. |
| Contrato em SSM em vez de `CfnOutput`/`Fn::ImportValue` | Exports de CloudFormation criam travas: uma stack consumidora impede alterar o recurso exportado. SSM desacopla. |
| `RemovalPolicy.RETAIN` em prod / `DESTROY` em dev | Evita perda de dados em produção e permite limpar ambientes de experimento sem resíduos cobrando armazenamento. |
| Role do GitHub apenas com `sts:AssumeRole` sobre `cdk-*` | O deploy real usa as roles de bootstrap do CDK; a role federada não precisa de permissões amplas. |

## 5. Como executar

### Localmente

```bash
# Pré-requisitos: Node.js 20+, AWS CLI v2, credenciais na conta alvo
cd abordagem-2-cdk
npm ci

# 1) Bootstrap do CDK (uma vez por conta+região)
npx cdk bootstrap aws://<ACCOUNT_ID>/us-east-1

# 2) Qualidade
npm run build          # tsc: erros de tipo antes de qualquer chamada à AWS
npm test               # asserções sobre o template
npx cdk synth -c env=dev   # gera CloudFormation + roda cdk-nag

# 3) Deploy
npx cdk diff   -c env=dev
npx cdk deploy --all -c env=dev --outputs-file cdk-outputs.json

# 4) Contrato para os próximos agentes
aws ssm get-parameter --name /agentes-devops/dev/base-infra-cdk --query Parameter.Value --output text | jq

# 5) Destruir (apenas dev)
npx cdk destroy --all -c env=dev
```

> Ajuste os `account` de `cdk.json` para as contas reais antes do primeiro deploy.

### Via CI/CD

`.github/workflows/cdk-base-infra.yml`

| Gatilho | Jobs |
|---|---|
| Pull Request | `build-test` (tsc, jest, synth + cdk-nag, Checkov sobre `cdk.out`) → `diff` + custo comentados no PR |
| Push em `main` | `build-test` → `diff` → `deploy` (aprovação no GitHub Environment) |
| `workflow_dispatch` | ambiente + ação `diff` / `deploy` / `destroy` com confirmação textual |

Secrets: `AWS_CDK_DEPLOY_ROLE_ARN`, `INFRACOST_API_KEY`. Autenticação por OIDC.

## 6. Vantagens e desvantagens

**Vantagens**
- Densidade de código muito maior: ~40% das linhas da Abordagem 1 para o mesmo resultado.
- IAM de menor privilégio por construção, com ARNs sempre coerentes com os recursos.
- Testes unitários e compliance automatizada nativos no ciclo de desenvolvimento.
- Refatoração segura: renomear um recurso é um erro de compilação, não um `destroy/create` descoberto no `plan`.
- Sem infraestrutura de state para operar; drift detection via CloudFormation.

**Desvantagens**
- Duas camadas de abstração entre o código e o recurso (TS → CloudFormation → API). Diagnosticar `UPDATE_ROLLBACK_FAILED` exige ler o template sintetizado, não o código.
- `cdk diff` é menos fiel que `tofu plan`: mudanças resolvidas em tempo de deploy nem sempre aparecem.
- Acoplamento total ao CloudFormation — rollbacks lentos, limites de serviço, recursos sem suporte exigem Custom Resources.
- Vendor lock-in arquitetural: portar para outra nuvem significa reescrever, não reconfigurar.
- Superfície de dependências npm (`aws-cdk-lib` traz centenas de módulos transitivos) — custo de manutenção e de supply chain.
- Uma linha inocente (`grantReadWrite` em um bucket errado) produz uma policy ampla sem que a revisão de código evidencie isso.

## 7. Análise crítica

O CDK desloca o esforço do **escrever** para o **revisar**. Escrever é muito mais rápido e o resultado tende a ser mais seguro por default, mas a revisão de PR passa a exigir que o revisor entenda o que cada método gera — `grant*` é conveniente e opaco. Na prática, isso significa que o `cdk diff` e o template sintetizado, e não o diff do TypeScript, precisam ser o objeto da revisão; o pipeline aqui foi construído com essa premissa (o diff é comentado no PR e o Checkov roda sobre `cdk.out`, não sobre o código).

O segundo ponto crítico é a dependência do CloudFormation, que é ao mesmo tempo a maior vantagem (estado gerenciado, rollback automático, drift detection) e a maior limitação (lentidão, mensagens de erro pobres, stacks que travam em estados irreversíveis). Para uma plataforma cujo roadmap é S3 + Glue + Step Functions + Lambda + SQS + Athena — todos serviços AWS de primeira classe, com constructs L2 maduros —, essa dependência é praticamente sem custo. Ela só se torna cara se o experimento evoluir para componentes fora da AWS.

Por fim, a testabilidade é o diferencial menos visível e mais relevante academicamente: é possível afirmar e verificar propriedades da infraestrutura ("nenhuma subnet pública atribui IP automaticamente") de forma executável e repetível — algo que na Abordagem 1 só se obtém com ferramentas externas de política.
