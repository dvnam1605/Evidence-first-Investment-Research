"""Ingestion run repository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.ingestion_run import IngestionRunModel
from src.domain.enums import IngestionRunStatus


class IngestionRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def start(self, *, source: str, ticker: str) -> IngestionRunModel:
        model = IngestionRunModel(
            id=uuid.uuid4(),
            source=source,
            ticker=ticker.upper(),
            started_at=datetime.now(tz=UTC),
            status=IngestionRunStatus.RUNNING.value,
        )
        self._session.add(model)
        await self._session.flush()
        return model

    async def finish(
        self,
        run: IngestionRunModel,
        *,
        status: IngestionRunStatus,
        documents_discovered: int,
        documents_downloaded: int,
        documents_skipped: int,
        documents_failed: int,
        error_summary: str | None = None,
    ) -> IngestionRunModel:
        run.finished_at = datetime.now(tz=UTC)
        run.status = status.value
        run.documents_discovered = documents_discovered
        run.documents_downloaded = documents_downloaded
        run.documents_skipped = documents_skipped
        run.documents_failed = documents_failed
        run.error_summary = error_summary
        await self._session.flush()
        return run

    async def finish_by_id(
        self,
        *,
        run_id: uuid.UUID,
        status: IngestionRunStatus,
        documents_discovered: int,
        documents_downloaded: int,
        documents_skipped: int,
        documents_failed: int,
        error_summary: str | None = None,
    ) -> None:
        run = await self._session.get(IngestionRunModel, run_id)
        if run is None:
            raise RuntimeError(f"IngestionRun missing: {run_id}")

        run.finished_at = datetime.now(tz=UTC)
        run.status = status.value
        run.documents_discovered = documents_discovered
        run.documents_downloaded = documents_downloaded
        run.documents_skipped = documents_skipped
        run.documents_failed = documents_failed
        run.error_summary = error_summary
        await self._session.flush()
