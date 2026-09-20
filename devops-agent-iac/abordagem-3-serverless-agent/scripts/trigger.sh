#!/usr/bin/env bash
# Dispara o provisionamento por evento e acompanha a execucao ate o fim.
# Uso: ./scripts/trigger.sh dev [dry-run]
set -euo pipefail

ENVIRONMENT="${1:-dev}"
DRY_RUN="${2:-}"
PROJECT="${PROJECT_NAME:-agentes-devops}"
BUS="${PROJECT}-agent-bus"

DETAIL=$(jq -nc --arg env "$ENVIRONMENT" --argjson dry "$([ "$DRY_RUN" = "dry-run" ] && echo true || echo false)" \
  '{environment: $env, dry_run: $dry}')

aws events put-events --entries "$(jq -nc --arg bus "$BUS" --arg detail "$DETAIL" '[{
  EventBusName: $bus,
  Source: "devops.agent",
  DetailType: "base-infra.provision-requested",
  Detail: $detail
}]')" >/dev/null

echo "evento publicado; aguardando execucao..."
sleep 8

SM_ARN=$(aws stepfunctions list-state-machines \
  --query "stateMachines[?name=='${PROJECT}-provisioning'].stateMachineArn | [0]" --output text)
EXEC_ARN=$(aws stepfunctions list-executions --state-machine-arn "$SM_ARN" --max-items 1 \
  --query 'executions[0].executionArn' --output text)

echo "execucao: $EXEC_ARN"
while true; do
  STATUS=$(aws stepfunctions describe-execution --execution-arn "$EXEC_ARN" --query status --output text)
  echo "status: $STATUS"
  [[ "$STATUS" == "RUNNING" ]] || break
  sleep 15
done

aws stepfunctions describe-execution --execution-arn "$EXEC_ARN" --query output --output text | jq .
