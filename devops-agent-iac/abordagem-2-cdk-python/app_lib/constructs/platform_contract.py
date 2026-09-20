"""Publica o contrato da camada base em SSM Parameter Store."""
import json

from aws_cdk import aws_ssm as ssm
from constructs import Construct


class PlatformContract(Construct):
    def __init__(
        self, scope: Construct, construct_id: str, *, parameter_name: str, payload: dict
    ) -> None:
        super().__init__(scope, construct_id)
        self.parameter = ssm.StringParameter(
            self,
            "Parameter",
            parameter_name=parameter_name,
            string_value=json.dumps(payload),
            tier=ssm.ParameterTier.ADVANCED,
            description="Contrato da camada base consumido pelos agentes seguintes",
        )
