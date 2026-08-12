"""Ingestion domain models (no database coupling)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field
from src.domain.enums import DocumentType, SourceType, VersionResolutionType


class SourceAttachment(BaseModel):
    filename: str
    download_reference: str
    reported_mime_type: str | None = None


class SourceDocument(BaseModel):
    source: SourceType
    source_document_id: str
    ticker: str
    title: str
    # May be NULL when the source provides only a date (e.g. "Updated: 7/27/2026")
    published_at: datetime | None = None
    # Date-only discovery timestamp from the source UI (do not fabricate time-of-day)
    source_updated_date: date | None = None
    # Precision of `published_at` / discovery timestamp. Example values: "DATE", "DATETIME".
    published_at_precision: str | None = None
    detail_reference: str | None = None
    attachments: list[SourceAttachment] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    document_type: DocumentType = DocumentType.OTHER
    period_start: date | None = None
    period_end: date | None = None
    fiscal_year: int | None = None
    fiscal_quarter: int | None = None
    is_correction: bool = False
    supersedes_source_document_id: str | None = None


class DownloadedArtifact(BaseModel):
    filename: str
    actual_mime_type: str
    size_bytes: int
    sha256: str
    object_path: str
    content: bytes | None = None


class DocumentCandidate(BaseModel):
    source_document: SourceDocument
    attachment: SourceAttachment
    artifact: DownloadedArtifact | None = None


class VersionResolution(BaseModel):
    resolution: VersionResolutionType
    parent_document_id: str | None = None
    existing_document_id: str | None = None
