"""PDF parsing service (async facade over native PyMuPDF)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

from src.processing.errors import OCRFailure
from src.processing.ocr.base import OCREngine
from src.processing.ocr.fallback import OCRFallback
from src.processing.ocr.models import DocumentOCRFallbackResult
from src.processing.ocr.quality import OCRQualityPolicy
from src.processing.pdf.detector import DocumentOCRDecision, OCRDecisionDetector
from src.processing.pdf.models import ParsedDocument
from src.processing.pdf.native import NativePDFParser


class PDFParser:
    """Plan interface: async parse(Path) -> ParsedDocument."""

    def __init__(
        self,
        *,
        native: NativePDFParser | None = None,
        ocr_detector: OCRDecisionDetector | None = None,
        ocr_engine: OCREngine | None = None,
        ocr_quality_policy: OCRQualityPolicy | None = None,
    ) -> None:
        self._native = native or NativePDFParser()
        self._ocr_detector = ocr_detector or OCRDecisionDetector()
        self._ocr_engine = ocr_engine
        self._ocr_quality_policy = ocr_quality_policy

    async def parse(
        self,
        path: Path,
        *,
        artifact_id: UUID | None = None,
    ) -> ParsedDocument:
        return await asyncio.to_thread(
            self._native.parse_path, path, artifact_id=artifact_id
        )

    async def parse_bytes(
        self,
        data: bytes,
        *,
        artifact_id: UUID | None = None,
        source_label: str | None = "bytes",
    ) -> ParsedDocument:
        return await asyncio.to_thread(
            self._native.parse_bytes,
            data,
            artifact_id=artifact_id,
            source_label=source_label,
        )

    def assess_ocr(self, document: ParsedDocument) -> DocumentOCRDecision:
        return self._ocr_detector.decide_document(document)

    async def apply_ocr(
        self,
        document: ParsedDocument,
        pdf_bytes: bytes,
        *,
        decision: DocumentOCRDecision | None = None,
    ) -> DocumentOCRFallbackResult:
        """Run OCR only on pages with needs_ocr; does not mutate native page text."""
        if self._ocr_engine is None:
            raise OCRFailure("OCR engine not configured on PDFParser")
        fallback = OCRFallback(
            self._ocr_engine,
            detector=self._ocr_detector,
            quality_policy=self._ocr_quality_policy,
        )
        return await fallback.run(document, pdf_bytes, decision=decision)
