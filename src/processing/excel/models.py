"""Parsed Excel workbook models (in-memory; coordinate-preserving)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID


class ExcelCellValueKind(StrEnum):
    """How to interpret ExcelCell.value / formula fields."""

    EMPTY = "empty"
    SCALAR = "scalar"
    # Formula text was preserved; calculated result was NOT evaluated by this parser.
    FORMULA = "formula"


class ExcelSheetVisibility(StrEnum):
    """Worksheet visibility as stored in the workbook."""

    VISIBLE = "visible"
    HIDDEN = "hidden"
    VERY_HIDDEN = "veryHidden"


@dataclass(frozen=True, slots=True)
class ExcelCell:
    """One spreadsheet cell with original coordinates."""

    sheet_name: str
    row: int
    column: int
    address: str
    value_kind: ExcelCellValueKind
    # Raw openpyxl value for scalars; for formulas this is the formula string
    # (same as formula_text). Never an evaluated numeric result from this parser.
    value: Any
    # Stable text form for evidence / downstream without losing address.
    value_text: str | None
    number_format: str
    # Explicit formula string when value_kind == FORMULA (e.g. "=SUM(A1:A2)").
    formula_text: str | None = None
    # Cached calculated value if the file embeds one AND a future data_only pass
    # reads it. Always None while this parser uses data_only=False.
    cached_value: Any = None
    is_merged: bool = False
    merge_range: str | None = None


@dataclass(frozen=True, slots=True)
class ExcelSheet:
    name: str
    index: int
    cells: tuple[ExcelCell, ...]
    visibility: ExcelSheetVisibility = ExcelSheetVisibility.VISIBLE
    merged_ranges: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ParsedWorkbook:
    sheets: tuple[ExcelSheet, ...]
    source_sha256: str
    parser_name: str = "openpyxl"
    parser_version: str = ""
    source_label: str | None = None
    artifact_id: UUID | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def sheet_names(self) -> tuple[str, ...]:
        return tuple(sheet.name for sheet in self.sheets)
