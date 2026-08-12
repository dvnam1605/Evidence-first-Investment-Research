"""Unit tests for DOC-04 OCR decision detector."""

from __future__ import annotations

import fitz
import pytest
from src.processing.pdf.detector import (
    DEFAULT_OCR_POLICY,
    OCRDecisionDetector,
    OCRThresholdPolicy,
)
from src.processing.pdf.models import ParsedDocument, ParsedPage, TextBlock
from src.processing.pdf.native import NativePDFParser, _image_coverage
from src.processing.pdf.service import PDFParser

MIN_NATIVE_CHARS = DEFAULT_OCR_POLICY.min_native_chars
HIGH_IMAGE_COVERAGE = DEFAULT_OCR_POLICY.high_image_coverage
LOW_IMAGE_COVERAGE = DEFAULT_OCR_POLICY.low_image_coverage


def _page(
    *,
    page_number: int = 1,
    text: str = "",
    blocks: list[TextBlock] | None = None,
    image_coverage: float | None = 0.0,
    image_count: int = 0,
    image_coverage_error: str | None = None,
) -> ParsedPage:
    return ParsedPage(
        page_number=page_number,
        text=text,
        text_normalized=text.strip(),
        blocks=blocks or [],
        width=595.0,
        height=842.0,
        parser_name="pymupdf",
        parser_version="test",
        source_sha256="abc",
        image_coverage=image_coverage,
        image_count=image_count,
        image_coverage_error=image_coverage_error,
    )


def test_sufficient_native_text_skips_ocr() -> None:
    text = "x" * MIN_NATIVE_CHARS
    decision = OCRDecisionDetector().decide_page(
        _page(text=text, blocks=[TextBlock(text, None)])
    )
    assert decision.needs_ocr is False
    assert decision.reason == "sufficient_native_text"
    assert decision.policy_version == DEFAULT_OCR_POLICY.version
    assert decision.policy_min_native_chars == MIN_NATIVE_CHARS


def test_image_heavy_with_sufficient_text_skips_ocr() -> None:
    text = "x" * MIN_NATIVE_CHARS
    decision = OCRDecisionDetector().decide_page(
        _page(text=text, image_coverage=0.95, image_count=1)
    )
    assert decision.needs_ocr is False
    assert decision.reason == "sufficient_native_text"


def test_blank_page_skips_ocr() -> None:
    decision = OCRDecisionDetector().decide_page(_page(text="", image_coverage=0.0))
    assert decision.needs_ocr is False
    assert decision.reason == "blank_page"


def test_low_text_high_image_requires_ocr() -> None:
    decision = OCRDecisionDetector().decide_page(
        _page(text="hi", image_coverage=HIGH_IMAGE_COVERAGE, image_count=1)
    )
    assert decision.needs_ocr is True
    assert decision.reason == "low_text_high_image_coverage"


def test_image_only_page_requires_ocr() -> None:
    decision = OCRDecisionDetector().decide_page(
        _page(text="", image_coverage=0.10, image_count=1)
    )
    assert decision.needs_ocr is True
    assert decision.reason == "image_only_page"


def test_insufficient_native_text_requires_ocr() -> None:
    decision = OCRDecisionDetector().decide_page(_page(text="short", image_coverage=0.0))
    assert decision.needs_ocr is True
    assert decision.reason == "insufficient_native_text"


def test_unavailable_image_coverage_is_not_treated_as_blank() -> None:
    decision = OCRDecisionDetector().decide_page(
        _page(
            text="",
            image_coverage=None,
            image_count=2,
            image_coverage_error="xref=7:no_rects",
        )
    )
    assert decision.needs_ocr is True
    assert decision.reason == "image_coverage_unavailable"
    assert decision.image_coverage is None
    assert decision.image_coverage_error == "xref=7:no_rects"


def test_incomplete_image_coverage_with_tiny_measured_area_requires_ocr() -> None:
    """Partial geometry failure must not look like blank_page."""
    decision = OCRDecisionDetector().decide_page(
        _page(
            text="",
            image_coverage=0.0001,
            image_count=2,
            image_coverage_error="xref=12:RuntimeError",
        )
    )
    assert decision.needs_ocr is True
    assert decision.reason == "image_coverage_incomplete"
    assert decision.image_coverage_error is not None


def test_partial_geometry_failure_through_image_coverage_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _make_two_image_pdf()
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        page = doc.load_page(0)
        images = page.get_images(full=True)
        assert len(images) >= 2
        failing_xref = int(images[0][0])
        ok_xref = int(images[1][0])

        def flaky_rects(xref: int, *args: object, **kwargs: object) -> list[fitz.Rect]:
            if int(xref) == failing_xref:
                raise RuntimeError("geometry_boom")
            if int(xref) == ok_xref:
                return [fitz.Rect(0, 0, 1, 1)]  # tiny measurable area
            return []

        monkeypatch.setattr(page, "get_image_rects", flaky_rects)
        signal = _image_coverage(page)
    finally:
        doc.close()

    assert signal.coverage is not None
    assert signal.coverage < LOW_IMAGE_COVERAGE
    assert signal.error is not None
    assert "geometry_boom" in signal.error or "RuntimeError" in signal.error

    parsed_page = _page(
        text="",
        image_coverage=signal.coverage,
        image_count=signal.image_count,
        image_coverage_error=signal.error,
    )
    decision = OCRDecisionDetector().decide_page(parsed_page)
    assert decision.needs_ocr is True
    assert decision.reason == "image_coverage_incomplete"


