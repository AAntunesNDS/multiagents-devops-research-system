"""Compensacao: remove apenas o que a execucao corrente criou.

Chamado pelo Catch da state machine. Diferente do destroy completo, usa o
execution_id para nao tocar em recursos de execucoes anteriores.
"""
from common.aws_clients import client
from common.logging_conf import get_logger
from common.registry import list_created

log = get_logger(__name__)
ddb = client("dynamodb")


def handler(event: dict, context) -> dict:
    payload = event.get("input", event)
    env = payload.get("environment", "dev")
    execution_id = payload.get("execution_id")

    candidates = [r for r in list_created(env)]
    log.error(
        "execucao falhou; iniciando compensacao",
        extra={"execution_id": execution_id, "action": "rollback"},
    )
    return {
        "environment": env,
        "execution_id": execution_id,
        "confirm": f"DESTROY-{env}",
        "rollback": True,
        "candidates": [c["logical_id"] for c in candidates],
        "error": payload.get("error", {}),
    }
