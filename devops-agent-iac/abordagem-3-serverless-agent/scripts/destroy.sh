#!/usr/bin/env bash
# Destruicao controlada. Exige confirmacao textual explicita.
# Uso: ./scripts/destroy.sh dev DESTROY-dev
set -euo pipefail

ENVIRONMENT="${1:?informe o ambiente}"
CONFIRM="${2:?informe DESTROY-<ambiente>}"
PROJECT="${PROJECT_NAME:-agentes-devops}"

[[ "$CONFIRM" == "DESTROY-${ENVIRONMENT}" ]] || { echo "confirmacao invalida"; exit 1; }

SM_ARN=$(aws stepfunctions list-state-machines \
  --query "stateMachines[?name=='${PROJECT}-decommission'].stateMachineArn | [0]" --output text)

EXEC_ARN=$(aws stepfunctions start-execution --state-machine-arn "$SM_ARN" \
  --input "$(jq -nc --arg env "$ENVIRONMENT" --arg c "$CONFIRM" '{environment:$env, confirm:$c}')" \
  --query executionArn --output text)

while true; do
  STATUS=$(aws stepfunctions describe-execution --execution-arn "$EXEC_ARN" --query status --output text)
  echo "status: $STATUS"
  [[ "$STATUS" == "RUNNING" ]] || break
  sleep 20
done
aws stepfunctions describe-execution --execution-arn "$EXEC_ARN" --query output --output text | jq .
