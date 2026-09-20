# Análise Comparativa — Agente DevOps: OpenTofu × AWS CDK (Python) × Agente Serverless

Documento final do experimento. Compara três implementações da **mesma** camada
de infraestrutura base (VPC, KMS, IAM, Security Groups e preparação para S3,
Glue, Step Functions, Lambda, SQS e Athena), todas com esteira em GitHub Actions.

---

## 1. Controle experimental

Variáveis mantidas constantes entre as três implementações:

| Variável controlada | Valor |
|---|---|
| Recursos provisionados | VPC multi-AZ, IGW, NAT, route tables, gateway endpoints, 3 CMKs, 3 SGs, 3 roles de workload, contrato em SSM |
| Autenticação do CI | OIDC (`id-token: write`), sem access keys estáticas |
| Estágios do pipeline | qualidade → plan/diff/dry-run → apply/deploy/provision com aprovação → destroy com dupla confirmação |
| Scanner de segurança | Checkov (HCL na 1; template sintetizado na 2; template SAM na 3) |
| Região e dimensionamento | `us-east-1`, dev = 2 AZ / 1 NAT |
| Contrato de saída | JSON em SSM Parameter Store |
| Linguagem de aplicação | Python nas Abordagens 2 e 3 (isola a ferramenta, não a linguagem) |

**Métricas objetivas, medidas no código deste repositório:**

| Métrica | 1. OpenTofu | 2. CDK Python | 3. Serverless |
|---|---|---|---|
| Linhas de definição de infraestrutura | 1.123 (`.tf`) | 671 (`.py`) | 1.787 (1.111 Python + 676 SAM/ASL) |
| Arquivos | 25 `.tf` | 14 `.py` | 22 (`.py`, `.json`, `.yaml`) |
| Bootstrap próprio | 106 linhas (`bootstrap/`) | 0 (`cdk bootstrap`) | 455 linhas (`template.yaml`) — o agente precisa de IaC declarativa para nascer |
| Testes unitários | 0 (linters + `validation`) | 4 asserções sobre o template | 4 testes de idempotência do registry |
| Razão LOC vs. menor | 1,67× | **1,00×** | 2,66× |
| Linhas dedicadas a reimplementar o motor de IaC | 0 | 0 | ~620 (registry, plan, ordem de destroy, drift, rollback) |

A última linha é o achado central do experimento: **um terço do código da
Abordagem 3 existe apenas para reproduzir, em versão reduzida, o que as outras
duas recebem pronto.**

---

## 2. Tabela comparativa por critério

Escala 1–5. Pesos: Alto = 3, Médio-Alto = 2,5, Médio = 2.

| Critério | Peso | 1. OpenTofu | 2. CDK Python | 3. Serverless | Evidência |
|---|---|---|---|---|---|
| Clareza Arquitetural | Alto (3) | **5** | 4 | 3 | HCL mapeia 1:1 para recursos. O CDK esconde ~40 recursos em `ec2.Vpc`. No agente a arquitetura só existe como efeito da execução: saber o que é criado exige ler nove handlers — ainda que o grafo da state machine seja o artefato visual mais legível dos três. |
| Segurança | Alto (3) | 4 | **5** | 4 | CDK vence pelo IAM gerado + cdk-nag. O agente empata em IAM manual, mas tem dois diferenciais reais: `PermissionsBoundary` nas roles criadas e runner de CI sem permissão de criar recursos (só `events:PutEvents`). |
| Modularidade e Reusabilidade | Alto (3) | **5** | 4 | 3 | Módulos OpenTofu servem outros projetos e outras clouds. Constructs CDK, só CDK. Handlers do agente são acoplados ao registry e ao formato do payload da state machine. |
| Qualidade da Pipeline CI/CD | Médio-Alto (2,5) | **5** | 4 | 4 | O `tofu plan` binário aprovado é o artefato aplicado. O agente tem a melhor postura de credencial e separa deploy-do-agente de provisionamento, mas seu "plan" compara hashes de spec, não o estado real. |
| Facilidade de Manutenção | Médio (2) | 3 | **5** | 2 | 671 linhas com testes e tipos contra 1.787 em que cada novo tipo de recurso exige escrever create, delete e check de drift. |
| Preparação para serviços futuros | Médio (2) | 4 | **5** | 3 | Os três publicam o mesmo contrato em SSM. O CDK adiciona L2/L3 prontos (`aws-stepfunctions-tasks`, event sources de SQS). O agente exigiria um handler novo por serviço. |
| **Métricas de Custo** | Alto (3) | **5** | 4 | 3 | Detalhado na seção 3. |
| Complexidade vs Benefício | Médio (2) | 4 | 4 | 2 | O agente entrega capacidades que as outras não têm (reatividade, ações não-IaC), ao custo de reimplementar o motor. |
| **Pontuação ponderada (máx. 102,5)** | | **86,5** | **89,0** | **63,0** | |

