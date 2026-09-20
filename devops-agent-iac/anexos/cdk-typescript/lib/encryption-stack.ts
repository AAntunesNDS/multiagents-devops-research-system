import * as cdk from 'aws-cdk-lib';
import * as kms from 'aws-cdk-lib/aws-kms';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';
import { BaseProps, prefix } from './config';

export interface EncryptionStackProps extends cdk.StackProps, BaseProps {}

/** CMKs do projeto: dados, mensageria e logs. Rotação anual habilitada. */
export class EncryptionStack extends cdk.Stack {
  public readonly dataKey: kms.Key;
  public readonly messagingKey: kms.Key;
  public readonly logsKey: kms.Key;

  constructor(scope: Construct, id: string, props: EncryptionStackProps) {
    super(scope, id, props);
    const p = prefix(props);
    const isProd = props.envName === 'prod';

    const makeKey = (name: string, description: string, servicePrincipals: string[]): kms.Key => {
      const key = new kms.Key(this, name, {
        alias: `${p}-${name.toLowerCase()}`,
        description,
        enableKeyRotation: true,
        pendingWindow: cdk.Duration.days(isProd ? 30 : 7),
        removalPolicy: isProd ? cdk.RemovalPolicy.RETAIN : cdk.RemovalPolicy.DESTROY,
      });

      if (servicePrincipals.length > 0) {
        key.addToResourcePolicy(
          new iam.PolicyStatement({
            sid: 'AllowServiceUse',
            principals: servicePrincipals.map((s) => new iam.ServicePrincipal(s)),
            actions: [
              'kms:Encrypt', 'kms:Decrypt', 'kms:ReEncrypt*',
              'kms:GenerateDataKey*', 'kms:DescribeKey', 'kms:CreateGrant',
            ],
            resources: ['*'],
            conditions: { StringEquals: { 'aws:SourceAccount': this.account } },
          }),
        );
      }
      return key;
    };

    this.dataKey = makeKey('Data', 'CMK para dados em repouso (S3, Glue, Athena)', [
      's3.amazonaws.com', 'glue.amazonaws.com', 'athena.amazonaws.com',
    ]);

    this.messagingKey = makeKey('Messaging', 'CMK para SQS e Step Functions', [
      'sqs.amazonaws.com', 'states.amazonaws.com', 'sns.amazonaws.com',
    ]);

    this.logsKey = makeKey('Logs', 'CMK para CloudWatch Logs', [
      `logs.${this.region}.amazonaws.com`,
    ]);
  }
}
