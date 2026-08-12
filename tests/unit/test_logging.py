"""Structured logging unit tests."""

from __future__ import annotations

import json
import logging

from src.config.logging import StructuredFormatter, sanitize_log_fields


def test_structured_formatter_emits_required_fields() -> None:
    formatter = StructuredFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="database connected",
        args=(),
        exc_info=None,
    )
    record.service = "investment-research"
    record.operation = "db.connect"
    record.ticker = "FPT"
    record.duration_ms = 12

    payload = json.loads(formatter.format(record))

    assert payload["level"] == "INFO"
    assert payload["service"] == "investment-research"
    assert payload["operation"] == "db.connect"
    assert payload["message"] == "database connected"
    assert payload["ticker"] == "FPT"
    assert payload["duration_ms"] == 12
    assert "timestamp" in payload


def test_sanitize_log_fields_redacts_secrets() -> None:
    sanitized = sanitize_log_fields(
        {
            "api_key": "secret-value",
            "document_id": "doc-123",
            "payload": b"binary-content",
        }
    )

    assert sanitized["api_key"] == "***REDACTED***"
    assert sanitized["document_id"] == "doc-123"
    assert sanitized["payload"] == "<binary:14 bytes>"
