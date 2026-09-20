"""Roles de execucao das workloads futuras + role de deploy via OIDC do GitHub.

Ponto central da abordagem: `bucket.grant_read_write(role)` gera a policy de
menor privilegio, incluindo as acoes de KMS da chave do bucket.
"""
import aws_cdk as cdk
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_s3 as s3
from constructs import Construct

from app_lib.config import EnvironmentConfig, prefix


class IamStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        project_name: str,
        config: EnvironmentConfig,
        github_repository: str,
        keys: list[kms.IKey],
        raw_bucket: s3.IBucket,
        curated_bucket: s3.IBucket,
        athena_results_bucket: s3.IBucket,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        name = prefix(project_name, env_name)
        _ = config

        # ------------------------------ Lambda ------------------------------
        self.lambda_role = iam.Role(
            self,
            "LambdaRole",
            role_name=f"{name}-py-lambda-exec",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Role de execucao das Lambdas dos proximos agentes",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                )
            ],
        )
        raw_bucket.grant_read(self.lambda_role)
        curated_bucket.grant_read_write(self.lambda_role)

        # ------------------------------- Glue -------------------------------
        self.glue_role = iam.Role(
            self,
            "GlueRole",
            role_name=f"{name}-py-glue-job",
            assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
            description="Role dos Glue Jobs",
        )
        raw_bucket.grant_read(self.glue_role)
        curated_bucket.grant_read_write(self.glue_role)
        self.glue_role.add_to_policy(
            iam.PolicyStatement(
                sid="GlueCatalog",
                actions=[
                    "glue:Get*",
                    "glue:BatchGet*",
                    "glue:CreateTable",
                    "glue:UpdateTable",
                    "glue:CreatePartition",
                    "glue:BatchCreatePartition",
                ],
                resources=[
                    self.format_arn(service="glue", resource="catalog"),
                    self.format_arn(
                        service="glue", resource="database", resource_name=f"{project_name}_*"
                    ),
                    self.format_arn(
                        service="glue", resource="table", resource_name=f"{project_name}_*/*"
                    ),
                ],
            )
        )
        self.glue_role.add_to_policy(
            iam.PolicyStatement(
                sid="GlueLogs",
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:AssociateKmsKey",
                ],
                resources=[
                    self.format_arn(service="logs", resource="log-group", resource_name="/aws-glue/*")
                ],
            )
        )
        self.glue_role.add_to_policy(
            iam.PolicyStatement(
                sid="GlueEni",
                actions=[
                    "ec2:CreateNetworkInterface",
                    "ec2:DeleteNetworkInterface",
                    "ec2:DescribeNetworkInterfaces",
                    "ec2:DescribeSubnets",
                    "ec2:DescribeSecurityGroups",
                    "ec2:DescribeVpcEndpoints",
                    "ec2:DescribeRouteTables",
                ],
                resources=["*"],  # API nao suporta ARN nessas acoes
            )
        )

        # --------------------------- Step Functions ---------------------------
        self.step_functions_role = iam.Role(
            self,
            "StepFunctionsRole",
            role_name=f"{name}-py-stepfunctions",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
            description="Role de execucao das state machines",
        )
        self.step_functions_role.add_to_policy(
            iam.PolicyStatement(
                sid="Orchestrate",
                actions=["lambda:InvokeFunction", "glue:StartJobRun", "glue:GetJobRun", "sqs:SendMessage"],
                resources=[
                    self.format_arn(
                        service="lambda",
                        resource="function",
                        resource_name=f"{name}-*",
                        arn_format=cdk.ArnFormat.COLON_RESOURCE_NAME,
                    ),
                    self.format_arn(service="glue", resource="job", resource_name=f"{name}-*"),
                    self.format_arn(
                        service="sqs", resource=f"{name}-*", arn_format=cdk.ArnFormat.NO_RESOURCE_NAME
                    ),
                ],
            )
        )

        for key in keys:
            key.grant_encrypt_decrypt(self.lambda_role)
            key.grant_encrypt_decrypt(self.glue_role)
            key.grant_encrypt_decrypt(self.step_functions_role)

        # ------------------------ Perfil analitico Athena ------------------------
        athena_policy = iam.ManagedPolicy(
            self,
            "AthenaAnalyst",
            managed_policy_name=f"{name}-py-athena-analyst",
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "athena:StartQueryExecution",
                        "athena:GetQueryExecution",
                        "athena:GetQueryResults",
                        "athena:StopQueryExecution",
                        "athena:GetWorkGroup",
                    ],
                    resources=[
                        self.format_arn(service="athena", resource="workgroup", resource_name=f"{name}-*")
                    ],
                )
            ],
        )
        athena_results_bucket.grant_read_write(iam.AccountRootPrincipal())
        cdk.CfnOutput(self, "AthenaAnalystPolicyArn", value=athena_policy.managed_policy_arn)

        # --------------------- GitHub Actions OIDC (deploy) ---------------------
        provider = iam.OpenIdConnectProvider(
            self,
            "GithubOidc",
            url="https://token.actions.githubusercontent.com",
            client_ids=["sts.amazonaws.com"],
        )

        self.github_deploy_role = iam.Role(
            self,
            "GithubDeployRole",
            role_name=f"{name}-py-gha-deploy",
            description="Role assumida pelo GitHub Actions para deploy do CDK Python",
            max_session_duration=cdk.Duration.hours(1),
            assumed_by=iam.WebIdentityPrincipal(
                provider.open_id_connect_provider_arn,
                {
                    "StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"},
                    "StringLike": {
                        "token.actions.githubusercontent.com:sub": [
                            f"repo:{github_repository}:ref:refs/heads/main",
                            f"repo:{github_repository}:pull_request",
                        ]
                    },
                },
            ),
        )
        self.github_deploy_role.add_to_policy(
            iam.PolicyStatement(
                sid="AssumeCdkBootstrapRoles",
                actions=["sts:AssumeRole"],
                resources=[
                    self.format_arn(service="iam", region="", resource="role", resource_name="cdk-*")
                ],
            )
        )
        cdk.CfnOutput(self, "GithubDeployRoleArn", value=self.github_deploy_role.role_arn)
