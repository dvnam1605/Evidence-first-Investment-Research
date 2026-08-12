"""Ingestion integration tests."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy import func, select
from src.config.settings import Settings
from src.db.models.document_artifact import DocumentArtifactModel
from src.db.models.ingestion_run import IngestionRunModel
from src.db.models.raw_object import RawObjectModel
from src.db.models.source_publication import SourcePublicationModel
from src.db.repositories.company import CompanyRepository
from src.db.session import create_engine, create_session_factory
from src.domain.enums import Exchange, SourceType
from src.ingestion.downloader import DocumentDownloader
from src.ingestion.fixture.connector import FixtureConnector
from src.ingestion.registry import ConnectorRegistry
from src.ingestion.service import IngestCompanyService
from src.storage.minio_adapter import MinioObjectStorage
from tests.integration.safety import require_safe_test_bucket, require_safe_test_database

pytestmark = pytest.mark.integration


@pytest.fixture
async def ingest_service() -> IngestCompanyService:
    settings = Settings()
    require_safe_test_database(
        settings.database.url,
        operation="destructive integration DB operations",
    )
    require_safe_test_bucket(
        settings.object_storage.bucket,
        operation="integration object-storage operations",
    )

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    async with session_factory() as session, session.begin():
        # Keep integration tests isolated across runs.
        await session.execute(sa.delete(DocumentArtifactModel))
        await session.execute(sa.delete(RawObjectModel))
        await session.execute(sa.delete(SourcePublicationModel))
        await session.execute(sa.delete(IngestionRunModel))

        repo = CompanyRepository(session)
        if await repo.get_by_ticker("FPT") is None:
            await repo.create(
                ticker="FPT",
                company_name="FPT Corporation",
                exchange=Exchange.HOSE.value,
                fiscal_year_end_month=12,
            )

    storage = MinioObjectStorage(settings.object_storage)
    await storage.ensure_bucket()
    registry = ConnectorRegistry()
    registry.register(FixtureConnector())
    service = IngestCompanyService(
        session_factory=session_factory,
        registry=registry,
        downloader=DocumentDownloader(crawler_settings=settings.crawler),
        storage=storage,
    )
    yield service
    await engine.dispose()


@pytest.mark.asyncio
async def test_idempotent_fixture_ingestion(ingest_service: IngestCompanyService) -> None:
    first = await ingest_service.ingest(ticker="FPT", source=SourceType.FIXTURE)
    second = await ingest_service.ingest(ticker="FPT", source=SourceType.FIXTURE)

    assert first.downloaded >= 1
    assert second.skipped >= first.downloaded
    assert second.downloaded == 0

    settings = Settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    async with session_factory() as session:
        pub_count = await session.scalar(
            select(func.count()).select_from(SourcePublicationModel)
        )
        artifact_count = await session.scalar(
            select(func.count()).select_from(DocumentArtifactModel)
        )
        run_count = await session.scalar(select(func.count()).select_from(IngestionRunModel))
    await engine.dispose()

    assert pub_count == 2
    assert artifact_count == 2
    assert run_count == 2


@pytest.mark.asyncio
async def test_dry_run_does_not_persist(ingest_service: IngestCompanyService) -> None:
    settings = Settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    before = 0
    async with session_factory() as session:
        before = await session.scalar(select(func.count()).select_from(RawObjectModel)) or 0

    result = await ingest_service.ingest(ticker="FPT", source=SourceType.FIXTURE, dry_run=True)
    assert result.discovered >= 1

    async with session_factory() as session:
        after = await session.scalar(select(func.count()).select_from(RawObjectModel)) or 0
    await engine.dispose()
    assert after == before
