"""Unit tests for DOC-12 financial table reconstruction."""

from __future__ import annotations

from src.processing.sections.models import StatementSection
from src.processing.tables import (
    ColumnRole,
    ExtractedCell,
    ExtractedRow,
    ExtractedTable,
    FinancialTableReconstructor,
    PassthroughTableReconstructor,
    ReconstructionContext,
    ReconstructStatus,
    RowKind,
    TableExtractionStatus,
    TableType,
)


def _cell(
    text: str,
    *,
    row: int,
    column: int,
    merged: bool = False,
) -> ExtractedCell:
    return ExtractedCell(
        raw_text=text,
        row=row,
        column=column,
        page=1,
        table_id="doc:p1:t0",
        is_merged_continuation=merged,
    )


def _table(grid: list[list[str | tuple[str, bool]]]) -> ExtractedTable:
    rows: list[ExtractedRow] = []
    for r, raw_row in enumerate(grid):
        cells: list[ExtractedCell] = []
        for c, item in enumerate(raw_row):
            if isinstance(item, tuple):
                text, merged = item
            else:
                text, merged = item, False
            cells.append(_cell(text, row=r, column=c, merged=merged))
        rows.append(ExtractedRow(row_index=r, cells=tuple(cells)))
    return ExtractedTable(
        page=1,
        rows=tuple(rows),
        table_id="doc:p1:t0",
        status=TableExtractionStatus.OK,
        confidence=0.75,
    )


def test_passthrough_still_never_discards_raw() -> None:
    table = _table([["a"]])
    snap = PassthroughTableReconstructor().reconstruct(table)
    assert snap.raw is table


def test_reconstruct_never_discards_raw_and_matches_example_shape() -> None:
    table = _table(
        [
            ["Báo cáo kết quả hoạt động kinh doanh", ("", True), ("", True)],
            ["Đơn vị: triệu đồng", ("", True), ("", True)],
            ["Chỉ tiêu", "Kỳ này", "Kỳ trước"],
            ["Doanh thu thuần", "(1,234.50)", "1.000,25"],
            ["Giá vốn hàng bán", "-50", "100"],
        ]
    )
    result = FinancialTableReconstructor().reconstruct(table)
    assert result.raw is table
    payload = result.to_intermediate_dict()
    assert payload["table_type"] == "income_statement"
    assert payload["unit_text"] == "Đơn vị: triệu đồng"
    assert payload["provenance"]["table_id"] == "doc:p1:t0"
    assert payload["provenance"]["page"] == 1
    assert payload["raw"]["table_id"] == "doc:p1:t0"
    assert payload["raw"]["cells"][0]["raw_text"] == "Báo cáo kết quả hoạt động kinh doanh"
    assert [col["header_text"] for col in payload["columns"]] == [
        "Chỉ tiêu",
        "Kỳ này",
        "Kỳ trước",
    ]
    assert payload["rows"][0]["label"] == "Doanh thu thuần"
    assert payload["rows"][0]["values"] == ["(1,234.50)", "1.000,25"]
    assert payload["rows"][1]["label"] == "Giá vốn hàng bán"
    assert payload["rows"][1]["values"] == ["-50", "100"]
    assert result.status is ReconstructStatus.OK
    assert result.type_confidence is not None
    assert result.type_confidence < 1.0


def test_day_month_year_headers_are_period_tokens_not_uncertain() -> None:
    table = _table(
        [
            ["Bảng cân đối kế toán", ("", True), ("", True)],
            ["Đơn vị: triệu đồng", ("", True), ("", True)],
            ["ASSETS", "30/06/2026", "31/12/2025"],
            ["A. CURRENT ASSETS", "100", "90"],
        ]
    )
    result = FinancialTableReconstructor().reconstruct(table)
    assert result.status is ReconstructStatus.OK
    assert "uncertain_header_row" not in result.warnings
    assert result.columns[1].header_text == "30/06/2026"
    assert result.columns[2].header_text == "31/12/2025"
    assert result.rows[0].label == "A. CURRENT ASSETS"
    assert result.rows[0].values == ("100", "90")


