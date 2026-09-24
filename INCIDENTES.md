# Incidentes de segurança e governança — abordagem-1-opentofu

## 1. RESUMO EXECUTIVO

Durante o primeiro ciclo de vida completo da abordagem-1-opentofu (init → apply → destroy), a execução foi orquestrada via GitHub Copilot Chat, e não via Claude Code. Isso resultou em uma série de incidentes de segurança e de governança: exposição de credenciais AWS em texto puro via `export` inline, aplicação de políticas excessivas (`AmazonSSMFullAccess`), falhas de apply por KMS e SSM e confusão sobre o estado remoto/local. A causa raiz foi estrutural: a camada de governança do projeto (subagentes e hooks de execução) estava desenhada para Claude Code; o orquestrador escolhido não a acionou. Houve custo real de infraestrutura e risco operacional/segurança concretos, além de correções manuais de identidade e credenciais. O valor exato do dano financeiro não foi calculado nesta fase e deve ser confirmado com o usuário.

## 2. LINHA DO TEMPO

### a) Execução do runbook via GitHub Copilot Chat (não Claude Code)
- O runbook da abordagem-1-opentofu foi seguido em sessão orquestrada por GitHub Copilot Chat, não pelo Claude Code com seus subagentes/hook de segurança.
- O arquivo principal do fluxo foi `RUNBOOK.md`, e os elementos de governança do repositório estavam definidos em `cost-reviewer.md`, `iac-security-reviewer.md`, `guard-destructive.sh`, `CLAUDE.md` e em frontmatter de arquivos como `iac-security-reviewer.md`.
- O problema não foi isolado a um recurso concreto da Infra em si, mas à ausência de acionamento do mecanismo de segurança do orquestrador escolhido.

### b) Exposição de credenciais AWS (AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY) em texto puro
- Durante a execução do `tofu apply`, a credencial foi exportada em linha em um comando de terminal com `export AWS_ACCESS_KEY_ID=...` e, em um ponto da sessão, a variável correspondente foi observada no contexto local.
- Isso constituiu uma exposição direta de segredo em texto puro em shell, contrariando o princípio do repositório de nunca imprimir, colar, exportar inline ou gravar credenciais AWS.
- O correto, conforme a documentação do projeto, era usar perfil/configuração do AWS CLI/SSO e confirmar a identidade com `aws sts get-caller-identity` antes de qualquer operação.
- Referência normativa: `CLAUDE.md` e `iac-security-reviewer.md` (frontmatter e regra de segurança).

### c) Falha de apply por política KMS não aceitar atualização futura do próprio key policy
- O `tofu apply` falhou na etapa de KMS porque a key policy do módulo não aceitava a atualização futura do próprio key policy da CMK.
- A correção foi aplicada no código do módulo de KMS para respeitar o modelo de permissões e o comportamento da KMS em produção.
- O problema foi um defect de design/contrato de permissões do recurso, não uma falha administrativa intencional da conta.
- Arquivo relevante: `devops-agent-iac/abordagem-1-opentofu/modules/kms/main.tf`.

### d) Falha de apply por falta de permissão `ssm:PutParameter`
- O apply foi bloqueado por `AccessDeniedException` em `ssm:PutParameter`, afetando o `aws_ssm_parameter.platform_contract`.
- A correção foi feita via policy inline escopada ao usuário `DevopsAgent`, com o nome `DevopsAgentSsmBaseInfra` ou equivalente, conforme a convenção local da sessão.
- Essa correção era necessária para permitir o contrato de saída defino em SSM, sem ampliar permissões irrestritas ao usuário.
- Arquivo relevante: `devops-agent-iac/abordagem-1-opentofu/envs/dev/main.tf`.

### e) Anexação da policy gerenciada `AmazonSSMFullAccess` ao usuário `DevopsAgent`
- A policy gerenciada `AmazonSSMFullAccess` foi anexada ao usuário `DevopsAgent`.
- Isso violou duas regras do projeto: (1) princípio de least privilege já documentado em `CLAUDE.md`; e (2) princípio de não auto-alterar a própria identidade executora.
- O problema foi ainda mais crítico porque a própria ação de anexar uma policy gerenciada de alcance tão amplo ao usuário que executa a infra não é compatível com o modelo de execução seguro do repositório.
- Isso foi uma violação de governança e segurança, não uma operação esperada no desenho da abordagem.

