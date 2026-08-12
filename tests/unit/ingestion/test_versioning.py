"""Version resolver unit tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from src.db.models.document import DocumentModel
from src.domain.enums import SourceType, VersionResolutionType
from src.ingestion.models import DocumentCandidate, SourceAttachment, SourceDocument
from src.ingestion.versioning import DocumentVersionResolver


def _candidate(*, is_correction: bool = False, supersedes: str | None = None) -> DocumentCandidate:
    return DocumentCandidate(
        source_document=SourceDocument(
            source=SourceType.FIXTURE,
            source_document_id="v2",
            ticker="FPT",
            title="Report v2",
            published_at=datetime(2024, 4, 20, 14, 0, tzinfo=UTC),
            is_correction=is_correction,
            supersedes_source_document_id=supersedes,
            attachments=[
                SourceAttachment(
                    filename="v2.pdf",
                    download_reference="fixture://tests/fixtures/disclosures/fpt-q1-2024-corrected.pdf",
                )
            ],
        ),
        attachment=SourceAttachment(
            filename="v2.pdf",
            download_reference="fixture://tests/fixtures/disclosures/fpt-q1-2024-corrected.pdf",
        ),
    )


def _parent() -> DocumentModel:
    return DocumentModel(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        source=SourceType.FIXTURE.value,
        source_document_id="v1",
        document_type="other",
        title="Report v1",
        published_at=datetime(2024, 4, 20, 10, 0, tzinfo=UTC),
        scope="unknown",
        audit_status="unknown",
        object_path="raw/FPT/2024/fixture/hash/v1.pdf",
        filename="v1.pdf",
        mime_type="application/pdf",
        file_size=10,
        sha256="hash1",
        is_correction=False,
        is_latest_version=True,
        processing_status="PENDING",
    )


@pytest.mark.asyncio
async def test_new_document_resolution() -> None:
    resolver = DocumentVersionResolver()
    resolution = await resolver.resolve(
        _candidate(), existing_by_source=None, parent_by_supersedes=None
    )
    assert resolution.resolution == VersionResolutionType.NEW_DOCUMENT


@pytest.mark.asyncio
async def test_duplicate_resolution() -> None:
    parent = _parent()
    resolver = DocumentVersionResolver()
    resolution = await resolver.resolve(
        _candidate(),
        existing_by_source=parent,
        parent_by_supersedes=None,
    )
    assert resolution.resolution == VersionResolutionType.DUPLICATE


@pytest.mark.asyncio
async def test_correction_resolution() -> None:
    parent = _parent()
    resolver = DocumentVersionResolver()
    resolution = await resolver.resolve(
        _candidate(is_correction=True, supersedes="v1"),
        existing_by_source=None,
        parent_by_supersedes=parent,
    )
    assert resolution.resolution == VersionResolutionType.CORRECTION


@pytest.mark.asyncio
async def test_new_version_resolution_distinct_from_correction() -> None:
    parent = _parent()
    resolver = DocumentVersionResolver()
    resolution = await resolver.resolve(
        _candidate(is_correction=False, supersedes="v1"),
        existing_by_source=None,
        parent_by_supersedes=parent,
    )
    assert resolution.resolution == VersionResolutionType.NEW_VERSION
    assert resolution.parent_document_id == str(parent.id)
