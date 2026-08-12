"""Deduplication unit tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from src.db.models.document import DocumentModel
from src.domain.enums import SourceType
from src.ingestion.deduplication import DocumentDeduplicator
from src.ingestion.models import SourceAttachment, SourceDocument


def _source_document() -> SourceDocument:
    return SourceDocument(
        source=SourceType.FIXTURE,
        source_document_id="doc-1",
        ticker="FPT",
        title="Report",
        published_at=datetime(2024, 4, 20, tzinfo=UTC),
        attachments=[
            SourceAttachment(
                filename="a.pdf",
                download_reference="fixture://tests/fixtures/disclosures/fpt-q1-2024.pdf",
            )
        ],
    )


def _existing_doc(**overrides: object) -> DocumentModel:
    defaults = {
        "id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "source": SourceType.FIXTURE.value,
        "source_document_id": "doc-1",
        "document_type": "other",
        "title": "Report",
        "published_at": datetime(2024, 4, 20, tzinfo=UTC),
        "scope": "unknown",
        "audit_status": "unknown",
        "object_path": "raw/FPT/2024/fixture/abc/a.pdf",
        "filename": "a.pdf",
        "mime_type": "application/pdf",
        "file_size": 10,
        "sha256": "abc",
        "is_correction": False,
        "is_latest_version": True,
        "processing_status": "PENDING",
    }
    defaults.update(overrides)
    return DocumentModel(**defaults)  # type: ignore[arg-type]


def test_skip_when_source_document_exists() -> None:
    dedup = DocumentDeduplicator()
    result = dedup.evaluate(
        source_document=_source_document(),
        sha256="hash",
        existing_by_source=_existing_doc(),
        existing_by_sha256=None,
    )
    assert result.skip_persist is True
    assert result.reason == "source_document_id"


def test_reuse_object_for_same_sha256() -> None:
    dedup = DocumentDeduplicator()
    result = dedup.evaluate(
        source_document=_source_document(),
        sha256="same-hash",
        existing_by_source=None,
        existing_by_sha256=_existing_doc(sha256="same-hash"),
    )
    assert result.skip_download is True
    assert result.skip_persist is False
    assert result.reason == "sha256"
