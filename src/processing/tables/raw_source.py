"""Table-ready raw tables (DOC-12). Bypass PDF find_tables for raster statements."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from src.domain.document_block import BoundingBox
from src.processing.tables.models import (
    ExtractedCell,
    ExtractedRow,
    ExtractedTable,
    TableExtractionContext,
    TableExtractionResult,
    TableExtractionStatus,
)


class RawTableSource(Protocol):
    """Upstream of vetted raw grids, selected by immutable source digest."""

    @property
    def name(self) -> str: ...

    def load_for(
        self,
        *,
        source_sha256: str,
        context: TableExtractionContext,
    ) -> TableExtractionResult | None: ...


def _bbox(raw: list[float] | None) -> BoundingBox | None:
    if raw is None:
        return None
    return BoundingBox(x0=raw[0], y0=raw[1], x1=raw[2], y1=raw[3])


def _uuid(raw: str | None) -> UUID | None:
    if raw is None:
        return None
    return UUID(raw)


def extracted_table_from_dict(payload: dict[str, Any]) -> ExtractedTable:
    """Build ExtractedTable from a vetted raw-grid dict (no PDF parsing)."""
    table = payload.get("table", payload)
    table_id = str(table["table_id"])
    page = int(table["page"])
    rows = _rows_from_table_dict(table, page=page, table_id=table_id)
    status_raw = table.get("status", TableExtractionStatus.OK.value)
    return ExtractedTable(
        page=page,
        rows=rows,
        table_id=table_id,
        table_index=int(table.get("table_index", 0)),
        document_id=_uuid(table.get("document_id")),
        artifact_id=_uuid(table.get("artifact_id")),
        source_sha256=table.get("source_sha256"),
        bbox=_bbox(table.get("bbox")),
        extractor_name=str(table.get("extractor_name", "raw_table_fixture")),
        extractor_version=str(table.get("extractor_version", "vetted-visual")),
        source_label=table.get("source_label"),
        confidence=table.get("confidence", 0.80),
        status=TableExtractionStatus(status_raw),
        warnings=tuple(table.get("warnings", ())),
    )


def _rows_from_table_dict(
    table: dict[str, Any],
    *,
    page: int,
    table_id: str,
) -> tuple[ExtractedRow, ...]:
    if "matrix" in table:
        return _rows_from_matrix(table, page=page, table_id=table_id)
    estimated_bboxes = any("bbox_estimated" in str(item) for item in table.get("warnings", ()))
    rows: list[ExtractedRow] = []
    for row in table["rows"]:
        row_index = int(row["row_index"])
        cells = tuple(
            ExtractedCell(
                raw_text=str(cell["raw_text"]),
                row=int(cell.get("row", row_index)),
                column=int(cell["column"]),
                page=int(cell.get("page", page)),
                table_id=str(cell.get("table_id", table_id)),
                document_id=_uuid(cell.get("document_id", table.get("document_id"))),
                artifact_id=_uuid(cell.get("artifact_id", table.get("artifact_id"))),
                bbox=_bbox(cell.get("bbox")),
                bbox_estimated=bool(
                    cell.get("bbox_estimated", estimated_bboxes)
                ),
                is_merged_continuation=bool(cell.get("is_merged_continuation", False)),
            )
            for cell in row["cells"]
        )
        rows.append(ExtractedRow(row_index=row_index, cells=cells))
    return tuple(rows)


def _rows_from_matrix(
    table: dict[str, Any],
    *,
    page: int,
    table_id: str,
) -> tuple[ExtractedRow, ...]:
    """Expand a concise, visually-vetted rectangular grid with cell provenance."""
    matrix = table["matrix"]
    if not isinstance(matrix, list) or not all(isinstance(row, list) for row in matrix):
        raise ValueError("raw table matrix must be a list of rows")
    table_bbox = _bbox(table.get("bbox"))
    row_count = len(matrix)
    column_count = max((len(row) for row in matrix), default=0)
    rows: list[ExtractedRow] = []
    for row_index, values in enumerate(matrix):
        cells = tuple(
            ExtractedCell(
                raw_text=str(value),
                row=row_index,
                column=column,
                page=page,
                table_id=table_id,
                document_id=_uuid(table.get("document_id")),
                artifact_id=_uuid(table.get("artifact_id")),
                bbox=_matrix_cell_bbox(
                    table_bbox,
                    row=row_index,
                    column=column,
                    row_count=row_count,
                    column_count=column_count,
                ),
                bbox_estimated=table_bbox is not None,
                bbox_missing_warning=(
                    "table_bbox_missing" if table_bbox is None else None
                ),
            )
            for column, value in enumerate(values)
        )
        rows.append(ExtractedRow(row_index=row_index, cells=cells))
    return tuple(rows)


def _matrix_cell_bbox(
    table_bbox: BoundingBox | None,
    *,
    row: int,
    column: int,
    row_count: int,
    column_count: int,
) -> BoundingBox | None:
    if table_bbox is None or row_count == 0 or column_count == 0:
        return None
    width = (table_bbox.x1 - table_bbox.x0) / column_count
    height = (table_bbox.y1 - table_bbox.y0) / row_count
    return BoundingBox(
        x0=table_bbox.x0 + (column * width),
        y0=table_bbox.y0 + (row * height),
        x1=table_bbox.x0 + ((column + 1) * width),
        y1=table_bbox.y0 + ((row + 1) * height),
    )


def load_raw_table_fixture(path: Path | str) -> tuple[ExtractedTable, dict[str, Any]]:
    """Load a vetted JSON fixture. Returns (raw table, full payload including expected)."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return extracted_table_from_dict(payload), payload


