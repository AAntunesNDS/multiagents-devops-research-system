import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { EnvironmentConfig } from './config';
import { EncryptionStack } from './encryption-stack';
import { NetworkStack } from './network-stack';
import { DataStack } from './data-stack';
import { IamStack } from './iam-stack';
import { PlatformContract } from './constructs/platform-contract';

export interface BaseInfraStageProps extends cdk.StageProps {
  readonly envName: string;
  readonly projectName: string;
  readonly githubRepository: string;
  readonly config: EnvironmentConfig;
}

/**
 * Stage = unidade de deploy de um ambiente inteiro.
 * A ordem de deploy é inferida pelo CDK a partir das dependências entre stacks.
 */
export class BaseInfraStage extends cdk.Stage {
  constructor(scope: Construct, id: string, props: BaseInfraStageProps) {
    super(scope, id, props);

    const base = { envName: props.envName, projectName: props.projectName, config: props.config };

    const encryption = new EncryptionStack(this, 'Encryption', base);

    const network = new NetworkStack(this, 'Network', {
      ...base,
      logsKey: encryption.logsKey,
    });

    const data = new DataStack(this, 'Data', {
      ...base,
      dataKey: encryption.dataKey,
    });

    const iam = new IamStack(this, 'Iam', {
      ...base,
      githubRepository: props.githubRepository,
      keys: [encryption.dataKey, encryption.messagingKey, encryption.logsKey],
      rawBucket: data.rawBucket,
      curatedBucket: data.curatedBucket,
      athenaResultsBucket: data.athenaResultsBucket,
    });

    // Contrato consumido pelos próximos agentes (SSM Parameter Store)
    new PlatformContract(iam, 'Contract', {
      parameterName: `/${props.projectName}/${props.envName}/base-infra-cdk`,
      payload: {
        vpcId: network.vpc.vpcId,
        privateSubnetIds: network.vpc.privateSubnets.map((s) => s.subnetId),
        publicSubnetIds: network.vpc.publicSubnets.map((s) => s.subnetId),
        lambdaSgId: network.lambdaSecurityGroup.securityGroupId,
        glueSgId: network.glueSecurityGroup.securityGroupId,
        microservicesSgId: network.microservicesSecurityGroup.securityGroupId,
        kmsDataKeyArn: encryption.dataKey.keyArn,
        kmsMessagingKeyArn: encryption.messagingKey.keyArn,
        kmsLogsKeyArn: encryption.logsKey.keyArn,
        lambdaRoleArn: iam.lambdaRole.roleArn,
        glueRoleArn: iam.glueRole.roleArn,
        stepFunctionsRoleArn: iam.stepFunctionsRole.roleArn,
        rawBucket: data.rawBucket.bucketName,
        curatedBucket: data.curatedBucket.bucketName,
        athenaResultsBucket: data.athenaResultsBucket.bucketName,
      },
    });
  }
}
