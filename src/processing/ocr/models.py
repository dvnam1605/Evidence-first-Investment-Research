"""OCR result models (sidecar to native PDF text; never overwrite it)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class OCRResultStatus(StrEnum):
    """Page-level OCR trust signal for downstream persistence."""

    OK = "OK"
    NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass(frozen=True, slots=True)
class PageImage:
    """Rasterized PDF page ready for OCR."""

    page_number: int
    width: int
    height: int
    png_bytes: bytes
    dpi: int


@dataclass(frozen=True, slots=True)
class OCRTextLine:
    text: str
    confidence: float | None
    # Axis-aligned bbox when available: x0, y0, x1, y1 in image pixel space.
    bbox: tuple[float, float, float, float] | None = None


@dataclass(frozen=True, slots=True)
class OCRPageResult:
    """OCR output for one page — stored alongside native text, not instead of it."""

    page_number: int
    engine: str
    engine_version: str
    text: str
    confidence: float | None
    lines: tuple[OCRTextLine, ...]
    # JSON-friendly line payloads retained for audit / DOC-06 persistence.
    raw: tuple[dict[str, Any], ...]
    decision_reason: str
    # Trust signal — engines may leave provisional values; OCRFallback assesses.
    status: OCRResultStatus = OCRResultStatus.NEEDS_REVIEW
    quality_reason: str = "unassessed"
    quality_policy_version: str = ""
    quality_policy_min_confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class DocumentOCRFallbackResult:
    """OCR applied only to pages flagged by the decision detector."""

    pages: tuple[OCRPageResult, ...]
    skipped_page_numbers: tuple[int, ...]
    source_sha256: str
    needs_review: bool
    quality_policy_version: str
    quality_policy_min_confidence: float
