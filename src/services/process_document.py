"""Orchestrate document processing against Postgres + object storage (DOC-13)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db.models.source_publication import SourcePublicationModel
from src.db.repositories.company import CompanyRepository
from src.db.repositories.document_artifact import DocumentArtifactRepository
from src.db.repositories.document_block import DocumentBlockRepository
from src.db.repositories.document_page import DocumentPageRepository
from src.db.repositories.document_processing_job import DocumentProcessingJobRepository
from src.db.repositories.raw_object import RawObjectRepository
from src.domain.enums import ProcessingStatus
from src.domain.processing_job import DocumentProcessingJob
from src.processing.errors import ProcessingError
from src.processing.pipeline import (
    PIPELINE_NAME,
    PIPELINE_VERSION,
    DocumentProcessingResult,
    DocumentProcessor,
    DocumentProcessRequest,
)
from src.storage.base import ObjectStorage
from src.storage.errors import StorageError


class ProcessDocumentError(ProcessingError):
    """CLI / service-level processing failure."""


@dataclass(frozen=True, slots=True)
class ProcessDocumentOutcome:
    job: DocumentProcessingJob
    result: DocumentProcessingResult


@dataclass(frozen=True, slots=True)
class ProcessCompanyOutcome:
    ticker: str
    processed: int
    needs_review: int
    failed: int
    skipped: int
    outcomes: tuple[ProcessDocumentOutcome, ...]


class ProcessDocumentService:
    """Load artifact bytes, run DocumentProcessor, persist pages/blocks/job."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        storage: ObjectStorage,
        processor: DocumentProcessor | None = None,
        stale_job_after_seconds: int = 3600,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage
        self._processor = processor or DocumentProcessor()
        self._stale_job_after = timedelta(seconds=stale_job_after_seconds)

    async def process_document(
        self, document_id: uuid.UUID
    ) -> ProcessDocumentOutcome:
        async with self._session_factory() as session:
            artifact_repo = DocumentArtifactRepository(session)
            raw_repo = RawObjectRepository(session)
            job_repo = DocumentProcessingJobRepository(session)
            page_repo = DocumentPageRepository(session)
            block_repo = DocumentBlockRepository(session)

            artifact = await artifact_repo.get_by_id(document_id)
            if artifact is None:
                raise ProcessDocumentError(f"document artifact not found: {document_id}")

            publication = await session.get(
                SourcePublicationModel, artifact.publication_id
            )
            raw = await raw_repo.get_by_id(artifact.raw_object_id)
            if raw is None:
                raise ProcessDocumentError(
                    f"raw object missing for artifact: {document_id}"
                )

            await job_repo.mark_stale_processing_failed(
                stale_before=datetime.now(tz=UTC) - self._stale_job_after,
            )
            job = await job_repo.create_pending(artifact_id=artifact.id)
            await session.commit()

            try:
                await job_repo.mark_processing(
                    job_id=job.id,
                    parser=PIPELINE_NAME,
                    parser_version=PIPELINE_VERSION,
                )
                await session.commit()
                data = await self._storage.get(raw.object_path)
                request = DocumentProcessRequest(
                    artifact_id=artifact.id,
                    data=data,
                    filename=artifact.filename,
                    title=publication.title if publication is not None else None,
                    document_type=(
                        publication.document_type if publication is not None else None
                    ),
                    source_label=artifact.filename,
                )
                result = await self._processor.process(request)

                await block_repo.delete_for_document(document_id=artifact.id)
                await page_repo.delete_by_document(document_id=artifact.id)

                page_ids: dict[int, uuid.UUID] = {}
                for page in result.pages:
                    saved = await page_repo.create(
                        document_id=artifact.id,
                        page_number=page.page_number,
                        text=page.text,
                        extraction_method=page.extraction_method,
                        ocr_confidence=page.ocr_confidence,
                        width=page.width,
                        height=page.height,
                    )
                    page_ids[page.page_number] = saved.id

                for block in result.blocks:
                    page_id = page_ids.get(block.page_number)
                    if page_id is None:
                        continue
                    await block_repo.create(
                        page_id=page_id,
                        block_index=block.block_index,
                        block_type=block.block_type,
                        content=block.content,
                        bbox=block.bbox,
                    )

                error = result.error
                if result.status is ProcessingStatus.NEEDS_REVIEW and result.warnings:
                    error = error or "; ".join(result.warnings[:8])

                finished = await job_repo.mark_finished(
                    job_id=job.id,
                    status=result.status,
                    error=error,
                    parser=result.parser,
                    parser_version=result.parser_version,
                )
                await session.commit()
                return ProcessDocumentOutcome(job=finished, result=result)
            except Exception as exc:  # noqa: BLE001 - every attempt must be terminal
                await session.rollback()
                failure = f"{type(exc).__name__}: {exc}"
                await self._mark_job_failed(job_id=job.id, failure=failure)
                if isinstance(exc, ProcessDocumentError):
                    raise
                if isinstance(exc, StorageError):
                    raise ProcessDocumentError(str(exc)) from exc
                raise ProcessDocumentError(failure) from exc

    async def _mark_job_failed(self, *, job_id: uuid.UUID, failure: str) -> None:
        """Record the terminal state in a fresh transaction after an attempt fails."""
        async with self._session_factory() as session:
            job_repo = DocumentProcessingJobRepository(session)
            await job_repo.mark_finished(
                job_id=job_id,
                status=ProcessingStatus.FAILED,
                error=failure,
            )
            await session.commit()

    async def process_company(self, ticker: str) -> ProcessCompanyOutcome:
        async with self._session_factory() as session:
            company = await CompanyRepository(session).get_by_ticker(ticker)
            if company is None:
                raise ProcessDocumentError(f"Unknown ticker {ticker}")
            artifact_ids = await DocumentArtifactRepository(session).list_ids_for_company(
                company.id
            )

        outcomes: list[ProcessDocumentOutcome] = []
        processed = needs_review = failed = skipped = 0
        for artifact_id in artifact_ids:
            try:
                outcome = await self.process_document(artifact_id)
            except ProcessDocumentError:
                failed += 1
                continue
            outcomes.append(outcome)
            if outcome.job.status is ProcessingStatus.PROCESSED:
                processed += 1
            elif outcome.job.status is ProcessingStatus.NEEDS_REVIEW:
                needs_review += 1
            elif outcome.job.status is ProcessingStatus.FAILED:
                failed += 1
            else:
                skipped += 1

        return ProcessCompanyOutcome(
            ticker=company.ticker,
            processed=processed,
            needs_review=needs_review,
            failed=failed,
            skipped=skipped,
            outcomes=tuple(outcomes),
        )
