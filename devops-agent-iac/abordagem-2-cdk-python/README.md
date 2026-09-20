# Abordagem 2 — Agente DevOps com AWS CDK (Python)

Mesma camada de infraestrutura base da Abordagem 1, expressa como programa
Python que sintetiza CloudFormation, com compliance automatizada (cdk-nag) e
testes unitários sobre o template.

---

## 1. Visão geral da arquitetura

```
app.py
  └── BaseInfraStage("BaseInfra-<env>")        # unidade de deploy do ambiente
        ├── EncryptionStack   → 3 CMKs (data / messaging / logs)
        ├── NetworkStack      → VPC multi-AZ, NAT, gateway endpoints, flow logs, 3 SGs
        ├── DataStack         → SecureBucket × 3 (raw, curated, athena-results)
        └── IamStack          → roles Lambda/Glue/StepFunctions, OIDC GitHub
              └── PlatformContract → SSM /agentes-devops/<env>/base-infra-cdk-py
```

A ordem de deploy não é declarada: o CDK a infere do grafo de referências
(`encryption.logs_key` consumido pela `NetworkStack`). Cada stack vira uma stack
de CloudFormation independente, com rollback próprio.

## 2. Justificativa da escolha

1. **Python em vez de TypeScript**: alinha com o restante do experimento — os handlers da Abordagem 3 também são Python, então a comparação isola a *ferramenta de IaC*, não a linguagem. Em contrapartida, o CDK Python tem tipagem mais fraca que o TS (bindings jsii, `**kwargs`), o que reduz parte da vantagem de type-safety do CDK.
2. **Least privilege gerado**: `bucket.grant_read_write(role)` emite as ações de S3 e as de KMS da chave do bucket, com ARNs corretos. A principal fonte de erro em IaC sai do caminho crítico.
3. **Compliance como aspecto**: `AwsSolutionsChecks` roda em todo `synth` e falha o build.
4. **Testabilidade real**: `Template.from_stack()` permite asserções executadas em segundos, sem tocar na AWS.
5. **Estado terceirizado**: o estado é a própria stack de CloudFormation — sem bucket de state, sem tabela de lock.

## 3. Estrutura de pastas

```
abordagem-2-cdk-python/
├── app.py                              # entrypoint: Stage por ambiente + Aspects
├── cdk.json                            # contexto (equivalente ao .tfvars)
├── requirements.txt / requirements-dev.txt
├── pyproject.toml                      # ruff, mypy, pytest
├── app_lib/
│   ├── config.py                       # EnvironmentConfig (dataclass frozen)
│   ├── stages.py                       # composição das 4 stacks
│   ├── stacks/
│   │   ├── encryption_stack.py
│   │   ├── network_stack.py
│   │   ├── data_stack.py
│   │   └── iam_stack.py
│   └── constructs/
│       ├── secure_bucket.py            # L3: baseline de segurança de bucket
│       └── platform_contract.py        # contrato em SSM
└── tests/
    └── test_base_infra.py
```

## 4. Decisões de design

| Decisão | Justificativa |
|---|---|
| Quatro stacks, não uma | Reduz blast radius e contorna o limite de recursos por stack. |
| `EnvironmentConfig` como dataclass frozen | Erro de configuração vira `TypeError` no synth, não `KeyError` no meio do deploy. |
| Configuração em `cdk.json`, não em código | Paridade metodológica com o `.tfvars` da Abordagem 1. |
| Construct L3 `SecureBucket` | Bucket inseguro passa a exigir esforço deliberado. |
| `allow_all_outbound=False` | O padrão do CDK libera egress; a decisão explícita fecha o desvio. |
| Key policy da CMK de logs com `kms:EncryptionContext:aws:logs:arn` | Sem essa condição o `CreateLogGroup` falha — o erro que aparece primeiro na Abordagem 1. |
| Contrato em SSM, não `CfnOutput`/`ImportValue` | Exports de CloudFormation travam o recurso exportado enquanto houver consumidor. |
| `RETAIN` em prod / `DESTROY` em dev | Evita perda de dados e permite limpar ambientes sem resíduo cobrando. |

