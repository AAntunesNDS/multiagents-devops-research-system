"""Asseroes sobre o template sintetizado - executam em segundos, sem tocar na AWS."""
import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

from app_lib.config import EnvironmentConfig
from app_lib.stacks.encryption_stack import EncryptionStack
from app_lib.stacks.network_stack import NetworkStack

CONFIG = EnvironmentConfig(
    account="111111111111",
    region="us-east-1",
    vpc_cidr="10.22.0.0/16",
    max_azs=2,
    nat_gateways=1,
    enable_interface_endpoints=False,
    log_retention_days=14,
)
COMMON = {"env_name": "dev", "project_name": "agentes-devops", "config": CONFIG}
ENV = cdk.Environment(account=CONFIG.account, region=CONFIG.region)


@pytest.fixture
def stacks():
    app = cdk.App()
    encryption = EncryptionStack(app, "Enc", env=ENV, **COMMON)
    network = NetworkStack(app, "Net", env=ENV, logs_key=encryption.logs_key, **COMMON)
    return encryption, network


def test_todas_cmks_com_rotacao(stacks):
    encryption, _ = stacks
    template = Template.from_stack(encryption)
    template.resource_count_is("AWS::KMS::Key", 3)
    template.all_resources_properties("AWS::KMS::Key", {"EnableKeyRotation": True})


def test_vpc_multi_az(stacks):
    _, network = stacks
    template = Template.from_stack(network)
    template.resource_count_is("AWS::EC2::Subnet", 6)
    template.resource_count_is("AWS::EC2::NatGateway", 1)
    template.has_resource_properties("AWS::EC2::VPC", {"CidrBlock": "10.22.0.0/16"})


def test_nenhuma_subnet_com_ip_publico_automatico(stacks):
    _, network = stacks
    Template.from_stack(network).all_resources_properties(
        "AWS::EC2::Subnet", {"MapPublicIpOnLaunch": Match.absent()}
    )


def test_flow_logs_habilitados(stacks):
    _, network = stacks
    Template.from_stack(network).resource_count_is("AWS::EC2::FlowLog", 1)
