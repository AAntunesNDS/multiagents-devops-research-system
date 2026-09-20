"""Construct L3 reutilizavel: baseline de seguranca de bucket S3."""
import aws_cdk as cdk
from aws_cdk import aws_kms as kms
from aws_cdk import aws_s3 as s3
from constructs import Construct


class SecureBucket(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        bucket_name: str,
        encryption_key: kms.IKey,
        retain: bool,
        lifecycle_rules: list[s3.LifecycleRule] | None = None,
    ) -> None:
        super().__init__(scope, construct_id)

        self.bucket = s3.Bucket(
            self,
            "Bucket",
            bucket_name=bucket_name,
            encryption=s3.BucketEncryption.KMS,
            encryption_key=encryption_key,
            bucket_key_enabled=True,
            versioned=True,
            enforce_ssl=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
            lifecycle_rules=lifecycle_rules,
            removal_policy=cdk.RemovalPolicy.RETAIN if retain else cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=not retain,
        )
