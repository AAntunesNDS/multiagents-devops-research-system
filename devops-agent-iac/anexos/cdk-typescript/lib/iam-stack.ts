import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as kms from 'aws-cdk-lib/aws-kms';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';
import { BaseProps, prefix } from './config';

export interface IamStackProps extends cdk.StackProps, BaseProps {
  readonly githubRepository: string;
  readonly keys: kms.IKey[];
  readonly rawBucket: s3.IBucket;
  readonly curatedBucket: s3.IBucket;
  readonly athenaResultsBucket: s3.IBucket;
}

/**
 * Roles de execução das workloads futuras + role de deploy do GitHub Actions
 * via OIDC. Aqui o CDK brilha: `bucket.grantReadWrite(role)` gera a policy de
 * menor privilégio (incluindo kms:Decrypt/GenerateDataKey na chave do bucket)
 * sem escrita manual de ARNs.
 */
export class IamStack extends cdk.Stack {
  public readonly lambdaRole: iam.Role;
  public readonly glueRole: iam.Role;
  public readonly stepFunctionsRole: iam.Role;
  public readonly githubDeployRole: iam.Role;

  constructor(scope: Construct, id: string, props: IamStackProps) {
    super(scope, id, props);
    const p = prefix(props);

    // ------------------------------ Lambda ------------------------------
    this.lambdaRole = new iam.Role(this, 'LambdaRole', {
      roleName: `${p}-lambda-exec`,
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      description: 'Role de execucao das Lambdas dos proximos agentes',
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaVPCAccessExecutionRole'),
      ],
    });
    props.rawBucket.grantRead(this.lambdaRole);
    props.curatedBucket.grantReadWrite(this.lambdaRole);

    // ------------------------------- Glue -------------------------------
    this.glueRole = new iam.Role(this, 'GlueRole', {
      roleName: `${p}-glue-job`,
      assumedBy: new iam.ServicePrincipal('glue.amazonaws.com'),
      description: 'Role dos Glue Jobs',
    });
    props.rawBucket.grantRead(this.glueRole);
    props.curatedBucket.grantReadWrite(this.glueRole);
    this.glueRole.addToPolicy(
      new iam.PolicyStatement({
        sid: 'GlueCatalog',
        actions: [
          'glue:Get*', 'glue:BatchGet*', 'glue:CreateTable', 'glue:UpdateTable',
          'glue:CreatePartition', 'glue:BatchCreatePartition',
        ],
        resources: [
          this.formatArn({ service: 'glue', resource: 'catalog' }),
          this.formatArn({ service: 'glue', resource: 'database', resourceName: `${props.projectName}_*` }),
          this.formatArn({ service: 'glue', resource: 'table', resourceName: `${props.projectName}_*/*` }),
        ],
      }),
    );
    this.glueRole.addToPolicy(
      new iam.PolicyStatement({
        sid: 'GlueLogs',
        actions: ['logs:CreateLogGroup', 'logs:CreateLogStream', 'logs:PutLogEvents', 'logs:AssociateKmsKey'],
        resources: [this.formatArn({ service: 'logs', resource: 'log-group', resourceName: '/aws-glue/*' })],
      }),
    );
    this.glueRole.addToPolicy(
      new iam.PolicyStatement({
        sid: 'GlueEni',
        actions: [
          'ec2:CreateNetworkInterface', 'ec2:DeleteNetworkInterface', 'ec2:DescribeNetworkInterfaces',
          'ec2:DescribeSubnets', 'ec2:DescribeSecurityGroups', 'ec2:DescribeVpcEndpoints', 'ec2:DescribeRouteTables',
        ],
        resources: ['*'], // API não suporta ARN nessas ações
      }),
    );

    // --------------------------- Step Functions ---------------------------
    this.stepFunctionsRole = new iam.Role(this, 'StepFunctionsRole', {
      roleName: `${p}-stepfunctions`,
      assumedBy: new iam.ServicePrincipal('states.amazonaws.com'),
      description: 'Role de execucao das state machines',
    });
    this.stepFunctionsRole.addToPolicy(
      new iam.PolicyStatement({
        sid: 'Orchestrate',
        actions: ['lambda:InvokeFunction', 'glue:StartJobRun', 'glue:GetJobRun', 'sqs:SendMessage'],
        resources: [
          this.formatArn({ service: 'lambda', resource: 'function', resourceName: `${p}-*`, arnFormat: cdk.ArnFormat.COLON_RESOURCE_NAME }),
          this.formatArn({ service: 'glue', resource: 'job', resourceName: `${p}-*` }),
          this.formatArn({ service: 'sqs', resource: `${p}-*`, arnFormat: cdk.ArnFormat.NO_RESOURCE_NAME }),
        ],
      }),
    );

    // Concede uso das CMKs às roles de workload
    for (const key of props.keys) {
      key.grantEncryptDecrypt(this.lambdaRole);
      key.grantEncryptDecrypt(this.glueRole);
      key.grantEncryptDecrypt(this.stepFunctionsRole);
    }

    // ------------------------ Perfil analítico Athena ------------------------
    const athenaPolicy = new iam.ManagedPolicy(this, 'AthenaAnalyst', {
      managedPolicyName: `${p}-athena-analyst`,
      statements: [
        new iam.PolicyStatement({
          actions: [
            'athena:StartQueryExecution', 'athena:GetQueryExecution',
            'athena:GetQueryResults', 'athena:StopQueryExecution', 'athena:GetWorkGroup',
          ],
          resources: [this.formatArn({ service: 'athena', resource: 'workgroup', resourceName: `${p}-*` })],
        }),
      ],
    });
    props.athenaResultsBucket.grantReadWrite(new iam.AccountRootPrincipal());
    new cdk.CfnOutput(this, 'AthenaAnalystPolicyArn', { value: athenaPolicy.managedPolicyArn });

    // --------------------- GitHub Actions OIDC (deploy) ---------------------
    const provider = new iam.OpenIdConnectProvider(this, 'GithubOidc', {
      url: 'https://token.actions.githubusercontent.com',
      clientIds: ['sts.amazonaws.com'],
    });

    this.githubDeployRole = new iam.Role(this, 'GithubDeployRole', {
      roleName: `${p}-gha-deploy-cdk`,
      description: 'Role assumida pelo GitHub Actions para deploy do CDK',
      maxSessionDuration: cdk.Duration.hours(1),
      assumedBy: new iam.WebIdentityPrincipal(provider.openIdConnectProviderArn, {
        StringEquals: { 'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com' },
        StringLike: {
          'token.actions.githubusercontent.com:sub': [
            `repo:${props.githubRepository}:ref:refs/heads/main`,
            `repo:${props.githubRepository}:pull_request`,
          ],
        },
      }),
    });

    // O CDK deploy assume as roles de bootstrap (cdk-*-deploy/file-publishing/...).
    // A role do GitHub precisa apenas de sts:AssumeRole sobre elas.
    this.githubDeployRole.addToPolicy(
      new iam.PolicyStatement({
        sid: 'AssumeCdkBootstrapRoles',
        actions: ['sts:AssumeRole'],
        resources: [this.formatArn({ service: 'iam', region: '', resource: 'role', resourceName: 'cdk-*' })],
      }),
    );

    new cdk.CfnOutput(this, 'GithubDeployRoleArn', { value: this.githubDeployRole.roleArn });
  }
}
