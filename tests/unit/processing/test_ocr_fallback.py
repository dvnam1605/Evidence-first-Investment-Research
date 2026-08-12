"""DOC-05: OCR fallback runs only when needs_ocr; never overwrites native text."""

from __future__ import annotations

from dataclasses import dataclass, field

import fitz
import pytest
from src.processing.errors import OCRFailure
from src.processing.ocr.fallback import OCRFallback
from src.processing.ocr.models import OCRPageResult, OCRResultStatus, OCRTextLine, PageImage
from src.processing.ocr.paddle import normalize_paddle_output
from src.processing.ocr.quality import OCRQualityPolicy, assess_ocr_quality
from src.processing.ocr.render import render_pdf_page
from src.processing.pdf.detector import OCRDecisionDetector
from src.processing.pdf.native import NativePDFParser
from src.processing.pdf.service import PDFParser


@dataclass
class FakeOCREngine:
    """Records recognize calls; returns canned text per page number."""

    texts: dict[int, str] = field(default_factory=dict)
    calls: list[int] = field(default_factory=list)
    confidence: float | None = 0.91
    lines_by_page: dict[int, tuple[OCRTextLine, ...]] = field(default_factory=dict)

    async def recognize(self, image: PageImage) -> OCRPageResult:
        self.calls.append(image.page_number)
        if image.page_number in self.lines_by_page:
            lines = self.lines_by_page[image.page_number]
            text = "\n".join(line.text for line in lines if line.text).strip()
            confidences = [line.confidence for line in lines if line.confidence is not None]
            confidence = (
                sum(confidences) / len(confidences) if confidences else self.confidence
            )
        else:
            text = self.texts.get(image.page_number, f"ocr-page-{image.page_number}")
            confidence = self.confidence
            lines = (
                (OCRTextLine(text=text, confidence=confidence, bbox=(0, 0, 10, 10)),)
                if text
                else ()
            )
        return OCRPageResult(
            page_number=image.page_number,
            engine="fake-ocr",
            engine_version="test",
            text=text,
            confidence=confidence,
            lines=lines,
            raw=tuple(
                {
                    "text": line.text,
                    "confidence": line.confidence,
                    "bbox": list(line.bbox) if line.bbox is not None else None,
                }
                for line in lines
            ),
            decision_reason="",
        )


@dataclass
class ExplodingOCREngine:
    async def recognize(self, image: PageImage) -> OCRPageResult:
        raise OCRFailure(f"boom on page {image.page_number}")


def _make_text_pdf(text: str, *, width: float = 400, height: float = 400) -> bytes:
    doc = fitz.open()
    try:
        page = doc.new_page(width=width, height=height)
        page.insert_text((40, 60), text, fontsize=12)
        return doc.tobytes()
    finally:
        doc.close()


def _make_image_only_pdf() -> bytes:
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


def _make_mixed_pdf() -> bytes:
    """Page 1: rich native text; page 2: image-only."""
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 200), 0)
    pix.set_rect(pix.irect, (120, 120, 120))
    doc = fitz.open()
    try:
        p1 = doc.new_page(width=400, height=400)
        p1.insert_text(
            (40, 60),
            "Báo cáo tài chính quý với đủ ký tự native để vượt ngưỡng OCR.",
            fontsize=12,
        )
        p2 = doc.new_page(width=200, height=200)
        p2.insert_image(p2.rect, pixmap=pix)
        return doc.tobytes()
    finally:
        doc.close()
        pix = None


@pytest.mark.asyncio
async def test_ocr_only_runs_on_pages_needing_ocr() -> None:
    pdf_bytes = _make_mixed_pdf()
    parsed = NativePDFParser().parse_bytes(pdf_bytes)
    engine = FakeOCREngine(texts={2: "scanned content"})
    fallback = OCRFallback(engine)

    result = await fallback.run(parsed, pdf_bytes)

    assert engine.calls == [2]
    assert [p.page_number for p in result.pages] == [2]
    assert result.skipped_page_numbers == (1,)
    assert result.pages[0].text == "scanned content"
    assert result.pages[0].engine == "fake-ocr"
    assert result.pages[0].confidence == pytest.approx(0.91)
    assert result.pages[0].raw[0]["text"] == "scanned content"
    assert result.pages[0].decision_reason  # detector reason attached
    assert result.pages[0].status == OCRResultStatus.OK
    assert result.pages[0].quality_reason == "sufficient_confidence"
    assert result.needs_review is False


@pytest.mark.asyncio
async def test_native_text_unchanged_after_ocr_fallback() -> None:
    pdf_bytes = _make_image_only_pdf()
    parsed = NativePDFParser().parse_bytes(pdf_bytes)
    native_before = [page.text for page in parsed.pages]
    engine = FakeOCREngine(texts={1: "ocr replacement attempt"})

    await OCRFallback(engine).run(parsed, pdf_bytes)

    assert [page.text for page in parsed.pages] == native_before
    # Sidecar OCR text is separate from native page text.
    assert native_before[0] != "ocr replacement attempt"


