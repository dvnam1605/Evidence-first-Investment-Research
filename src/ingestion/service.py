"""Ingestion service orchestrating discovery, download, and persistence."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from src.db.repositories.company import CompanyRepository
from src.db.repositories.document_artifact import DocumentArtifactRepository
from src.db.repositories.ingestion_run import IngestionRunRepository
from src.db.repositories.raw_object import RawObjectRepository
from src.db.repositories.source_publication import SourcePublicationRepository
from src.domain.company import Company
from src.domain.enums import (
    AuditStatus,
    IngestionRunStatus,
    ProcessingStatus,
    Scope,
    SourceType,
)
from src.ingestion.downloader import DocumentDownloader
from src.ingestion.errors import DownloadError, IngestionError, SourceError
from src.ingestion.models import DownloadedArtifact, SourceAttachment, SourceDocument
from src.ingestion.registry import ConnectorRegistry
from src.storage.base import ObjectStorage
from src.storage.errors import StorageError
from src.storage.paths import build_raw_object_path_by_sha


@dataclass(frozen=True, slots=True)
class IngestionResult:
    run_id: uuid.UUID
    discovered: int
    publications_created: int
    downloaded: int
    skipped: int
    failed: int
    artifacts_downloaded: int
    duplicates_skipped: int
    status: IngestionRunStatus


class IngestCompanyService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        registry: ConnectorRegistry,
        downloader: DocumentDownloader,
        storage: ObjectStorage,
    ) -> None:
        self._session_factory = session_factory
        self._registry = registry
        self._downloader = downloader
        self._storage = storage

    async def ingest(
        self,
        *,
        ticker: str,
        source: SourceType | str,
        from_date: date | None = None,
        to_date: date | None = None,
        dry_run: bool = False,
    ) -> IngestionResult:
        source_type = SourceType(source)
        connector = self._registry.get(source_type)

        downloaded = 0
        skipped = 0
        failed = 0
        publications_created = 0
        errors: list[str] = []
        discovered = 0

        company = await self._get_company(ticker)
        if company is None:
            raise IngestionError(f"Unknown ticker {ticker}")

        run_id = await self._start_run(source=source_type.value, ticker=company.ticker)

        if not dry_run:
            try:
                await self._storage.ensure_ready()
            except StorageError as exc:
                await self._finish_run(
                    run_id=run_id,
                    status=IngestionRunStatus.FAILED,
                    discovered=0,
                    downloaded=0,
                    skipped=0,
                    failed=0,
                    error_summary=str(exc),
                )
                return IngestionResult(
                    run_id=run_id,
                    discovered=0,
                    publications_created=0,
                    downloaded=0,
                    skipped=0,
                    failed=0,
                    artifacts_downloaded=0,
                    duplicates_skipped=0,
                    status=IngestionRunStatus.FAILED,
                )

        try:
            publications = await connector.discover(
                company.ticker, from_date=from_date, to_date=to_date
            )
            discovered = len(publications)
        except SourceError as exc:
            await self._finish_run(
                run_id=run_id,
                status=IngestionRunStatus.FAILED,
                discovered=0,
                downloaded=0,
                skipped=0,
                failed=0,
                error_summary=str(exc),
            )
            raise

        # Upsert all publications first.
        publication_ids: dict[tuple[str, str], uuid.UUID] = {}
        try:
            for pub in publications:
                pid, created = await self._ensure_publication(
                    company_id=company.id, pub=pub
                )
                publication_ids[(pub.source.value, pub.source_document_id)] = pid
                if created:
                    publications_created += 1
        except SQLAlchemyError as exc:
            await self._finish_run(
                run_id=run_id,
                status=IngestionRunStatus.FAILED,
                discovered=discovered,
                downloaded=downloaded,
                skipped=skipped,
                failed=failed + 1,
                error_summary=str(exc),
            )
            return IngestionResult(
                run_id=run_id,
                discovered=discovered,
                publications_created=publications_created,
                downloaded=downloaded,
                skipped=skipped,
                failed=failed + 1,
                artifacts_downloaded=downloaded,
                duplicates_skipped=skipped,
                status=IngestionRunStatus.FAILED,
            )

        # Link correction/version lineage (short transactions).
        try:
            for pub in publications:
                child_id = publication_ids[(pub.source.value, pub.source_document_id)]

                # Corrections without a predecessor cannot be part of the point-in-time lineage.
                if not pub.supersedes_source_document_id:
                    if pub.is_correction:
                        await self._mark_unresolved_correction(
                            publication_id=child_id
                        )
                    continue

                parent_key = (pub.source.value, pub.supersedes_source_document_id)
                parent_id = publication_ids.get(parent_key)

                if parent_id is None:
                    # Resolve parent in the same transaction we update it (best-effort).
                    async with self._session_factory() as session, session.begin():
                        repo = SourcePublicationRepository(session)
                        parent_id = await repo.get_id_by_natural_key(
                            source=pub.source.value,
                            source_document_id=pub.supersedes_source_document_id,
                        )
                        if parent_id is None:
                            await repo.mark_needs_review(child_id)
                            continue

                        await repo.link_child_to_parent_and_update_latest(
                            child_id=child_id, parent_id=parent_id
                        )
                    continue

                async with self._session_factory() as session, session.begin():
                    repo = SourcePublicationRepository(session)
                    await repo.link_child_to_parent_and_update_latest(
                        child_id=child_id, parent_id=parent_id
                    )
        except SQLAlchemyError as exc:
            await self._finish_run(
                run_id=run_id,
                status=IngestionRunStatus.PARTIAL
                if (downloaded or skipped)
                else IngestionRunStatus.FAILED,
                discovered=discovered,
                downloaded=downloaded,
                skipped=skipped,
                failed=failed + 1,
                error_summary=str(exc),
            )
            return IngestionResult(
                run_id=run_id,
                discovered=discovered,
                publications_created=publications_created,
                downloaded=downloaded,
                skipped=skipped,
                failed=failed + 1,
                artifacts_downloaded=downloaded,
                duplicates_skipped=skipped,
                status=IngestionRunStatus.PARTIAL
                if (downloaded or skipped)
                else IngestionRunStatus.FAILED,
            )

        # Process attachments.
        for pub in publications:
            pub_id = publication_ids[(pub.source.value, pub.source_document_id)]
            for attachment in pub.attachments:
                try:
                    if dry_run:
                        skipped += 1
                        continue

                    artifact_exists = await self._artifact_id_if_exists(
                        publication_id=pub_id,
                        attachment_reference=attachment.download_reference,
                    )
                    if artifact_exists is not None:
                        skipped += 1
                        continue

                    # Download outside any DB transaction.
                    artifact = await self._downloader.download(
                        attachment,
                        object_path="raw_objects/pending/blob",
                    )

                    raw_object_path = build_raw_object_path_by_sha(sha256=artifact.sha256)

                    raw_object_id = await self._ensure_raw_object(
                        artifact=artifact,
                        object_path=raw_object_path,
                    )

                    await self._ensure_artifact(
                        publication_id=pub_id,
                        attachment=attachment,
                        artifact=artifact,
                        raw_object_id=raw_object_id,
                    )
                    downloaded += 1
                except (
                    DownloadError,
                    StorageError,
                    IngestionError,
                    SQLAlchemyError,
                ) as exc:
                    failed += 1
                    errors.append(str(exc))

        if failed and (downloaded or skipped):
            status = IngestionRunStatus.PARTIAL
        elif failed and not downloaded and not skipped:
            status = IngestionRunStatus.FAILED
        else:
            status = IngestionRunStatus.COMPLETED

        await self._finish_run(
            run_id=run_id,
            status=status,
            discovered=discovered,
            downloaded=downloaded,
            skipped=skipped,
            failed=failed,
            error_summary="; ".join(errors[:10]) if errors else None,
        )

        return IngestionResult(
            run_id=run_id,
            discovered=discovered,
            publications_created=publications_created,
            downloaded=downloaded,
            skipped=skipped,
            failed=failed,
            artifacts_downloaded=downloaded,
            duplicates_skipped=skipped,
            status=status,
        )

    async def _get_company(self, ticker: str) -> Company | None:
        async with self._session_factory() as session:
            return await CompanyRepository(session).get_by_ticker(ticker)

    async def _start_run(self, *, source: str, ticker: str) -> uuid.UUID:
        async with self._session_factory() as session, session.begin():
            run = await IngestionRunRepository(session).start(
                source=source, ticker=ticker
            )
            return run.id

    async def _finish_run(
        self,
        *,
        run_id: uuid.UUID,
        status: IngestionRunStatus,
        discovered: int,
        downloaded: int,
        skipped: int,
        failed: int,
        error_summary: str | None,
    ) -> None:
        async with self._session_factory() as session, session.begin():
            await IngestionRunRepository(session).finish_by_id(
                run_id=run_id,
                status=status,
                documents_discovered=discovered,
                documents_downloaded=downloaded,
                documents_skipped=skipped,
                documents_failed=failed,
                error_summary=error_summary,
            )

    async def _ensure_publication(
        self, *, company_id: uuid.UUID, pub: SourceDocument
    ) -> tuple[uuid.UUID, bool]:
        needs_review = pub.is_correction and not pub.supersedes_source_document_id
        # A successor becomes latest only in the lineage-link transaction.  Keeping
        # it false until then prevents an interrupted linkage from exposing both
        # predecessor and successor as latest versions.
        is_latest_version = not needs_review and not pub.supersedes_source_document_id
        processing_status = (
            ProcessingStatus.NEEDS_REVIEW.value
            if needs_review
            else ProcessingStatus.PENDING.value
        )
        async with self._session_factory() as session, session.begin():
            scope = pub.metadata.get("scope", Scope.UNKNOWN.value)
            audit_status = pub.metadata.get(
                "audit_status", AuditStatus.UNKNOWN.value
            )
            return await SourcePublicationRepository(session).ensure(
                company_id=company_id,
                source=pub.source.value,
                source_document_id=pub.source_document_id,
                document_type=pub.document_type.value,
                title=pub.title,
                published_at=pub.published_at,
                source_updated_date=pub.source_updated_date,
                published_at_precision=pub.published_at_precision,
                period_start=pub.period_start,
                period_end=pub.period_end,
                fiscal_year=pub.fiscal_year,
                fiscal_quarter=pub.fiscal_quarter,
                scope=scope,
                audit_status=audit_status,
                language=pub.metadata.get("language"),
                source_reference=pub.detail_reference,
                is_correction=pub.is_correction,
                parent_publication_id=None,
                is_latest_version=is_latest_version,
                processing_status=processing_status,
            )

    async def _mark_not_latest(self, *, publication_id: uuid.UUID) -> None:
        async with self._session_factory() as session, session.begin():
            await SourcePublicationRepository(session).mark_not_latest(publication_id)

    async def _mark_unresolved_correction(self, *, publication_id: uuid.UUID) -> None:
        async with self._session_factory() as session, session.begin():
            await SourcePublicationRepository(session).mark_needs_review(publication_id)
            await SourcePublicationRepository(session).mark_not_latest(publication_id)

    async def _mark_unresolved_version(self, *, publication_id: uuid.UUID) -> None:
        async with self._session_factory() as session, session.begin():
            await SourcePublicationRepository(session).mark_needs_review(publication_id)
            await SourcePublicationRepository(session).mark_not_latest(publication_id)

    async def _artifact_id_if_exists(
        self,
        *,
        publication_id: uuid.UUID,
        attachment_reference: str,
    ) -> uuid.UUID | None:
        async with self._session_factory() as session:
            artifact = await DocumentArtifactRepository(session).get_by_natural_key(
                publication_id=publication_id,
                attachment_reference=attachment_reference,
            )
            return artifact.id if artifact else None

    async def _ensure_raw_object(
        self,
        *,
        artifact: DownloadedArtifact,
        object_path: str,
    ) -> uuid.UUID:
        async with self._session_factory() as session:
            raw_repo = RawObjectRepository(session)
            existing = await raw_repo.get_by_sha256(artifact.sha256)
            if existing is not None:
                return existing.id

        if artifact.content is None:
            raise IngestionError("Downloaded artifact missing content")

        # Upload outside DB transaction.
        if not await self._storage.exists(object_path):
            await self._storage.put(object_path, artifact.content, artifact.actual_mime_type)

        async with self._session_factory() as session, session.begin():
            return await RawObjectRepository(session).ensure(
                sha256=artifact.sha256,
                object_path=object_path,
                mime_type=artifact.actual_mime_type,
                size_bytes=artifact.size_bytes,
            )

    async def _ensure_artifact(
        self,
        *,
        publication_id: uuid.UUID,
        attachment: SourceAttachment,
        artifact: DownloadedArtifact,
        raw_object_id: uuid.UUID,
    ) -> None:
        async with self._session_factory() as session, session.begin():
            await DocumentArtifactRepository(session).ensure(
                publication_id=publication_id,
                attachment_reference=attachment.download_reference,
                filename=artifact.filename,
                mime_type=artifact.actual_mime_type,
                file_size=artifact.size_bytes,
                raw_object_id=raw_object_id,
            )
