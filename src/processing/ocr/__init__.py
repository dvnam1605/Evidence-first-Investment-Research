"""OCR processing package."""

from src.processing.ocr.base import OCREngine
from src.processing.ocr.fallback import OCRFallback
from src.processing.ocr.models import (
    DocumentOCRFallbackResult,
    OCRPageResult,
    OCRResultStatus,
    OCRTextLine,
    PageImage,
)
from src.processing.ocr.quality import (
    DEFAULT_OCR_QUALITY_POLICY,
    OCRQualityPolicy,
    assess_ocr_quality,
)

__all__ = [
    "DEFAULT_OCR_QUALITY_POLICY",
    "DocumentOCRFallbackResult",
    "OCREngine",
    "OCRFallback",
    "OCRPageResult",
    "OCRQualityPolicy",
    "OCRResultStatus",
    "OCRTextLine",
    "PageImage",
    "assess_ocr_quality",
]
