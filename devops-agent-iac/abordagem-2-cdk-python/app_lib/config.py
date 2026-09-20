"""Tipos de configuracao de ambiente (equivalente ao .tfvars da Abordagem 1)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class EnvironmentConfig:
    account: str
    region: str
    vpc_cidr: str
    max_azs: int
    nat_gateways: int
    enable_interface_endpoints: bool
    log_retention_days: int


def prefix(project_name: str, env_name: str) -> str:
    return f"{project_name}-{env_name}"
