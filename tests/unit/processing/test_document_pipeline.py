"""Unit tests for DOC-13 document processing pipeline."""

from __future__ import annotations

from uuid import uuid4

import fitz
from openpyxl import Workbook
from src.domain.enums import BlockType, DetectedFileType, ProcessingStatus
from src.processing.pipeline import DocumentProcessor, DocumentProcessRequest


def _pdf_bytes(text: str) -> bytes:
    doc = fitz.open()
    try:
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), text)
        return doc.tobytes()
    finally:
        doc.close()


def _xlsx_bytes() -> bytes:
    from io import BytesIO

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Bang can doi ke toan"
    ws["A1"] = "Tai san"
    ws["B1"] = 100
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def test_pipeline_processes_digital_pdf_without_ocr_engine() -> None:
    data = _pdf_bytes("CONSOLIDATED INCOME STATEMENT\nNet revenue 1,000")
    processor = DocumentProcessor(ocr_engine=None)
    result = await processor.process(
        DocumentProcessRequest(
            artifact_id=uuid4(),
            data=data,
            filename="fpt_income.pdf",
            title="Bao cao tai chinh hop nhat",
            document_type="financial_statement",
        )
    )
    assert result.file_type is DetectedFileType.PDF
    assert result.status in {ProcessingStatus.PROCESSED, ProcessingStatus.NEEDS_REVIEW}
    assert len(result.pages) == 1
    assert result.pages[0].text
    assert result.classification is not None
    assert result.error is None
    assert all(block.block_type in {BlockType.TEXT, BlockType.TABLE} for block in result.blocks)


async def test_pipeline_marks_unsupported_bytes_failed() -> None:
    processor = DocumentProcessor(ocr_engine=None)
    result = await processor.process(
        DocumentProcessRequest(
            artifact_id=uuid4(),
            data=b"not-a-real-document",
            filename="notes.txt",
        )
    )
    assert result.status is ProcessingStatus.FAILED
    assert result.file_type is DetectedFileType.UNKNOWN
    assert "unsupported_file_type" in result.warnings


async def test_pipeline_processes_xlsx() -> None:
    processor = DocumentProcessor(ocr_engine=None)
    result = await processor.process(
        DocumentProcessRequest(
            artifact_id=uuid4(),
            data=_xlsx_bytes(),
            filename="fs.xlsx",
            title="BCTC",
            document_type="financial_statement",
        )
    )
    assert result.file_type is DetectedFileType.XLSX
    assert result.status in {ProcessingStatus.PROCESSED, ProcessingStatus.NEEDS_REVIEW}
    assert len(result.pages) >= 1
    assert result.table_extraction is not None
    assert len(result.reconstructed_tables) >= 1
    assert any(block.block_type is BlockType.TABLE for block in result.blocks)


async def test_pipeline_flags_ocr_required_without_engine() -> None:
    # Below min_native_chars → detector requests OCR.
    data = _pdf_bytes("hi")
    result = await DocumentProcessor(ocr_engine=None).process(
        DocumentProcessRequest(artifact_id=uuid4(), data=data, filename="scan.pdf")
    )
    assert result.file_type is DetectedFileType.PDF
    assert result.ocr_decision is not None
    assert result.ocr_decision.needs_ocr is True
    assert result.status is ProcessingStatus.NEEDS_REVIEW
    assert "ocr_required_but_engine_not_configured" in result.warnings