def test_unit_text_from_surrounding_not_normalized() -> None:
    table = _table(
        [
            ["Chỉ tiêu", "Năm nay", "Năm trước"],
            ["Lợi nhuận sau thuế", "25", "10"],
        ]
    )
    result = FinancialTableReconstructor().reconstruct(
        table,
        context=ReconstructionContext(
            surrounding_text="Bảng cân đối kế toán\nĐơn vị tính: tỷ đồng\n",
            section_hint=StatementSection.BALANCE_SHEET,
        ),
    )
    assert result.table_type is TableType.BALANCE_SHEET
    assert result.unit_text == "Đơn vị tính: tỷ đồng"
    assert result.rows[0].values == ("25", "10")


def test_merged_continuation_is_not_a_value_or_label() -> None:
    table = _table(
        [
            ["Chỉ tiêu", "Kỳ này"],
            ["Doanh thu thuần", "(50)"],
            [("", True), ""],
        ]
    )
    result = FinancialTableReconstructor().reconstruct(
        table,
        context=ReconstructionContext(surrounding_text="Đơn vị: VND\n"),
    )
    assert result.rows[0].label == "Doanh thu thuần"
    assert result.rows[0].values == ("(50)",)
    assert result.rows[1].kind is RowKind.EMPTY
    assert result.rows[1].is_continuation is False


def test_section_header_row_flagged() -> None:
    table = _table(
        [
            ["Bảng cân đối kế toán", ("", True)],
            ["Đơn vị: triệu đồng", ("", True)],
            ["Chỉ tiêu", "Số cuối kỳ"],
            ["TÀI SẢN", ""],
            ["Tiền và tương đương tiền", "100"],
        ]
    )
    result = FinancialTableReconstructor().reconstruct(table)
    assert result.table_type is TableType.BALANCE_SHEET
    assert result.rows[0].label == "TÀI SẢN"
    assert result.rows[0].is_section_header is True
    assert result.rows[1].label == "Tiền và tương đương tiền"
    assert result.rows[1].is_section_header is False


def test_unknown_type_and_missing_unit_needs_review() -> None:
    table = _table(
        [
            ["Item", "A", "B"],
            ["Foo", "1", "2"],
        ]
    )
    result = FinancialTableReconstructor().reconstruct(table)
    assert result.raw is table
    assert result.table_type is TableType.UNKNOWN
    assert result.unit_text is None
    assert result.status is ReconstructStatus.NEEDS_REVIEW
    assert "unknown_table_type" in result.warnings
    assert "missing_unit_text" in result.warnings


def test_conflicting_hint_needs_review() -> None:
    table = _table(
        [
            ["Báo cáo lưu chuyển tiền tệ", ("", True)],
            ["Đơn vị: triệu đồng", ("", True)],
            ["Chỉ tiêu", "Kỳ này"],
            ["Lưu chuyển từ HĐKD", "10"],
        ]
    )
    result = FinancialTableReconstructor().reconstruct(
        table,
        context=ReconstructionContext(section_hint=StatementSection.INCOME_STATEMENT),
    )
    assert result.table_type is TableType.CASH_FLOW_STATEMENT
    assert result.status is ReconstructStatus.NEEDS_REVIEW
    assert "conflicting_table_type" in result.warnings


def test_ambiguous_surrounding_sections_do_not_guess() -> None:
    table = _table(
        [
            ["Chỉ tiêu", "Kỳ này"],
            ["Doanh thu thuần", "1"],
        ]
    )
    result = FinancialTableReconstructor().reconstruct(
        table,
        context=ReconstructionContext(
            surrounding_text=(
                "Bảng cân đối kế toán\n"
                "Báo cáo kết quả hoạt động kinh doanh\n"
                "Đơn vị: triệu đồng\n"
            )
        ),
    )
    assert result.table_type is TableType.UNKNOWN
    assert result.unit_text == "Đơn vị: triệu đồng"
    assert "ambiguous_section_context" in result.warnings
    assert result.status is ReconstructStatus.NEEDS_REVIEW


def test_empty_raw_table_needs_review() -> None:
    table = ExtractedTable(
        page=1,
        rows=(),
        table_id="doc:p1:t0",
        status=TableExtractionStatus.NEEDS_REVIEW,
        warnings=("empty_grid",),
    )
    result = FinancialTableReconstructor().reconstruct(table)
    assert result.raw is table
    assert result.columns == ()
    assert result.rows == ()
    assert result.status is ReconstructStatus.NEEDS_REVIEW
    assert "empty_raw_table" in result.warnings