<details>
<summary>Memória de cálculo</summary>

- OpenTofu: (5×3)+(4×3)+(5×3)+(5×2,5)+(3×2)+(4×2)+(5×3)+(4×2) = **86,5**
- CDK Python: (4×3)+(5×3)+(4×3)+(4×2,5)+(5×2)+(5×2)+(4×3)+(4×2) = **89,0**
- Serverless: (3×3)+(4×3)+(3×3)+(4×2,5)+(2×2)+(3×2)+(3×3)+(2×2) = **63,0**

Entre 1 e 2 a diferença é de 2,5%: **empate técnico**, decidido por preferência
organizacional e não por mérito. A distância até a 3 (−26 pontos) é estrutural e
não se fecha com refinamento de código.
</details>

---

## 3. Métricas de custo

### 3.1 Custo direto da ferramenta / plataforma

| Item | OpenTofu | CDK Python | Serverless |
|---|---|---|---|
| Licença | US$ 0 (MPL 2.0, Linux Foundation) | US$ 0 (Apache 2.0) | US$ 0 |
| Plataforma de execução | Backend próprio | CloudFormation (sem cobrança para recursos AWS) | Lambda + Step Functions + DynamoDB + EventBridge |
| Infra de suporte, ociosa | S3 + DynamoDB + CMK ≈ **US$ 1,07/mês** | Bucket + ECR + CMK do bootstrap ≈ **US$ 1,10/mês** | Registry DynamoDB + CMK + log groups ≈ **US$ 0,60/mês** |
| Custo por execução | Minutos de runner (~2 min de plan) | Minutos de runner (~3 min) | ~50 transições de Standard Workflow (US$ 0,025/1.000) + 9 invocações Lambda ≈ **US$ 0,002** |
| CI em repo privado (40 execuções/mês) | ≈ US$ 1,90 | ≈ US$ 3,50 | ≈ **US$ 0,80** — o runner só publica evento e faz polling |

**Veredito:** a Abordagem 3 é a mais barata em operação (o trabalho migra do
runner pago para serviços cobrados por uso). A diferença absoluta, porém, é de
poucos dólares por mês.

> Custo da infraestrutura provisionada — **idêntico nas três** (`us-east-1`, valores de referência): NAT Gateway ≈ US$ 32,85/mês + US$ 0,045/GB; Interface Endpoint ≈ US$ 7,30/mês por AZ; CMK ≈ US$ 1,00/mês. Perfil dev ≈ **US$ 36/mês**; perfil prod (3 NAT + endpoints) ≈ **US$ 300/mês**. A maior alavanca de custo do projeto é de configuração, não de ferramenta.

### 3.2 Custo de desenvolvimento

| Indicador | OpenTofu | CDK Python | Serverless |
|---|---|---|---|
| LOC | 1.123 | 671 | 1.787 |
| Policies IAM escritas à mão | ~180 linhas | ~60 linhas | ~200 (workloads) + ~150 (o próprio agente) |
| Motor de reconciliação | pronto | pronto | **~620 linhas próprias** |
| Curva de entrada | HCL: dias | CDK + CloudFormation: semanas | boto3 + ASL + modelagem de estado distribuído: semanas, com risco de design |
| Esforço relativo | 1,6× | **1,0×** | **2,8×** |

**Veredito: vantagem clara do CDK.** O agente serverless custa quase três vezes
mais para chegar a um resultado funcionalmente inferior (sem update in-place).

### 3.3 Custo de manutenção a longo prazo

| Fator | OpenTofu | CDK Python | Serverless |
|---|---|---|---|
| Novo tipo de recurso | 1 bloco `resource` | 1 construct L2 | create + delete + drift check + ordem no registry |
| Atualização de dependências | Provider AWS (~1 major/ano) | `aws-cdk-lib` semanal + feature flags | boto3 (estável) + SAM |
| Cobertura de API | Provider acompanha serviços novos rapidamente | L1 imediato, L2 com atraso | Sempre disponível via boto3 — **única vantagem de manutenção** |
| Drift | `tofu plan` completo | `detect-stack-drift` parcial | Só o que você escreveu em `drift.py` |
| Risco operacional do estado | State corrompido / lock preso | Stack em `UPDATE_ROLLBACK_FAILED` | Registry dessincronizado da AWS (recurso órfão invisível) |
| Onboarding | Rápido | Médio | Lento — exige entender o modelo de estado inventado pelo time |

