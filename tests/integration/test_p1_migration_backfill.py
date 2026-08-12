from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import sqlalchemy as sa
from src.config.settings import Settings
from src.db.models.company import CompanyModel
from src.db.models.document import DocumentModel
from src.db.models.document_artifact import DocumentArtifactModel
from src.db.models.raw_object import RawObjectModel
from src.db.models.source_publication import SourcePublicationModel
from src.db.repositories.company import CompanyRepository
from src.db.session import create_engine, create_session_factory
from src.domain.enums import DocumentType, Exchange, SourceType
from tests.integration.safety import require_safe_test_database

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def database_settings() -> Settings:
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not configured for integration tests")
    return Settings()


def _alembic(env: dict[str, str], *args: str) -> None:
    proc = subprocess.run(
        ["alembic", *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr


@pytest.mark.asyncio
async def test_p1_backfill_migrates_documents_rows(database_settings: Settings) -> None:
    # Create a pre-existing P1 `documents` row, then upgrade to head and ensure
    # it appears in the new publication/artifact/raw-object tables.
    require_safe_test_database(
        database_settings.database.url,
        operation="destructive migration integration test",
    )

    env = os.environ.copy()
    env["DATABASE_URL"] = database_settings.database.url

    _alembic(env, "downgrade", "002_p1_domain")

    engine = create_engine(database_settings)
    session_factory = create_session_factory(engine)

    try:
        async def _seed() -> None:
            async with session_factory() as session, session.begin():
                await session.execute(sa.delete(DocumentModel))
                await session.execute(sa.delete(CompanyModel))
                company_repo = CompanyRepository(session)
                company = await company_repo.create(
                    ticker="MIG",
                    company_name="Migration Test",
                    exchange=Exchange.HOSE.value,
                    industry_code=None,
                    industry_name=None,
                    fiscal_year_end_month=12,
                    is_active=True,
                )

                doc = DocumentModel(
                    id=uuid4(),
                    company_id=company.id,
                    source=SourceType.FIXTURE.value,
                    source_document_id="legacy-1",
                    document_type=DocumentType.PERIODIC_REPORT.value,
                    title="legacy-1",
                    published_at=datetime(2024, 4, 20, 10, 0, tzinfo=UTC),
                    period_start=None,
                    period_end=None,
                    fiscal_year=None,
                    fiscal_quarter=None,
                    scope="unknown",
                    audit_status="unknown",
                    language=None,
                    source_reference=None,
                    object_path="raw/legacy/object.pdf",
                    filename="object.pdf",
                    mime_type="application/pdf",
                    file_size=10,
                    sha256="legacy-sha",
                    parent_document_id=None,
                    is_correction=False,
                    is_latest_version=True,
                    processing_status="PENDING",
                )
                session.add(doc)

        await _seed()

        _alembic(env, "upgrade", "head")

        async def _assert() -> None:
            async with session_factory() as session:
                sp_count = await session.scalar(
                    sa.select(sa.func.count()).select_from(SourcePublicationModel)
                )
                ro_count = await session.scalar(
                    sa.select(sa.func.count()).select_from(RawObjectModel)
                )
                da_count = await session.scalar(
                    sa.select(sa.func.count()).select_from(DocumentArtifactModel)
                )

                assert sp_count == 1
                assert ro_count == 1
                assert da_count == 1

                sp = (
                    await session.execute(
                        sa.select(SourcePublicationModel).where(
                            SourcePublicationModel.source_document_id
                            == "legacy-1"
                        )
                    )
                ).scalar_one()
                assert sp.source == SourceType.FIXTURE.value

        await _assert()
    finally:
        await engine.dispose()

