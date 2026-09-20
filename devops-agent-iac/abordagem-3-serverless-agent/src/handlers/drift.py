"""Deteccao de drift: compara o registro com o estado real na AWS.

Acionada por regra agendada do EventBridge. E o equivalente ao `tofu plan` em
modo refresh-only, porem escrito a mao para cada tipo de recurso -- o custo
estrutural desta abordagem.
"""
import json
import os

from botocore.exceptions import ClientError

from common.aws_clients import client
from common.logging_conf import get_logger
from common.registry import list_created

log = get_logger(__name__)
ec2 = client("ec2")
iam = client("iam")
events = client("events")
EVENT_BUS = os.environ["EVENT_BUS"]

CHECKS = {
    "ec2:vpc": lambda pid: ec2.describe_vpcs(VpcIds=[pid]),
    "ec2:subnet": lambda pid: ec2.describe_subnets(SubnetIds=pid.split(",")),
    "ec2:security-group": lambda pid: ec2.describe_security_groups(GroupIds=[pid]),
    "ec2:nat-gateway": lambda pid: ec2.describe_nat_gateways(NatGatewayIds=pid.split(",")),
    "iam:role": lambda pid: iam.get_role(RoleName=pid.split("/")[-1]),
}


def handler(event: dict, context) -> dict:
    env = event.get("environment", os.getenv("DEFAULT_ENV", "dev"))
    missing, ok = [], 0

    for item in list_created(env):
        check = CHECKS.get(item["resource_type"])
        if check is None:
            continue
        try:
            check(item["physical_id"])
            ok += 1
        except ClientError as exc:
            log.warning("recurso ausente", extra={"logical_id": item["logical_id"]})
            missing.append({"logical_id": item["logical_id"], "error": exc.response["Error"]["Code"]})

    if missing:
        events.put_events(
            Entries=[
                {
                    "EventBusName": EVENT_BUS,
                    "Source": "devops.agent",
                    "DetailType": "base-infra.drift-detected",
                    "Detail": json.dumps({"environment": env, "missing": missing}),
                }
            ]
        )

    return {"environment": env, "checked": ok, "missing": missing, "drift": bool(missing)}
