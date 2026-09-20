"""Roles de execucao das workloads futuras (Lambda, Glue, Step Functions)."""
import json

from botocore.exceptions import ClientError

from common.aws_clients import client
from common.logging_conf import get_logger
from common.registry import claim, commit, get
from common.tagging import tags

log = get_logger(__name__)
iam = client("iam")
sts = client("sts")

TRUST = {
    "role-lambda": "lambda.amazonaws.com",
    "role-glue": "glue.amazonaws.com",
    "role-stepfunctions": "states.amazonaws.com",
}


def _assume_policy(service: str, account_id: str) -> str:
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": service},
                    "Action": "sts:AssumeRole",
                    "Condition": {"StringEquals": {"aws:SourceAccount": account_id}},
                }
            ],
        }
    )


def _inline_policy(logical_id: str, env: str, account_id: str, region: str, out: dict) -> str:
    buckets = [f"arn:aws:s3:::{env}-raw-{account_id}", f"arn:aws:s3:::{env}-curated-{account_id}"]
    objects = [f"{b}/*" for b in buckets]
    kms_keys = [out[k] for k in ("kms-data", "kms-messaging", "kms-logs") if k in out]

    statements = [
        {"Sid": "S3List", "Effect": "Allow", "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
         "Resource": buckets},
        {"Sid": "S3Objects", "Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"],
         "Resource": objects},
        {"Sid": "Kms", "Effect": "Allow",
         "Action": ["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"], "Resource": kms_keys},
    ]

    if logical_id == "role-lambda":
        statements.append(
            {"Sid": "Logs", "Effect": "Allow",
             "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
             "Resource": f"arn:aws:logs:{region}:{account_id}:log-group:/aws/lambda/{env}-*:*"}
        )
        statements.append(
            {"Sid": "Eni", "Effect": "Allow",
             "Action": ["ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces",
                        "ec2:DeleteNetworkInterface"],
             "Resource": "*"}
        )
    if logical_id == "role-glue":
        statements.append(
            {"Sid": "Catalog", "Effect": "Allow",
             "Action": ["glue:Get*", "glue:BatchGet*", "glue:CreateTable", "glue:UpdateTable",
                        "glue:CreatePartition", "glue:BatchCreatePartition"],
             "Resource": [f"arn:aws:glue:{region}:{account_id}:catalog",
                          f"arn:aws:glue:{region}:{account_id}:database/{env}_*",
                          f"arn:aws:glue:{region}:{account_id}:table/{env}_*/*"]}
        )
    if logical_id == "role-stepfunctions":
        statements.append(
            {"Sid": "Orchestrate", "Effect": "Allow",
             "Action": ["lambda:InvokeFunction", "glue:StartJobRun", "glue:GetJobRun",
                        "sqs:SendMessage"],
             "Resource": [f"arn:aws:lambda:{region}:{account_id}:function:{env}-*",
                          f"arn:aws:glue:{region}:{account_id}:job/{env}-*",
                          f"arn:aws:sqs:{region}:{account_id}:{env}-*"]}
        )

    return json.dumps({"Version": "2012-10-17", "Statement": statements})


def handler(event: dict, context) -> dict:
    env = event["environment"]
    execution_id = event["execution_id"]
    out = event["outputs"]
    account_id = sts.get_caller_identity()["Account"]
    region = iam.meta.region_name

    for order, (logical_id, service) in enumerate(TRUST.items(), start=50):
        role_name = f"{env}-{logical_id}"
        spec = {"service": service}
        if not claim(env, logical_id, "iam:role", spec, execution_id):
            out[logical_id] = get(env, logical_id)["physical_id"]
            continue

        try:
            arn = iam.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=_assume_policy(service, account_id),
                Description=f"Role gerada pelo agente serverless ({logical_id})",
                MaxSessionDuration=3600,
                Tags=tags(env, logical_id),
            )["Role"]["Arn"]
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "EntityAlreadyExists":
                raise
            # Adocao: a role existe na AWS mas nao no registro (execucao anterior
            # interrompida entre o create e o commit).
            arn = iam.get_role(RoleName=role_name)["Role"]["Arn"]
            log.info("role adotada", extra={"logical_id": logical_id, "action": "adopt"})

        iam.put_role_policy(
            RoleName=role_name,
            PolicyName="least-privilege",
            PolicyDocument=_inline_policy(logical_id, env, account_id, region, out),
        )
        commit(env, logical_id, arn, order, {"role_name": role_name})
        out[logical_id] = arn

    event["outputs"] = out
    return event
