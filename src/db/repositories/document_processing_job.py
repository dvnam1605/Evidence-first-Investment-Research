"""Document processing job repository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.document_processing_job import DocumentProcessingJobModel
from src.domain.enums import ProcessingStatus
from src.domain.processing_job import DocumentProcessingJob


class DocumentProcessingJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_domain(self, model: DocumentProcessingJobModel) -> DocumentProcessingJob:
        return DocumentProcessingJob(
            id=model.id,
            artifact_id=model.artifact_id,
            status=ProcessingStatus(model.status),
            parser=model.parser,
            parser_version=model.parser_version,
            started_at=model.started_at,
            finished_at=model.finished_at,
            error=model.error,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def create_pending(self, *, artifact_id: uuid.UUID) -> DocumentProcessingJob:
        now = datetime.now(tz=UTC)
        model = DocumentProcessingJobModel(
            id=uuid.uuid4(),
            artifact_id=artifact_id,
            status=ProcessingStatus.PENDING.value,
            created_at=now,
            updated_at=now,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_domain(model)

    async def get_by_id(self, job_id: uuid.UUID) -> DocumentProcessingJob | None:
        model = await self._session.get(DocumentProcessingJobModel, job_id)
        return self._to_domain(model) if model else None

    async def get_latest_for_artifact(
        self, *, artifact_id: uuid.UUID
    ) -> DocumentProcessingJob | None:
        result = await self._session.execute(
            select(DocumentProcessingJobModel)
            .where(DocumentProcessingJobModel.artifact_id == artifact_id)
            .order_by(
                DocumentProcessingJobModel.created_at.desc(),
                DocumentProcessingJobModel.id.desc(),
            )
            .limit(1)
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def mark_processing(
        self,
        *,
        job_id: uuid.UUID,
        parser: str,
        parser_version: str,
    ) -> DocumentProcessingJob:
        model = await self._session.get(DocumentProcessingJobModel, job_id)
        if model is None:
            raise RuntimeError(f"DocumentProcessingJob missing: {job_id}")

        now = datetime.now(tz=UTC)
        model.status = ProcessingStatus.PROCESSING.value
        model.parser = parser
        model.parser_version = parser_version
        model.started_at = now
        model.finished_at = None
        model.error = None
        model.updated_at = now
        await self._session.flush()
        return self._to_domain(model)

    async def mark_finished(
        self,
        *,
        job_id: uuid.UUID,
        status: ProcessingStatus,
        error: str | None = None,
    ) -> DocumentProcessingJob:
        DocumentProcessingJob.validate_terminal_status(status)
        model = await self._session.get(DocumentProcessingJobModel, job_id)
        if model is None:
            raise RuntimeError(f"DocumentProcessingJob missing: {job_id}")

        now = datetime.now(tz=UTC)
        model.status = status.value
        model.finished_at = now
        model.error = error
        model.updated_at = now
        await self._session.flush()
        return self._to_domain(model)
