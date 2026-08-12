"""Safety guard for destructive integration-database tests."""

from __future__ import annotations

import os
from urllib.parse import unquote, urlsplit

import pytest


def is_safe_test_database(database_url: str) -> bool:
    """Return whether ``database_url`` names an explicitly disposable database."""
    if os.getenv("EVIDENCE_TEST_DB_SAFE", "").lower() == "1":
        return True

    database_name = unquote(urlsplit(database_url).path).rstrip("/").rsplit("/", 1)[-1]
    return database_name.lower().endswith("_test")


def require_safe_test_database(database_url: str, *, operation: str) -> None:
    if not is_safe_test_database(database_url):
        pytest.skip(f"Skipping {operation} on a non-disposable database")


def is_safe_test_bucket(bucket: str) -> bool:
    return bucket.lower().endswith("-test")


def require_safe_test_bucket(bucket: str, *, operation: str) -> None:
    if not is_safe_test_bucket(bucket):
        pytest.skip(f"Skipping {operation} on a non-disposable object-storage bucket")
