"""Security Groups de workload, com egress restrito a 443."""
from common.aws_clients import client
from common.logging_conf import get_logger
from common.registry import claim, commit, get
from common.tagging import tag_spec

log = get_logger(__name__)
ec2 = client("ec2")

GROUPS = {
    "sg-lambda": "SG das funcoes Lambda em subnets privadas",
    "sg-glue": "SG das Glue Connections",
    "sg-microservices": "SG reservado para os proximos agentes",
}


def _revoke_default_egress(sg_id: str) -> None:
    """A AWS cria egress 0.0.0.0/0 all-traffic por padrao. Removemos."""
    ec2.revoke_security_group_egress(
        GroupId=sg_id,
        IpPermissions=[{"IpProtocol": "-1", "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}],
    )


def handler(event: dict, context) -> dict:
    env = event["environment"]
    execution_id = event["execution_id"]
    out = event["outputs"]
    vpc_id = out["vpc_id"]
    vpc_cidr = event["spec"]["vpc_cidr"]

    for order, (logical_id, description) in enumerate(GROUPS.items(), start=40):
        if not claim(env, logical_id, "ec2:security-group", {"vpc": vpc_id}, execution_id):
            out[logical_id] = get(env, logical_id)["physical_id"]
            continue

        sg_id = ec2.create_security_group(
            GroupName=f"{env}-{logical_id}",
            Description=description,
            VpcId=vpc_id,
            TagSpecifications=tag_spec("security-group", env, logical_id),
        )["GroupId"]
        _revoke_default_egress(sg_id)

        ec2.authorize_security_group_egress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "HTTPS para servicos AWS"}],
                }
            ],
        )

        if logical_id == "sg-glue":
            ec2.authorize_security_group_ingress(
                GroupId=sg_id,
                IpPermissions=[{"IpProtocol": "-1", "UserIdGroupPairs": [{"GroupId": sg_id}]}],
            )
            ec2.authorize_security_group_egress(
                GroupId=sg_id,
                IpPermissions=[{"IpProtocol": "-1", "UserIdGroupPairs": [{"GroupId": sg_id}]}],
            )

        if logical_id == "sg-microservices":
            ec2.authorize_security_group_ingress(
                GroupId=sg_id,
                IpPermissions=[
                    {
                        "IpProtocol": "tcp",
                        "FromPort": 8080,
                        "ToPort": 8080,
                        "IpRanges": [{"CidrIp": vpc_cidr, "Description": "HTTP interno da VPC"}],
                    }
                ],
            )

        commit(env, logical_id, sg_id, order)
        out[logical_id] = sg_id
        log.info("security group criado", extra={"logical_id": logical_id, "physical_id": sg_id})

    event["outputs"] = out
    return event
