"""VPC multi-AZ, endpoints, flow logs e security groups."""
import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_kms as kms
from aws_cdk import aws_logs as logs
from constructs import Construct

from app_lib.config import EnvironmentConfig, prefix

INTERFACE_ENDPOINTS = {
    "Sqs": ec2.InterfaceVpcEndpointAwsService.SQS,
    "StepFunctions": ec2.InterfaceVpcEndpointAwsService.STEP_FUNCTIONS,
    "Glue": ec2.InterfaceVpcEndpointAwsService.GLUE,
    "Lambda": ec2.InterfaceVpcEndpointAwsService.LAMBDA_,
    "Athena": ec2.InterfaceVpcEndpointAwsService.ATHENA,
    "Kms": ec2.InterfaceVpcEndpointAwsService.KMS,
    "CloudWatchLogs": ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
    "SecretsManager": ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
    "Sts": ec2.InterfaceVpcEndpointAwsService.STS,
}


class NetworkStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        project_name: str,
        config: EnvironmentConfig,
        logs_key: kms.IKey,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        name = prefix(project_name, env_name)

        flow_log_group = logs.LogGroup(
            self,
            "FlowLogs",
            log_group_name=f"/aws/vpc/{name}/flow-logs",
            retention=logs.RetentionDays(f"{config.log_retention_days}"),
            encryption_key=logs_key,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            vpc_name=f"{name}-vpc",
            ip_addresses=ec2.IpAddresses.cidr(config.vpc_cidr),
            max_azs=config.max_azs,
            nat_gateways=config.nat_gateways,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=20,
                    map_public_ip_on_launch=False,
                ),
                ec2.SubnetConfiguration(
                    name="private", subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS, cidr_mask=20
                ),
                ec2.SubnetConfiguration(
                    name="isolated", subnet_type=ec2.SubnetType.PRIVATE_ISOLATED, cidr_mask=24
                ),
            ],
            gateway_endpoints={
                "S3": ec2.GatewayVpcEndpointOptions(service=ec2.GatewayVpcEndpointAwsService.S3),
                "DynamoDB": ec2.GatewayVpcEndpointOptions(
                    service=ec2.GatewayVpcEndpointAwsService.DYNAMODB
                ),
            },
            flow_logs={
                "all": ec2.FlowLogOptions(
                    destination=ec2.FlowLogDestination.to_cloud_watch_logs(flow_log_group),
                    traffic_type=ec2.FlowLogTrafficType.ALL,
                )
            },
        )

        if config.enable_interface_endpoints:
            for endpoint_id, service in INTERFACE_ENDPOINTS.items():
                self.vpc.add_interface_endpoint(
                    endpoint_id,
                    service=service,
                    private_dns_enabled=True,
                    subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
                )

        self.lambda_sg = ec2.SecurityGroup(
            self,
            "LambdaSg",
            vpc=self.vpc,
            security_group_name=f"{name}-lambda-sg",
            description="SG das funcoes Lambda em subnets privadas",
            allow_all_outbound=False,
        )
        self.lambda_sg.add_egress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443), "HTTPS para servicos AWS")

        self.glue_sg = ec2.SecurityGroup(
            self,
            "GlueSg",
            vpc=self.vpc,
            security_group_name=f"{name}-glue-sg",
            description="SG das Glue Connections",
            allow_all_outbound=False,
        )
        self.glue_sg.add_ingress_rule(self.glue_sg, ec2.Port.all_traffic(), "Self-reference exigido pelo Glue")
        self.glue_sg.add_egress_rule(self.glue_sg, ec2.Port.all_traffic(), "Self-reference exigido pelo Glue")
        self.glue_sg.add_egress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443), "HTTPS para S3/Glue/KMS")

        self.microservices_sg = ec2.SecurityGroup(
            self,
            "MicroservicesSg",
            vpc=self.vpc,
            security_group_name=f"{name}-microservices-sg",
            description="SG reservado para os proximos agentes",
            allow_all_outbound=False,
        )
        self.microservices_sg.add_ingress_rule(
            ec2.Peer.ipv4(config.vpc_cidr), ec2.Port.tcp(8080), "HTTP interno da VPC"
        )
        self.microservices_sg.add_egress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443), "HTTPS de saida")

        cdk.CfnOutput(self, "VpcId", value=self.vpc.vpc_id, export_name=f"{name}-py-vpc-id")