## 5. Como executar

### Localmente

```bash
cd abordagem-2-cdk-python
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
npm install -g aws-cdk@2.150.0          # CLI em Node mesmo com app Python

# Ajuste cdk.json: environments.dev.account e githubRepository

cdk bootstrap aws://<ACCOUNT_ID>/us-east-1   # 💸 ~US$ 1,10/mês
ruff check . && pytest
cdk synth -c env=dev --quiet                 # roda cdk-nag
cdk diff  -c env=dev
cdk deploy --all -c env=dev --outputs-file cdk-outputs.json   # 💸 9 a 14 min

aws ssm get-parameter --name /agentes-devops/dev/base-infra-cdk-py \
  --query Parameter.Value --output text | jq

cdk destroy --all -c env=dev
```

### Via CI/CD

`.github/workflows/cdk-python-base-infra.yml`: PR roda ruff + mypy + pytest +
synth com cdk-nag + Checkov sobre `cdk.out`, depois comenta `cdk diff` e custo.
Push em `main` acrescenta o deploy com aprovação de Environment. Destroy só por
`workflow_dispatch` com confirmação textual; produção bloqueada por código.

O job de qualidade roda **sem credencial AWS** — não há context lookup no código,
então o synth usa o `account` placeholder do `cdk.json`. Os jobs que tocam a conta
substituem esse valor pelo account real vindo do STS, o que evita versionar o ID
da conta no repositório.

A estimativa de custo **não** usa Infracost: ele lê Terraform, não CloudFormation.
O job conta NAT Gateways, CMKs e interface endpoints no template sintetizado e
aplica os preços de referência do `COMPARATIVO.md` (seção 3).

Secret: `AWS_CDK_PY_DEPLOY_ROLE_ARN`. OIDC, sem access keys.
Environments: `dev`, `prod`, `dev-destroy`, `prod-destroy`.

## 6. Vantagens e desvantagens

**Vantagens**
- Cerca de metade das linhas da Abordagem 1 para o mesmo resultado.
- IAM de menor privilégio por construção; ARNs sempre coerentes com os recursos.
- Testes unitários e compliance nativos no ciclo de desenvolvimento.
- Sem infraestrutura de state para operar; drift detection via CloudFormation.
- Python facilita composição, laços e validação — e reaproveita a stack de lint/teste que o time já usa.

**Desvantagens**
- Duas camadas entre código e recurso (Python → CloudFormation → API).
- Tipagem do CDK Python é mais fraca que a do TypeScript: erros que o TS pegaria em compilação aparecem só no synth.
- `cdk diff` é menos fiel que `tofu plan`.
- Acoplamento total ao CloudFormation: rollbacks lentos, limites de serviço, `UPDATE_ROLLBACK_FAILED`.
- Vendor lock-in arquitetural; portar significa reescrever.
- Velocidade de synth: bindings jsii tornam o CDK Python perceptivelmente mais lento que o TS em projetos grandes.

## 7. Análise crítica

O CDK desloca o esforço do **escrever** para o **revisar**. Escrever é muito mais
rápido e o default é mais seguro, mas `grant_read_write` é conveniente e opaco:
a revisão de PR precisa recair sobre o template sintetizado, não sobre o diff do
Python. O pipeline desta abordagem foi construído com essa premissa — o `cdk diff`
é comentado no PR e o Checkov roda sobre `cdk.out`.

A escolha de Python tem um efeito colateral relevante para o experimento: ela
reduz a distância de linguagem em relação à Abordagem 3, permitindo comparar
diretamente "descrever o recurso" (CDK) contra "executar a chamada de API"
(agente serverless) com o mesmo vocabulário. O que sobra da diferença é
exatamente o que interessa academicamente: o modelo de execução.

Por fim, a dependência do CloudFormation é ao mesmo tempo a maior vantagem
(estado gerenciado, rollback automático, drift detection) e a maior limitação
(lentidão, mensagens de erro pobres, estados irreversíveis). Para uma plataforma
cujo roadmap é S3 + Glue + Step Functions + Lambda + SQS + Athena, essa
dependência é praticamente sem custo.
