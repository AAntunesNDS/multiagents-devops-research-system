"""Clientes boto3 com retry adaptativo e reuso entre invocacoes (cold start)."""
import os
from functools import lru_cache

import boto3
from botocore.config import Config

_CONFIG = Config(
    retries={"max_attempts": 5, "mode": "adaptive"},
    connect_timeout=5,
    read_timeout=30,
    user_agent_extra="serverless-devops-agent/1.0",
)

REGION = os.getenv("AWS_REGION", "us-east-1")


@lru_cache(maxsize=None)
def client(service: str):
    return boto3.client(service, region_name=REGION, config=_CONFIG)


@lru_cache(maxsize=None)
def resource(service: str):
    return boto3.resource(service, region_name=REGION, config=_CONFIG)