@pytest.mark.asyncio
async def test_sufficient_native_skips_ocr_entirely() -> None:
    text = "Doanh thu thuần hợp nhất đạt mức cao trong kỳ báo cáo tài chính."
    pdf_bytes = _make_text_pdf(text)
    parsed = NativePDFParser().parse_bytes(pdf_bytes)
    engine = FakeOCREngine()

    result = await OCRFallback(engine).run(parsed, pdf_bytes)

    assert engine.calls == []
    assert result.pages == ()
    assert result.skipped_page_numbers == (1,)
    assert result.needs_review is False


@pytest.mark.asyncio
async def test_pdf_parser_apply_ocr_requires_engine() -> None:
    parser = PDFParser()
    pdf_bytes = _make_image_only_pdf()
    parsed = await parser.parse_bytes(pdf_bytes)
    with pytest.raises(OCRFailure, match="not configured"):
        await parser.apply_ocr(parsed, pdf_bytes)


@pytest.mark.asyncio
async def test_pdf_parser_apply_ocr_with_injected_engine() -> None:
    engine = FakeOCREngine(texts={1: "via parser"})
    parser = PDFParser(ocr_engine=engine)
    pdf_bytes = _make_image_only_pdf()
    parsed = await parser.parse_bytes(pdf_bytes)
    decision = parser.assess_ocr(parsed)
    assert decision.needs_ocr is True

    result = await parser.apply_ocr(parsed, pdf_bytes, decision=decision)

    assert engine.calls == [1]
    assert result.pages[0].text == "via parser"
    assert result.pages[0].status == OCRResultStatus.OK


@pytest.mark.asyncio
async def test_ocr_engine_failure_surfaces_as_ocr_failure() -> None:
    pdf_bytes = _make_image_only_pdf()
    parsed = NativePDFParser().parse_bytes(pdf_bytes)
    with pytest.raises(OCRFailure, match="boom"):
        await OCRFallback(ExplodingOCREngine()).run(parsed, pdf_bytes)


@pytest.mark.asyncio
async def test_empty_ocr_text_is_needs_review() -> None:
    pdf_bytes = _make_image_only_pdf()
    parsed = NativePDFParser().parse_bytes(pdf_bytes)
    engine = FakeOCREngine(texts={1: ""}, confidence=0.99)

    result = await OCRFallback(engine).run(parsed, pdf_bytes)

    page = result.pages[0]
    assert page.text == ""
    assert page.status == OCRResultStatus.NEEDS_REVIEW
    assert page.quality_reason == "no_text_detected"
    assert result.needs_review is True


@pytest.mark.asyncio
async def test_missing_confidence_is_needs_review() -> None:
    pdf_bytes = _make_image_only_pdf()
    parsed = NativePDFParser().parse_bytes(pdf_bytes)
    engine = FakeOCREngine(texts={1: "ambiguous text"}, confidence=None)

    result = await OCRFallback(engine).run(parsed, pdf_bytes)

    page = result.pages[0]
    assert page.status == OCRResultStatus.NEEDS_REVIEW
    assert page.quality_reason == "missing_confidence"
    assert result.needs_review is True


@pytest.mark.asyncio
async def test_low_confidence_is_needs_review() -> None:
    pdf_bytes = _make_image_only_pdf()
    parsed = NativePDFParser().parse_bytes(pdf_bytes)
    policy = OCRQualityPolicy(min_confidence=0.60)
    engine = FakeOCREngine(texts={1: "blurry guess"}, confidence=0.01)

    result = await OCRFallback(engine, quality_policy=policy).run(parsed, pdf_bytes)

    page = result.pages[0]
    assert page.confidence == pytest.approx(0.01)
    assert page.status == OCRResultStatus.NEEDS_REVIEW
    assert page.quality_reason == "low_confidence"
    assert page.quality_policy_min_confidence == pytest.approx(0.60)
    assert result.needs_review is True


@pytest.mark.asyncio
async def test_rasterization_failure_surfaces_as_ocr_failure() -> None:
    pdf_bytes = _make_image_only_pdf()
    parsed = NativePDFParser().parse_bytes(pdf_bytes)
    with pytest.raises(OCRFailure, match="rasterize|open PDF"):
        await OCRFallback(FakeOCREngine()).run(parsed, b"%PDF-1.4 not-a-real-pdf")


def test_render_invalid_page_raises_ocr_failure() -> None:
    pdf_bytes = _make_image_only_pdf()
    with pytest.raises(OCRFailure, match="out of range"):
        render_pdf_page(pdf_bytes, page_number=99)


