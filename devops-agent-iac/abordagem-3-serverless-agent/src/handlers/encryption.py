"""Provisionamento das CMKs. Idempotente via registry + alias determinístico."""
import json

from botocore.exceptions import ClientError

from common.aws_clients import client
from common.errors import RetryableError
from common.logging_conf import get_logger
from common.registry import claim, commit, fail
from common.tagging import tags

log = get_logger(__name__)
kms = client("kms")
sts = client("sts")

KEYS = {
    "kms-data": ("CMK dados", ["s3.amazonaws.com", "glue.amazonaws.com", "athena.amazonaws.com"]),
    "kms-messaging": ("CMK mensageria", ["sqs.amazonaws.com", "states.amazonaws.com"]),
    "kms-logs": ("CMK logs", ["logs.{region}.amazonaws.com"]),
}


def _policy(account_id: str, region: str, principals: list[str], logical_id: str) -> str:
    statements = [
        {
            "Sid": "EnableIAMUserPermissions",
            "Effect": "Allow",
            "Principal": {"AWS": f"arn:aws:iam::{account_id}:root"},
            "Action": "kms:*",
            "Resource": "*",
        }
    ]
    conditions = {"StringEquals": {"aws:SourceAccount": account_id}}
    if logical_id == "kms-logs":
        conditions = {
            "ArnLike": {
                "kms:EncryptionContext:aws:logs:arn": f"arn:aws:logs:{region}:{account_id}:log-group:*"
            }
        }
    statements.append(
        {
            "Sid": "AllowServiceUse",
            "Effect": "Allow",
            "Principal": {"Service": [p.format(region=region) for p in principals]},
            "Action": [
                "kms:Encrypt",
                "kms:Decrypt",
                "kms:ReEncrypt*",
                "kms:GenerateDataKey*",
                "kms:DescribeKey",
                "kms:CreateGrant",
            ],
            "Resource": "*",
            "Condition": conditions,
        }
    )
    return json.dumps({"Version": "2012-10-17", "Statement": statements})


def handler(event: dict, context) -> dict:
    env = event["environment"]
    execution_id = event["execution_id"]
    region = client("kms").meta.region_name
    account_id = sts.get_caller_identity()["Account"]
    outputs = event.get("outputs", {})

    for order, (logical_id, (description, principals)) in enumerate(KEYS.items(), start=10):
        spec = {"description": description, "principals": principals}
        if not claim(env, logical_id, "kms:key", spec, execution_id):
            from common.registry import get  # noqa: PLC0415

            outputs[logical_id] = get(env, logical_id)["physical_id"]
            log.info("chave ja existente", extra={"logical_id": logical_id, "action": "noop"})
            continue

        try:
            key = kms.create_key(
                Description=f"{description} ({env})",
                KeyUsage="ENCRYPT_DECRYPT",
                Origin="AWS_KMS",
                Policy=_policy(account_id, region, principals, logical_id),
                Tags=[{"TagKey": t["Key"], "TagValue": t["Value"]} for t in tags(env, logical_id)],
            )["KeyMetadata"]
            kms.enable_key_rotation(KeyId=key["KeyId"])
            alias = f"alias/{env}-{logical_id}"
            try:
                kms.create_alias(AliasName=alias, TargetKeyId=key["KeyId"])
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "AlreadyExistsException":
                    raise
            commit(env, logical_id, key["Arn"], order, {"alias": alias})
            outputs[logical_id] = key["Arn"]
            log.info(
                "chave criada",
                extra={"logical_id": logical_id, "physical_id": key["Arn"], "action": "create"},
            )
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            fail(env, logical_id, str(exc))
            if code in ("ThrottlingException", "KMSInternalException", "RequestLimitExceeded"):
                raise RetryableError(code) from exc
            raise

    event["outputs"] = outputs
    return event