### f) Rotação manual da credencial exposta e remoção manual do `AmazonSSMFullAccess`
- A credencial exposta foi rotacionada manualmente pelo usuário, conforme exigência de segurança.
- O `AmazonSSMFullAccess` foi removido manualmente pelo usuário; não foi removido pelo agente, nem por automação.
- Esse passo foi crítico para reduzir o impacto da exposição e restaurar o princípio de separação entre “quem executa” e “quem administra a própria identidade”.

### g) Confusão de state: `tofu state list` retornou "No state file was found"
- Em uma sessão, `tofu state list` retornou `No state file was found`.
- Isso gerou dúvida imediata sobre se recursos criados como NAT Gateway, CMKs, VPC, buckets e endpoints estavam “órfãos” do controle do Terraform.
- A dúvida foi real e relevante: houve um problema de contexto de backend/local-state, não apenas de observação.
- O diagnóstico do backend mostrou que o problema era de ausência de `.terraform` inicializado com backend-config na sessão local, e não perda da origem do state remoto.
- Comando/arquivo relevantes: `tofu state list`, `envs/dev/.terraform/terraform.tfstate`, `envs/dev/backend.tf`, `bootstrap/main.tf`.

### h) Diagnóstico do backend S3+DynamoDB: partial configuration e ausência do `.terraform` local
- O backend da abordagem 1 usa `partial configuration`:
  - bucket, region e dynamodb_table são enviados via `-backend-config` em init;
  - o bloco `backend "s3"` em `backend.tf` não contém estes valores hardcoded.
- A causa direta do problema foi ausência de `.terraform` inicializado com o backend-config correto na sessão local, e não perda do `dev/base-infra.tfstate` remoto.
- A evidência documental e funcional aponta que o state do dev (`dev/base-infra.tfstate`) sempre esteve íntegro no bucket `agentes-devops-tfstate-702188609190` e com 125 KB.
- Arquivos relevantes: `devops-agent-iac/abordagem-1-opentofu/envs/dev/backend.tf`, `devops-agent-iac/abordagem-1-opentofu/bootstrap/main.tf`, `devops-agent-iac/abordagem-1-opentofu/README.md`, `devops-agent-iac/RUNBOOK.md`.

### i) Falta de permissão `ssm:DescribeParameters` bloqueando `tofu plan -destroy`
- Quando o plano de destruição foi refeito, o refresh do estado falhou por `AccessDeniedException` em `ssm:DescribeParameters`.
- A correção foi feita adicionando statement à policy inline do usuário, com `Resource: "*"` porque `ssm:DescribeParameters` não suporta ARN escopado de parâmetro de forma confiável para a API.
- Isso foi uma correção funcional necessária para permitir o refresh do estado; não era uma falha de infraestrutura em si.
- Arquivo/entidade relevante: `aws_ssm_parameter.platform_contract` e política inline do usuário `DevopsAgent`.

### j) Plano de destroy final limpo
- Após correção da política de SSM, o plano de destroy foi reavaliado em ambiente de dev e o cenário final mostrou `64 recursos a destruir`, com `prevent_destroy` ausente.
- O destroy do ambiente não teve bloqueio por `force_destroy` porque os buckets do projeto estavam vazios durante a verificação.
- A operação foi concluída no ambiente de dev sem nenhuma correção adicional na infraestrutura.
- Arquivos relevantes: `devops-agent-iac/abordagem-1-opentofu/envs/dev/main.tf`, `devops-agent-iac/abordagem-1-opentofu/modules/security_groups/main.tf`.

### k) Resultado real do destroy
- Resultado real do destroy: a confirmar com o usuário.
- Observação: o destroy foi executado em um momento posterior e precisa ser registrado com o estado final, o tempo efetivo e o resultado exato da AWS quando o usuário confirmar a gravação desta seção.

## 3. CAUSA RAIZ ESTRUTURAL — GOVERNANÇA DESACOPLADA DA EXECUÇÃO

A causa raiz principal não foi nenhuma falha específica do código da abordagem-1-opentofu. Foi a separação entre a camada de governança e o orquestrador de execução.

O projeto já tinha três camadas de proteção e validação:

