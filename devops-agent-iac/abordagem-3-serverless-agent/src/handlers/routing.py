"""Route tables, associacoes e gateway endpoints (S3/DynamoDB, gratuitos)."""
from common.aws_clients import client
from common.logging_conf import get_logger
from common.registry import claim, commit, get
from common.tagging import tag_spec

log = get_logger(__name__)
ec2 = client("ec2")


def handler(event: dict, context) -> dict:
    env = event["environment"]
    execution_id = event["execution_id"]
    out = event["outputs"]
    vpc_id, igw_id = out["vpc_id"], out["igw_id"]
    nat_ids = out["nat_gateway_ids"]
    public_ids, private_ids = out["public_subnet_ids"], out["private_subnet_ids"]

    if claim(env, "route-tables", "ec2:route-table", {"subnets": len(private_ids)}, execution_id):
        public_rt = ec2.create_route_table(
            VpcId=vpc_id, TagSpecifications=tag_spec("route-table", env, "route-tables")
        )["RouteTable"]["RouteTableId"]
        ec2.create_route(RouteTableId=public_rt, DestinationCidrBlock="0.0.0.0/0", GatewayId=igw_id)
        for subnet_id in public_ids:
            ec2.associate_route_table(RouteTableId=public_rt, SubnetId=subnet_id)

        private_rts = []
        for idx, subnet_id in enumerate(private_ids):
            rt = ec2.create_route_table(
                VpcId=vpc_id, TagSpecifications=tag_spec("route-table", env, "route-tables")
            )["RouteTable"]["RouteTableId"]
            ec2.create_route(
                RouteTableId=rt,
                DestinationCidrBlock="0.0.0.0/0",
                NatGatewayId=nat_ids[idx] if len(nat_ids) > idx else nat_ids[0],
            )
            ec2.associate_route_table(RouteTableId=rt, SubnetId=subnet_id)
            private_rts.append(rt)

        commit(env, "route-tables", ",".join([public_rt, *private_rts]), 30,
               {"public": public_rt, "private": private_rts})
    else:
        stored = get(env, "route-tables")["physical_id"].split(",")
        public_rt, private_rts = stored[0], stored[1:]

    out["public_route_table_id"] = public_rt
    out["private_route_table_ids"] = private_rts

    if claim(env, "endpoints", "ec2:vpc-endpoint", {"services": ["s3", "dynamodb"]}, execution_id):
        endpoint_ids = []
        region = ec2.meta.region_name
        for service in ("s3", "dynamodb"):
            endpoint_ids.append(
                ec2.create_vpc_endpoint(
                    VpcId=vpc_id,
                    ServiceName=f"com.amazonaws.{region}.{service}",
                    VpcEndpointType="Gateway",
                    RouteTableIds=private_rts + ([public_rt] if service == "s3" else []),
                    TagSpecifications=tag_spec("vpc-endpoint", env, "endpoints"),
                )["VpcEndpoint"]["VpcEndpointId"]
            )
        commit(env, "endpoints", ",".join(endpoint_ids), 31)

    event["outputs"] = out
    return event
