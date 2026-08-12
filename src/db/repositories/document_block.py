"""Document block repository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.document_block import DocumentBlockModel
from src.domain.document_block import BoundingBox, DocumentBlock
from src.domain.enums import BlockType


class DocumentBlockRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _bbox_from_model(self, model: DocumentBlockModel) -> BoundingBox | None:
        values = (model.bbox_x0, model.bbox_y0, model.bbox_x1, model.bbox_y1)
        if all(v is None for v in values):
            return None
        if any(v is None for v in values):
            raise ValueError("partial bbox is invalid; all components required")
        assert model.bbox_x0 is not None
        assert model.bbox_y0 is not None
        assert model.bbox_x1 is not None
        assert model.bbox_y1 is not None
        return BoundingBox(
            x0=model.bbox_x0,
            y0=model.bbox_y0,
            x1=model.bbox_x1,
            y1=model.bbox_y1,
        )

    def _to_domain(self, model: DocumentBlockModel) -> DocumentBlock:
        return DocumentBlock(
            id=model.id,
            page_id=model.page_id,
            block_index=model.block_index,
            block_type=BlockType(model.block_type),
            bbox=self._bbox_from_model(model),
            content=dict(model.content or {}),
            created_at=model.created_at,
        )

    async def create(
        self,
        *,
        page_id: uuid.UUID,
        block_index: int,
        block_type: BlockType,
        content: dict[str, Any],
        bbox: BoundingBox | None = None,
    ) -> DocumentBlock:
        now = datetime.now(tz=UTC)
        page_block = DocumentBlock(
            id=uuid.uuid4(),
            page_id=page_id,
            block_index=block_index,
            block_type=block_type,
            bbox=bbox,
            content=content,
            created_at=now,
        )
        model = DocumentBlockModel(
            id=page_block.id,
            page_id=page_block.page_id,
            block_index=page_block.block_index,
            block_type=page_block.block_type.value,
            bbox_x0=bbox.x0 if bbox is not None else None,
            bbox_y0=bbox.y0 if bbox is not None else None,
            bbox_x1=bbox.x1 if bbox is not None else None,
            bbox_y1=bbox.y1 if bbox is not None else None,
            content=dict(page_block.content),
            created_at=page_block.created_at,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_domain(model)

    async def list_by_page(self, *, page_id: uuid.UUID) -> list[DocumentBlock]:
        result = await self._session.execute(
            select(DocumentBlockModel)
            .where(DocumentBlockModel.page_id == page_id)
            .order_by(DocumentBlockModel.block_index.asc())
        )
        return [self._to_domain(model) for model in result.scalars().all()]

    async def delete_by_page(self, *, page_id: uuid.UUID) -> int:
        result = await self._session.execute(
            delete(DocumentBlockModel).where(DocumentBlockModel.page_id == page_id)
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def delete_for_document(self, *, document_id: uuid.UUID) -> int:
        """Delete all blocks for pages belonging to a document artifact."""
        from src.db.models.document_page import DocumentPageModel

        page_ids = (
            await self._session.execute(
                select(DocumentPageModel.id).where(
                    DocumentPageModel.document_id == document_id
                )
            )
        ).scalars().all()
        if not page_ids:
            return 0
        result = await self._session.execute(
            delete(DocumentBlockModel).where(DocumentBlockModel.page_id.in_(page_ids))
        )
        return int(getattr(result, "rowcount", 0) or 0)
