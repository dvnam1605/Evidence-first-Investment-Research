"""Document artifact repository (natural key: publication + attachment_reference)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.document_artifact import DocumentArtifactModel


class DocumentArtifactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, artifact_id: uuid.UUID) -> DocumentArtifactModel | None:
        return await self._session.get(DocumentArtifactModel, artifact_id)

    async def list_ids_for_company(self, company_id: uuid.UUID) -> list[uuid.UUID]:
        """Artifact ids for publications belonging to a company (newest first)."""
        from src.db.models.source_publication import SourcePublicationModel

        result = await self._session.execute(
            select(DocumentArtifactModel.id)
            .join(
                SourcePublicationModel,
                SourcePublicationModel.id == DocumentArtifactModel.publication_id,
            )
            .where(SourcePublicationModel.company_id == company_id)
            .order_by(
                DocumentArtifactModel.created_at.desc(),
                DocumentArtifactModel.id.desc(),
            )
        )
        return list(result.scalars().all())

    async def get_by_natural_key(
        self,
        *,
        publication_id: uuid.UUID,
        attachment_reference: str,
    ) -> DocumentArtifactModel | None:
        result = await self._session.execute(
            select(DocumentArtifactModel).where(
                DocumentArtifactModel.publication_id == publication_id,
                DocumentArtifactModel.attachment_reference == attachment_reference,
            )
        )
        return result.scalar_one_or_none()

    async def ensure(
        self,
        *,
        publication_id: uuid.UUID,
        attachment_reference: str,
        filename: str,
        mime_type: str,
        file_size: int,
        raw_object_id: uuid.UUID,
    ) -> uuid.UUID:
        stmt = (
            insert(DocumentArtifactModel)
            .values(
                publication_id=publication_id,
                attachment_reference=attachment_reference,
                filename=filename,
                mime_type=mime_type,
                file_size=file_size,
                raw_object_id=raw_object_id,
                id=uuid.uuid4(),
                created_at=datetime.now(tz=UTC),
                updated_at=datetime.now(tz=UTC),
            )
            .on_conflict_do_nothing(
                index_elements=["publication_id", "attachment_reference"]
            )
            .returning(DocumentArtifactModel.id)
        )
        res = await self._session.execute(stmt)
        inserted_id = res.scalar_one_or_none()
        if inserted_id is not None:
            return inserted_id

        existing = await self.get_by_natural_key(
            publication_id=publication_id,
            attachment_reference=attachment_reference,
        )
        if existing is None:
            raise RuntimeError("artifact missing after ensure")
        return existing.id

