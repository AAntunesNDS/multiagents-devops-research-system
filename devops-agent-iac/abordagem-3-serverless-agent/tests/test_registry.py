"""Testes do registro (substituto do state). Usam moto para simular o DynamoDB."""
import os

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("REGISTRY_TABLE", "test-registry")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def registry():
    with mock_aws():
        ddb = boto3.client("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="test-registry",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "env", "AttributeType": "S"},
                {"AttributeName": "logical_id", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "by-env",
                    "KeySchema": [
                        {"AttributeName": "env", "KeyType": "HASH"},
                        {"AttributeName": "logical_id", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        from common import registry as module  # import tardio: depende do env

        yield module


def test_claim_permite_primeira_criacao(registry):
    assert registry.claim("dev", "vpc", "ec2:vpc", {"cidr": "10.0.0.0/16"}, "exec-1") is True


def test_claim_e_idempotente_apos_commit(registry):
    registry.claim("dev", "vpc", "ec2:vpc", {"cidr": "10.0.0.0/16"}, "exec-1")
    registry.commit("dev", "vpc", "vpc-123", 20)
    # segunda execucao com a mesma spec nao recria
    assert registry.claim("dev", "vpc", "ec2:vpc", {"cidr": "10.0.0.0/16"}, "exec-2") is False


def test_spec_divergente_e_erro_fatal(registry):
    from common.errors import FatalError

    registry.claim("dev", "vpc", "ec2:vpc", {"cidr": "10.0.0.0/16"}, "exec-1")
    registry.commit("dev", "vpc", "vpc-123", 20)
    with pytest.raises(FatalError):
        registry.claim("dev", "vpc", "ec2:vpc", {"cidr": "10.9.0.0/16"}, "exec-3")


def test_list_created_ordena_por_ordem_de_criacao(registry):
    for logical_id, order in [("vpc", 20), ("kms-data", 10), ("sg-lambda", 40)]:
        registry.claim("dev", logical_id, "x", {"a": order}, "e")
        registry.commit("dev", logical_id, f"id-{logical_id}", order)
    created = [i["logical_id"] for i in registry.list_created("dev")]
    assert created == ["kms-data", "vpc", "sg-lambda"]
