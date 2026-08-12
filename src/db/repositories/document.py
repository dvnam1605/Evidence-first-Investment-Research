"""Document repository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.document import DocumentModel


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_source_document(
        self, *, source: str, source_document_id: str
    ) -> DocumentModel | None:
        result = await self._session.execute(
            select(DocumentModel).where(
                DocumentModel.source == source,
                DocumentModel.source_document_id == source_document_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_sha256(self, sha256: str) -> DocumentModel | None:
        result = await self._session.execute(
            select(DocumentModel).where(DocumentModel.sha256 == sha256)
        )
        return result.scalar_one_or_none()

    async def create(self, **fields: object) -> DocumentModel:
        now = datetime.now(tz=UTC)
        model = DocumentModel(id=uuid.uuid4(), created_at=now, updated_at=now, **fields)
        self._session.add(model)
        await self._session.flush()
        return model

    async def mark_not_latest(self, document_id: uuid.UUID) -> None:
        await self._session.execute(
            update(DocumentModel)
            .where(DocumentModel.id == document_id)
            .values(is_latest_version=False, updated_at=datetime.now(tz=UTC))
        )

    async def list_by_company(self, company_id: uuid.UUID) -> list[DocumentModel]:
        result = await self._session.execute(
            select(DocumentModel)
            .where(DocumentModel.company_id == company_id)
            .order_by(DocumentModel.published_at.desc())
        )
        return list(result.scalars().all())

    async def count_by_company(self, company_id: uuid.UUID) -> int:
        rows = await self.list_by_company(company_id)
        return len(rows)
