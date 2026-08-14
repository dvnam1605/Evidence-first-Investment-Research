"""Golden reconstruction from vetted FPT Q2 2026 raw-table fixtures."""

from __future__ import annotations

import json
from pathlib import Path

from src.processing.sections.models import StatementSection
from src.processing.tables import FinancialTableReconstructor, ReconstructionContext
from src.processing.tables.raw_source import JsonRawTableSource, load_raw_table_fixture

FPT_RAW = Path(__file__).resolve().parents[2] / "fixtures" / "processing" / "tables" / "fpt_raw"
FIXTURES = (
    "q2_2026_consol_bs_p3.json",
    "q2_2026_consol_is_p7.json",
    "q2_2026_consol_cf_p10.json",
)


def _context(payload: dict) -> ReconstructionContext:
    raw = payload.get("context") or {}
    hint = raw.get("section_hint")
    section = StatementSection(hint) if hint else None
    return ReconstructionContext(
        surrounding_text=raw.get("surrounding_text"),
        section_hint=section,
    )


def _assert_fixture(name: str) -> None:
    path = FPT_RAW / name
    assert path.is_file(), f"missing vetted fixture {path}"
    table, payload = load_raw_table_fixture(path)
    expected = payload["expected"]
    source = payload["source"]
    result = FinancialTableReconstructor().reconstruct(table, context=_context(payload))

    assert result.raw is table
    assert result.raw.page == source["pdf_page"]
    assert result.raw.artifact_id is not None
    assert result.raw.source_sha256 == source["sha256"]
    assert result.status.value == expected["status"]
    assert list(result.warnings) == expected["warnings"]
    assert result.table_type.value == expected["table_type"]
    assert result.unit_text == expected["unit_text"]
    assert list(result.header_band_row_indices) == expected["header_band_row_indices"]
    assert result.label_column_index == expected["label_column_index"]
    assert [col.header_text for col in result.columns] == expected["column_headers"]
    assert [col.role.value for col in result.columns] == expected["column_roles"]

    body = [row for row in result.rows if row.kind.value != "empty"]
    assert len(body) == len(expected["data"])
    for got, want in zip(body, expected["data"], strict=True):
        assert got.label == want["label"]
        assert list(got.values) == want["values"]
        assert got.kind.value == want["kind"]
        if "indent_spaces" in want:
            assert got.indent_spaces == want["indent_spaces"]
        assert got.cells_by_column[got.label_column_index or 0] == want["label"]
        for cell in got.cells:
            assert cell.page == source["pdf_page"]
            assert cell.table_id == table.table_id
            assert cell.bbox is not None
            assert cell.bbox.x1 > cell.bbox.x0
            if "bbox_estimated_from_visual_layout" in table.warnings:
                assert cell.bbox_estimated is True

    payload_dict = result.to_intermediate_dict()
    assert payload_dict["provenance"]["page"] == source["pdf_page"]
    assert payload_dict["provenance"]["table_id"] == table.table_id
    assert payload_dict["raw"]["cells"][0]["bbox"] is not None


def test_fpt_q2_consol_balance_sheet_raw_reconstruction() -> None:
    _assert_fixture("q2_2026_consol_bs_p3.json")


def test_fpt_q2_consol_income_statement_raw_reconstruction() -> None:
    _assert_fixture("q2_2026_consol_is_p7.json")


def test_fpt_q2_consol_cash_flow_raw_reconstruction() -> None:
    _assert_fixture("q2_2026_consol_cf_p10.json")


def test_json_raw_table_source_loads_all_statement_fixtures() -> None:
    paths = tuple(FPT_RAW / name for name in FIXTURES)
    result = JsonRawTableSource(paths).load()
    assert len(result.tables) == 3
    assert [t.page for t in result.tables] == [3, 7, 10]
    assert result.context.source_sha256 is not None


def test_compact_vetted_matrix_expands_cell_provenance(tmp_path: Path) -> None:
    path = tmp_path / "compact.json"
    path.write_text(
        json.dumps(
            {
                "table": {
                    "table_id": "fixture:p1:t0",
                    "page": 1,
                    "bbox": [10, 20, 210, 120],
                    "matrix": [["Header", "2026"], ["Revenue", "1,000"]],
                }
            }
        ),
        encoding="utf-8",
    )

    table, _ = load_raw_table_fixture(path)

    cell = table.rows[1].cells[1]
    assert cell.raw_text == "1,000"
    assert cell.row == 1 and cell.column == 1 and cell.page == 1
    assert cell.bbox is not None
    assert cell.bbox.as_list() == [110.0, 70.0, 210.0, 120.0]
    assert cell.bbox_estimated is True
