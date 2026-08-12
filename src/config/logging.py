"""Structured logging configuration."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

SENSITIVE_FIELD_NAMES = frozenset(
    {
        "api_key",
        "access_key",
        "secret_key",
        "password",
        "token",
        "authorization",
    }
)


class StructuredFormatter(logging.Formatter):
    """Emit JSON log records with optional research/document context fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "service": getattr(record, "service", None),
            "operation": getattr(record, "operation", None),
            "message": record.getMessage(),
        }

        for field_name in (
            "research_id",
            "document_id",
            "ticker",
            "source",
            "duration_ms",
            "error",
        ):
            value = getattr(record, field_name, None)
            if value is not None:
                payload[field_name] = value

        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)

        return json.dumps({key: value for key, value in payload.items() if value is not None})


def configure_logging(*, level: str = "INFO", service_name: str = "investment-research") -> None:
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())

    root_logger.addHandler(handler)
    root_logger.setLevel(level.upper())

    logging.LoggerAdapter(logging.getLogger(__name__), {"service": service_name})


def sanitize_log_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Remove sensitive values before logging structured context."""
    sanitized: dict[str, Any] = {}
    for key, value in fields.items():
        if key.lower() in SENSITIVE_FIELD_NAMES:
            sanitized[key] = "***REDACTED***"
        elif isinstance(value, (bytes, bytearray)):
            sanitized[key] = f"<binary:{len(value)} bytes>"
        else:
            sanitized[key] = value
    return sanitized
