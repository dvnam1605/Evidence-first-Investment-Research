"""Factory helpers for document processing wiring (DOC-13)."""

from __future__ import annotations

from pathlib import Path

from src.config.settings import Settings, get_settings
from src.db.session import create_engine, create_session_factory
from src.processing.ocr.base import OCREngine
from src.processing.pipeline import DocumentProcessor
from src.processing.tables.raw_source import JsonRawTableSource, RawTableSource
from src.services.process_document import ProcessDocumentService
from src.storage.minio_adapter import MinioObjectStorage


def _optional_paddle_engine() -> OCREngine | None:
    """PaddleOCR is an optional extra; absence is a review signal, not a crash."""
    try:
        from src.processing.ocr.paddle import PaddleOCREngine
    except ImportError:
        return None
    try:
        return PaddleOCREngine()
    except Exception:  # noqa: BLE001 — optional dependency may fail at runtime
        return None


def _configured_raw_table_source(settings: Settings) -> RawTableSource | None:
    configured = settings.processing.raw_table_dir
    directory = configured or _bundled_raw_table_directory()
    if configured is not None and not directory.is_absolute():
        directory = Path(__file__).resolve().parents[2] / directory
    if not directory.is_dir():
        raise ValueError(f"PROCESSING_RAW_TABLE_DIR is not a directory: {directory}")
    paths = tuple(sorted(directory.glob("*.json")))
    if not paths:
        raise ValueError(f"PROCESSING_RAW_TABLE_DIR has no JSON sidecars: {directory}")
    return JsonRawTableSource(paths)


def _bundled_raw_table_directory() -> Path:
    package_directory = (
        Path(__file__).resolve().parents[1] / "processing" / "assets" / "fpt_raw"
    )
    if package_directory.is_dir():
        return package_directory
    return (
        Path(__file__).resolve().parents[2]
        / "tests"
        / "fixtures"
        / "processing"
        / "tables"
        / "fpt_raw"
    )


def build_document_processor(
    settings: Settings | None = None,
    *,
    ocr_engine: OCREngine | None = None,
    use_optional_ocr: bool = True,
    raw_table_source: RawTableSource | None = None,
) -> DocumentProcessor:
    resolved = settings or get_settings()
    engine = ocr_engine
    if engine is None and use_optional_ocr:
        engine = _optional_paddle_engine()
    return DocumentProcessor(
        ocr_engine=engine,
        raw_table_source=raw_table_source or _configured_raw_table_source(resolved),
    )


def build_process_service(
    settings: Settings | None = None,
    *,
    processor: DocumentProcessor | None = None,
    use_optional_ocr: bool = True,
) -> ProcessDocumentService:
    resolved = settings or get_settings()
    engine = create_engine(resolved)
    session_factory = create_session_factory(engine)
    storage = MinioObjectStorage(resolved.object_storage)
    return ProcessDocumentService(
        session_factory=session_factory,
        storage=storage,
        processor=processor
        or build_document_processor(resolved, use_optional_ocr=use_optional_ocr),
        stale_job_after_seconds=resolved.processing.stale_job_after_seconds,
    )
