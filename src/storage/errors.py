"""Storage-layer errors (used by storage adapters and services)."""

from __future__ import annotations


class StorageError(Exception):
    """Object storage operation failed."""

