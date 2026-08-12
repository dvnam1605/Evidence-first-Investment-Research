"""Source connector protocol."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from src.domain.enums import SourceType
from src.ingestion.models import SourceDocument


class SourceConnector(Protocol):
    source: SourceType

    async def discover(
        self,
        ticker: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[SourceDocument]: ...

    async def get_document(self, source_document_id: str) -> SourceDocument: ...
