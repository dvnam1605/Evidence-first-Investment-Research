"""Unit tests for DOC-03 native PDF parser."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from uuid import uuid4

import fitz
import pytest
from src.processing.errors import PDFParseError
from src.processing.pdf.native import NativePDFParser
from src.processing.pdf.service import PDFParser

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "processing"
VIETNAMESE_PDF = FIXTURES / "vietnamese_sample.pdf"
VIETNAMESE_EXPECTED = (
    FIXTURES / "vietnamese_sample.expected.txt"
).read_text(encoding="utf-8")
VIETNAMESE_PHRASE = "Doanh thu tăng nhưng CFO giảm."


def _make_pdf_bytes(
    *,
    pages: list[str | None],
    width: float = 595,
    height: float = 842,
) -> bytes:
    """Build a PDF. Use `None` for a blank page (no text drawn)."""
    doc = fitz.open()
    try:
        for text in pages:
            page = doc.new_page(width=width, height=height)
            if text is not None:
                page.insert_text((72, 72), text)
        return doc.tobytes()
    finally:
        doc.close()


def _make_zero_page_pdf_bytes() -> bytes:
    # PyMuPDF refuses to save zero-page docs; handcraft a minimal valid Catalog.
    return b"""%PDF-1.4
1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj
2 0 obj<< /Type /Pages /Kids [] /Count 0 >>endobj
xref
0 3
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
trailer<< /Size 3 /Root 1 0 R >>
startxref
110
%%EOF
"""


def _make_encrypted_pdf_bytes() -> bytes:
    doc = fitz.open()
    try:
        page = doc.new_page()
        page.insert_text((72, 72), "secret")
        buf = io.BytesIO()
        doc.save(
            buf,
            encryption=fitz.PDF_ENCRYPT_AES_256,
            user_pw="user-secret",
            owner_pw="owner-secret",
        )
        return buf.getvalue()
    finally:
        doc.close()


def test_native_parse_bytes_extracts_text_blocks_and_dimensions() -> None:
    data = _make_pdf_bytes(pages=["FPT Q2 revenue note", "Second page cash flow"])
    artifact_id = uuid4()
    parsed = NativePDFParser().parse_bytes(data, artifact_id=artifact_id)

    assert parsed.parser_name == "pymupdf"
    assert parsed.parser_version
    assert parsed.source_sha256 == hashlib.sha256(data).hexdigest()
    assert parsed.artifact_id == artifact_id
    assert parsed.source_label == "bytes"
    assert len(parsed.pages) == 2

    p1 = parsed.pages[0]
    assert p1.page_number == 1
    assert "FPT Q2 revenue note" in p1.text
    assert p1.text_normalized == p1.text.strip()
    assert p1.width == pytest.approx(595, abs=0.1)
    assert p1.height == pytest.approx(842, abs=0.1)
    assert p1.parser_name == parsed.parser_name
    assert p1.parser_version == parsed.parser_version
    assert p1.source_sha256 == parsed.source_sha256
    assert p1.blocks
    assert any("FPT Q2 revenue note" in b.text for b in p1.blocks)
    assert p1.blocks[0].bbox is not None

    assert parsed.pages[1].page_number == 2
    assert "Second page cash flow" in parsed.pages[1].text


def test_blank_page_retained_in_order_with_dimensions() -> None:
    data = _make_pdf_bytes(pages=["Page one", None, "Page three"])
    parsed = NativePDFParser().parse_bytes(data)
    assert [p.page_number for p in parsed.pages] == [1, 2, 3]
    assert "Page one" in parsed.pages[0].text
    assert parsed.pages[1].text_normalized == ""
    assert parsed.pages[1].blocks == []
    assert parsed.pages[1].width == pytest.approx(595, abs=0.1)
    assert parsed.pages[1].height == pytest.approx(842, abs=0.1)
    assert "Page three" in parsed.pages[2].text


def test_zero_page_pdf_rejected() -> None:
    data = _make_zero_page_pdf_bytes()
    with pytest.raises(PDFParseError, match="zero pages"):
        NativePDFParser().parse_bytes(data)


def test_corrupt_pdf_rejected() -> None:
    with pytest.raises(PDFParseError):
        NativePDFParser().parse_bytes(b"%PDF-1.4\nthis is not a valid pdf structure")


def test_encrypted_pdf_rejected() -> None:
    data = _make_encrypted_pdf_bytes()
    with pytest.raises(PDFParseError, match="encrypted"):
        NativePDFParser().parse_bytes(data)


def test_vietnamese_unicode_preserved() -> None:
    """Stable fixture PDF; assert full diacritic phrase (no skip / ASCII fallback)."""
    assert VIETNAMESE_PDF.is_file(), f"missing fixture: {VIETNAMESE_PDF}"
    assert VIETNAMESE_PHRASE in VIETNAMESE_EXPECTED.replace("\xa0", " ")

    data = VIETNAMESE_PDF.read_bytes()
    parsed = NativePDFParser().parse_bytes(data)

    assert parsed.pages[0].text == VIETNAMESE_EXPECTED
    assert VIETNAMESE_PHRASE in parsed.pages[0].text.replace("\xa0", " ")
    assert "tăng" in parsed.pages[0].text
    assert "nhưng" in parsed.pages[0].text
    assert "giảm" in parsed.pages[0].text


def test_raw_text_not_stripped() -> None:
    # insert_text may not preserve leading spaces in layout, but we assert we do not
    # call .strip() on page.get_text("text") — trailing newline from extractor kept.
    data = _make_pdf_bytes(pages=["KeepTrailing"])
    parsed = NativePDFParser().parse_bytes(data)
    raw = parsed.pages[0].text
    assert raw == raw  # identity
    assert parsed.pages[0].text_normalized == raw.strip()
    # If extractor includes trailing newline, raw must keep it.
    with fitz.open(stream=data, filetype="pdf") as doc:
        expected = doc.load_page(0).get_text("text")
    assert raw == expected


def test_rerun_parse_is_stateless_and_equal() -> None:
    data = _make_pdf_bytes(pages=["Idempotent parse"])
    parser = NativePDFParser()
    first = parser.parse_bytes(data, source_label="run-a")
    second = parser.parse_bytes(data, source_label="run-a")
    assert first == second
    assert first.source_sha256 == second.source_sha256
    assert [p.text for p in first.pages] == [p.text for p in second.pages]


@pytest.mark.asyncio
async def test_pdf_parser_async_parse_path(tmp_path: Path) -> None:
    data = _make_pdf_bytes(pages=["Async path parse"])
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(data)
    artifact_id = uuid4()

    parsed = await PDFParser().parse(pdf_path, artifact_id=artifact_id)
    assert len(parsed.pages) == 1
    assert "Async path parse" in parsed.pages[0].text
    assert parsed.artifact_id == artifact_id
    assert parsed.source_label == str(pdf_path)
    assert parsed.pages[0].source_sha256 == parsed.source_sha256


def test_native_parse_missing_file_raises(tmp_path: Path) -> None:
    missing = tmp_path / "missing.pdf"
    with pytest.raises(FileNotFoundError):
        NativePDFParser().parse_path(missing)


def test_native_parse_empty_bytes_raises() -> None:
    with pytest.raises(PDFParseError, match="empty"):
        NativePDFParser().parse_bytes(b"")
