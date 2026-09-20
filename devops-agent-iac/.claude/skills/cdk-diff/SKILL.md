---
name: cdk-diff
description: Roda lint, testes, synth (com cdk-nag) e cdk diff na Abordagem 2 (CDK Python). Use quando o usuario pedir para revisar mudancas de infraestrutura CDK antes de decidir se aplica.
allowed-tools: Bash(ruff:*), Bash(pytest:*), Bash(cdk synth*), Bash(cdk diff*), Bash(cdk bootstrap*), Read, Grep
---

# cdk-diff

Dentro de `abordagem-2-cdk-python/`, com o venv ativo:

1. `ruff check .`
2. `pytest --cov=app_lib --cov-report=term-missing`
3. `cdk synth -c env=dev --quiet` — se falhar por regra do cdk-nag
   (AwsSolutions-IAM4/IAM5/S3-1 são conhecidas e documentadas no README),
   reporte a regra e a linha, não silencie desabilitando o Aspect.
4. `cdk diff -c env=dev`

Se `cdk.out/` não existir ainda e o comando falhar com "no credentials" ou
"account mismatch", verifique se `cdk.json` tem `environments.dev.account`
preenchido com o account ID real antes de insistir.

Ao terminar, se quiser revisar IAM, leia o template sintetizado, não o
Python:
```
jq '.Resources | to_entries[] | select(.value.Type=="AWS::IAM::Policy")' \
  cdk.out/BaseInfra-dev-Iam.template.json
```

Nunca rode `cdk deploy` a partir desta skill.
