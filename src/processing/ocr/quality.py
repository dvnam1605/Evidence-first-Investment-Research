"""OCR quality policy and review assessment."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from src.processing.ocr.models import OCRPageResult, OCRResultStatus

DEFAULT_OCR_QUALITY_POLICY_VERSION = "ocr-quality-v1"


@dataclass(frozen=True, slots=True)
class OCRQualityPolicy:
    """Immutable OCR acceptance thresholds (injectable for audit/repro)."""

    min_confidence: float = 0.60
    version: str = DEFAULT_OCR_QUALITY_POLICY_VERSION


DEFAULT_OCR_QUALITY_POLICY = OCRQualityPolicy()


def _is_valid_confidence(value: float) -> bool:
    """Finite score in the conventional OCR range [0, 1]."""
    return math.isfinite(value) and 0.0 <= value <= 1.0


def assess_ocr_quality(
    result: OCRPageResult,
    policy: OCRQualityPolicy | None = None,
) -> OCRPageResult:
    """
    Mark empty / unscored / invalid / low-confidence OCR as NEEDS_REVIEW.

    Does not discard text — downstream may still inspect sidecar OCR — but the
    status/reason make uncertainty explicit so it is never treated as trusted.
    """
    resolved = policy or DEFAULT_OCR_QUALITY_POLICY

    if not result.text.strip():
        status = OCRResultStatus.NEEDS_REVIEW
        reason = "no_text_detected"
    elif result.confidence is None:
        status = OCRResultStatus.NEEDS_REVIEW
        reason = "missing_confidence"
    elif not _is_valid_confidence(result.confidence):
        status = OCRResultStatus.NEEDS_REVIEW
        reason = "invalid_confidence"
    elif result.confidence < resolved.min_confidence:
        status = OCRResultStatus.NEEDS_REVIEW
        reason = "low_confidence"
    else:
        status = OCRResultStatus.OK
        reason = "sufficient_confidence"

    return replace(
        result,
        status=status,
        quality_reason=reason,
        quality_policy_version=resolved.version,
        quality_policy_min_confidence=resolved.min_confidence,
    )
