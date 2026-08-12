"""HNX source connector stub."""

from __future__ import annotations

from datetime import date

from src.domain.enums import SourceType
from src.ingestion.errors import SourceUnavailableError
from src.ingestion.models import SourceDocument


class HnxConnector:
    source = SourceType.HNX

    async def discover(
        self,
        ticker: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[SourceDocument]:
        raise SourceUnavailableError(
            "HNX connector not yet implemented; waiting for stable HOSE/SSC strategy."
        )

    async def get_document(self, source_document_id: str) -> SourceDocument:
        raise SourceUnavailableError("HNX connector not yet implemented.")
