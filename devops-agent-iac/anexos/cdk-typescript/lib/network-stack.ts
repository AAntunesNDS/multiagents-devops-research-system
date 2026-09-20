import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as kms from 'aws-cdk-lib/aws-kms';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';
import { BaseProps, prefix } from './config';

export interface NetworkStackProps extends cdk.StackProps, BaseProps {
  readonly logsKey: kms.IKey;
}

/**
 * VPC multi-AZ. O L2 `ec2.Vpc` cria subnets, IGW, NAT, EIPs e route tables
 * a partir da configuração de subnetConfiguration — ~15 linhas substituem
 * ~150 linhas de HCL equivalente.
 */
export class NetworkStack extends cdk.Stack {
  public readonly vpc: ec2.Vpc;
  public readonly lambdaSecurityGroup: ec2.SecurityGroup;
  public readonly glueSecurityGroup: ec2.SecurityGroup;
  public readonly microservicesSecurityGroup: ec2.SecurityGroup;

  constructor(scope: Construct, id: string, props: NetworkStackProps) {
    super(scope, id, props);
    const p = prefix(props);
    const { config } = props;

    const flowLogGroup = new logs.LogGroup(this, 'FlowLogs', {
      logGroupName: `/aws/vpc/${p}/flow-logs`,
      retention: config.logRetentionDays as logs.RetentionDays,
      encryptionKey: props.logsKey,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    this.vpc = new ec2.Vpc(this, 'Vpc', {
      vpcName: `${p}-vpc`,
      ipAddresses: ec2.IpAddresses.cidr(config.vpcCidr),
      maxAzs: config.maxAzs,
      natGateways: config.natGateways,
      subnetConfiguration: [
        { name: 'public', subnetType: ec2.SubnetType.PUBLIC, cidrMask: 20, mapPublicIpOnLaunch: false },
        { name: 'private', subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS, cidrMask: 20 },
        { name: 'isolated', subnetType: ec2.SubnetType.PRIVATE_ISOLATED, cidrMask: 24 },
      ],
      gatewayEndpoints: {
        // Gateway endpoints são gratuitos: evitam custo de NAT data processing
        S3: { service: ec2.GatewayVpcEndpointAwsService.S3 },
        DynamoDB: { service: ec2.GatewayVpcEndpointAwsService.DYNAMODB },
      },
      flowLogs: {
        all: {
          destination: ec2.FlowLogDestination.toCloudWatchLogs(flowLogGroup),
          trafficType: ec2.FlowLogTrafficType.ALL,
        },
      },
    });

    if (config.enableInterfaceEndpoints) {
      const services: Record<string, ec2.InterfaceVpcEndpointAwsService> = {
        Sqs: ec2.InterfaceVpcEndpointAwsService.SQS,
        StepFunctions: ec2.InterfaceVpcEndpointAwsService.STEP_FUNCTIONS,
        Glue: ec2.InterfaceVpcEndpointAwsService.GLUE,
        Lambda: ec2.InterfaceVpcEndpointAwsService.LAMBDA,
        Athena: ec2.InterfaceVpcEndpointAwsService.ATHENA,
        Kms: ec2.InterfaceVpcEndpointAwsService.KMS,
        CloudWatchLogs: ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
        SecretsManager: ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
        Sts: ec2.InterfaceVpcEndpointAwsService.STS,
      };
      for (const [name, service] of Object.entries(services)) {
        this.vpc.addInterfaceEndpoint(name, {
          service,
          privateDnsEnabled: true,
          subnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
        });
      }
    }

    // ---------------------------- Security Groups ----------------------------
    this.lambdaSecurityGroup = new ec2.SecurityGroup(this, 'LambdaSg', {
      vpc: this.vpc,
      securityGroupName: `${p}-lambda-sg`,
      description: 'SG das funcoes Lambda em subnets privadas',
      allowAllOutbound: false, // egress explícito: sem 0.0.0.0/0 all-ports
    });
    this.lambdaSecurityGroup.addEgressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(443), 'HTTPS para servicos AWS');

    this.glueSecurityGroup = new ec2.SecurityGroup(this, 'GlueSg', {
      vpc: this.vpc,
      securityGroupName: `${p}-glue-sg`,
      description: 'SG das Glue Connections',
      allowAllOutbound: false,
    });
    // Requisito da AWS para Glue Connections
    this.glueSecurityGroup.addIngressRule(this.glueSecurityGroup, ec2.Port.allTraffic(), 'Self-referencing exigido pelo Glue');
    this.glueSecurityGroup.addEgressRule(this.glueSecurityGroup, ec2.Port.allTraffic(), 'Self-referencing exigido pelo Glue');
    this.glueSecurityGroup.addEgressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(443), 'HTTPS para S3/Glue/KMS');

    this.microservicesSecurityGroup = new ec2.SecurityGroup(this, 'MicroservicesSg', {
      vpc: this.vpc,
      securityGroupName: `${p}-microservices-sg`,
      description: 'SG reservado para os proximos agentes',
      allowAllOutbound: false,
    });
    this.microservicesSecurityGroup.addIngressRule(
      ec2.Peer.ipv4(config.vpcCidr), ec2.Port.tcp(8080), 'HTTP interno da VPC',
    );
    this.microservicesSecurityGroup.addEgressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(443), 'HTTPS de saida');

    new cdk.CfnOutput(this, 'VpcId', { value: this.vpc.vpcId, exportName: `${p}-vpc-id` });
  }
}
