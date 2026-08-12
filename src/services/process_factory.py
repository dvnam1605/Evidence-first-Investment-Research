"""Factory helpers for document processing wiring (DOC-13)."""

from __future__ import annotations

from src.config.settings import Settings, get_settings
from src.db.session import create_engine, create_session_factory
from src.processing.ocr.base import OCREngine
from src.processing.pipeline import DocumentProcessor
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


def build_document_processor(
    settings: Settings | None = None,
    *,
    ocr_engine: OCREngine | None = None,
    use_optional_ocr: bool = True,
) -> DocumentProcessor:
    _ = settings or get_settings()
    engine = ocr_engine
    if engine is None and use_optional_ocr:
        engine = _optional_paddle_engine()
    return DocumentProcessor(ocr_engine=engine)


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
    )