**Veredito: vantagem do CDK; a Abordagem 3 é a mais cara.** Cada serviço novo
custa esforço constante nas duas primeiras e esforço crescente na terceira.

### 3.4 Custo de risco (vendor lock-in e licenciamento)

| Dimensão | OpenTofu | CDK Python | Serverless |
|---|---|---|---|
| Licença | MPL 2.0, fundação neutra | Apache 2.0, governança AWS | N/A (código próprio) |
| Portabilidade multi-cloud | **Alta** | Nula na prática | Nula (boto3 + Step Functions) |
| Dependência de runtime proprietário | Nenhuma | CloudFormation | Lambda + Step Functions + EventBridge + DynamoDB |
| Custo de saída | Médio | Alto (reescrita) | **Muito alto** (reescrita + perda do motor próprio) |
| Risco de pessoa-chave | Baixo (padrão de mercado) | Baixo-médio | **Alto** — motor artesanal, sem comunidade nem sucessor natural |
| Empregabilidade / mercado | Amplo | Restrito a AWS | Nenhum padrão externo |

**Veredito: vantagem decisiva do OpenTofu.** Aqui a diferença é qualitativa, não
gradual.

### 3.5 Custo de execução

| Operação | OpenTofu | CDK Python | Serverless |
|---|---|---|---|
| Setup do runner | 10–25 s | 40–70 s (pip + CLI Node) | 15–30 s |
| Plan / diff / dry-run | 20–45 s | 70–130 s (jsii é mais lento que o CDK TS) | **8–15 s** (só o Planner) |
| Apply inicial | 6–9 min | 9–14 min | 7–11 min (limitado pelo NAT, como todos) |
| Mudança incremental | **~60 s** | 3–6 min | Não suportada — exige destroy + recreate |
| Falha e recuperação | Estado parcial, intervenção manual | Rollback automático, porém lento | Compensação best-effort |
| Onde o tempo é gasto | Runner do CI (pago) | Runner do CI (pago) | **Dentro da AWS** (quase grátis); o runner só faz polling |

**Veredito:** a Abordagem 3 tem o melhor tempo de plan e o menor custo de
minutos de CI, mas perde o critério por não suportar update in-place — o caso
mais frequente no dia a dia.

### 3.6 Síntese de custo

| Subcritério | Vencedor | Magnitude |
|---|---|---|
| Custo direto | Serverless | Baixa (poucos dólares/mês) |
| Custo de desenvolvimento | **CDK Python** | Alta (2,8× vs. Serverless; 1,6× vs. OpenTofu) |
| Custo de manutenção | CDK Python | Alta |
| Custo de risco | **OpenTofu** | Alta e qualitativa |
| Custo de execução | Empate entre 1 e 3, por motivos opostos | Média |

---

## 4. Diferenças em relação ao modelo "template pronto da organização"

| Aspecto | Template corporativo (IU Pipes / DataMesh) | 1. OpenTofu | 2. CDK Python | 3. Serverless |
|---|---|---|---|---|
| O que você edita | IDs, KMS, roles, policies | Mesmo gesto: blocos de policy e `.tfvars` | Muda o gesto: concede capacidade (`grant_*`) em vez de escrever policy | Muda o paradigma: escreve a chamada de API e o tratamento de erro |
| Onde revisar IAM | Diff do arquivo | Diff do arquivo | `cdk.out/*.template.json` | Diff do Python + policy do SAM |
| Backend de state | Provisionado pela plataforma | Você cria e opera | Não existe (CloudFormation) | Você projeta o modelo de estado |
| Permission boundary | Aplicado pela conta | Ausente | Ausente | **Presente** (implementado no agente) |
| Drift detection | Job central | `tofu plan` | `detect-stack-drift` | Lambda agendada escrita por você |
| Reatividade | Pipeline por commit | Pipeline por commit | Pipeline por commit | **Eventos + schedule** |

Ponto prático: a Abordagem 1 exige a menor mudança de hábito; a 2 muda como você
escreve IAM; a 3 muda o que significa "fazer IaC".

---

## 5. Recomendação final fundamentada

