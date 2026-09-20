"""Tags obrigatorias: identidade do recurso para deteccao/adocao sem state file."""
import os

PROJECT = os.getenv("PROJECT_NAME", "agentes-devops")


def tags(env: str, logical_id: str, extra: dict[str, str] | None = None) -> list[dict[str, str]]:
    base = {
        "Project": PROJECT,
        "Environment": env,
        "ManagedBy": "serverless-devops-agent",
        "LogicalId": logical_id,
        "Layer": "base-infra",
    }
    base.update(extra or {})
    return [{"Key": k, "Value": v} for k, v in base.items()]


def tag_spec(resource_type: str, env: str, logical_id: str) -> list[dict]:
    return [{"ResourceType": resource_type, "Tags": tags(env, logical_id)}]
