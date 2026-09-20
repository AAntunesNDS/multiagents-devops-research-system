export interface EnvironmentConfig {
  readonly account: string;
  readonly region: string;
  readonly vpcCidr: string;
  readonly maxAzs: number;
  readonly natGateways: number;
  readonly enableInterfaceEndpoints: boolean;
  readonly logRetentionDays: number;
}

export interface BaseProps {
  readonly envName: string;
  readonly projectName: string;
  readonly config: EnvironmentConfig;
}

export const prefix = (p: BaseProps): string => `${p.projectName}-${p.envName}`;
