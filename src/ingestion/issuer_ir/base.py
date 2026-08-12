"""Issuer IR connector abstraction."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from src.ingestion.models import SourceDocument


class IssuerIRConnector(Protocol):
    ticker: str

    async def discover(
        self,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[SourceDocument]: ...

    async def get_document(self, source_document_id: str) -> SourceDocument: ...
