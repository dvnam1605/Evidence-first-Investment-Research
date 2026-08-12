"""Document page repository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.document_page import DocumentPageModel
from src.domain.document_page import DocumentPage
from src.domain.enums import ExtractionMethod


class DocumentPageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_domain(self, model: DocumentPageModel) -> DocumentPage:
        return DocumentPage(
            id=model.id,
            document_id=model.document_id,
            page_number=model.page_number,
            text=model.text,
            extraction_method=ExtractionMethod(model.extraction_method),
            ocr_confidence=model.ocr_confidence,
            width=model.width,
            height=model.height,
            created_at=model.created_at,
        )

    async def create(
        self,
        *,
        document_id: uuid.UUID,
        page_number: int,
        text: str,
        extraction_method: ExtractionMethod,
        ocr_confidence: float | None,
        width: float,
        height: float,
    ) -> DocumentPage:
        # Validate domain rules before insert.
        now = datetime.now(tz=UTC)
        page = DocumentPage(
            id=uuid.uuid4(),
            document_id=document_id,
            page_number=page_number,
            text=text,
            extraction_method=extraction_method,
            ocr_confidence=ocr_confidence,
            width=width,
            height=height,
            created_at=now,
        )
        model = DocumentPageModel(
            id=page.id,
            document_id=page.document_id,
            page_number=page.page_number,
            text=page.text,
            extraction_method=page.extraction_method.value,
            ocr_confidence=page.ocr_confidence,
            width=page.width,
            height=page.height,
            created_at=page.created_at,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_domain(model)

    async def get_by_document_page(
        self, *, document_id: uuid.UUID, page_number: int
    ) -> DocumentPage | None:
        result = await self._session.execute(
            select(DocumentPageModel).where(
                DocumentPageModel.document_id == document_id,
                DocumentPageModel.page_number == page_number,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model is not None else None

    async def list_by_document(self, *, document_id: uuid.UUID) -> list[DocumentPage]:
        result = await self._session.execute(
            select(DocumentPageModel)
            .where(DocumentPageModel.document_id == document_id)
            .order_by(DocumentPageModel.page_number.asc())
        )
        return [self._to_domain(model) for model in result.scalars().all()]

    async def delete_by_document(self, *, document_id: uuid.UUID) -> int:
        result = await self._session.execute(
            delete(DocumentPageModel).where(DocumentPageModel.document_id == document_id)
        )
        return int(getattr(result, "rowcount", 0) or 0)
