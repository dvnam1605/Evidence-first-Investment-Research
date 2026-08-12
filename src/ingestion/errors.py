"""Ingestion errors."""

from __future__ import annotations


class IngestionError(Exception):
    """Base ingestion error."""


class SourceError(IngestionError):
    """Source discovery or parsing failed."""


class DownloadError(IngestionError):
    """Attachment download failed."""


class SourceUnavailableError(SourceError):
    """Public source cannot be accessed reliably."""