**Para produção, no escopo descrito: Abordagem 1 (OpenTofu) na camada base,
Abordagem 2 (CDK Python) nas camadas de aplicação dos próximos agentes, e o
padrão da Abordagem 3 — não a implementação — como camada de automação em volta
das duas.**

1. **Entre 1 e 2 os critérios técnicos empatam (86,5 × 89,0); o desempate é a assimetria do erro.** Escolher CDK e precisar sair custa reescrita completa; escolher OpenTofu e precisar de mais velocidade custa escrever mais linhas. O segundo erro é reversível.

2. **A camada base é a mais estável do sistema.** VPC, KMS, IAM e SGs mudam raramente. A vantagem do CDK (metade do código) se materializa na criação; a do OpenTofu (plano auditável, ausência de lock-in, feedback rápido) se materializa nos anos de operação.

3. **A Abordagem 3 não deve ser usada como ferramenta de IaC de propósito geral.** Os 26 pontos de distância não vêm de qualidade de implementação, mas de escopo: ela reimplementa um motor maduro em ~620 linhas e ainda assim não entrega update in-place, plano fiel nem rollback transacional. Em produção isso é dívida técnica com risco de pessoa-chave.

4. **O que a Abordagem 3 entrega e nenhuma outra entrega: ações e reatividade.** Aprovação humana via `waitForTaskToken`, remediação automática de drift, reação a eventos de CloudTrail em segundos, integração com ITSM, validação de política de negócio antes de provisionar. Nada disso tem expressão em HCL ou em CDK.

5. **Daí a recomendação ser composicional.** O desenho mais defensável usa o agente serverless como **orquestrador de IaC declarativa** — Step Functions disparando um job (CodeBuild ou Actions) que executa `tofu apply` — em vez de provisionador direto via boto3. Preserva a reconciliação madura e o plano auditável, e ganha auditoria por estado, retry declarativo, reatividade a eventos e a melhor postura de credencial (runner sem permissão de criar recursos).

### Arquitetura recomendada

```
EventBridge (commit, schedule, CloudTrail, ticket aprovado)
        │
        ▼
Step Functions "orquestrador"
        ├── valida política de negócio (λ)
        ├── aguarda aprovação humana (waitForTaskToken)
        ├── executa tofu plan/apply  ──▶ camada base (Abordagem 1)
        ├── executa cdk deploy       ──▶ camadas de serviço (Abordagem 2)
        └── remedia drift / notifica (λ)
                 │
                 ▼
      Contrato em SSM Parameter Store  ──▶ próximos agentes
```

Essa divisão aloca cada tecnologia onde sua vantagem é maior e sua desvantagem
custa menos — e é, na prática, o mesmo padrão do modelo corporativo (plataforma
provê a base, time provê o serviço), com a fronteira explícita no repositório em
vez de implícita na organização.

### Quando a recomendação se inverte

- **CDK como camada base**: organização declaradamente AWS-only com decisão registrada, equipe proficiente em Python/TypeScript e volume de policies IAM como principal fonte de defeitos.
- **Agente serverless como provisionador direto**: apenas quando o recurso não tiver provider nem construct (APIs internas, SaaS sem provider Terraform) ou quando o provisionamento depender de lógica de negócio que nenhuma IaC declarativa expressa.

---

## 6. Limitações do experimento

- As pontuações são atribuições justificadas do avaliador, não medições cegas. A margem entre 1 e 2 (2,5%) inverte com pequenas mudanças de peso; a distância até a 3 não.
- Os tempos são faixas típicas para este porte (~90 recursos). Para rigor acadêmico, coletar ≥10 execuções de cada pipeline — os três workflows já registram tempo de plan e de apply no PR e no job summary.
- Preços AWS são de referência para `us-east-1` e devem ser reconfirmados na calculadora oficial na data da entrega.
- O esforço de desenvolvimento foi estimado por proxy (LOC e número de artefatos), que subestima o custo cognitivo de abstrações e superestima o de código repetitivo.
- A Abordagem 3 implementa um subconjunto deliberado (sem update in-place, sem import de recursos preexistentes). Uma implementação completa ampliaria ainda mais a diferença de LOC — o que reforça a conclusão.
- As três implementações foram validadas estaticamente (sintaxe, lint, testes unitários), não aplicadas em conta AWS real durante a redação.
- A Abordagem 2 existe também em TypeScript (`anexos/cdk-typescript/`), útil para isolar o efeito da linguagem dentro da mesma ferramenta: a versão TS tem 577 linhas contra 671 da Python — diferença atribuível à verbosidade dos `kwargs` e dos objetos de configuração do jsii.
