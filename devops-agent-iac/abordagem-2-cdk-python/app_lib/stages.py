"""Stage = unidade de deploy de um ambiente inteiro."""
import aws_cdk as cdk
from constructs import Construct

from app_lib.config import EnvironmentConfig
from app_lib.constructs.platform_contract import PlatformContract
from app_lib.stacks.data_stack import DataStack
from app_lib.stacks.encryption_stack import EncryptionStack
from app_lib.stacks.iam_stack import IamStack
from app_lib.stacks.network_stack import NetworkStack


class BaseInfraStage(cdk.Stage):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        project_name: str,
        github_repository: str,
        config: EnvironmentConfig,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        common = {"env_name": env_name, "project_name": project_name, "config": config}

        encryption = EncryptionStack(self, "Encryption", **common)
        network = NetworkStack(self, "Network", logs_key=encryption.logs_key, **common)
        data = DataStack(self, "Data", data_key=encryption.data_key, **common)
        iam = IamStack(
            self,
            "Iam",
            github_repository=github_repository,
            keys=[encryption.data_key, encryption.messaging_key, encryption.logs_key],
            raw_bucket=data.raw_bucket,
            curated_bucket=data.curated_bucket,
            athena_results_bucket=data.athena_results_bucket,
            **common,
        )

        parameter_name = f"/{project_name}/{env_name}/base-infra-cdk-py"
        PlatformContract(
            iam,
            "Contract",
            parameter_name=parameter_name,
            payload={
                "vpc_id": network.vpc.vpc_id,
                "private_subnet_ids": [s.subnet_id for s in network.vpc.private_subnets],
                "public_subnet_ids": [s.subnet_id for s in network.vpc.public_subnets],
                "lambda_sg_id": network.lambda_sg.security_group_id,
                "glue_sg_id": network.glue_sg.security_group_id,
                "microservices_sg_id": network.microservices_sg.security_group_id,
                "kms_data_key_arn": encryption.data_key.key_arn,
                "kms_messaging_key_arn": encryption.messaging_key.key_arn,
                "kms_logs_key_arn": encryption.logs_key.key_arn,
                "lambda_role_arn": iam.lambda_role.role_arn,
                "glue_role_arn": iam.glue_role.role_arn,
                "step_functions_role_arn": iam.step_functions_role.role_arn,
                "raw_bucket": data.raw_bucket.bucket_name,
                "curated_bucket": data.curated_bucket.bucket_name,
                "athena_results_bucket": data.athena_results_bucket.bucket_name,
            },
        )

        cdk.CfnOutput(iam, "ContractParameter", value=parameter_name)
