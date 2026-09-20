---
name: cost-check
description: Levanta o custo real acumulado das tres abordagens na conta AWS, agrupado pela tag ManagedBy, e compara com as estimativas do COMPARATIVO.md. Use quando o usuario pedir para "conferir custo", "ver quanto gastei" ou "atualizar as métricas de custo".
allowed-tools: Bash(aws ce get-cost-and-usage*), Bash(aws ec2 describe-nat-gateways*), Bash(aws ec2 describe-addresses*), Read, Edit
---

# cost-check

1. Custo por abordagem via Cost Explorer, agrupado pela tag `ManagedBy`
   (valores: `OpenTofu`, `AWS-CDK-Python`, `serverless-devops-agent`):
   ```
   aws ce get-cost-and-usage \
     --time-period Start=$(date -d '7 days ago' +%F),End=$(date +%F) \
     --granularity DAILY --metrics UnblendedCost \
     --group-by Type=TAG,Key=ManagedBy
   ```
2. Resíduos que ainda cobram:
   ```
   aws ec2 describe-nat-gateways --query 'NatGateways[?State==`available`]'
   aws ec2 describe-addresses --query 'Addresses[?AssociationId==null]'
   ```
3. Compare os números reais com a seção 3 do `COMPARATIVO.md`. Se a
   diferença for relevante, proponha a edição da tabela (não edite sem
   mostrar o diff primeiro).

Não rode nada que crie ou destrua recursos a partir desta skill.
