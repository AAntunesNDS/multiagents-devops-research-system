#!/usr/bin/env node
/**
 * Ponto de entrada da aplicação CDK.
 * Estratégia: uma Stage por ambiente, com 4 stacks desacopladas
 * (KMS -> Network -> Data -> IAM), ligadas por referências tipadas.
 */
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { Aspects } from 'aws-cdk-lib';
import { AwsSolutionsChecks } from 'cdk-nag';
import { BaseInfraStage } from '../lib/base-infra-stage';
import { EnvironmentConfig } from '../lib/config';

const app = new cdk.App();

const projectName: string = app.node.tryGetContext('projectName');
const githubRepository: string = app.node.tryGetContext('githubRepository');
const environments: Record<string, EnvironmentConfig> = app.node.tryGetContext('environments');

// Permite `cdk deploy -c env=dev`; sem o parâmetro, sintetiza todos os ambientes.
const requested = app.node.tryGetContext('env') as string | undefined;
const targets = requested ? [requested] : Object.keys(environments);

for (const envName of targets) {
  const cfg = environments[envName];
  if (!cfg) throw new Error(`Ambiente desconhecido: ${envName}`);

  new BaseInfraStage(app, `BaseInfra-${envName}`, {
    env: { account: cfg.account, region: cfg.region },
    envName,
    projectName,
    githubRepository,
    config: cfg,
  });
}

// Tags obrigatórias de governança/FinOps aplicadas a toda a árvore de constructs
cdk.Tags.of(app).add('Project', projectName);
cdk.Tags.of(app).add('ManagedBy', 'AWS-CDK');
cdk.Tags.of(app).add('Layer', 'base-infra');

// Verificação automática de compliance (AWS Solutions rules) no synth
Aspects.of(app).add(new AwsSolutionsChecks({ verbose: true }));

app.synth();
