import * as cdk from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { EncryptionStack } from '../lib/encryption-stack';
import { NetworkStack } from '../lib/network-stack';

const config = {
  account: '111111111111',
  region: 'us-east-1',
  vpcCidr: '10.21.0.0/16',
  maxAzs: 2,
  natGateways: 1,
  enableInterfaceEndpoints: false,
  logRetentionDays: 14,
};

const base = { envName: 'dev', projectName: 'agentes-devops', config };
const env = { account: config.account, region: config.region };

describe('Infraestrutura base', () => {
  test('todas as CMKs possuem rotacao habilitada', () => {
    const app = new cdk.App();
    const stack = new EncryptionStack(app, 'Enc', { ...base, env });
    const t = Template.fromStack(stack);
    t.resourceCountIs('AWS::KMS::Key', 3);
    t.allResourcesProperties('AWS::KMS::Key', { EnableKeyRotation: true });
  });

  test('VPC cria subnets publicas e privadas nas 2 AZs', () => {
    const app = new cdk.App();
    const enc = new EncryptionStack(app, 'Enc', { ...base, env });
    const net = new NetworkStack(app, 'Net', { ...base, env, logsKey: enc.logsKey });
    const t = Template.fromStack(net);
    t.resourceCountIs('AWS::EC2::Subnet', 6); // public + private + isolated x 2 AZ
    t.resourceCountIs('AWS::EC2::NatGateway', 1);
    t.hasResourceProperties('AWS::EC2::VPC', { CidrBlock: '10.21.0.0/16' });
  });

  test('nenhuma subnet publica atribui IP publico automaticamente', () => {
    const app = new cdk.App();
    const enc = new EncryptionStack(app, 'Enc', { ...base, env });
    const net = new NetworkStack(app, 'Net', { ...base, env, logsKey: enc.logsKey });
    Template.fromStack(net).allResourcesProperties('AWS::EC2::Subnet', {
      MapPublicIpOnLaunch: Match.absent(),
    });
  });

  test('Flow Logs habilitados na VPC', () => {
    const app = new cdk.App();
    const enc = new EncryptionStack(app, 'Enc', { ...base, env });
    const net = new NetworkStack(app, 'Net', { ...base, env, logsKey: enc.logsKey });
    Template.fromStack(net).resourceCountIs('AWS::EC2::FlowLog', 1);
  });
});
