"""Destruicao controlada: percorre o registro na ordem inversa de criacao.

Nao existe `destroy -auto-approve` implicito: o fluxo exige
`confirm == "DESTROY-<env>"` no evento de entrada. Sem isso, falha cedo.
"""
import time

from botocore.exceptions import ClientError

from common.aws_clients import client
from common.errors import FatalError, NotReadyError
from common.logging_conf import get_logger
from common.registry import list_created, mark_deleted

log = get_logger(__name__)
ec2 = client("ec2")
iam = client("iam")
kms = client("kms")


def _delete_nat(physical_id: str) -> None:
    for nat_id in physical_id.split(","):
        try:
            ec2.delete_nat_gateway(NatGatewayId=nat_id)
        except ClientError as exc:
            if "NotFound" not in exc.response["Error"]["Code"]:
                raise
    deadline = time.time() + 240
    while time.time() < deadline:
        states = [
            n["State"]
            for n in ec2.describe_nat_gateways(NatGatewayIds=physical_id.split(","))["NatGateways"]
        ]
        if all(s == "deleted" for s in states):
            break
        time.sleep(15)
    else:
        raise NotReadyError("NAT ainda em delecao; a state machine tentara novamente")

    for addr in ec2.describe_addresses()["Addresses"]:
        if "AssociationId" not in addr and addr.get("Tags"):
            if any(t["Key"] == "ManagedBy" and t["Value"] == "serverless-devops-agent" for t in addr["Tags"]):
                ec2.release_address(AllocationId=addr["AllocationId"])


DELETERS = {
    "ec2:vpc-endpoint": lambda pid: ec2.delete_vpc_endpoints(VpcEndpointIds=pid.split(",")),
    "ec2:route-table": lambda pid: [
        ec2.delete_route_table(RouteTableId=r) for r in pid.split(",")
    ],
    "ec2:nat-gateway": _delete_nat,
    "ec2:subnet": lambda pid: [ec2.delete_subnet(SubnetId=s) for s in pid.split(",")],
    "ec2:security-group": lambda pid: ec2.delete_security_group(GroupId=pid),
    "iam:role": None,  # tratado separadamente (precisa remover policies antes)
    "ec2:internet-gateway": None,
    "ec2:vpc": lambda pid: ec2.delete_vpc(VpcId=pid),
    "kms:key": None,
}


def handler(event: dict, context) -> dict:
    env = event["environment"]
    if event.get("confirm") != f"DESTROY-{env}":
        raise FatalError(f'Confirmacao ausente ou invalida. Esperado: "DESTROY-{env}"')
    if env == "prod" and not event.get("break_glass"):
        raise FatalError("Destroy de producao exige break_glass explicito e aprovacao fora do agente")

    resources = list(reversed(list_created(env)))
    deleted, skipped = [], []

    for item in resources:
        logical_id = item["logical_id"]
        rtype = item["resource_type"]
        pid = item["physical_id"]
        try:
            if rtype == "iam:role":
                role_name = pid.split("/")[-1]
                for policy in iam.list_role_policies(RoleName=role_name)["PolicyNames"]:
                    iam.delete_role_policy(RoleName=role_name, PolicyName=policy)
                iam.delete_role(RoleName=role_name)
            elif rtype == "kms:key":
                # KMS nao deleta imediatamente: agenda com janela minima de 7 dias.
                kms.schedule_key_deletion(KeyId=pid, PendingWindowInDays=7)
            elif rtype == "ec2:internet-gateway":
                vpc = ec2.describe_internet_gateways(InternetGatewayIds=[pid])["InternetGateways"][0]
                for att in vpc.get("Attachments", []):
                    ec2.detach_internet_gateway(InternetGatewayId=pid, VpcId=att["VpcId"])
                ec2.delete_internet_gateway(InternetGatewayId=pid)
            else:
                deleter = DELETERS.get(rtype)
                if deleter is None:
                    skipped.append(logical_id)
                    continue
                deleter(pid)

            mark_deleted(env, logical_id)
            deleted.append(logical_id)
            log.info("recurso removido", extra={"logical_id": logical_id, "action": "delete"})
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code in ("DependencyViolation", "InvalidParameterValue"):
                # Ordem inversa nem sempre basta: ENIs orfas seguram subnets/SGs.
                raise NotReadyError(f"{logical_id}: {code}") from exc
            if "NotFound" in code or "NoSuchEntity" in code:
                mark_deleted(env, logical_id)
                deleted.append(logical_id)
                continue
            raise

    return {"environment": env, "deleted": deleted, "skipped": skipped, "remaining": len(list_created(env))}