def test_multiline_vietnamese_label_preserved() -> None:
    table = _table(
        [
            ["Chỉ tiêu", "Giá trị"],
            ["Doanh thu thuần\ntừ hợp đồng\nvới khách hàng", "(1,234.50)"],
        ]
    )
    result = FinancialTableReconstructor().reconstruct(
        table,
        context=ReconstructionContext(
            surrounding_text="Báo cáo kết quả hoạt động kinh doanh\nĐơn vị: triệu đồng",
        ),
    )
    assert result.rows[0].label == "Doanh thu thuần\ntừ hợp đồng\nvới khách hàng"
    assert result.rows[0].values == ("(1,234.50)",)
    assert result.columns[1].header_text == "Giá trị"


def test_two_row_period_header_is_header_band_not_data() -> None:
    table = _table(
        [
            ["Báo cáo kết quả hoạt động kinh doanh", *([("", True)] * 6)],
            ["Đơn vị: triệu đồng", *([("", True)] * 6)],
            [
                "",
                "",
                "",
                "Current period",
                ("", True),
                "Previous period",
                ("", True),
            ],
            ["Code", "Items", "Notes", "2026", "2025", "2026", "2025"],
            ["", "Revenue", "01", "1000", "900", "800", "700"],
            ["", "Net profit", "60", "100", "90", "80", "70"],
        ]
    )
    result = FinancialTableReconstructor().reconstruct(table)
    assert result.header_band_row_indices == (2, 3)
    assert result.columns[1].header_text == "Items"
    assert result.columns[1].role is ColumnRole.LABEL
    assert result.columns[3].header_text == "Current period | 2026"
    assert result.columns[4].header_text == "Current period | 2025"
    assert result.columns[5].header_text == "Previous period | 2026"
    assert result.columns[3].header_parts == ("Current period", "2026")
    labels = [row.label for row in result.rows if row.kind is RowKind.DATA]
    assert labels == ["Revenue", "Net profit"]
    assert result.rows[0].label != "2026"
    assert result.rows[0].values == ("1000", "900", "800", "700")
    assert result.rows[1].values == ("100", "90", "80", "70")
    assert result.status is ReconstructStatus.OK
    payload = result.to_intermediate_dict()
    assert payload["rows"][0]["cells"][1]["raw_text"] == "Revenue"
    assert payload["rows"][0]["cells"][1]["column"] == 1


def test_index_code_columns_do_not_become_labels() -> None:
    table = _table(
        [
            ["No.", "Items", "Codes", "Current", "Comparative"],
            ["1", "Revenue", "01", "1000", "900"],
            ["2", "Net profit", "60", "100", "90"],
        ]
    )
    result = FinancialTableReconstructor().reconstruct(
        table,
        context=ReconstructionContext(
            surrounding_text="Income statement\nUnit: million VND\n",
        ),
    )
    assert result.label_column_index == 1
    assert result.columns[0].role is ColumnRole.INDEX
    assert result.columns[1].role is ColumnRole.LABEL
    assert result.columns[2].role is ColumnRole.CODE
    assert result.rows[0].label == "Revenue"
    assert result.rows[0].values == ("1000", "900")
    assert result.rows[0].cells_by_column == ("1", "Revenue", "01", "1000", "900")
    assert result.rows[0].label != "1"


def test_indented_label_separator_and_continuation_preserved() -> None:
    table = _table(
        [
            ["Chỉ tiêu", "Kỳ này"],
            ["TÀI SẢN", ""],
            ["  Services revenue", "10"],
            ["---", "---"],
            [("", True), "5"],
        ]
    )
    result = FinancialTableReconstructor().reconstruct(
        table,
        context=ReconstructionContext(
            surrounding_text="Bảng cân đối kế toán\nĐơn vị: triệu đồng\n",
        ),
    )
    assert result.rows[0].kind is RowKind.SECTION_HEADER
    assert result.rows[1].label == "  Services revenue"
    assert result.rows[1].indent_spaces == 2
    assert result.rows[2].kind is RowKind.SEPARATOR
    assert result.rows[3].kind is RowKind.CONTINUATION
    assert result.rows[3].is_continuation is True
    payload = result.to_intermediate_dict()
    assert payload["rows"][1]["label"] == "  Services revenue"
    assert payload["rows"][1]["indent_spaces"] == 2
