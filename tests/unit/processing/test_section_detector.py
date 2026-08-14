"""Unit tests for DOC-10 financial statement section detector."""

from __future__ import annotations

from src.processing.excel.models import ExcelSheet, ParsedWorkbook
from src.processing.pdf.models import ParsedDocument, ParsedPage
from src.processing.sections import (
    StatementSection,
    StatementSectionDetector,
)


def _page(page_number: int, text: str) -> ParsedPage:
    return ParsedPage(
        page_number=page_number,
        text=text,
        text_normalized=text.strip(),
        blocks=[],
        width=595.0,
        height=842.0,
        parser_name="test",
        parser_version="0",
        source_sha256="abc",
    )


def test_vietnamese_balance_sheet_heading() -> None:
    hits = StatementSectionDetector().detect_text(
        "CÔNG TY CỔ PHẦN FPT\nBảng cân đối kế toán\nTại ngày 31 tháng 03 năm 2026\n"
    )
    assert len(hits) == 1
    assert hits[0].section == StatementSection.BALANCE_SHEET
    assert hits[0].matched_rule == "vi_balance_sheet"
    assert "cân đối" in hits[0].matched_text.lower() or "Cân đối" in hits[0].matched_text


def test_vietnamese_income_and_cash_flow() -> None:
    text = (
        "Báo cáo kết quả hoạt động kinh doanh\n"
        "...\n"
        "Báo cáo lưu chuyển tiền tệ\n"
        "Theo phương pháp gián tiếp\n"
    )
    result = StatementSectionDetector().detect_page_texts([(2, text)])
    assert StatementSection.INCOME_STATEMENT in result.sections_found
    assert StatementSection.CASH_FLOW_STATEMENT in result.sections_found
    assert result.first_page(StatementSection.INCOME_STATEMENT) == 2


def test_notes_preferred_over_loose_matches() -> None:
    hits = StatementSectionDetector().detect_text(
        "Thuyết minh Báo cáo tài chính hợp nhất\nQuý I năm 2026\n"
    )
    assert hits[0].section == StatementSection.NOTES
    assert hits[0].matched_rule.startswith("vi_")


def test_notes_column_inside_balance_sheet_header_is_not_a_section_heading() -> None:
    hits = StatementSectionDetector().detect_text(
        "Mã số TÀI SẢN Thuyết minh 2025 VND 2024 VND\n"
    )

    assert hits == []


def test_short_notes_heading_remains_supported() -> None:
    hits = StatementSectionDetector().detect_text("Thuyết minh\n")

    assert len(hits) == 1
    assert hits[0].section is StatementSection.NOTES


def test_english_fallback_headings() -> None:
    hits = StatementSectionDetector().detect_text(
        "Consolidated statement of financial position\nAs at 31 December 2025\n"
    )
    assert hits[0].section == StatementSection.BALANCE_SHEET
    assert hits[0].matched_rule == "en_balance_sheet"


def test_detect_parsed_document_pages() -> None:
    doc = ParsedDocument(
        pages=[
            _page(1, "Mục lục\n"),
            _page(5, "Bảng cân đối kế toán\nTài sản\n"),
            _page(12, "Báo cáo lưu chuyển tiền tệ\n"),
            _page(40, "Thuyết minh báo cáo tài chính\n"),
        ],
        source_sha256="abc",
    )
    result = StatementSectionDetector().detect_parsed_document(doc)
    assert result.sections_found == (
        StatementSection.BALANCE_SHEET,
        StatementSection.CASH_FLOW_STATEMENT,
        StatementSection.NOTES,
    )
    assert result.first_page(StatementSection.BALANCE_SHEET) == 5
    assert result.first_page(StatementSection.NOTES) == 40


def test_detect_workbook_sheet_names() -> None:
    workbook = ParsedWorkbook(
        sheets=(
            ExcelSheet(name="Bảng cân đối kế toán", index=0, cells=()),
            ExcelSheet(name="Báo cáo kết quả hoạt động kinh doanh", index=1, cells=()),
            ExcelSheet(name="Báo cáo lưu chuyển tiền tệ", index=2, cells=()),
            ExcelSheet(name="Thuyết minh", index=3, cells=()),
        ),
        source_sha256="abc",
    )
    result = StatementSectionDetector().detect_workbook(workbook)
    assert set(result.sections_found) == {
        StatementSection.BALANCE_SHEET,
        StatementSection.INCOME_STATEMENT,
        StatementSection.CASH_FLOW_STATEMENT,
        StatementSection.NOTES,
    }


def test_long_paragraph_not_treated_as_heading() -> None:
    long = "Bảng cân đối kế toán " + ("chi tiết " * 40)
    hits = StatementSectionDetector().detect_text(long)
    assert hits == []
