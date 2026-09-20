"""Log estruturado em JSON: uma linha por evento, correlacionada por execution_id."""
import json
import logging
import os
import sys
from typing import Any

_LEVEL = os.getenv("LOG_LEVEL", "INFO")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("execution_id", "logical_id", "resource_type", "physical_id", "action"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(_LEVEL)
    logger.propagate = False
    return logger
