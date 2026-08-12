"""Apply OCR only to pages that require it; never mutate native PDF text."""

from __future__ import annotations

from dataclasses import replace

from src.processing.errors import OCRFailure
from src.processing.ocr.base import OCREngine
from src.processing.ocr.models import DocumentOCRFallbackResult, OCRPageResult, OCRResultStatus
from src.processing.ocr.quality import (
    DEFAULT_OCR_QUALITY_POLICY,
    OCRQualityPolicy,
    assess_ocr_quality,
)
from src.processing.ocr.render import DEFAULT_OCR_DPI, render_pdf_page
from src.processing.pdf.detector import DocumentOCRDecision, OCRDecisionDetector
from src.processing.pdf.models import ParsedDocument


class OCRFallback:
    """
    Run an OCREngine on detector-flagged pages only.

    OCR output is returned as a sidecar result. Callers must not write OCR text
    into ParsedPage.text — native extraction stays authoritative when present.
    Empty / low-confidence / unscored OCR is marked NEEDS_REVIEW.
    """

    def __init__(
        self,
        engine: OCREngine,
        *,
        detector: OCRDecisionDetector | None = None,
        quality_policy: OCRQualityPolicy | None = None,
        dpi: int = DEFAULT_OCR_DPI,
    ) -> None:
        self._engine = engine
        self._detector = detector or OCRDecisionDetector()
        self._quality_policy = quality_policy or DEFAULT_OCR_QUALITY_POLICY
        self._dpi = dpi

    @property
    def quality_policy(self) -> OCRQualityPolicy:
        return self._quality_policy

    async def run(
        self,
        document: ParsedDocument,
        pdf_bytes: bytes,
        *,
        decision: DocumentOCRDecision | None = None,
    ) -> DocumentOCRFallbackResult:
        if not pdf_bytes:
            raise OCRFailure("pdf_bytes must not be empty for OCR fallback")

        resolved = decision or self._detector.decide_document(document)
        if len(resolved.pages) != len(document.pages):
            raise OCRFailure(
                "OCR decision page count does not match parsed document pages"
            )

        ocr_pages: list[OCRPageResult] = []
        skipped: list[int] = []
        policy = self._quality_policy

        for page, page_decision in zip(document.pages, resolved.pages, strict=True):
            if page.page_number != page_decision.page_number:
                raise OCRFailure(
                    "OCR decision page_number mismatch: "
                    f"parsed={page.page_number} decision={page_decision.page_number}"
                )
            if not page_decision.needs_ocr:
                skipped.append(page.page_number)
                continue

            image = render_pdf_page(pdf_bytes, page.page_number, dpi=self._dpi)
            result = await self._engine.recognize(image)
            if result.page_number != page.page_number:
                raise OCRFailure(
                    "OCR engine returned mismatched page_number: "
                    f"expected={page.page_number} got={result.page_number}"
                )
            assessed = assess_ocr_quality(
                replace(result, decision_reason=page_decision.reason),
                policy,
            )
            ocr_pages.append(assessed)

        return DocumentOCRFallbackResult(
            pages=tuple(ocr_pages),
            skipped_page_numbers=tuple(skipped),
            source_sha256=document.source_sha256,
            needs_review=any(p.status == OCRResultStatus.NEEDS_REVIEW for p in ocr_pages),
            quality_policy_version=policy.version,
            quality_policy_min_confidence=policy.min_confidence,
        )
