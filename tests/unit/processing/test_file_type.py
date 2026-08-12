"""Unit tests for DOC-02 file type detector."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from src.domain.enums import DetectedFileType
from src.processing.file_type import FileTypeDetector

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "disclosures"


def _ooxml_bytes(*member_names: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        for name in member_names:
            archive.writestr(name, b"dummy")
    return buf.getvalue()


def test_detect_pdf_by_magic_ignores_wrong_extension() -> None:
    data = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"
    result = FileTypeDetector().detect(data, filename="report.xlsx")
    assert result.file_type is DetectedFileType.PDF
    assert result.mime_type == "application/pdf"


def test_detect_xlsx_by_zip_structure() -> None:
    data = _ooxml_bytes("xl/workbook.xml", "xl/worksheets/sheet1.xml")
    result = FileTypeDetector().detect(data, filename="notes.pdf")
    assert result.file_type is DetectedFileType.XLSX


def test_detect_docx_by_zip_structure() -> None:
    data = _ooxml_bytes("word/document.xml")
    result = FileTypeDetector().detect(data, filename="sheet.xls")
    assert result.file_type is DetectedFileType.DOCX


def test_html_masquerading_as_pdf_is_unknown() -> None:
    data = (FIXTURES / "fake.pdf").read_bytes()
    result = FileTypeDetector().detect(data, filename="fake.pdf")
    assert result.file_type is DetectedFileType.UNKNOWN
    assert result.mime_type == "text/html"


def test_random_bytes_unknown() -> None:
    result = FileTypeDetector().detect(b"not-a-real-office-file", filename="a.docx")
    assert result.file_type is DetectedFileType.UNKNOWN


def test_empty_bytes_unknown() -> None:
    result = FileTypeDetector().detect(b"")
    assert result.file_type is DetectedFileType.UNKNOWN
    assert result.mime_type is None
