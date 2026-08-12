"""SSC source connector stub."""

from __future__ import annotations

from datetime import date

from src.domain.enums import SourceType
from src.ingestion.errors import SourceUnavailableError
from src.ingestion.models import SourceDocument


class SscConnector:
    source = SourceType.SSC

    async def discover(
        self,
        ticker: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[SourceDocument]:
        raise SourceUnavailableError(
            "SSC connector not yet implemented; portal requires further reverse engineering."
        )

    async def get_document(self, source_document_id: str) -> SourceDocument:
        raise SourceUnavailableError("SSC connector not yet implemented.")
