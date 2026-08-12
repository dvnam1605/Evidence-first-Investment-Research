"""G1 ingestion semantics tests.

These tests validate the required separation:
SourcePublication -> DocumentArtifacts -> RawObject (SHA256).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import func, select
from src.config.settings import CrawlerSettings, Settings
from src.db.models.document_artifact import DocumentArtifactModel
from src.db.models.ingestion_run import IngestionRunModel
from src.db.models.raw_object import RawObjectModel
from src.db.models.source_publication import SourcePublicationModel
from src.db.repositories.company import CompanyRepository
from src.db.session import create_engine, create_session_factory
from src.domain.enums import (
    DocumentType,
    Exchange,
    IngestionRunStatus,
    ProcessingStatus,
    SourceType,
)
from src.ingestion.downloader import DocumentDownloader
from src.ingestion.errors import SourceError, SourceUnavailableError
from src.ingestion.models import SourceAttachment, SourceDocument
from src.ingestion.registry import ConnectorRegistry
from src.ingestion.service import IngestCompanyService
from src.storage.base import ObjectStorage
from src.storage.errors import StorageError
from tests.integration.safety import require_safe_test_bucket, require_safe_test_database

pytestmark = pytest.mark.integration


class StaticConnector:
    source = SourceType.FIXTURE

    def __init__(self, documents: list[SourceDocument], *, fail_discover: bool = False) -> None:
        self._documents = documents
        self._fail_discover = fail_discover

    async def discover(
        self,
        ticker: str,
        from_date: Any | None = None,
        to_date: Any | None = None,
    ) -> list[SourceDocument]:
        if self._fail_discover:
            raise SourceUnavailableError("fixture discovery failure")
        return self._documents

    async def get_document(self, source_document_id: str) -> SourceDocument:
        raise SourceUnavailableError("fixture connector does not support get_document")


@dataclass
class PutFailureMode:
    fail_first_put: bool = False
    fail_times: int = 0


class InMemoryObjectStorage(ObjectStorage):
    def __init__(self, mode: PutFailureMode | None = None) -> None:
        self._mode = mode or PutFailureMode()
        self._store: dict[str, bytes] = {}
        self._put_calls = 0
        self._lock = asyncio.Lock()

    @property
    def put_calls(self) -> int:
        return self._put_calls

    async def ensure_ready(self) -> None:
        return None

    async def put(self, object_path: str, data: bytes, content_type: str) -> None:
        async with self._lock:
            self._put_calls += 1
            if self._mode.fail_first_put and self._put_calls == 1:
                raise StorageError("in-memory put failure (first)")
            if self._mode.fail_times and self._put_calls <= self._mode.fail_times:
                raise StorageError("in-memory put failure (times)")
            self._store[object_path] = data

    async def get(self, object_path: str) -> bytes:
        return self._store[object_path]

    async def exists(self, object_path: str) -> bool:
        async with self._lock:
            return object_path in self._store

    async def delete(self, object_path: str) -> None:
        async with self._lock:
            self._store.pop(object_path, None)


class ReadinessFailureStorage(InMemoryObjectStorage):
    async def ensure_ready(self) -> None:
        raise StorageError("in-memory storage readiness failure")


def _pdf_ref(filename: str) -> str:
    # Uses the downloader fixture scheme.
    return f"fixture://tests/fixtures/disclosures/{filename}"


@pytest.fixture
async def db() -> tuple[Any, Any]:
    settings = Settings()
    require_safe_test_database(
        settings.database.url,
        operation="destructive integration DB operations",
    )

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    # Seed company once.
    async with session_factory() as session, session.begin():
        repo = CompanyRepository(session)
        if await repo.get_by_ticker("FPT") is None:
            await repo.create(
                ticker="FPT",
                company_name="FPT Corporation",
                exchange=Exchange.HOSE.value,
                fiscal_year_end_month=12,
            )

        # Clean G1 tables before each test.
        await session.execute(sa.delete(DocumentArtifactModel))
        await session.execute(sa.delete(RawObjectModel))
        await session.execute(sa.delete(SourcePublicationModel))
        await session.execute(sa.delete(IngestionRunModel))

    yield engine, session_factory
    await engine.dispose()


def _downloader() -> DocumentDownloader:
    return DocumentDownloader(crawler_settings=CrawlerSettings(_env_file=None))


async def _run_ingest(
    *,
    session_factory: Any,
    documents: list[SourceDocument],
    storage: ObjectStorage,
    fail_discover: bool = False,
    concurrent: int = 1,
) -> list[Any]:
    connector = StaticConnector(documents, fail_discover=fail_discover)
    registry = ConnectorRegistry()
    registry.register(connector)

    service = IngestCompanyService(
        session_factory=session_factory,
        registry=registry,
        downloader=_downloader(),
        storage=storage,
    )

    if concurrent == 1:
        return [await service.ingest(ticker="FPT", source=SourceType.FIXTURE)]

    tasks = [service.ingest(ticker="FPT", source=SourceType.FIXTURE) for _ in range(concurrent)]
    return await asyncio.gather(*tasks)


def _doc_ids(documents: list[SourceDocument]) -> list[str]:
    return [d.source_document_id for d in documents]


@pytest.mark.asyncio
async def test_publication_multiple_attachments_and_rerun_idempotent(db: tuple[Any, Any]) -> None:
    _engine, session_factory = db

    published_at = datetime(2024, 4, 20, 10, 0, tzinfo=UTC)
    doc = SourceDocument(
        source=SourceType.FIXTURE,
        source_document_id="pub-v1",
        ticker="FPT",
        title="v1",
        published_at=published_at,
        document_type=DocumentType.PERIODIC_REPORT,
        attachments=[
            SourceAttachment(
                filename="a1.pdf",
                download_reference=_pdf_ref("fpt-q1-2024.pdf"),
                reported_mime_type="application/pdf",
            ),
            SourceAttachment(
                filename="a2.pdf",
                download_reference=_pdf_ref("fpt-q1-2024-corrected.pdf"),
                reported_mime_type="application/pdf",
            ),
        ],
    )

    storage = InMemoryObjectStorage()
    results = await _run_ingest(
        session_factory=session_factory, documents=[doc], storage=storage
    )
    first = results[0]
    results2 = await _run_ingest(
        session_factory=session_factory, documents=[doc], storage=storage
    )
    second = results2[0]

    async with session_factory() as session:
        pub_count = await session.scalar(
            select(func.count()).select_from(SourcePublicationModel)
        )
        artifact_count = await session.scalar(
            select(func.count()).select_from(DocumentArtifactModel)
        )
        raw_count = await session.scalar(
            select(func.count()).select_from(RawObjectModel)
        )
        run_count = await session.scalar(
            select(func.count()).select_from(IngestionRunModel)
        )

    assert first.downloaded == 2
    assert second.downloaded == 0
    assert second.skipped == 2
    assert pub_count == 1
    assert artifact_count == 2
    assert raw_count == 2
    assert run_count == 2


@pytest.mark.asyncio
async def test_duplicate_attachment_handling(db: tuple[Any, Any]) -> None:
    _engine, session_factory = db
    published_at = datetime(2024, 4, 20, 10, 0, tzinfo=UTC)

    doc = SourceDocument(
        source=SourceType.FIXTURE,
        source_document_id="pub-dup",
        ticker="FPT",
        title="dup",
        published_at=published_at,
        document_type=DocumentType.PERIODIC_REPORT,
        attachments=[
            SourceAttachment(
                filename="x1.pdf",
                download_reference=_pdf_ref("shared-a.pdf"),
                reported_mime_type="application/pdf",
            ),
            SourceAttachment(
                filename="x2.pdf",
                download_reference=_pdf_ref("shared-a.pdf"),  # same attachment_reference
                reported_mime_type="application/pdf",
            ),
        ],
    )

    storage = InMemoryObjectStorage()
    await _run_ingest(session_factory=session_factory, documents=[doc], storage=storage)

    async with session_factory() as session:
        artifact_count = await session.scalar(
            select(func.count()).select_from(DocumentArtifactModel)
        )
        raw_count = await session.scalar(select(func.count()).select_from(RawObjectModel))

    assert artifact_count == 1
    assert raw_count == 1


@pytest.mark.asyncio
async def test_multiple_publications_share_identical_raw_bytes(db: tuple[Any, Any]) -> None:
    _engine, session_factory = db
    published_at = datetime(2024, 4, 20, 10, 0, tzinfo=UTC)

    doc1 = SourceDocument(
        source=SourceType.FIXTURE,
        source_document_id="pub-a",
        ticker="FPT",
        title="a",
        published_at=published_at,
        document_type=DocumentType.PERIODIC_REPORT,
        attachments=[
            SourceAttachment(
                filename="a.pdf",
                download_reference=_pdf_ref("shared-a.pdf"),
                reported_mime_type="application/pdf",
            )
        ],
    )
    doc2 = SourceDocument(
        source=SourceType.FIXTURE,
        source_document_id="pub-b",
        ticker="FPT",
        title="b",
        published_at=published_at,
        document_type=DocumentType.PERIODIC_REPORT,
        attachments=[
            SourceAttachment(
                filename="b.pdf",
                download_reference=_pdf_ref("shared-b.pdf"),
                reported_mime_type="application/pdf",
            )
        ],
    )

    storage = InMemoryObjectStorage()
    await _run_ingest(session_factory=session_factory, documents=[doc1, doc2], storage=storage)

    async with session_factory() as session:
        raw_count = await session.scalar(select(func.count()).select_from(RawObjectModel))
        artifacts = (await session.execute(select(DocumentArtifactModel))).scalars().all()

        raw_ids = {a.raw_object_id for a in artifacts}

    assert raw_count == 1
    assert len(raw_ids) == 1
    assert len(artifacts) == 2


@pytest.mark.asyncio
async def test_correction_chain_v1_to_v2_to_v3(db: tuple[Any, Any]) -> None:
    _engine, session_factory = db
    t0 = datetime(2024, 4, 20, 10, 0, tzinfo=UTC)
    t1 = datetime(2024, 4, 20, 14, 0, tzinfo=UTC)
    t2 = datetime(2024, 4, 20, 18, 0, tzinfo=UTC)

    v1 = SourceDocument(
        source=SourceType.FIXTURE,
        source_document_id="v1",
        ticker="FPT",
        title="v1",
        published_at=t0,
        document_type=DocumentType.PERIODIC_REPORT,
        attachments=[
            SourceAttachment(
                filename="v1.pdf",
                download_reference=_pdf_ref("fpt-q1-2024.pdf"),
                reported_mime_type="application/pdf",
            )
        ],
        is_correction=False,
    )
    v2 = SourceDocument(
        source=SourceType.FIXTURE,
        source_document_id="v2",
        ticker="FPT",
        title="v2 correction",
        published_at=t1,
        document_type=DocumentType.PERIODIC_REPORT,
        attachments=[
            SourceAttachment(
                filename="v2.pdf",
                download_reference=_pdf_ref("fpt-q1-2024-corrected.pdf"),
                reported_mime_type="application/pdf",
            )
        ],
        is_correction=True,
        supersedes_source_document_id="v1",
    )
    v3 = SourceDocument(
        source=SourceType.FIXTURE,
        source_document_id="v3",
        ticker="FPT",
        title="v3 correction",
        published_at=t2,
        document_type=DocumentType.PERIODIC_REPORT,
        attachments=[
            SourceAttachment(
                filename="v3.pdf",
                download_reference=_pdf_ref("fpt-q1-2024-v3.pdf"),
                reported_mime_type="application/pdf",
            )
        ],
        is_correction=True,
        supersedes_source_document_id="v2",
    )

    storage = InMemoryObjectStorage()
    await _run_ingest(session_factory=session_factory, documents=[v1, v2, v3], storage=storage)

    async with session_factory() as session:
        pubs = (
            await session.execute(
                select(SourcePublicationModel).where(
                    SourcePublicationModel.source_document_id.in_(
                        ["v1", "v2", "v3"]
                    )
                )
            )
        ).scalars().all()
        by_id = {p.source_document_id: p for p in pubs}

    assert by_id["v3"].is_latest_version is True
    assert by_id["v2"].is_latest_version is False
    assert by_id["v1"].is_latest_version is False
    assert by_id["v2"].parent_publication_id == by_id["v1"].id
    assert by_id["v3"].parent_publication_id == by_id["v2"].id


@pytest.mark.asyncio
async def test_failed_lineage_link_does_not_expose_successor_as_latest(
    db: tuple[Any, Any],
) -> None:
    _engine, session_factory = db
    published_at = datetime(2024, 4, 20, 10, 0, tzinfo=UTC)
    v1 = SourceDocument(
        source=SourceType.FIXTURE,
        source_document_id="link-failure-v1",
        ticker="FPT",
        title="link failure v1",
        published_at=published_at,
        document_type=DocumentType.PERIODIC_REPORT,
    )
    v2 = SourceDocument(
        source=SourceType.FIXTURE,
        source_document_id="link-failure-v2",
        ticker="FPT",
        title="link failure v2",
        published_at=published_at,
        document_type=DocumentType.PERIODIC_REPORT,
        supersedes_source_document_id="link-failure-v1",
    )

    async with session_factory() as session, session.begin():
        await session.execute(
            sa.text(
                """
                CREATE OR REPLACE FUNCTION fail_publication_link_for_g1()
                RETURNS trigger AS $$
                BEGIN
                    RAISE EXCEPTION 'simulated lineage-link failure';
                END;
                $$ LANGUAGE plpgsql
                """
            )
        )
        await session.execute(
            sa.text(
                """
                CREATE TRIGGER fail_publication_link_for_g1
                BEFORE UPDATE OF parent_publication_id ON source_publications
                FOR EACH ROW EXECUTE FUNCTION fail_publication_link_for_g1()
                """
            )
        )

    try:
        results = await _run_ingest(
            session_factory=session_factory,
            documents=[v1, v2],
            storage=InMemoryObjectStorage(),
        )
        assert results[0].status == IngestionRunStatus.FAILED
    finally:
        async with session_factory() as session, session.begin():
            await session.execute(
                sa.text(
                    "DROP TRIGGER IF EXISTS fail_publication_link_for_g1 "
                    "ON source_publications"
                )
            )
            await session.execute(
                sa.text("DROP FUNCTION IF EXISTS fail_publication_link_for_g1()")
            )

    async with session_factory() as session:
        pubs = (
            await session.execute(
                select(SourcePublicationModel).where(
                    SourcePublicationModel.source_document_id.in_(
                        ["link-failure-v1", "link-failure-v2"]
                    )
                )
            )
        ).scalars().all()
        by_id = {publication.source_document_id: publication for publication in pubs}

    assert by_id["link-failure-v1"].is_latest_version is True
    assert by_id["link-failure-v2"].is_latest_version is False


@pytest.mark.asyncio
async def test_normal_new_version_closes_parent(db: tuple[Any, Any]) -> None:
    _engine, session_factory = db
    base = datetime(2024, 4, 20, 10, 0, tzinfo=UTC)
    new = datetime(2024, 4, 20, 15, 0, tzinfo=UTC)

    v0 = SourceDocument(
        source=SourceType.FIXTURE,
        source_document_id="nv0",
        ticker="FPT",
        title="nv0",
        published_at=base,
        document_type=DocumentType.PERIODIC_REPORT,
        attachments=[
            SourceAttachment(
                filename="nv0.pdf",
                download_reference=_pdf_ref("shared-a.pdf"),
                reported_mime_type="application/pdf",
            )
        ],
        is_correction=False,
    )
    v1 = SourceDocument(
        source=SourceType.FIXTURE,
        source_document_id="nv1",
        ticker="FPT",
        title="nv1",
        published_at=new,
        document_type=DocumentType.PERIODIC_REPORT,
        attachments=[
            SourceAttachment(
                filename="nv1.pdf",
                download_reference=_pdf_ref("fpt-q1-2024.pdf"),
                reported_mime_type="application/pdf",
            )
        ],
        is_correction=False,
        supersedes_source_document_id="nv0",
    )

    storage = InMemoryObjectStorage()
    await _run_ingest(session_factory=session_factory, documents=[v0, v1], storage=storage)

    async with session_factory() as session:
        nv0 = (
            await session.execute(
                select(SourcePublicationModel).where(
                    SourcePublicationModel.source_document_id == "nv0"
                )
            )
        ).scalar_one()
        nv1 = (
            await session.execute(
                select(SourcePublicationModel).where(
                    SourcePublicationModel.source_document_id == "nv1"
                )
            )
        ).scalar_one()

    assert nv0.is_latest_version is False
    assert nv1.is_latest_version is True


@pytest.mark.asyncio
async def test_unresolved_correction_sets_needs_review(db: tuple[Any, Any]) -> None:
    _engine, session_factory = db
    published = datetime(2024, 4, 20, 18, 0, tzinfo=UTC)

    unresolved = SourceDocument(
        source=SourceType.FIXTURE,
        source_document_id="u1",
        ticker="FPT",
        title="unresolved correction",
        published_at=published,
        document_type=DocumentType.PERIODIC_REPORT,
        attachments=[
            SourceAttachment(
                filename="u1.pdf",
                download_reference=_pdf_ref("fpt-q1-2024.pdf"),
                reported_mime_type="application/pdf",
            )
        ],
        is_correction=True,
        supersedes_source_document_id="missing-parent",
    )

    storage = InMemoryObjectStorage()
    await _run_ingest(session_factory=session_factory, documents=[unresolved], storage=storage)

    async with session_factory() as session:
        pub = (
            await session.execute(
                select(SourcePublicationModel).where(
                    SourcePublicationModel.source_document_id == "u1"
                )
            )
        ).scalar_one()

    assert pub.processing_status == ProcessingStatus.NEEDS_REVIEW.value
    assert pub.is_latest_version is False
    assert pub.parent_publication_id is None


@pytest.mark.asyncio
async def test_correction_without_predecessor_sets_needs_review(db: tuple[Any, Any]) -> None:
    _engine, session_factory = db
    published = datetime(2024, 4, 20, 18, 0, tzinfo=UTC)

    unresolved = SourceDocument(
        source=SourceType.FIXTURE,
        source_document_id="u2",
        ticker="FPT",
        title="correction without predecessor",
        published_at=published,
        document_type=DocumentType.PERIODIC_REPORT,
        attachments=[
            SourceAttachment(
                filename="u2.pdf",
                download_reference=_pdf_ref("fpt-q1-2024.pdf"),
                reported_mime_type="application/pdf",
            )
        ],
        is_correction=True,
        supersedes_source_document_id=None,
    )

    storage = InMemoryObjectStorage()
    results = await _run_ingest(
        session_factory=session_factory, documents=[unresolved], storage=storage
    )
    assert results[0].status == IngestionRunStatus.COMPLETED

    async with session_factory() as session:
        pub = (
            await session.execute(
                select(SourcePublicationModel).where(
                    SourcePublicationModel.source_document_id == "u2"
                )
            )
        ).scalar_one()

    assert pub.processing_status == ProcessingStatus.NEEDS_REVIEW.value
    assert pub.is_latest_version is False
    assert pub.parent_publication_id is None


@pytest.mark.asyncio
async def test_source_discovery_failure_persists_failed_ingestion_run(db: tuple[Any, Any]) -> None:
    _engine, session_factory = db
    storage = InMemoryObjectStorage()

    connector = StaticConnector([], fail_discover=True)
    registry = ConnectorRegistry()
    registry.register(connector)
    service = IngestCompanyService(
        session_factory=session_factory,
        registry=registry,
        downloader=_downloader(),
        storage=storage,
    )

    with pytest.raises(SourceError):
        await service.ingest(ticker="FPT", source=SourceType.FIXTURE)

    async with session_factory() as session:
        run = (await session.execute(select(IngestionRunModel))).scalars().all()[0]

    assert run.status == IngestionRunStatus.FAILED.value


@pytest.mark.asyncio
async def test_storage_readiness_failure_persists_failed_ingestion_run(
    db: tuple[Any, Any],
) -> None:
    _engine, session_factory = db
    results = await _run_ingest(
        session_factory=session_factory,
        documents=[],
        storage=ReadinessFailureStorage(),
    )

    async with session_factory() as session:
        run = (await session.execute(select(IngestionRunModel))).scalars().one()

    assert results[0].status == IngestionRunStatus.FAILED
    assert run.status == IngestionRunStatus.FAILED.value


@pytest.mark.asyncio
async def test_partial_download_failure_marks_partial(db: tuple[Any, Any]) -> None:
    _engine, session_factory = db
    published_at = datetime(2024, 4, 20, 10, 0, tzinfo=UTC)

    doc = SourceDocument(
        source=SourceType.FIXTURE,
        source_document_id="partial",
        ticker="FPT",
        title="partial",
        published_at=published_at,
        document_type=DocumentType.PERIODIC_REPORT,
        attachments=[
            SourceAttachment(
                filename="ok.pdf",
                download_reference=_pdf_ref("fpt-q1-2024.pdf"),
                reported_mime_type="application/pdf",
            ),
            SourceAttachment(
                filename="missing.pdf",
                download_reference=_pdf_ref("this-does-not-exist.pdf"),
                reported_mime_type="application/pdf",
            ),
        ],
    )

    storage = InMemoryObjectStorage()
    results = await _run_ingest(session_factory=session_factory, documents=[doc], storage=storage)
    result = results[0]

    async with session_factory() as session:
        run = (await session.execute(select(IngestionRunModel))).scalars().all()[0]
        artifact_count = await session.scalar(
            select(func.count()).select_from(DocumentArtifactModel)
        )

    assert result.status == IngestionRunStatus.PARTIAL
    assert run.status == IngestionRunStatus.PARTIAL.value
    assert artifact_count == 1


@pytest.mark.asyncio
async def test_storage_failure_is_retryable_in_memory(db: tuple[Any, Any]) -> None:
    _engine, session_factory = db
    published_at = datetime(2024, 4, 20, 10, 0, tzinfo=UTC)

    doc = SourceDocument(
        source=SourceType.FIXTURE,
        source_document_id="minio-fail",
        ticker="FPT",
        title="minio-fail",
        published_at=published_at,
        document_type=DocumentType.PERIODIC_REPORT,
        attachments=[
            SourceAttachment(
                filename="x.pdf",
                download_reference=_pdf_ref("shared-a.pdf"),
                reported_mime_type="application/pdf",
            )
        ],
    )

    storage = InMemoryObjectStorage(mode=PutFailureMode(fail_first_put=True))
    results = await _run_ingest(session_factory=session_factory, documents=[doc], storage=storage)
    assert results[0].status == IngestionRunStatus.FAILED

    # Retry with working storage.
    storage2 = InMemoryObjectStorage()
    results2 = await _run_ingest(session_factory=session_factory, documents=[doc], storage=storage2)

    async with session_factory() as session:
        artifact_count = await session.scalar(
            select(func.count()).select_from(DocumentArtifactModel)
        )
        raw_count = await session.scalar(select(func.count()).select_from(RawObjectModel))

    assert results2[0].status == IngestionRunStatus.COMPLETED
    assert artifact_count == 1
    assert raw_count == 1


@pytest.mark.asyncio
async def test_minio_failure_is_retryable(db: tuple[Any, Any]) -> None:
    """
    Real MinIO/S3 integration test.

    Skips if OBJECT_STORAGE_* environment variables are not configured.
    """
    import os
    import uuid as _uuid

    from src.storage.minio_adapter import MinioObjectStorage

    endpoint = os.getenv("OBJECT_STORAGE_ENDPOINT")
    access_key = os.getenv("OBJECT_STORAGE_ACCESS_KEY")
    secret_key = os.getenv("OBJECT_STORAGE_SECRET_KEY")
    bucket = os.getenv("OBJECT_STORAGE_BUCKET", "research")
    secure_raw = os.getenv("OBJECT_STORAGE_SECURE", "false")

    if not endpoint or not access_key or not secret_key:
        pytest.skip("OBJECT_STORAGE_* not configured")
    require_safe_test_bucket(bucket, operation="real MinIO integration test")

    secure = secure_raw.lower() in {"1", "true", "yes", "y", "on"}

    # Use unique bucket name to avoid interfering with other runs.
    test_bucket = f"{bucket}-{_uuid.uuid4().hex[:8]}"

    from src.config.settings import ObjectStorageSettings

    bad_storage = MinioObjectStorage(
        ObjectStorageSettings(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key + "corrupt",
            bucket=test_bucket,
            secure=secure,
        )
    )
    good_storage = MinioObjectStorage(
        ObjectStorageSettings(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            bucket=test_bucket,
            secure=secure,
        )
    )

    # Ensure bucket exists for the retry.
    await good_storage.ensure_bucket()

    _engine, session_factory = db
    published_at = datetime(2024, 4, 20, 10, 0, tzinfo=UTC)

    doc = SourceDocument(
        source=SourceType.FIXTURE,
        source_document_id="minio-fail-real",
        ticker="FPT",
        title="minio-fail-real",
        published_at=published_at,
        document_type=DocumentType.PERIODIC_REPORT,
        attachments=[
            SourceAttachment(
                filename="x.pdf",
                download_reference=_pdf_ref("shared-a.pdf"),
                reported_mime_type="application/pdf",
            )
        ],
    )

    class ReadyThenFailingPutStorage:
        """Use real MinIO for readiness and fail only the real object upload."""

        async def ensure_ready(self) -> None:
            await good_storage.ensure_ready()

        async def put(self, object_path: str, data: bytes, content_type: str) -> None:
            await bad_storage.put(object_path, data, content_type)

        async def get(self, object_path: str) -> bytes:
            return await good_storage.get(object_path)

        async def exists(self, object_path: str) -> bool:
            return await good_storage.exists(object_path)

        async def delete(self, object_path: str) -> None:
            await good_storage.delete(object_path)

    # First attempt reaches a real MinIO put_object call with bad credentials.
    results = await _run_ingest(
        session_factory=session_factory,
        documents=[doc],
        storage=ReadyThenFailingPutStorage(),
    )
    assert results[0].status == IngestionRunStatus.FAILED

    # Retry with working storage.
    results2 = await _run_ingest(
        session_factory=session_factory, documents=[doc], storage=good_storage
    )

    async with session_factory() as session:
        artifact_count = await session.scalar(
            select(func.count()).select_from(DocumentArtifactModel)
        )
        raw_count = await session.scalar(
            select(func.count()).select_from(RawObjectModel)
        )

    assert results2[0].status == IngestionRunStatus.COMPLETED
    assert artifact_count == 1
    assert raw_count == 1


@pytest.mark.asyncio
async def test_db_failure_after_object_upload_and_retry(db: tuple[Any, Any]) -> None:
    _engine, session_factory = db
    published_at = datetime(2024, 4, 20, 10, 0, tzinfo=UTC)

    doc = SourceDocument(
        source=SourceType.FIXTURE,
        source_document_id="db-after-upload",
        ticker="FPT",
        title="db-after-upload",
        published_at=published_at,
        document_type=DocumentType.PERIODIC_REPORT,
        attachments=[
            SourceAttachment(
                filename="x.pdf",
                download_reference=_pdf_ref("shared-a.pdf"),
                reported_mime_type="application/pdf",
            )
        ],
    )

    storage = InMemoryObjectStorage()

    # Make PostgreSQL reject the raw-object insert.  This occurs after the
    # downloader has written the binary, so it validates the real recovery
    # path without replacing repository behavior in-process.
    async with session_factory() as session, session.begin():
        await session.execute(
            sa.text(
                """
                CREATE OR REPLACE FUNCTION fail_raw_object_insert_for_g1()
                RETURNS trigger AS $$
                BEGIN
                    RAISE EXCEPTION 'simulated DB failure after object upload';
                END;
                $$ LANGUAGE plpgsql
                """
            )
        )
        await session.execute(
            sa.text(
                """
                CREATE TRIGGER fail_raw_object_insert_for_g1
                BEFORE INSERT ON raw_objects
                FOR EACH ROW EXECUTE FUNCTION fail_raw_object_insert_for_g1()
                """
            )
        )

    try:
        results = await _run_ingest(
            session_factory=session_factory, documents=[doc], storage=storage
        )
        assert results[0].status == IngestionRunStatus.FAILED
    finally:
        async with session_factory() as session, session.begin():
            await session.execute(
                sa.text(
                    "DROP TRIGGER IF EXISTS fail_raw_object_insert_for_g1 ON raw_objects"
                )
            )
            await session.execute(
                sa.text("DROP FUNCTION IF EXISTS fail_raw_object_insert_for_g1()")
            )

    # Retry should not need to re-put the same SHA object.
    results2 = await _run_ingest(session_factory=session_factory, documents=[doc], storage=storage)
    assert results2[0].status == IngestionRunStatus.COMPLETED

    async with session_factory() as session:
        raw_count = await session.scalar(select(func.count()).select_from(RawObjectModel))
        artifact_count = await session.scalar(
            select(func.count()).select_from(DocumentArtifactModel)
        )

    assert raw_count == 1
    assert artifact_count == 1
    assert storage.put_calls == 1


@pytest.mark.asyncio
async def test_concurrent_ingestion_no_logical_duplicates(db: tuple[Any, Any]) -> None:
    _engine, session_factory = db
    published_at = datetime(2024, 4, 20, 10, 0, tzinfo=UTC)

    doc = SourceDocument(
        source=SourceType.FIXTURE,
        source_document_id="concurrent",
        ticker="FPT",
        title="concurrent",
        published_at=published_at,
        document_type=DocumentType.PERIODIC_REPORT,
        attachments=[
            SourceAttachment(
                filename="x.pdf",
                download_reference=_pdf_ref("shared-a.pdf"),
                reported_mime_type="application/pdf",
            )
        ],
    )

    storage = InMemoryObjectStorage()
    await _run_ingest(
        session_factory=session_factory,
        documents=[doc],
        storage=storage,
        concurrent=2,
    )

    async with session_factory() as session:
        pub_count = await session.scalar(
            select(func.count()).select_from(SourcePublicationModel)
        )
        artifact_count = await session.scalar(
            select(func.count()).select_from(DocumentArtifactModel)
        )
        raw_count = await session.scalar(
            select(func.count()).select_from(RawObjectModel)
        )
        run_count = await session.scalar(select(func.count()).select_from(IngestionRunModel))

    assert pub_count == 1
    assert artifact_count == 1
    assert raw_count == 1
    assert run_count == 2


@pytest.mark.asyncio
async def test_concurrent_out_of_order_lineage_keeps_terminal_v3_latest(
    db: tuple[Any, Any],
) -> None:
    _engine, session_factory = db
    published_at = datetime(2024, 4, 20, 10, 0, tzinfo=UTC)

    v1 = SourceDocument(
        source=SourceType.FIXTURE,
        source_document_id="v1",
        ticker="FPT",
        title="v1",
        published_at=published_at,
        document_type=DocumentType.PERIODIC_REPORT,
        attachments=[
            SourceAttachment(
                filename="v1.pdf",
                download_reference=_pdf_ref("shared-a.pdf"),
                reported_mime_type="application/pdf",
            )
        ],
    )
    v2 = SourceDocument(
        source=SourceType.FIXTURE,
        source_document_id="v2",
        ticker="FPT",
        title="v2",
        published_at=published_at,
        document_type=DocumentType.PERIODIC_REPORT,
        attachments=[
            SourceAttachment(
                filename="v2.pdf",
                download_reference=_pdf_ref("fpt-q1-2024.pdf"),
                reported_mime_type="application/pdf",
            )
        ],
        supersedes_source_document_id="v1",
    )
    v3 = SourceDocument(
        source=SourceType.FIXTURE,
        source_document_id="v3",
        ticker="FPT",
        title="v3",
        published_at=published_at,
        document_type=DocumentType.PERIODIC_REPORT,
        attachments=[
            SourceAttachment(
                filename="v3.pdf",
                download_reference=_pdf_ref("fpt-q1-2024-corrected.pdf"),
                reported_mime_type="application/pdf",
            )
        ],
        supersedes_source_document_id="v2",
    )

    storage = InMemoryObjectStorage()

    await _run_ingest(
        session_factory=session_factory,
        documents=[v3, v2, v1],
        storage=storage,
        concurrent=2,
    )

    async with session_factory() as session:
        pubs = (
            await session.execute(
                sa.select(SourcePublicationModel).where(
                    SourcePublicationModel.source_document_id.in_(["v1", "v2", "v3"])
                )
            )
        ).scalars().all()
        by_id = {p.source_document_id: p for p in pubs}

    assert by_id["v1"].is_latest_version is False
    assert by_id["v2"].is_latest_version is False
    assert by_id["v3"].is_latest_version is True

