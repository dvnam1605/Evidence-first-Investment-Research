"""Financial table reconstruction (DOC-12). Never discards the raw ExtractedTable."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from src.processing.classify.patterns import fold_text
from src.processing.sections.headings import match_heading_line
from src.processing.sections.models import StatementSection
from src.processing.tables.models import ExtractedCell, ExtractedRow, ExtractedTable

_MAX_UNIT_CHARS = 120
_MAX_HEADER_BAND_ROWS = 4
_YEAR = re.compile(r"^(19|20)\d{2}$")
_DATE_DMY = re.compile(r"^\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}$")
_DATE_ISO = re.compile(r"^\d{4}[/.\-]\d{1,2}[/.\-]\d{1,2}$")
_DATE_TEXT = re.compile(
    r"(?i)^(?:\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})$"
)
_PERIOD_TOKEN = re.compile(
    r"(?i)^(kỳ này|kỳ trước|năm nay|năm trước|số cuối kỳ|số đầu kỳ|"
    r"current(?: period)?|comparative|previous(?: period)?|"
    r"this period|year to date|quarter\s*(?:i{1,3}|iv|[1-4])|"
    r"q[1-4]|quý\s*[1-4])$"
)
_SEPARATOR_CELL = re.compile(r"^[\s\-–—_=.*]+$")


class TableType(StrEnum):
    BALANCE_SHEET = "balance_sheet"
    INCOME_STATEMENT = "income_statement"
    CASH_FLOW_STATEMENT = "cash_flow_statement"
    NOTES = "notes"
    UNKNOWN = "unknown"


class ReconstructStatus(StrEnum):
    OK = "OK"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ColumnRole(StrEnum):
    LABEL = "label"
    INDEX = "index"
    CODE = "code"
    NOTE = "note"
    VALUE = "value"


class RowKind(StrEnum):
    DATA = "data"
    SECTION_HEADER = "section_header"
    SEPARATOR = "separator"
    CONTINUATION = "continuation"
    EMPTY = "empty"


@dataclass(frozen=True, slots=True)
class ReconstructionContext:
    """Optional page/section context. Does not replace cell-level provenance."""

    surrounding_text: str | None = None
    section_hint: StatementSection | None = None


@dataclass(frozen=True, slots=True)
class ReconstructedColumn:
    index: int
    header_text: str
    header_parts: tuple[str, ...] = ()
    role: ColumnRole = ColumnRole.VALUE
    span: int = 1


@dataclass(frozen=True, slots=True)
class ReconstructedRow:
    row_index: int
    label: str
    values: tuple[str, ...]
    cells: tuple[ExtractedCell, ...]
    cells_by_column: tuple[str, ...] = ()
    kind: RowKind = RowKind.DATA
    indent_spaces: int = 0
    is_section_header: bool = False
    is_continuation: bool = False
    is_separator: bool = False
    label_column_index: int | None = None


@dataclass(frozen=True, slots=True)
class ReconstructedTable:
    """Intermediate table. `raw` is the untouched ExtractedTable."""

    table_type: TableType
    unit_text: str | None
    columns: tuple[ReconstructedColumn, ...]
    rows: tuple[ReconstructedRow, ...]
    raw: ExtractedTable
    status: ReconstructStatus = ReconstructStatus.NEEDS_REVIEW
    warnings: tuple[str, ...] = ()
    type_confidence: float | None = None
    type_matched_text: str | None = None
    header_band_row_indices: tuple[int, ...] = ()
    label_column_index: int | None = None

    def to_intermediate_dict(self) -> dict[str, object]:
        raw = self.raw
        return {
            "table_type": self.table_type.value,
            "unit_text": self.unit_text,
            "provenance": {
                "table_id": raw.table_id,
                "page": raw.page,
                "table_index": raw.table_index,
                "document_id": None if raw.document_id is None else str(raw.document_id),
                "artifact_id": None if raw.artifact_id is None else str(raw.artifact_id),
                "source_sha256": raw.source_sha256,
            },
            "header_band_row_indices": list(self.header_band_row_indices),
            "label_column_index": self.label_column_index,
            "columns": [
                {
                    "index": col.index,
                    "header_text": col.header_text,
                    "header_parts": list(col.header_parts),
                    "role": col.role.value,
                    "span": col.span,
                }
                for col in self.columns
            ],
            "rows": [
                {
                    "row_index": row.row_index,
                    "label": row.label,
                    "values": list(row.values),
                    "cells_by_column": list(row.cells_by_column),
                    "kind": row.kind.value,
                    "indent_spaces": row.indent_spaces,
                    "is_section_header": row.is_section_header,
                    "is_continuation": row.is_continuation,
                    "is_separator": row.is_separator,
                    "label_column_index": row.label_column_index,
                    "cells": [_cell_ref(cell) for cell in row.cells],
                }
                for row in self.rows
            ],
            "raw": {
                "table_id": raw.table_id,
                "page": raw.page,
                "table_index": raw.table_index,
                "document_id": None if raw.document_id is None else str(raw.document_id),
                "artifact_id": None if raw.artifact_id is None else str(raw.artifact_id),
                "source_sha256": raw.source_sha256,
                "source_label": raw.source_label,
                "extractor_name": raw.extractor_name,
                "extractor_version": raw.extractor_version,
                "confidence": raw.confidence,
                "status": raw.status.value,
                "warnings": list(raw.warnings),
                "bbox": None if raw.bbox is None else raw.bbox.as_list(),
                "row_count": raw.row_count,
                "column_count": raw.column_count,
                "cells": [
                    _cell_ref(cell) for extracted_row in raw.rows for cell in extracted_row.cells
                ],
            },
        }


@dataclass(frozen=True, slots=True)
class RawTableSnapshot:
    """DOC-11 compatibility holder. Prefer ReconstructedTable.raw."""

    raw: ExtractedTable


class TableReconstructor(Protocol):
    def reconstruct(
        self,
        table: ExtractedTable,
        *,
        context: ReconstructionContext | None = None,
    ) -> ReconstructedTable: ...


def _cell_ref(cell: ExtractedCell) -> dict[str, object]:
    return {
        "row": cell.row,
        "column": cell.column,
        "page": cell.page,
        "table_id": cell.table_id,
        "document_id": None if cell.document_id is None else str(cell.document_id),
        "artifact_id": None if cell.artifact_id is None else str(cell.artifact_id),
        "raw_text": cell.raw_text,
        "bbox": None if cell.bbox is None else cell.bbox.as_list(),
        "bbox_estimated": cell.bbox_estimated,
        "is_merged_continuation": cell.is_merged_continuation,
        "bbox_missing_warning": cell.bbox_missing_warning,
    }


_UNIT_CAPTION = re.compile(
    r"(?is)"
    r"("
    r"đơn\s*vị(?:\s*tính)?\s*[:\-–]?\s*[^\n]{0,80}"
    r"|đvt\s*[:\-–]?\s*[^\n]{0,80}"
    r"|unit(?:s)?\s*(?:of\s*measure)?\s*[:\-–]?\s*[^\n]{0,80}"
    r"|in\s+(?:thousands?|millions?|billions?)\s+of[^\n]{0,80}"
    r")"
)
_UNIT_SCALE = re.compile(
    r"(?i)(?:nghìn|nghin|triệu|trieu|tỷ|ty)\s*đồng"
    r"|(?:thousand|million|billion)s?\s*(?:vnd|dong)"
    r"|\bvnd\b"
)


def _row_visible_texts(row: ExtractedRow) -> list[str]:
    return [
        cell.raw_text.strip()
        for cell in row.cells
        if not cell.is_merged_continuation and cell.raw_text.strip()
    ]


def _row_joined(row: ExtractedRow) -> str:
    return " ".join(_row_visible_texts(row))


def _is_empty_row(row: ExtractedRow) -> bool:
    return not _row_visible_texts(row)


def _has_digit(text: str) -> bool:
    return any(ch.isdigit() for ch in text)


def _extract_unit_text(*blobs: str | None) -> str | None:
    for blob in blobs:
        if not blob:
            continue
        match = _UNIT_CAPTION.search(blob)
        if match:
            captured = " ".join(match.group(1).split())
            if captured and len(captured) <= _MAX_UNIT_CHARS:
                return captured
        match = _UNIT_SCALE.search(blob)
        if match:
            captured = match.group(0).strip()
            if captured:
                return captured
    return None


def _table_type_from_section(section: StatementSection) -> TableType:
    return TableType(section.value)


def _heading_from_text(text: str) -> tuple[StatementSection, str, float] | None:
    best: tuple[StatementSection, str, float] | None = None
    best_priority = -1
    for line in text.splitlines():
        rule = match_heading_line(line)
        if rule is None:
            continue
        if rule.priority > best_priority:
            best = (rule.section, line.strip(), rule.confidence)
            best_priority = rule.priority
    if best is None:
        rule = match_heading_line(text.strip()[:180])
        if rule is not None:
            return rule.section, text.strip()[:180], rule.confidence
    return best


def _collect_section_hits_in_text(text: str) -> set[StatementSection]:
    found: set[StatementSection] = set()
    for line in text.splitlines():
        rule = match_heading_line(line)
        if rule is not None:
            found.add(rule.section)
    return found


def _is_unit_row(row: ExtractedRow) -> bool:
    joined = _row_joined(row)
    if not joined:
        return False
    return _UNIT_CAPTION.search(joined) is not None or _UNIT_SCALE.search(joined) is not None


def _is_title_row(row: ExtractedRow) -> bool:
    texts = _row_visible_texts(row)
    if not texts:
        return False
    joined = " ".join(texts)
    if match_heading_line(joined) is not None:
        return True
    if match_heading_line(texts[0]) is not None:
        return True
    return len(texts) == 1 and not _has_digit(texts[0]) and len(texts[0]) >= 8


def _is_period_token(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return (
        _YEAR.match(stripped) is not None
        or _DATE_DMY.match(stripped) is not None
        or _DATE_ISO.match(stripped) is not None
        or _DATE_TEXT.match(stripped) is not None
        or _PERIOD_TOKEN.match(stripped) is not None
    )


def _looks_like_period_subheader(row: ExtractedRow) -> bool:
    texts = _row_visible_texts(row)
    if not texts:
        return False
    periodish = sum(1 for text in texts if _is_period_token(text))
    return periodish >= max(1, len(texts) - 1)


def _looks_like_header_row(row: ExtractedRow) -> bool:
    texts = _row_visible_texts(row)
    if not texts:
        return False
    if _looks_like_period_subheader(row):
        return True
    if len(texts) < 2:
        return False
    numeric = sum(
        1 for text in texts if _has_digit(text) and not _is_period_token(text)
    )
    return numeric <= max(1, len(texts) // 3)


def _looks_like_data_row(row: ExtractedRow) -> bool:
    texts = _row_visible_texts(row)
    if len(texts) < 2:
        return False
    if _looks_like_period_subheader(row):
        return False
    amounts = sum(
        1
        for text in texts
        if _has_digit(text)
        and not _is_period_token(text)
        and not re.fullmatch(r"\d{1,3}", text.strip())
    )
    return amounts >= 1


def _split_header_band(
    rows: tuple[ExtractedRow, ...],
) -> tuple[tuple[ExtractedRow, ...], tuple[ExtractedRow, ...], list[str]]:
    warnings: list[str] = []
    idx = 0
    while idx < len(rows) and (
        _is_empty_row(rows[idx]) or _is_unit_row(rows[idx]) or _is_title_row(rows[idx])
    ):
        idx += 1
    if idx >= len(rows):
        warnings.append("no_header_or_body")
        return (), (), warnings

    band: list[ExtractedRow] = []
    while idx < len(rows) and len(band) < _MAX_HEADER_BAND_ROWS:
        row = rows[idx]
        if band and _looks_like_data_row(row) and not _looks_like_period_subheader(row):
            break
        if not _looks_like_header_row(row) and not _looks_like_period_subheader(row):
            if not band:
                warnings.append("uncertain_header_row")
                band.append(row)
                idx += 1
            break
        band.append(row)
        idx += 1

    if len(band) >= _MAX_HEADER_BAND_ROWS and idx < len(rows) and _looks_like_header_row(rows[idx]):
        warnings.append("oversized_header_band")
    if not band:
        warnings.append("no_header_or_body")
        return (), rows[idx:], warnings
    body = rows[idx:]
    if body and _looks_like_period_subheader(body[0]):
        warnings.append("header_band_incomplete")
    return tuple(band), body, warnings


def _carry_parts(row: ExtractedRow) -> list[str]:
    parts: list[str] = []
    last = ""
    for cell in row.cells:
        if cell.is_merged_continuation:
            parts.append(last)
        else:
            last = cell.raw_text.strip()
            parts.append(last)
    return parts


def _column_span(row: ExtractedRow, col: int) -> int:
    if col >= len(row.cells):
        return 1
    if row.cells[col].is_merged_continuation:
        return 0
    span = 1
    nxt = col + 1
    while nxt < len(row.cells) and row.cells[nxt].is_merged_continuation:
        span += 1
        nxt += 1
    return span


def _role_from_header(header_text: str) -> ColumnRole:
    folded = fold_text(header_text)
    if re.search(
        r"\b(chi tieu|items?|noi dung|description|label|assets|resources)\b",
        folded,
    ):
        return ColumnRole.LABEL
    if re.search(r"\b(stt|so tt|no|number)\b", folded):
        return ColumnRole.INDEX
    if re.search(r"\b(ma so|codes?)\b", folded):
        return ColumnRole.CODE
    if re.search(r"\b(thuyet minh|notes?)\b", folded):
        return ColumnRole.NOTE
    return ColumnRole.VALUE


def _columns_from_band(band: tuple[ExtractedRow, ...]) -> tuple[ReconstructedColumn, ...]:
    width = max(len(row.cells) for row in band)
    part_rows = [_carry_parts(row) for row in band]
    columns: list[ReconstructedColumn] = []
    for col in range(width):
        parts = tuple(
            parts[col] if col < len(parts) else ""
            for parts in part_rows
        )
        composed = " | ".join(part for part in parts if part)
        span = max(_column_span(row, col) for row in band)
        if (
            band
            and col < len(band[0].cells)
            and not band[0].cells[col].is_merged_continuation
        ):
            span = max(span, 1)
        columns.append(
            ReconstructedColumn(
                index=col,
                header_text=composed,
                header_parts=parts,
                role=_role_from_header(composed),
                span=span,
            )
        )
    return tuple(columns)


def _pick_label_column(
    columns: tuple[ReconstructedColumn, ...],
) -> tuple[int | None, list[str]]:
    labels = [col.index for col in columns if col.role is ColumnRole.LABEL]
    if len(labels) == 1:
        return labels[0], []
    if len(labels) > 1:
        return labels[0], ["ambiguous_label_column"]
    for col in columns:
        if col.role not in {ColumnRole.INDEX, ColumnRole.CODE, ColumnRole.NOTE}:
            return col.index, ["ambiguous_label_column"]
    return None, ["ambiguous_label_column"]


def _row_kind(
    *,
    label: str,
    value_texts: tuple[str, ...],
    cells: tuple[ExtractedCell, ...],
    label_column_index: int | None,
) -> RowKind:
    visible = [cell.raw_text for cell in cells if not cell.is_merged_continuation]
    if not any(text.strip() for text in visible):
        return RowKind.EMPTY
    separator_like = all(
        (not text.strip()) or _SEPARATOR_CELL.match(text) for text in visible
    )
    if separator_like and not any(ch.isalnum() for text in visible for ch in text):
        return RowKind.SEPARATOR
    label_cell = None
    if label_column_index is not None and label_column_index < len(cells):
        label_cell = cells[label_column_index]
    if label_cell is not None and label_cell.is_merged_continuation:
        return RowKind.CONTINUATION
    if label.strip() and not any(text.strip() for text in value_texts):
        return RowKind.SECTION_HEADER
    return RowKind.DATA


def _body_row(
    row: ExtractedRow,
    *,
    columns: tuple[ReconstructedColumn, ...],
    label_column_index: int | None,
) -> ReconstructedRow:
    by_col = tuple(cell.raw_text for cell in row.cells)
    label = ""
    if label_column_index is not None and label_column_index < len(row.cells):
        label_cell = row.cells[label_column_index]
        if not label_cell.is_merged_continuation:
            label = label_cell.raw_text
    value_indexes = [col.index for col in columns if col.role is ColumnRole.VALUE]
    values = tuple(
        row.cells[idx].raw_text if idx < len(row.cells) else ""
        for idx in value_indexes
        if label_column_index is None or idx != label_column_index
    )
    kind = _row_kind(
        label=label,
        value_texts=values,
        cells=row.cells,
        label_column_index=label_column_index,
    )
    indent = len(label) - len(label.lstrip(" \t"))
    return ReconstructedRow(
        row_index=row.row_index,
        label=label,
        values=values,
        cells=row.cells,
        cells_by_column=by_col,
        kind=kind,
        indent_spaces=indent,
        is_section_header=kind is RowKind.SECTION_HEADER,
        is_continuation=kind is RowKind.CONTINUATION,
        is_separator=kind is RowKind.SEPARATOR,
        label_column_index=label_column_index,
    )


def _resolve_type(
    table: ExtractedTable,
    context: ReconstructionContext | None,
) -> tuple[TableType, float | None, str | None, list[str]]:
    warnings: list[str] = []
    internal_parts = [_row_joined(row) for row in table.rows]
    internal_text = "\n".join(part for part in internal_parts if part)
    internal = _heading_from_text(internal_text) if internal_text else None

    surrounding = None
    if context and context.surrounding_text:
        hits = _collect_section_hits_in_text(context.surrounding_text)
        if len(hits) > 1 and internal is None and context.section_hint is None:
            warnings.append("ambiguous_section_context")
        else:
            surrounding = _heading_from_text(context.surrounding_text)

    hint_section = context.section_hint if context else None
    chosen: tuple[StatementSection, str, float] | None = None
    if internal is not None:
        chosen = internal
        hint_conflict = hint_section is not None and hint_section is not internal[0]
        surround_conflict = surrounding is not None and surrounding[0] is not internal[0]
        if hint_conflict or surround_conflict:
            warnings.append("conflicting_table_type")
    elif hint_section is not None:
        chosen = (hint_section, hint_section.value, 0.70)
    elif surrounding is not None and "ambiguous_section_context" not in warnings:
        chosen = surrounding

    if chosen is None:
        return TableType.UNKNOWN, None, None, warnings
    return (
        _table_type_from_section(chosen[0]),
        chosen[2],
        chosen[1],
        warnings,
    )


class PassthroughTableReconstructor:
    """DOC-11 default: preserve ExtractedTable as-is."""

    def reconstruct(self, table: ExtractedTable) -> RawTableSnapshot:
        return RawTableSnapshot(raw=table)


class FinancialTableReconstructor:
    """Build table_type / unit_text / columns / rows without normalizing values."""

    def reconstruct(
        self,
        table: ExtractedTable,
        *,
        context: ReconstructionContext | None = None,
    ) -> ReconstructedTable:
        warnings: list[str] = list(table.warnings)
        table_type, type_confidence, type_matched, type_warnings = _resolve_type(
            table, context
        )
        warnings.extend(type_warnings)

        surrounding = context.surrounding_text if context else None
        cell_blob = "\n".join(_row_joined(row) for row in table.rows)
        unit_text = _extract_unit_text(cell_blob, surrounding)

        band, body, split_warnings = _split_header_band(table.rows)
        warnings.extend(split_warnings)

        columns: tuple[ReconstructedColumn, ...] = ()
        rows: tuple[ReconstructedRow, ...] = ()
        label_column_index: int | None = None
        if band:
            columns = _columns_from_band(band)
            label_column_index, label_warnings = _pick_label_column(columns)
            warnings.extend(label_warnings)
            rows = tuple(
                _body_row(
                    row,
                    columns=columns,
                    label_column_index=label_column_index,
                )
                for row in body
            )

        if not table.rows:
            warnings.append("empty_raw_table")
        if table_type is TableType.UNKNOWN:
            warnings.append("unknown_table_type")
        if unit_text is None:
            warnings.append("missing_unit_text")
        data_rows = [row for row in rows if row.kind is RowKind.DATA]
        if band and not data_rows:
            warnings.append("empty_body")

        review_tokens = (
            "empty_raw_table",
            "unknown_table_type",
            "no_header_or_body",
            "empty_body",
            "conflicting_table_type",
            "ambiguous_section_context",
            "uncertain_header_row",
            "ambiguous_label_column",
            "header_band_incomplete",
            "oversized_header_band",
            "jagged_rows",
            "empty_grid",
        )
        needs_review = any(
            warning == token or warning.startswith(f"{token}:")
            for warning in warnings
            for token in review_tokens
        )
        if table_type is not TableType.UNKNOWN and unit_text is None:
            needs_review = True
        if table.status.value != "OK":
            needs_review = True
            warnings.append("raw_extraction_not_ok")
        status = (
            ReconstructStatus.NEEDS_REVIEW if needs_review else ReconstructStatus.OK
        )

        if type_confidence is not None:
            type_confidence = min(type_confidence, 0.95)

        return ReconstructedTable(
            table_type=table_type,
            unit_text=unit_text,
            columns=columns,
            rows=rows,
            raw=table,
            status=status,
            warnings=tuple(dict.fromkeys(warnings)),
            type_confidence=type_confidence,
            type_matched_text=type_matched,
            header_band_row_indices=tuple(row.row_index for row in band),
            label_column_index=label_column_index,
        )