class JsonRawTableSource:
    """Read vetted raw-table JSON sidecars selected by their PDF SHA-256."""

    def __init__(self, paths: tuple[Path, ...]) -> None:
        self._paths = paths

    @property
    def name(self) -> str:
        return "json_raw_table"

    def load(self) -> TableExtractionResult:
        """Load every table, retained for fixture validation and offline tooling."""
        tables = []
        context = TableExtractionContext()
        for path in self._paths:
            table, payload = load_raw_table_fixture(path)
            tables.append(table)
            source = payload.get("source") or {}
            context = TableExtractionContext(
                source_sha256=source.get("sha256", table.source_sha256),
                source_label=source.get("pdf") or table.source_label,
            )
        return TableExtractionResult(
            tables=tuple(sorted(tables, key=lambda table: (table.page, table.table_index))),
            context=context,
        )

    def load_for(
        self,
        *,
        source_sha256: str,
        context: TableExtractionContext,
    ) -> TableExtractionResult | None:
        """Return only sidecars proven to belong to the document being processed."""
        selected: list[ExtractedTable] = []
        warnings: list[str] = []
        for path in self._paths:
            try:
                table, payload = load_raw_table_fixture(path)
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                warnings.append(
                    f"raw_table_sidecar_failed:{path.name}:{type(exc).__name__}"
                )
                continue
            source = payload.get("source") or {}
            declared_sha = str(source.get("sha256") or table.source_sha256 or "")
            if declared_sha != source_sha256:
                continue
            selected.append(
                replace(
                    _bind_to_processing_context(table, context),
                    extractor_name=self.name,
                )
            )
        if not selected and not warnings:
            return None
        return TableExtractionResult(
            tables=tuple(sorted(selected, key=lambda table: (table.page, table.table_index))),
            context=context,
            warnings=tuple(warnings),
        )


def _bind_to_processing_context(
    table: ExtractedTable,
    context: TableExtractionContext,
) -> ExtractedTable:
    """Replace fixture identity with the active artifact without changing raw text."""
    table_key = (
        str(context.document_id)
        if context.document_id is not None
        else str(context.artifact_id or context.source_sha256 or "unknown-doc")
    )
    table_id = f"{table_key}:p{table.page}:raw:t{table.table_index}"
    rows = tuple(
        replace(
            row,
            cells=tuple(
                replace(
                    cell,
                    table_id=table_id,
                    document_id=context.document_id,
                    artifact_id=context.artifact_id,
                )
                for cell in row.cells
            ),
        )
        for row in table.rows
    )
    return replace(
        table,
        table_id=table_id,
        document_id=context.document_id,
        artifact_id=context.artifact_id,
        source_sha256=context.source_sha256,
        source_label=context.source_label,
        rows=rows,
    )
