"""Factory helpers for ingestion wiring."""

from __future__ import annotations

from src.config.settings import Settings, get_settings
from src.db.session import create_engine, create_session_factory
from src.ingestion.downloader import DocumentDownloader
from src.ingestion.fixture.connector import FixtureConnector
from src.ingestion.hnx.connector import HnxConnector
from src.ingestion.hose.connector import HoseConnector
from src.ingestion.issuer_ir.fpt.connector import FptIrConnector
from src.ingestion.registry import ConnectorRegistry
from src.ingestion.service import IngestCompanyService
from src.ingestion.ssc.connector import SscConnector
from src.storage.minio_adapter import MinioObjectStorage


def build_connector_registry(settings: Settings | None = None) -> ConnectorRegistry:
    _ = settings
    registry = ConnectorRegistry()
    registry.register(HoseConnector())
    registry.register(HnxConnector())
    registry.register(SscConnector())
    registry.register(FptIrConnector())
    registry.register(FixtureConnector())
    return registry


def build_ingest_service(settings: Settings | None = None) -> IngestCompanyService:
    resolved = settings or get_settings()
    engine = create_engine(resolved)
    session_factory = create_session_factory(engine)
    storage = MinioObjectStorage(resolved.object_storage)
    downloader = DocumentDownloader(crawler_settings=resolved.crawler)
    registry = build_connector_registry(resolved)
    return IngestCompanyService(
        session_factory=session_factory,
        registry=registry,
        downloader=downloader,
        storage=storage,
    )


async def ensure_storage(settings: Settings | None = None) -> MinioObjectStorage:
    resolved = settings or get_settings()
    storage = MinioObjectStorage(resolved.object_storage)
    await storage.ensure_bucket()
    return storage
