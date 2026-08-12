"""Deterministic OCR necessity detection for scanned/digital PDF pages."""

from __future__ import annotations

from dataclasses import dataclass

from src.processing.pdf.models import ParsedDocument, ParsedPage

DEFAULT_POLICY_VERSION = "ocr-policy-v1"


@dataclass(frozen=True, slots=True)
class OCRThresholdPolicy:
    """Immutable OCR decision thresholds (injectable for audit/repro)."""

    min_native_chars: int = 50
    high_image_coverage: float = 0.20
    low_image_coverage: float = 0.05
    version: str = DEFAULT_POLICY_VERSION


DEFAULT_OCR_POLICY = OCRThresholdPolicy()


@dataclass(frozen=True, slots=True)
class PageOCRDecision:
    page_number: int
    needs_ocr: bool
    reason: str
    char_count: int
    text_block_count: int
    # None means coverage could not be measured (geometry failure / unavailable).
    image_coverage: float | None
    image_count: int
    image_coverage_error: str | None
    policy_version: str
    policy_min_native_chars: int
    policy_high_image_coverage: float
    policy_low_image_coverage: float


@dataclass(frozen=True, slots=True)
class DocumentOCRDecision:
    needs_ocr: bool
    reason: str
    pages: list[PageOCRDecision]
    policy_version: str
    policy_min_native_chars: int
    policy_high_image_coverage: float
    policy_low_image_coverage: float


class OCRDecisionDetector:
    """
    Decide whether OCR should run.

    Rule (deterministic, policy-driven):
    - Sufficient native text (>= min_native_chars) → no OCR.
    - Image coverage fully unavailable (None) with insufficient text → OCR.
    - Image coverage incomplete (error set) with insufficient text → OCR.
    - No text and negligible measured images (no error) → blank page, no OCR.
    - Low text + high image coverage → OCR.
    - Otherwise low text → OCR as insufficient native text.
    """

    def __init__(self, policy: OCRThresholdPolicy | None = None) -> None:
        self._policy = policy or DEFAULT_OCR_POLICY

    @property
    def policy(self) -> OCRThresholdPolicy:
        return self._policy

    def _decision(
        self,
        *,
        page: ParsedPage,
        needs_ocr: bool,
        reason: str,
    ) -> PageOCRDecision:
        policy = self._policy
        return PageOCRDecision(
            page_number=page.page_number,
            needs_ocr=needs_ocr,
            reason=reason,
            char_count=len(page.text_normalized),
            text_block_count=len(page.blocks),
            image_coverage=page.image_coverage,
            image_count=page.image_count,
            image_coverage_error=page.image_coverage_error,
            policy_version=policy.version,
            policy_min_native_chars=policy.min_native_chars,
            policy_high_image_coverage=policy.high_image_coverage,
            policy_low_image_coverage=policy.low_image_coverage,
        )

    def decide_page(self, page: ParsedPage) -> PageOCRDecision:
        policy = self._policy
        char_count = len(page.text_normalized)
        coverage = page.image_coverage

        if char_count >= policy.min_native_chars:
            return self._decision(
                page=page, needs_ocr=False, reason="sufficient_native_text"
            )

        # Geometry failure / unavailable coverage must not look like a blank page.
        if coverage is None:
            return self._decision(
                page=page, needs_ocr=True, reason="image_coverage_unavailable"
            )

        # Partial geometry failure: numeric coverage may be misleadingly low.
        if page.image_coverage_error is not None:
            return self._decision(
                page=page, needs_ocr=True, reason="image_coverage_incomplete"
            )

        if char_count == 0 and coverage < policy.low_image_coverage:
            return self._decision(page=page, needs_ocr=False, reason="blank_page")

        if coverage >= policy.high_image_coverage:
            return self._decision(
                page=page, needs_ocr=True, reason="low_text_high_image_coverage"
            )

        if char_count == 0 and coverage >= policy.low_image_coverage:
            return self._decision(page=page, needs_ocr=True, reason="image_only_page")

        return self._decision(
            page=page, needs_ocr=True, reason="insufficient_native_text"
        )

    def decide_document(self, document: ParsedDocument) -> DocumentOCRDecision:
        policy = self._policy
        page_decisions = [self.decide_page(page) for page in document.pages]
        needing = [d for d in page_decisions if d.needs_ocr]
        if not needing:
            reason = (
                "all_pages_native_or_blank" if page_decisions else "empty_document"
            )
            return DocumentOCRDecision(
                needs_ocr=False,
                reason=reason,
                pages=page_decisions,
                policy_version=policy.version,
                policy_min_native_chars=policy.min_native_chars,
                policy_high_image_coverage=policy.high_image_coverage,
                policy_low_image_coverage=policy.low_image_coverage,
            )
        return DocumentOCRDecision(
            needs_ocr=True,
            reason="pages_require_ocr",
            pages=page_decisions,
            policy_version=policy.version,
            policy_min_native_chars=policy.min_native_chars,
            policy_high_image_coverage=policy.high_image_coverage,
            policy_low_image_coverage=policy.low_image_coverage,
        )
