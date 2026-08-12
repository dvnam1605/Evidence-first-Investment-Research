"""Raw-object repository (identified by SHA256)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.raw_object import RawObjectModel


class RawObjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, raw_object_id: uuid.UUID) -> RawObjectModel | None:
        return await self._session.get(RawObjectModel, raw_object_id)

    async def get_by_sha256(self, sha256: str) -> RawObjectModel | None:
        result = await self._session.execute(
            select(RawObjectModel).where(RawObjectModel.sha256 == sha256)
        )
        return result.scalar_one_or_none()

    async def ensure(
        self,
        *,
        sha256: str,
        object_path: str,
        mime_type: str,
        size_bytes: int,
    ) -> uuid.UUID:
        stmt = (
            insert(RawObjectModel)
            .values(
                sha256=sha256,
                object_path=object_path,
                mime_type=mime_type,
                size_bytes=size_bytes,
                id=uuid.uuid4(),
                created_at=datetime.now(tz=UTC),
                updated_at=datetime.now(tz=UTC),
            )
            .on_conflict_do_nothing(index_elements=["sha256"])
            .returning(RawObjectModel.id)
        )
        res = await self._session.execute(stmt)
        inserted_id = res.scalar_one_or_none()
        if inserted_id is not None:
            return inserted_id

        existing = await self.get_by_sha256(sha256)
        if existing is None:
            # Extremely rare: unique constraint missing. Keep explicit.
            raise RuntimeError("raw object missing after ensure")
        return existing.id

