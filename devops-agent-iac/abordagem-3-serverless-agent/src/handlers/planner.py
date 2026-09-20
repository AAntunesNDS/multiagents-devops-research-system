"""Planner: transforma a spec desejada em um plano de acoes.

Equivalente funcional do `tofu plan`: le a spec (SSM), confronta com o registro
(DynamoDB) e devolve, para cada recurso logico, a acao CREATE / NOOP / DRIFT.
O plano vai inteiro no payload da execucao para ficar auditavel no historico da
state machine.
"""
import json
import os

from common.aws_clients import client
from common.logging_conf import get_logger
from common.registry import STATUS_CREATED, get, spec_hash

log = get_logger(__name__)
SPEC_PARAMETER = os.environ["SPEC_PARAMETER"]

RESOURCE_ORDER = [
    ("kms", ["kms-data", "kms-messaging", "kms-logs"]),
    ("network", ["vpc", "igw", "subnets", "nat", "route-tables", "endpoints", "flow-logs"]),
    ("security", ["sg-lambda", "sg-glue", "sg-microservices"]),
    ("identity", ["role-lambda", "role-glue", "role-stepfunctions"]),
]


def handler(event: dict, context) -> dict:
    env = event["environment"]
    execution_id = event.get("execution_id", getattr(context, "aws_request_id", "local"))

    spec = json.loads(
        client("ssm").get_parameter(Name=f"{SPEC_PARAMETER}/{env}")["Parameter"]["Value"]
    )

    plan = []
    for stage, logical_ids in RESOURCE_ORDER:
        for logical_id in logical_ids:
            record = get(env, logical_id)
            desired = spec.get(logical_id, spec)
            if record is None or record["status"] != STATUS_CREATED:
                action = "CREATE"
            elif record["spec_hash"] != spec_hash(desired):
                action = "DRIFT"
            else:
                action = "NOOP"
            plan.append({"stage": stage, "logical_id": logical_id, "action": action})

    summary = {
        "create": sum(1 for p in plan if p["action"] == "CREATE"),
        "noop": sum(1 for p in plan if p["action"] == "NOOP"),
        "drift": sum(1 for p in plan if p["action"] == "DRIFT"),
    }
    log.info("plano calculado", extra={"execution_id": execution_id, "action": "plan"})

    return {
        "environment": env,
        "execution_id": execution_id,
        "spec": spec,
        "plan": plan,
        "summary": summary,
        "dry_run": event.get("dry_run", False),
    }
