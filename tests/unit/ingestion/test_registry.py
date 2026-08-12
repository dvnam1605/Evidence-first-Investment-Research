"""Ingestion model and registry tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from src.domain.enums import SourceType
from src.ingestion.errors import SourceError, SourceUnavailableError
from src.ingestion.fixture.connector import FixtureConnector
from src.ingestion.hose.connector import HoseConnector
from src.ingestion.models import SourceAttachment, SourceDocument
from src.ingestion.registry import ConnectorRegistry


@pytest.mark.asyncio
async def test_fixture_connector_discover_fpt() -> None:
    connector = FixtureConnector()
    documents = await connector.discover("FPT")
    assert len(documents) == 2
    assert documents[0].source == SourceType.FIXTURE


@pytest.mark.asyncio
async def test_hose_connector_blocked() -> None:
    connector = HoseConnector()
    with pytest.raises(SourceUnavailableError):
        await connector.discover("FPT")


def test_registry_get_connector() -> None:
    registry = ConnectorRegistry()
    registry.register(FixtureConnector())
    connector = registry.get(SourceType.FIXTURE)
    assert connector.source == SourceType.FIXTURE


def test_registry_missing_raises() -> None:
    registry = ConnectorRegistry()
    with pytest.raises(SourceError):
        registry.get(SourceType.HOSE)


def test_source_attachment_model() -> None:
    attachment = SourceAttachment(
        filename="report.pdf",
        download_reference="https://example.com/report.pdf",
        reported_mime_type="application/pdf",
    )
    document = SourceDocument(
        source=SourceType.FIXTURE,
        source_document_id="abc",
        ticker="FPT",
        title="Test",
        published_at=datetime(2024, 4, 20, tzinfo=UTC),
        attachments=[attachment],
    )
    assert document.attachments[0].filename == "report.pdf"
