import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as kms from 'aws-cdk-lib/aws-kms';
import { Construct } from 'constructs';

export interface SecureBucketProps {
  readonly bucketName: string;
  readonly encryptionKey: kms.IKey;
  readonly retain: boolean;
  readonly lifecycleRules?: s3.LifecycleRule[];
}

/**
 * Construct L3 reutilizável: bucket com criptografia KMS, bucket key (economia
 * de chamadas ao KMS), versionamento, bloqueio público total, TLS obrigatório
 * e ownership enforced. Padroniza o baseline de segurança em uma única linha.
 */
export class SecureBucket extends Construct {
  public readonly bucket: s3.Bucket;

  constructor(scope: Construct, id: string, props: SecureBucketProps) {
    super(scope, id);

    this.bucket = new s3.Bucket(this, 'Bucket', {
      bucketName: props.bucketName,
      encryption: s3.BucketEncryption.KMS,
      encryptionKey: props.encryptionKey,
      bucketKeyEnabled: true,
      versioned: true,
      enforceSSL: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
      lifecycleRules: props.lifecycleRules,
      removalPolicy: props.retain ? cdk.RemovalPolicy.RETAIN : cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: !props.retain,
    });
  }
}