@pytest.mark.asyncio
async def test_vietnamese_ocr_lines_preserve_diacritics() -> None:
    pdf_bytes = _make_image_only_pdf()
    parsed = NativePDFParser().parse_bytes(pdf_bytes)
    vietnamese = "Doanh thu thuần hợp nhất quý I"
    engine = FakeOCREngine(
        lines_by_page={
            1: (
                OCRTextLine(text=vietnamese, confidence=0.93, bbox=(1, 2, 3, 4)),
                OCRTextLine(text="Năm 2025", confidence=0.88, bbox=(5, 6, 7, 8)),
            )
        }
    )

    result = await OCRFallback(engine).run(parsed, pdf_bytes)

    page = result.pages[0]
    assert page.status == OCRResultStatus.OK
    assert page.lines[0].text == vietnamese
    assert "thuần" in page.text
    assert "hợp nhất" in page.text
    assert page.raw[0]["text"] == vietnamese


def test_assess_ocr_quality_reasons() -> None:
    base = OCRPageResult(
        page_number=1,
        engine="fake",
        engine_version="t",
        text="x",
        confidence=0.01,
        lines=(),
        raw=(),
        decision_reason="image_only_page",
    )
    low = assess_ocr_quality(base, OCRQualityPolicy(min_confidence=0.5))
    assert low.status == OCRResultStatus.NEEDS_REVIEW
    assert low.quality_reason == "low_confidence"

    ok = assess_ocr_quality(
        OCRPageResult(
            page_number=1,
            engine="fake",
            engine_version="t",
            text="good",
            confidence=0.9,
            lines=(),
            raw=(),
            decision_reason="image_only_page",
        )
    )
    assert ok.status == OCRResultStatus.OK
    assert ok.quality_reason == "sufficient_confidence"


@pytest.mark.parametrize(
    "confidence",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        -0.01,
        1.01,
    ],
)
def test_invalid_confidence_is_needs_review(confidence: float) -> None:
    result = assess_ocr_quality(
        OCRPageResult(
            page_number=1,
            engine="fake",
            engine_version="t",
            text="looks fine",
            confidence=confidence,
            lines=(),
            raw=(),
            decision_reason="image_only_page",
        )
    )
    assert result.status == OCRResultStatus.NEEDS_REVIEW
    assert result.quality_reason == "invalid_confidence"


@pytest.mark.asyncio
async def test_nan_confidence_through_fallback_is_needs_review() -> None:
    pdf_bytes = _make_image_only_pdf()
    parsed = NativePDFParser().parse_bytes(pdf_bytes)
    engine = FakeOCREngine(texts={1: "nan trap"}, confidence=float("nan"))

    result = await OCRFallback(engine).run(parsed, pdf_bytes)

    page = result.pages[0]
    assert page.status == OCRResultStatus.NEEDS_REVIEW
    assert page.quality_reason == "invalid_confidence"
    assert result.needs_review is True


def test_normalize_paddle_classic_and_predict_shapes() -> None:
    classic = [
        [
            [[0, 0], [10, 0], [10, 10], [0, 10]],
            ("Hello", 0.95),
        ],
        [
            [[0, 20], [20, 20], [20, 30], [0, 30]],
            ("World", 0.85),
        ],
    ]
    classic_lines = normalize_paddle_output([classic])
    assert [line.text for line in classic_lines] == ["Hello", "World"]
    assert classic_lines[0].confidence == pytest.approx(0.95)

    predict_item = {
        "rec_texts": ["A", "B"],
        "rec_scores": [0.7, 0.8],
        "dt_polys": [
            [[0, 0], [1, 0], [1, 1], [0, 1]],
            [[2, 2], [3, 2], [3, 3], [2, 3]],
        ],
    }
    predict_lines = normalize_paddle_output([predict_item])
    assert [line.text for line in predict_lines] == ["A", "B"]
    assert predict_lines[1].confidence == pytest.approx(0.8)

    vietnamese_item = {
        "rec_texts": ["Doanh thu thuần"],
        "rec_scores": [0.97],
        "dt_polys": [[[0, 0], [1, 0], [1, 1], [0, 1]]],
    }
    vi_lines = normalize_paddle_output([vietnamese_item])
    assert vi_lines[0].text == "Doanh thu thuần"


def test_detector_still_drives_blank_vs_image_only() -> None:
    """Fallback relies on detector; blank pages must not call OCR."""
    doc = fitz.open()
    try:
        doc.new_page(width=200, height=200)
        pdf_bytes = doc.tobytes()
    finally:
        doc.close()
    parsed = NativePDFParser().parse_bytes(pdf_bytes)
    decision = OCRDecisionDetector().decide_page(parsed.pages[0])
    assert decision.needs_ocr is False
    assert decision.reason == "blank_page"
