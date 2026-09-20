import * as ssm from 'aws-cdk-lib/aws-ssm';
import { Construct } from 'constructs';

export interface PlatformContractProps {
  readonly parameterName: string;
  readonly payload: Record<string, unknown>;
}

/**
 * Publica o "contrato de plataforma" em SSM Parameter Store.
 * Os próximos agentes leem este parâmetro em vez de importar outputs de stack,
 * o que evita acoplamento rígido (CloudFormation exports bloqueiam alterações).
 */
export class PlatformContract extends Construct {
  public readonly parameter: ssm.StringParameter;

  constructor(scope: Construct, id: string, props: PlatformContractProps) {
    super(scope, id);
    this.parameter = new ssm.StringParameter(this, 'Parameter', {
      parameterName: props.parameterName,
      stringValue: JSON.stringify(props.payload),
      tier: ssm.ParameterTier.ADVANCED,
      description: 'Contrato da camada de infraestrutura base consumido pelos agentes seguintes',
    });
  }
}
