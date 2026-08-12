"""Tests for destructive integration-test database protection."""

from __future__ import annotations

import pytest
from tests.integration.safety import is_safe_test_bucket, is_safe_test_database


def test_development_database_is_not_considered_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVIDENCE_TEST_DB_SAFE", raising=False)
    database_url = "postgresql+asyncpg://user:pass@localhost/investment_research"
    assert is_safe_test_database(database_url) is False


def test_test_suffix_is_considered_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVIDENCE_TEST_DB_SAFE", raising=False)
    database_url = "postgresql+asyncpg://user:pass@localhost/investment_research_test"
    assert is_safe_test_database(database_url) is True


def test_explicit_environment_override_is_considered_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVIDENCE_TEST_DB_SAFE", "1")
    database_url = "postgresql+asyncpg://user:pass@localhost/investment_research"
    assert is_safe_test_database(database_url) is True


def test_only_test_suffixed_buckets_are_considered_safe() -> None:
    assert is_safe_test_bucket("research") is False
    assert is_safe_test_bucket("research-test") is True
