"""FPT Investor Relations connector (HTTP-first, no browser automation)."""

from __future__ import annotations

from datetime import date

import httpx
from src.domain.enums import DocumentType, SourceType
from src.ingestion.errors import SourceError, SourceUnavailableError
from src.ingestion.issuer_ir.fpt.parser import (
    parse_fpt_information_disclosures_html,
)
from src.ingestion.models import SourceAttachment, SourceDocument


class FptIrConnector:
    source = SourceType.ISSUER_IR

    def __init__(self, *, timeout_seconds: float = 30.0) -> None:
        self._timeout_seconds = timeout_seconds
        self._url = "https://fpt.com/en/ir/information-disclosures"

    async def discover(
        self,
        ticker: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[SourceDocument]:
        if ticker.upper() != "FPT":
            raise SourceUnavailableError("ISSUER_IR MVP only supports FPT for now")

        async with httpx.AsyncClient(
            timeout=self._timeout_seconds,
            headers={"User-Agent": "InvestmentResearchBot/0.1"},
        ) as client:
            resp = await client.get(self._url)
            resp.raise_for_status()
            html = resp.text

        disclosures = parse_fpt_information_disclosures_html(html, ticker=ticker)

        filtered: list[SourceDocument] = []
        for d in disclosures:
            if from_date and d.updated_date < from_date:
                continue
            if to_date and d.updated_date > to_date:
                continue

            scope = d.scope
            audit_status = d.audit_status

            filtered.append(
                SourceDocument(
                    source=self.source,
                    source_document_id=d.document_id,
                    ticker=ticker.upper(),
                    title=d.title,
                    published_at=None,
                    source_updated_date=d.updated_date,
                    published_at_precision="DATE",
                    detail_reference=self._url,
                    document_type=(
                        DocumentType.FINANCIAL_STATEMENT
                        if "financial statement" in d.title.lower()
                        else DocumentType.OTHER
                    ),
                    attachments=[
                        SourceAttachment(
                            filename=a.filename,
                            download_reference=a.download_reference,
                            reported_mime_type="application/pdf",
                        )
                        for a in d.attachments
                    ],
                    metadata={"scope": scope, "audit_status": audit_status},
                )
            )

        return filtered

    async def get_document(self, source_document_id: str) -> SourceDocument:
        raise SourceError("FPT IR connector does not implement get_document() yet")

