"""HOSE source connector.

Blocked: hsx.vn migrated to a React SPA without a public disclosure JSON API.
See docs/decisions/DATA-10-hose-blocker.md
"""

from __future__ import annotations

from datetime import date

from src.domain.enums import SourceType
from src.ingestion.errors import SourceUnavailableError
from src.ingestion.models import SourceDocument


class HoseConnector:
    source = SourceType.HOSE

    async def discover(
        self,
        ticker: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[SourceDocument]:
        raise SourceUnavailableError(
            "HOSE disclosure ingestion is blocked: hsx.vn no longer exposes the legacy "
            "DisclosureList JSON endpoint and requires a JavaScript SPA. "
            "See docs/decisions/DATA-10-hose-blocker.md"
        )

    async def get_document(self, source_document_id: str) -> SourceDocument:
        raise SourceUnavailableError(
            "HOSE disclosure ingestion is blocked. See docs/decisions/DATA-10-hose-blocker.md"
        )
