# Multiagents DevOps Research System

Repositório experimental que reúne um conjunto de artefatos para pesquisa, automação e comparação de abordagens de infraestrutura como código (IaC), políticas de segurança e orchestration de agentes DevOps.

## Estrutura do projeto

- [CLAUDE.md](CLAUDE.md) — instruções e regras do projeto para o agente Claude Code.
- [devops-agent-iac/](devops-agent-iac) — núcleo do experimento principal, com três abordagens de provisionamento na AWS.
- [cost-reviewer.md](cost-reviewer.md) — revisão de custo e impacto financeiro.
- [iac-security-reviewer.md](iac-security-reviewer.md) — revisão de segurança e hardening.
- [guard-destructive.sh](guard-destructive.sh) — proteção para ações destrutivas.
- [settings.json](settings.json) — configuração local do ambiente/editor.

## Projeto principal

O diretório [devops-agent-iac/](devops-agent-iac) contém a implementação principal do experimento:

- abordagem-1-opentofu/
- abordagem-2-cdk-python/
- abordagem-3-serverless-agent/
- anexos/cdk-typescript/
- README.md
- RUNBOOK.md
- COMPARATIVO.md
- CLAUDE.md

Leia primeiro:

1. [CLAUDE.md](CLAUDE.md)
2. [devops-agent-iac/README.md](devops-agent-iac/README.md)
3. [devops-agent-iac/RUNBOOK.md](devops-agent-iac/RUNBOOK.md)
4. [devops-agent-iac/COMPARATIVO.md](devops-agent-iac/COMPARATIVO.md)


## Objetivo geral

Este repositório funciona como um laboratório de pesquisa para avaliar diferentes modelos de provisionamento, governança e automação em ambientes cloud, com foco em:

- infraestrutura como código;
- segurança e least privilege;
- custos operacionais;
- orquestração e automação de agentes; e
- comparação entre paradigmas declarativos e imperativos.
