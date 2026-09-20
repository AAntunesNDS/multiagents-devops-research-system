"""Polling do NAT Gateway: chamado em loop pela state machine (Wait + Choice)."""
from common.aws_clients import client
from common.logging_conf import get_logger

log = get_logger(__name__)
ec2 = client("ec2")


def handler(event: dict, context) -> dict:
    nat_ids = event["outputs"]["nat_gateway_ids"]
    states = {
        n["NatGatewayId"]: n["State"]
        for n in ec2.describe_nat_gateways(NatGatewayIds=nat_ids)["NatGateways"]
    }
    log.info("estado dos NAT", extra={"action": "poll", "physical_id": ",".join(nat_ids)})

    if any(s in ("failed", "deleted") for s in states.values()):
        event["nat_status"] = "FAILED"
    elif all(s == "available" for s in states.values()):
        event["nat_status"] = "AVAILABLE"
    else:
        event["nat_status"] = "PENDING"
    event["nat_states"] = states
    return event
