"""CMKs do projeto: dados, mensageria e logs."""
import aws_cdk as cdk
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from constructs import Construct

from app_lib.config import EnvironmentConfig, prefix


class EncryptionStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        project_name: str,
        config: EnvironmentConfig,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self._prefix = prefix(project_name, env_name)
        self._is_prod = env_name == "prod"
        self._config = config

        self.data_key = self._make_key(
            "Data",
            "CMK para dados em repouso (S3, Glue, Athena)",
            ["s3.amazonaws.com", "glue.amazonaws.com", "athena.amazonaws.com"],
        )
        self.messaging_key = self._make_key(
            "Messaging",
            "CMK para SQS e Step Functions",
            ["sqs.amazonaws.com", "states.amazonaws.com", "sns.amazonaws.com"],
        )
        self.logs_key = self._make_key(
            "Logs",
            "CMK para CloudWatch Logs",
            [f"logs.{self.region}.amazonaws.com"],
            logs_encryption_context=True,
        )

    def _make_key(
        self,
        name: str,
        description: str,
        service_principals: list[str],
        logs_encryption_context: bool = False,
    ) -> kms.Key:
        key = kms.Key(
            self,
            name,
            alias=f"{self._prefix}-{name.lower()}",
            description=description,
            enable_key_rotation=True,
            pending_window=cdk.Duration.days(30 if self._is_prod else 7),
            removal_policy=cdk.RemovalPolicy.RETAIN if self._is_prod else cdk.RemovalPolicy.DESTROY,
        )

        conditions: dict = {"StringEquals": {"aws:SourceAccount": self.account}}
        if logs_encryption_context:
            # CloudWatch Logs exige a condicao de encryption context; sem ela o
            # CreateLogGroup falha com "KMS key does not exist or is not allowed".
            conditions = {
                "ArnLike": {
                    "kms:EncryptionContext:aws:logs:arn": (
                        f"arn:aws:logs:{self.region}:{self.account}:log-group:*"
                    )
                }
            }

        key.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AllowServiceUse",
                principals=[iam.ServicePrincipal(s) for s in service_principals],
                actions=[
                    "kms:Encrypt",
                    "kms:Decrypt",
                    "kms:ReEncrypt*",
                    "kms:GenerateDataKey*",
                    "kms:DescribeKey",
                    "kms:CreateGrant",
                ],
                resources=["*"],
                conditions=conditions,
            )
        )
        return key
