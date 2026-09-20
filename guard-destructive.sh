#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash). Bloqueia comandos que criam/destroem
# infraestrutura real, mesmo que o comando esteja fora da lista `ask` do
# settings.json — a lista `permissions.deny/ask` para Bash tem bugs
# documentados com comandos compostos (pipes, subshells), então o bloqueio
# de verdade fica aqui, não só na config declarativa.
#
# Contrato: recebe no stdin um JSON {"tool_name": "...", "tool_input": {...}}.
# Saida: exit 0 libera; exit 2 bloqueia e devolve stderr para o Claude.
set -euo pipefail

INPUT="$(cat)"
CMD="$(echo "$INPUT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || echo "")"

[ -z "$CMD" ] && exit 0

# Padroes que provisionam/destroem recursos reais nas tres abordagens.
DESTRUCTIVE_PATTERN='tofu apply|tofu destroy|terraform apply|terraform destroy|cdk deploy|cdk destroy|sam deploy|sam delete|stepfunctions start-execution|events put-events|scripts/trigger\.sh|scripts/destroy\.sh'

if ! echo "$CMD" | grep -qE "$DESTRUCTIVE_PATTERN"; then
  exit 0
fi

# Exige que a MENSAGEM DO USUARIO nesta rodada (nao o comando) contenha
# confirmacao explicita. O hook nao tem acesso ao prompt do usuario
# diretamente, entao usa uma marca de ambiente que o usuario define quando
# de fato autoriza a execucao nesta sessao.
if [ "${AGENT_IAC_CONFIRMED:-}" != "yes" ]; then
  cat >&2 <<'MSG'
Bloqueado: este comando cria ou destroi infraestrutura real (custo real e/ou
efeito irreversivel). Para autorizar nesta sessao, rode:

  export AGENT_IAC_CONFIRMED=yes

e peca a operacao novamente. Revise o plan/diff/dry-run antes de confirmar.
MSG
  exit 2
fi

# Mesmo confirmado, destroy de prod nunca passa por aqui.
if echo "$CMD" | grep -qE 'prod' && echo "$CMD" | grep -qE 'destroy|delete'; then
  echo "Bloqueado: destroy/delete em ambiente prod nao e permitido por este hook, mesmo com AGENT_IAC_CONFIRMED=yes. Siga o processo de break-glass do RUNBOOK." >&2
  exit 2
fi

exit 0