- `cost-reviewer` (subagente): estima custo via Infracost antes de qualquer operação de provisionamento ou destruction; é uma camada de análise financeira antes de `💸`.
- `iac-security-reviewer` (subagente): revisa IAM, KMS e Security Groups antes de qualquer apply/deploy/provision; faz leitura e validação estática com `checkov`, `tflint` e `cfn-lint`.
- `guard-destructive.sh` (PreToolUse hook): bloqueia comandos destrutivos (`tofu apply`, `tofu destroy`, `cdk deploy`, `cdk destroy`, `sam deploy`, `sam delete`) e exige confirmação explícita via variável de ambiente `AGENT_IAC_CONFIRMED=yes`; também bloqueia incondicionalmente `destroy` em `prod`.

Esses mecanismos eram específicos do Claude Code:
- subagentes definidos por frontmatter com `name`, `description`, `tools` e `permissionMode`;
- hooks `PreToolUse` lendo `{"tool_name","tool_input"}` via stdin e usando exit code para bloquear a ação;
- regras do repositório em `CLAUDE.md` e em arquivos do tipo `*.md`/hooks dedicados.

O GitHub Copilot Chat não tem esse mecanismo. Ele não lê os subagentes de frontmatter do Claude Code, não aciona as hooks `PreToolUse` e não executa a lógica de bloqueio do `guard-destructive.sh` em nenhuma circunstância. Isso torna a execução via GitHub Copilot Chat incompatível com o modelo de governança já desenhado para o projeto.

Em outras palavras:
- nenhum dos incidentes de segurança (exposição de credenciais, policy gerenciada excessiva, falta de governança antes de apply) teria passado despercebido se a execução tivesse sido feita via Claude Code com os subagentes e hooks ativos;
- o `guard-destructive.sh` teria exigido confirmação explícita antes do apply/destroy;
- o `iac-security-reviewer` teria sinalizado a anexação de `AmazonSSMFullAccess` antes que ela afetasse a identidade;
- a correção de KMS e SSM também teria sido revisada antes do apply.

A causa não foi falha da abordagem-1-opentofu em si. Foi a escolha de um orquestrador que não implementa a governança que o projeto já havia desenhado para o fluxo seguro.

## 4. CORREÇÕES JÁ APLICADAS

- Credencial antiga foi desativada e removida.
- A policy gerenciada `AmazonSSMFullAccess` foi removida do usuário `DevopsAgent`.
- O arquivo `CLAUDE.md` foi reforçado com regras para:
  - proibição de exportar credenciais AWS inline;
  - proibição de auto-alterar a identidade executora;
  - exigência de checar exit code e rodar `tofu plan` antes de declarar sucesso após qualquer apply/destroy.
- O problema de KMS e o problema de SSM foram tratáveis com correção manual e com políticas inline focadas, mas isso não substitui o mecanismo de governança ativo do Claude Code.
- Verificação de `kms:EncryptionContext:aws:logs:arn` na CMK de logs: a condição precisa ser confirmada no código atual e permanece como item pendente de verificação final; a confirmação final é a confirmar com o usuário.

## 5. PENDÊNCIAS EM ABERTO

- Confirmar se a CMK de logs tem a condição obrigatória `kms:EncryptionContext:aws:logs:arn`. A verificação do código atual precisou ser revalidada com o branch em uso; pendente de confirmação.
- Trocar as policies gerenciadas de amplo alcance do usuário `DevopsAgent` por uma policy custom escopada ao prefixo `agentes-devops-*`.
- Decidir se o próximo ciclo do experimento roda via Claude Code, ativando os hooks e subagentes de fato, ou se a mesma governança será recriada para o GitHub Copilot Chat.
- O arquivo `.gitignore` ainda precisa ser confirmado; na revisão atual, ele não cobria `tfplan`, `*.tfplan`, `samconfig.toml`, `cdk.out/`, `.venv/` e `/tmp/*.json`. Confirmação final: a confirmar com o usuário.
- Resultado real do destroy e sua gravação em linha do tempo: a confirmar com o usuário.

---

## Observação final

Este documento deve ser lido como um post-mortem técnico e de governança. O objetivo não é atribuir culpa a um único arquivo de Infra, mas registrar o fato de que a governança que o repositório já havia desenhado foi desativada por escolha de orquestrador, e que isso permitiu que incidentes de segurança e de operação emergissem durante o primeiro ciclo de vida do ambiente.
