"""Table-ready raw tables (DOC-12). Bypass PDF find_tables for raster statements."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol
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
    """Upstream that already has a cell grid (OCR, Excel, or vetted fixture)."""

    @property
    def name(self) -> str: ...

    def load(self) -> TableExtractionResult: ...


def _bbox(raw: list[float] | None) -> BoundingBox | None:
    if raw is None:
        return None
    return BoundingBox(x0=raw[0], y0=raw[1], x1=raw[2], y1=raw[3])


def _uuid(raw: str | None) -> UUID | None:
    if raw is None:
        return None
    return UUID(raw)


def extracted_table_from_dict(payload: dict) -> ExtractedTable:
    """Build ExtractedTable from a vetted raw-grid dict (no PDF parsing)."""
    table = payload.get("table", payload)
    table_id = str(table["table_id"])
    page = int(table["page"])
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
                is_merged_continuation=bool(cell.get("is_merged_continuation", False)),
            )
            for cell in row["cells"]
        )
        rows.append(ExtractedRow(row_index=row_index, cells=cells))
    status_raw = table.get("status", TableExtractionStatus.OK.value)
    return ExtractedTable(
        page=page,
        rows=tuple(rows),
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


def load_raw_table_fixture(path: Path | str) -> tuple[ExtractedTable, dict]:
    """Load a vetted JSON fixture. Returns (raw table, full payload including expected)."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return extracted_table_from_dict(payload), payload


class JsonRawTableSource:
    """Read one or more vetted raw-table JSON files as TableExtractionResult."""

    def __init__(self, paths: tuple[Path, ...]) -> None:
        self._paths = paths

    @property
    def name(self) -> str:
        return "json_raw_table_fixture"

    def load(self) -> TableExtractionResult:
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
        return TableExtractionResult(tables=tuple(tables), context=context)
