"""Source publication repository (natural key: source + source_document_id)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import sqlalchemy as sa
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.source_publication import SourcePublicationModel


class SourcePublicationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_natural_key(
        self, *, source: str, source_document_id: str
    ) -> SourcePublicationModel | None:
        result = await self._session.execute(
            select(SourcePublicationModel).where(
                SourcePublicationModel.source == source,
                SourcePublicationModel.source_document_id == source_document_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_id_by_natural_key(
        self, *, source: str, source_document_id: str
    ) -> uuid.UUID | None:
        result = await self._session.execute(
            select(SourcePublicationModel.id).where(
                SourcePublicationModel.source == source,
                SourcePublicationModel.source_document_id == source_document_id,
            )
        )
        return result.scalar_one_or_none()

    async def ensure(
        self,
        *,
        company_id: uuid.UUID,
        source: str,
        source_document_id: str,
        document_type: str,
        title: str,
        published_at: datetime | None,
        source_updated_date: date | None,
        published_at_precision: str | None,
        period_start: date | None,
        period_end: date | None,
        fiscal_year: int | None,
        fiscal_quarter: int | None,
        scope: str,
        audit_status: str,
        language: str | None,
        source_reference: str | None,
        is_correction: bool,
        parent_publication_id: uuid.UUID | None,
        is_latest_version: bool,
        processing_status: str,
    ) -> tuple[uuid.UUID, bool]:
        now = datetime.now(tz=UTC)
        existing = await self.get_by_natural_key(
            source=source, source_document_id=source_document_id
        )
        created = existing is None

        stmt = (
            insert(SourcePublicationModel)
            .values(
                company_id=company_id,
                source=source,
                source_document_id=source_document_id,
                document_type=document_type,
                title=title,
                published_at=published_at,
                source_updated_date=source_updated_date,
                published_at_precision=published_at_precision,
                period_start=period_start,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_quarter=fiscal_quarter,
                scope=scope,
                audit_status=audit_status,
                language=language,
                source_reference=source_reference,
                parent_publication_id=parent_publication_id,
                is_correction=is_correction,
                is_latest_version=is_latest_version,
                processing_status=processing_status,
                id=uuid.uuid4(),
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["source", "source_document_id"],
                set_={
                    # Refresh discoverable metadata on re-ingest (parser fixes).
                    "title": title,
                    "document_type": document_type,
                    "published_at": published_at,
                    "source_updated_date": source_updated_date,
                    "published_at_precision": published_at_precision,
                    "scope": scope,
                    "audit_status": audit_status,
                    "language": language,
                    "source_reference": source_reference,
                    "updated_at": now,
                },
            )
            .returning(SourcePublicationModel.id)
        )
        res = await self._session.execute(stmt)
        publication_id = res.scalar_one()
        return publication_id, created

    async def mark_not_latest(self, publication_id: uuid.UUID) -> None:
        await self._session.execute(
            update(SourcePublicationModel)
            .where(SourcePublicationModel.id == publication_id)
            .values(is_latest_version=False, updated_at=datetime.now(tz=UTC))
        )

    async def mark_needs_review(self, publication_id: uuid.UUID) -> None:
        await self._session.execute(
            update(SourcePublicationModel)
            .where(SourcePublicationModel.id == publication_id)
            .values(
                is_latest_version=False,
                processing_status="NEEDS_REVIEW",
                updated_at=datetime.now(tz=UTC),
            )
        )

    async def link_child_to_parent_and_update_latest(
        self, *, child_id: uuid.UUID, parent_id: uuid.UUID
    ) -> None:
        """
        Atomically link `child_id` -> `parent_id` and maintain the "latest" invariant.

        This is intentionally implemented in the repository so the service can keep
        transaction boundaries and row-locking co-located.
        """
        now = datetime.now(tz=UTC)

        async def _find_root(start_id: uuid.UUID) -> uuid.UUID:
            """
            Find lineage root by walking parent_publication_id upwards.
            We lock each visited row to serialize concurrent lineage updates.
            """
            current = start_id
            while True:
                row = await self._session.execute(
                    select(SourcePublicationModel.parent_publication_id).where(
                        SourcePublicationModel.id == current
                    ).with_for_update()
                )
                parent = row.scalar_one()
                if parent is None:
                    return current
                current = parent

        async def _lock_and_clear_latest(root_id: uuid.UUID) -> None:
            # Lock every row in the subtree so concurrent tasks can't interleave
            # latest-flag updates across the chain.
            await self._session.execute(
                sa.text(
                    """
                    WITH RECURSIVE lineage(id) AS (
                        SELECT sp.id
                        FROM source_publications sp
                        WHERE sp.id = :root_id
                        UNION ALL
                        SELECT sp2.id
                        FROM source_publications sp2
                        JOIN lineage l ON sp2.parent_publication_id = l.id
                    )
                    SELECT sp.id
                    FROM source_publications sp
                    WHERE sp.id IN (SELECT id FROM lineage)
                    FOR UPDATE
                    """
                ),
                {"root_id": root_id},
            )

            await self._session.execute(
                sa.text(
                    """
                    WITH RECURSIVE lineage(id) AS (
                        SELECT sp.id
                        FROM source_publications sp
                        WHERE sp.id = :root_id
                        UNION ALL
                        SELECT sp2.id
                        FROM source_publications sp2
                        JOIN lineage l ON sp2.parent_publication_id = l.id
                    )
                    UPDATE source_publications sp
                    SET is_latest_version = FALSE,
                        updated_at = :now
                    WHERE sp.id IN (SELECT id FROM lineage)
                    """
                ),
                {"root_id": root_id, "now": now},
            )

        async def _latest_leaf_id(root_id: uuid.UUID) -> uuid.UUID:
            result = await self._session.execute(
                sa.text(
                    """
                    WITH RECURSIVE lineage(id) AS (
                        SELECT sp.id
                        FROM source_publications sp
                        WHERE sp.id = :root_id
                        UNION ALL
                        SELECT sp2.id
                        FROM source_publications sp2
                        JOIN lineage l ON sp2.parent_publication_id = l.id
                    )
                    SELECT sp.id
                    FROM source_publications sp
                    WHERE sp.id IN (SELECT id FROM lineage)
                      AND NOT EXISTS (
                          SELECT 1
                          FROM source_publications child
                          WHERE child.parent_publication_id = sp.id
                      )
                    ORDER BY sp.published_at DESC, sp.id::text DESC
                    LIMIT 1
                    """
                ),
                {"root_id": root_id},
            )
            return uuid.UUID(str(result.scalar_one()))

        # Serialize on the lineage roots that could be affected by re-linking
        # `child_id` under `parent_id`.
        child_root = await _find_root(child_id)
        parent_root = await _find_root(parent_id)
        roots_to_clear = (
            [child_root]
            if child_root == parent_root
            else sorted([child_root, parent_root], key=lambda u: str(u))
        )

        for rid in roots_to_clear:
            await _lock_and_clear_latest(rid)

        # 1) Link child to its parent.
        await self._session.execute(
            update(SourcePublicationModel)
            .where(SourcePublicationModel.id == child_id)
            .values(parent_publication_id=parent_id, updated_at=now)
        )

        # 2) Mark the newest terminal descendant as latest. This preserves the
        # invariant when an intermediate predecessor arrives after its child.
        latest_id = await _latest_leaf_id(parent_root)
        await self._session.execute(
            update(SourcePublicationModel)
            .where(SourcePublicationModel.id == latest_id)
            .values(is_latest_version=True, updated_at=now)
        )

