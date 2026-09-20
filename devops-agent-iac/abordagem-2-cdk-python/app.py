#!/usr/bin/env python3
"""Entrypoint da aplicacao CDK (Python).

Uma Stage por ambiente; quatro stacks com dependencia inferida pelo grafo de
referencias. Configuracao vem de cdk.json (context), nunca hardcoded no codigo.
"""
import aws_cdk as cdk
from cdk_nag import AwsSolutionsChecks

from app_lib.config import EnvironmentConfig
from app_lib.stages import BaseInfraStage

app = cdk.App()

project_name: str = app.node.try_get_context("projectName")
github_repository: str = app.node.try_get_context("githubRepository")
environments: dict = app.node.try_get_context("environments")

requested = app.node.try_get_context("env")
targets = [requested] if requested else list(environments.keys())

for env_name in targets:
    raw = environments.get(env_name)
    if raw is None:
        raise ValueError(f"Ambiente desconhecido: {env_name}")
    config = EnvironmentConfig(**raw)

    BaseInfraStage(
        app,
        f"BaseInfra-{env_name}",
        env=cdk.Environment(account=config.account, region=config.region),
        env_name=env_name,
        project_name=project_name,
        github_repository=github_repository,
        config=config,
    )

cdk.Tags.of(app).add("Project", project_name)
cdk.Tags.of(app).add("ManagedBy", "AWS-CDK-Python")
cdk.Tags.of(app).add("Layer", "base-infra")

cdk.Aspects.of(app).add(AwsSolutionsChecks(verbose=True))

app.synth()
