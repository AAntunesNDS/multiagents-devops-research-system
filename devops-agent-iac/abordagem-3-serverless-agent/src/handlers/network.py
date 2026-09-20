"""Provisionamento de rede: VPC, IGW, subnets, NAT, route tables e endpoints.

A criacao do NAT Gateway e assincrona (2-5 min). O handler NAO bloqueia
esperando: ele cria e devolve o estado, e a state machine faz o polling via
`nat_poller`. Esse e o padrao que substitui o "apply que espera" do OpenTofu
dentro do limite de 15 min da Lambda.
"""
import ipaddress

from botocore.exceptions import ClientError

from common.aws_clients import client
from common.errors import FatalError, RetryableError
from common.logging_conf import get_logger
from common.registry import commit, claim, fail, get
from common.tagging import tag_spec, tags

log = get_logger(__name__)
ec2 = client("ec2")


def _subnet_cidrs(vpc_cidr: str, az_count: int) -> tuple[list[str], list[str]]:
    net = ipaddress.ip_network(vpc_cidr)
    blocks = list(net.subnets(new_prefix=20))
    return [str(b) for b in blocks[:az_count]], [str(b) for b in blocks[az_count : az_count * 2]]


def _azs(az_count: int) -> list[str]:
    zones = ec2.describe_availability_zones(
        Filters=[{"Name": "state", "Values": ["available"]}]
    )["AvailabilityZones"]
    return [z["ZoneName"] for z in zones[:az_count]]


def handler(event: dict, context) -> dict:
    env = event["environment"]
    execution_id = event["execution_id"]
    spec = event["spec"]
    outputs = event.get("outputs", {})

    vpc_cidr = spec["vpc_cidr"]
    az_count = int(spec.get("az_count", 2))
    single_nat = bool(spec.get("single_nat_gateway", True))

    try:
        # ------------------------------- VPC -------------------------------
        if claim(env, "vpc", "ec2:vpc", {"cidr": vpc_cidr}, execution_id):
            vpc_id = ec2.create_vpc(
                CidrBlock=vpc_cidr, TagSpecifications=tag_spec("vpc", env, "vpc")
            )["Vpc"]["VpcId"]
            ec2.get_waiter("vpc_available").wait(VpcIds=[vpc_id])
            ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport={"Value": True})
            ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={"Value": True})
            commit(env, "vpc", vpc_id, 20)
        else:
            vpc_id = get(env, "vpc")["physical_id"]
        outputs["vpc_id"] = vpc_id

        # ------------------------------- IGW -------------------------------
        if claim(env, "igw", "ec2:internet-gateway", {"vpc": vpc_id}, execution_id):
            igw_id = ec2.create_internet_gateway(
                TagSpecifications=tag_spec("internet-gateway", env, "igw")
            )["InternetGateway"]["InternetGatewayId"]
            ec2.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
            commit(env, "igw", igw_id, 21)
        else:
            igw_id = get(env, "igw")["physical_id"]
        outputs["igw_id"] = igw_id

        # ----------------------------- Subnets -----------------------------
        public_cidrs, private_cidrs = _subnet_cidrs(vpc_cidr, az_count)
        azs = _azs(az_count)
        subnet_spec = {"public": public_cidrs, "private": private_cidrs, "azs": azs}

        if claim(env, "subnets", "ec2:subnet", subnet_spec, execution_id):
            public_ids, private_ids = [], []
            for idx, az in enumerate(azs):
                pub = ec2.create_subnet(
                    VpcId=vpc_id,
                    CidrBlock=public_cidrs[idx],
                    AvailabilityZone=az,
                    TagSpecifications=[
                        {
                            "ResourceType": "subnet",
                            "Tags": tags(env, "subnets", {"Tier": "public", "Name": f"{env}-public-{az}"}),
                        }
                    ],
                )["Subnet"]["SubnetId"]
                priv = ec2.create_subnet(
                    VpcId=vpc_id,
                    CidrBlock=private_cidrs[idx],
                    AvailabilityZone=az,
                    TagSpecifications=[
                        {
                            "ResourceType": "subnet",
                            "Tags": tags(env, "subnets", {"Tier": "private", "Name": f"{env}-private-{az}"}),
                        }
                    ],
                )["Subnet"]["SubnetId"]
                public_ids.append(pub)
                private_ids.append(priv)
            commit(env, "subnets", ",".join(public_ids + private_ids), 22,
                   {"public": public_ids, "private": private_ids})
        else:
            stored = get(env, "subnets")["physical_id"].split(",")
            public_ids, private_ids = stored[:az_count], stored[az_count:]

        outputs["public_subnet_ids"] = public_ids
        outputs["private_subnet_ids"] = private_ids

        # ------------------------------- NAT -------------------------------
        nat_count = 1 if single_nat else az_count
        if claim(env, "nat", "ec2:nat-gateway", {"count": nat_count}, execution_id):
            nat_ids = []
            for idx in range(nat_count):
                alloc = ec2.allocate_address(
                    Domain="vpc", TagSpecifications=tag_spec("elastic-ip", env, "nat")
                )["AllocationId"]
                nat_ids.append(
                    ec2.create_nat_gateway(
                        SubnetId=public_ids[idx],
                        AllocationId=alloc,
                        TagSpecifications=tag_spec("natgateway", env, "nat"),
                    )["NatGateway"]["NatGatewayId"]
                )
            commit(env, "nat", ",".join(nat_ids), 23)
        else:
            nat_ids = get(env, "nat")["physical_id"].split(",")
        outputs["nat_gateway_ids"] = nat_ids

    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        fail(env, "vpc", str(exc))
        if code in ("RequestLimitExceeded", "Unavailable", "InsufficientInstanceCapacity"):
            raise RetryableError(code) from exc
        if code == "AddressLimitExceeded":
            raise FatalError(
                "Limite de Elastic IPs atingido (default 5/regiao). Libere EIPs orfaos "
                "ou solicite aumento de quota antes de repetir."
            ) from exc
        raise

    event["outputs"] = outputs
    return event
