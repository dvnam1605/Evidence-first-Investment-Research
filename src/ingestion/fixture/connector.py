"""Fixture connector for tests and local pipeline validation."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from src.domain.enums import DocumentType, SourceType
from src.ingestion.errors import SourceError
from src.ingestion.models import SourceAttachment, SourceDocument

DEFAULT_CATALOG = Path("tests/fixtures/disclosures/catalog.json")


class FixtureConnector:
    source = SourceType.FIXTURE

    def __init__(self, catalog_path: Path | None = None) -> None:
        self._catalog_path = catalog_path or DEFAULT_CATALOG

    async def discover(
        self,
        ticker: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[SourceDocument]:
        if not self._catalog_path.exists():
            raise SourceError(f"Fixture catalog not found: {self._catalog_path}")

        payload = json.loads(self._catalog_path.read_text(encoding="utf-8"))
        documents: list[SourceDocument] = []
        for item in payload:
            if item["ticker"].upper() != ticker.upper():
                continue
            published_at = datetime.fromisoformat(item["published_at"])
            if from_date and published_at.date() < from_date:
                continue
            if to_date and published_at.date() > to_date:
                continue
            attachments = [
                SourceAttachment(
                    filename=attachment["filename"],
                    download_reference=attachment["download_reference"],
                    reported_mime_type=attachment.get("reported_mime_type"),
                )
                for attachment in item.get("attachments", [])
            ]
            documents.append(
                SourceDocument(
                    source=SourceType.FIXTURE,
                    source_document_id=item["source_document_id"],
                    ticker=ticker.upper(),
                    title=item["title"],
                    published_at=published_at,
                    detail_reference=item.get("detail_reference"),
                    attachments=attachments,
                    metadata=item.get("metadata", {}),
                    document_type=DocumentType(item.get("document_type", "other")),
                    is_correction=item.get("is_correction", False),
                    supersedes_source_document_id=item.get("supersedes_source_document_id"),
                )
            )
        return documents

    async def get_document(self, source_document_id: str) -> SourceDocument:
        for document in await self.discover("FPT"):
            if document.source_document_id == source_document_id:
                return document
        raise SourceError(f"Fixture document not found: {source_document_id}")
