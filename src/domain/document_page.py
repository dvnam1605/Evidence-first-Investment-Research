"""Document page domain model (persisted extraction unit)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.enums import ExtractionMethod


@dataclass(frozen=True, slots=True)
class DocumentPage:
    """
    One extracted page for a document artifact.

    `document_id` is the processed artifact id (`document_artifacts.id`), matching
    DOC-01 processing jobs and ParsedDocument.artifact_id.
    """

    id: UUID
    document_id: UUID
    page_number: int
    text: str
    extraction_method: ExtractionMethod
    ocr_confidence: float | None
    width: float
    height: float
    created_at: datetime

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValueError("page_number must be >= 1")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width and height must be > 0")
        if self.extraction_method is ExtractionMethod.NATIVE and self.ocr_confidence is not None:
            raise ValueError("native extraction must not set ocr_confidence")
        if self.extraction_method is ExtractionMethod.OCR and self.ocr_confidence is None:
            raise ValueError("ocr extraction requires ocr_confidence")