def test_boundary_just_below_min_chars_requires_ocr() -> None:
    text = "x" * (MIN_NATIVE_CHARS - 1)
    decision = OCRDecisionDetector().decide_page(_page(text=text, image_coverage=0.0))
    assert len(text) == MIN_NATIVE_CHARS - 1
    assert decision.needs_ocr is True
    assert decision.reason == "insufficient_native_text"


def test_boundary_just_below_high_coverage_with_low_text() -> None:
    coverage = HIGH_IMAGE_COVERAGE - 1e-9
    decision = OCRDecisionDetector().decide_page(
        _page(text="hi", image_coverage=coverage, image_count=1)
    )
    assert decision.needs_ocr is True
    assert decision.reason == "insufficient_native_text"


def test_boundary_just_below_low_coverage_empty_is_blank() -> None:
    coverage = LOW_IMAGE_COVERAGE - 1e-9
    decision = OCRDecisionDetector().decide_page(
        _page(text="", image_coverage=coverage, image_count=0)
    )
    assert decision.needs_ocr is False
    assert decision.reason == "blank_page"


def test_mixed_document_only_scanned_page_flagged() -> None:
    rich = "y" * MIN_NATIVE_CHARS
    document = ParsedDocument(
        pages=[
            _page(page_number=1, text=rich, image_coverage=0.0),
            _page(page_number=2, text="", image_coverage=0.8, image_count=1),
        ],
        source_sha256="mix",
    )
    decision = OCRDecisionDetector().decide_document(document)
    assert decision.needs_ocr is True
    assert decision.reason == "pages_require_ocr"
    assert decision.pages[0].needs_ocr is False
    assert decision.pages[0].reason == "sufficient_native_text"
    assert decision.pages[1].needs_ocr is True
    assert decision.pages[1].reason == "low_text_high_image_coverage"
    assert decision.policy_version == DEFAULT_OCR_POLICY.version


def test_custom_policy_is_recorded_on_decision() -> None:
    policy = OCRThresholdPolicy(
        min_native_chars=10,
        high_image_coverage=0.5,
        low_image_coverage=0.1,
        version="ocr-policy-test",
    )
    decision = OCRDecisionDetector(policy).decide_page(_page(text="abcdefghij"))
    assert decision.needs_ocr is False
    assert decision.policy_version == "ocr-policy-test"
    assert decision.policy_min_native_chars == 10
    assert decision.policy_high_image_coverage == 0.5


def test_document_decision_aggregates_pages() -> None:
    rich = "y" * MIN_NATIVE_CHARS
    detector = OCRDecisionDetector()
    doc_rich = NativePDFParser().parse_bytes(_make_text_pdf(rich))
    decision = detector.decide_document(doc_rich)
    assert decision.needs_ocr is False
    assert decision.reason == "all_pages_native_or_blank"
    assert decision.pages[0].needs_ocr is False


def test_scanned_like_pdf_with_image_flags_ocr() -> None:
    data = _make_image_only_pdf()
    parsed = NativePDFParser().parse_bytes(data)
    assert parsed.pages[0].image_coverage is not None
    assert parsed.pages[0].image_coverage >= HIGH_IMAGE_COVERAGE
    decision = PDFParser().assess_ocr(parsed)
    assert decision.needs_ocr is True
    assert decision.pages[0].needs_ocr is True
    assert decision.pages[0].reason in {
        "low_text_high_image_coverage",
        "image_only_page",
    }


def test_detector_is_deterministic() -> None:
    page = _page(text="abc", image_coverage=0.4, image_count=1)
    detector = OCRDecisionDetector()
    assert detector.decide_page(page) == detector.decide_page(page)


def _make_text_pdf(text: str) -> bytes:
    doc = fitz.open()
    try:
        page = doc.new_page()
        page.insert_text((72, 72), text)
        return doc.tobytes()
    finally:
        doc.close()


def _make_image_only_pdf() -> bytes:
    """Full-page pixmap image, essentially no extractable text."""
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 200), 0)
    pix.set_rect(pix.irect, (180, 180, 180))
    doc = fitz.open()
    try:
        page = doc.new_page(width=200, height=200)
        page.insert_image(page.rect, pixmap=pix)
        return doc.tobytes()
    finally:
        doc.close()
        pix = None


def _make_two_image_pdf() -> bytes:
    """Page with two embedded images (for partial geometry-failure tests)."""
    pix_a = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), 0)
    pix_a.set_rect(pix_a.irect, (10, 10, 10))
    pix_b = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), 0)
    pix_b.set_rect(pix_b.irect, (200, 200, 200))
    doc = fitz.open()
    try:
        page = doc.new_page(width=400, height=400)
        page.insert_image(fitz.Rect(0, 0, 40, 40), pixmap=pix_a)
        page.insert_image(fitz.Rect(50, 50, 90, 90), pixmap=pix_b)
        return doc.tobytes()
    finally:
        doc.close()
        pix_a = None
        pix_b = None
