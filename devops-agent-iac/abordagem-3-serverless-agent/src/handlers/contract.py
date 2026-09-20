"""Publica o contrato da camada base em SSM e emite evento de conclusao."""
import json
import os

from common.aws_clients import client
from common.logging_conf import get_logger

log = get_logger(__name__)
ssm = client("ssm")
events = client("events")

PROJECT = os.getenv("PROJECT_NAME", "agentes-devops")
EVENT_BUS = os.environ["EVENT_BUS"]


def handler(event: dict, context) -> dict:
    env = event["environment"]
    out = event["outputs"]

    payload = {
        "vpc_id": out["vpc_id"],
        "public_subnet_ids": out["public_subnet_ids"],
        "private_subnet_ids": out["private_subnet_ids"],
        "lambda_sg_id": out.get("sg-lambda"),
        "glue_sg_id": out.get("sg-glue"),
        "microservices_sg_id": out.get("sg-microservices"),
        "kms_data_key_arn": out.get("kms-data"),
        "kms_messaging_key_arn": out.get("kms-messaging"),
        "kms_logs_key_arn": out.get("kms-logs"),
        "lambda_role_arn": out.get("role-lambda"),
        "glue_role_arn": out.get("role-glue"),
        "step_functions_role_arn": out.get("role-stepfunctions"),
    }

    parameter = f"/{PROJECT}/{env}/base-infra-serverless"
    ssm.put_parameter(
        Name=parameter,
        Value=json.dumps(payload),
        Type="String",
        Tier="Advanced",
        Overwrite=True,
    )

    events.put_events(
        Entries=[
            {
                "EventBusName": EVENT_BUS,
                "Source": "devops.agent",
                "DetailType": "base-infra.provisioned",
                "Detail": json.dumps(
                    {"environment": env, "execution_id": event["execution_id"], "contract": parameter}
                ),
            }
        ]
    )

    log.info("contrato publicado", extra={"execution_id": event["execution_id"], "action": "contract"})
    event["contract_parameter"] = parameter
    return event
