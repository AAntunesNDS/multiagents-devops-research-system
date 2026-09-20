"""Camada de armazenamento consumida por Glue, Athena, Lambda e Step Functions."""
import aws_cdk as cdk
from aws_cdk import aws_kms as kms
from aws_cdk import aws_s3 as s3
from constructs import Construct

from app_lib.config import EnvironmentConfig, prefix
from app_lib.constructs.secure_bucket import SecureBucket


class DataStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        project_name: str,
        config: EnvironmentConfig,
        data_key: kms.IKey,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        name = prefix(project_name, env_name)
        is_prod = env_name == "prod"
        _ = config

        self.raw_bucket = SecureBucket(
            self,
            "Raw",
            bucket_name=f"{name}-py-raw-{self.account}",
            encryption_key=data_key,
            retain=is_prod,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="tiering",
                    enabled=True,
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INTELLIGENT_TIERING,
                            transition_after=cdk.Duration.days(30),
                        ),
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER_INSTANT_RETRIEVAL,
                            transition_after=cdk.Duration.days(180),
                        ),
                    ],
                    noncurrent_version_expiration=cdk.Duration.days(90),
                )
            ],
        ).bucket

        self.curated_bucket = SecureBucket(
            self,
            "Curated",
            bucket_name=f"{name}-py-curated-{self.account}",
            encryption_key=data_key,
            retain=is_prod,
        ).bucket

        self.athena_results_bucket = SecureBucket(
            self,
            "AthenaResults",
            bucket_name=f"{name}-py-athena-results-{self.account}",
            encryption_key=data_key,
            retain=False,
            lifecycle_rules=[
                s3.LifecycleRule(id="expire-results", enabled=True, expiration=cdk.Duration.days(30))
            ],
        ).bucket
