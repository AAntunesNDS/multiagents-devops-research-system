import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as kms from 'aws-cdk-lib/aws-kms';
import { Construct } from 'constructs';
import { BaseProps, prefix } from './config';
import { SecureBucket } from './constructs/secure-bucket';

export interface DataStackProps extends cdk.StackProps, BaseProps {
  readonly dataKey: kms.IKey;
}

/** Camada de armazenamento que Glue, Athena, Lambda e Step Functions consumirão. */
export class DataStack extends cdk.Stack {
  public readonly rawBucket: s3.IBucket;
  public readonly curatedBucket: s3.IBucket;
  public readonly athenaResultsBucket: s3.IBucket;

  constructor(scope: Construct, id: string, props: DataStackProps) {
    super(scope, id, props);
    const p = prefix(props);
    const isProd = props.envName === 'prod';

    this.rawBucket = new SecureBucket(this, 'Raw', {
      bucketName: `${p}-raw-${this.account}`,
      encryptionKey: props.dataKey,
      retain: isProd,
      lifecycleRules: [
        {
          id: 'tiering',
          enabled: true,
          transitions: [
            { storageClass: s3.StorageClass.INTELLIGENT_TIERING, transitionAfter: cdk.Duration.days(30) },
            { storageClass: s3.StorageClass.GLACIER_INSTANT_RETRIEVAL, transitionAfter: cdk.Duration.days(180) },
          ],
          noncurrentVersionExpiration: cdk.Duration.days(90),
        },
      ],
    }).bucket;

    this.curatedBucket = new SecureBucket(this, 'Curated', {
      bucketName: `${p}-curated-${this.account}`,
      encryptionKey: props.dataKey,
      retain: isProd,
    }).bucket;

    this.athenaResultsBucket = new SecureBucket(this, 'AthenaResults', {
      bucketName: `${p}-athena-results-${this.account}`,
      encryptionKey: props.dataKey,
      retain: false,
      lifecycleRules: [{ id: 'expire-results', enabled: true, expiration: cdk.Duration.days(30) }],
    }).bucket;
  }
}
