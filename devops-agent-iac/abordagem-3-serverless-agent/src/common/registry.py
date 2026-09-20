"""Substituto do state file: registro de recursos em DynamoDB.

Diferencas em relacao ao state do OpenTofu:
- granularidade por recurso (item), nao por arquivo -> sem lock global;
- concorrencia resolvida por escrita condicional, nao por lock em tabela separada;
- o registro e a fonte de verdade de "o que eu criei", nunca de "como esta agora"
  (isso vem da AWS, via describe_* na deteccao de drift).
"""
import hashlib
import json
import os
import time
from typing import Any

from botocore.exceptions import ClientError

from common.aws_clients import client
from common.errors import FatalError

TABLE = os.environ["REGISTRY_TABLE"]
_ddb = client("dynamodb")

STATUS_PENDING = "PENDING"
STATUS_CREATED = "CREATED"
STATUS_FAILED = "FAILED"
STATUS_DELETED = "DELETED"


def spec_hash(spec: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]


def _key(env: str, logical_id: str) -> dict:
    return {"pk": {"S": f"{env}#{logical_id}"}}


def get(env: str, logical_id: str) -> dict[str, Any] | None:
    item = _ddb.get_item(TableName=TABLE, Key=_key(env, logical_id), ConsistentRead=True).get("Item")
    if not item:
        return None
    return {
        "logical_id": logical_id,
        "physical_id": item.get("physical_id", {}).get("S"),
        "resource_type": item.get("resource_type", {}).get("S"),
        "status": item.get("status", {}).get("S"),
        "spec_hash": item.get("spec_hash", {}).get("S"),
        "order": int(item.get("order", {}).get("N", "0")),
    }


def claim(env: str, logical_id: str, resource_type: str, spec: dict, execution_id: str) -> bool:
    """Reserva a criacao do recurso. Retorna False se ja existe em estado CREATED
    com o mesmo hash de spec (idempotencia)."""
    existing = get(env, logical_id)
    if existing and existing["status"] == STATUS_CREATED:
        if existing["spec_hash"] == spec_hash(spec):
            return False
        raise FatalError(
            f"{logical_id} existe com spec divergente "
            f"(registro={existing['spec_hash']}, desejado={spec_hash(spec)}). "
            "Replace nao e suportado pelo agente; destrua e recrie explicitamente."
        )
    try:
        _ddb.put_item(
            TableName=TABLE,
            Item={
                "pk": {"S": f"{env}#{logical_id}"},
                "env": {"S": env},
                "logical_id": {"S": logical_id},
                "resource_type": {"S": resource_type},
                "status": {"S": STATUS_PENDING},
                "spec_hash": {"S": spec_hash(spec)},
                "execution_id": {"S": execution_id},
                "updated_at": {"N": str(int(time.time()))},
            },
            ConditionExpression="attribute_not_exists(pk) OR #s IN (:pending, :failed, :deleted)",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":pending": {"S": STATUS_PENDING},
                ":failed": {"S": STATUS_FAILED},
                ":deleted": {"S": STATUS_DELETED},
            },
        )
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            # Outra execucao esta criando o mesmo recurso agora.
            raise FatalError(f"Execucao concorrente detectada para {logical_id}") from exc
        raise


def commit(env: str, logical_id: str, physical_id: str, order: int, extra: dict | None = None) -> None:
    attrs = {
        ":p": {"S": physical_id},
        ":s": {"S": STATUS_CREATED},
        ":o": {"N": str(order)},
        ":t": {"N": str(int(time.time()))},
        ":e": {"S": json.dumps(extra or {})},
    }
    _ddb.update_item(
        TableName=TABLE,
        Key=_key(env, logical_id),
        UpdateExpression="SET physical_id=:p, #s=:s, #o=:o, updated_at=:t, extra=:e",
        ExpressionAttributeNames={"#s": "status", "#o": "order"},
        ExpressionAttributeValues=attrs,
    )


def fail(env: str, logical_id: str, reason: str) -> None:
    _ddb.update_item(
        TableName=TABLE,
        Key=_key(env, logical_id),
        UpdateExpression="SET #s=:s, reason=:r, updated_at=:t",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": {"S": STATUS_FAILED},
            ":r": {"S": reason[:900]},
            ":t": {"N": str(int(time.time()))},
        },
    )


def mark_deleted(env: str, logical_id: str) -> None:
    _ddb.update_item(
        TableName=TABLE,
        Key=_key(env, logical_id),
        UpdateExpression="SET #s=:s, updated_at=:t REMOVE physical_id",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": {"S": STATUS_DELETED}, ":t": {"N": str(int(time.time()))}},
    )


def list_created(env: str) -> list[dict[str, Any]]:
    """Recursos vivos do ambiente, em ordem de criacao (para destruir na ordem inversa)."""
    paginator = _ddb.get_paginator("query")
    items: list[dict[str, Any]] = []
    for page in paginator.paginate(
        TableName=TABLE,
        IndexName="by-env",
        KeyConditionExpression="env = :e",
        FilterExpression="#s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":e": {"S": env}, ":s": {"S": STATUS_CREATED}},
    ):
        for item in page["Items"]:
            items.append(
                {
                    "logical_id": item["logical_id"]["S"],
                    "physical_id": item.get("physical_id", {}).get("S"),
                    "resource_type": item["resource_type"]["S"],
                    "order": int(item.get("order", {}).get("N", "0")),
                }
            )
    return sorted(items, key=lambda i: i["order"])
