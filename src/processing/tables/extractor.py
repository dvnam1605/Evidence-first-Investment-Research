"""Table extractors for PDF (PyMuPDF) and Excel grids."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from uuid import UUID

import fitz  # type: ignore[import-untyped]

from src.domain.document_block import BoundingBox
from src.processing.errors import PDFParseError
from src.processing.excel.models import ParsedWorkbook
from src.processing.tables.detector import TableRegion, region_from_bbox
from src.processing.tables.models import (
    ExtractedCell,
    ExtractedRow,
    ExtractedTable,
    PageTableExtractionIssue,
    TableExtractionContext,
    TableExtractionResult,
    TableExtractionStatus,
)

PYMUPDF_EXTRACTOR_NAME = "pymupdf_find_tables"
EXCEL_EXTRACTOR_NAME = "excel_grid"
PDF_MAGIC = b"%PDF"
HTML_MARKERS = (b"<!doctype html", b"<html", b"<HTML")


def _pymupdf_version() -> str:
    try:
        return version("pymupdf")
    except PackageNotFoundError:
        return "unknown"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _make_table_id(
    *,
    context: TableExtractionContext,
    page: int,
    table_index: int,
) -> str:
    doc_key = (
        str(context.document_id)
        if context.document_id is not None
        else (
            str(context.artifact_id)
            if context.artifact_id is not None
            else (context.source_sha256 or context.source_label or "unknown-doc")
        )
    )
    return f"{doc_key}:p{page}:t{table_index}"


def _bbox_from_tuple(raw: object) -> BoundingBox | None:
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        return None
    values = raw
    if len(values) < 4:
        return None
    try:
        return BoundingBox(
            x0=float(values[0]),
            y0=float(values[1]),
            x1=float(values[2]),
            y1=float(values[3]),
        )
    except (TypeError, ValueError):
        return None


def _assess_table_quality(
    *,
    rows: tuple[ExtractedRow, ...],
    table_bbox: BoundingBox | None,
    warnings: list[str],
    expect_page_bboxes: bool = True,
) -> tuple[float | None, TableExtractionStatus, tuple[str, ...]]:
    if not rows:
        warnings.append("empty_grid")
        return 0.2, TableExtractionStatus.NEEDS_REVIEW, tuple(warnings)
    if expect_page_bboxes and table_bbox is None:
        warnings.append("missing_table_bbox")
    jagged = len({len(row.cells) for row in rows}) > 1
    if jagged:
        warnings.append("jagged_rows")
    missing_bbox = 0
    if expect_page_bboxes:
        missing_bbox = sum(
            1
            for row in rows
            for cell in row.cells
            if cell.bbox is None and not cell.is_merged_continuation
        )
        total = sum(len(row.cells) for row in rows) or 1
        if missing_bbox:
            warnings.append(f"missing_cell_bbox:{missing_bbox}/{total}")
    else:
        total = 1

    # Conservative score — never fabricate 1.0 certainty.
    score = 0.75
    if expect_page_bboxes and table_bbox is None:
        score -= 0.15
    if jagged:
        score -= 0.20
    if missing_bbox:
        score -= min(0.25, 0.25 * (missing_bbox / total))
    score = max(0.05, min(0.85, score))
    status = (
        TableExtractionStatus.OK
        if score >= 0.60 and not jagged
        else TableExtractionStatus.NEEDS_REVIEW
    )
    if status is TableExtractionStatus.OK and missing_bbox:
        status = TableExtractionStatus.NEEDS_REVIEW
    return score, status, tuple(warnings)


def _validate_pdf_bytes(pdf_bytes: bytes) -> None:
    if not pdf_bytes:
        raise PDFParseError("PDF bytes must not be empty for table extraction")
    head = pdf_bytes[:256].lstrip().lower()
    if any(marker in head for marker in HTML_MARKERS):
        raise PDFParseError("Rejected HTML content; not a PDF for table extraction")
    if not pdf_bytes.startswith(PDF_MAGIC):
        raise PDFParseError("Input does not start with %PDF magic for table extraction")


def _page_has_raster_content(page: object) -> bool:
    """True when the page may hide tables in images (native find_tables sees none)."""
    get_images = getattr(page, "get_images", None)
    if callable(get_images):
        try:
            images = get_images()
        except Exception:  # noqa: BLE001
            images = ()
        if images:
            return True
    return False


class PyMuPDFTableExtractor:
    """Extract tables from PDF bytes via PyMuPDF find_tables()."""

    @property
    def name(self) -> str:
        return PYMUPDF_EXTRACTOR_NAME

    def detect_regions(
        self,
        pdf_bytes: bytes,
        *,
        context: TableExtractionContext | None = None,
    ) -> tuple[TableRegion, ...]:
        result = self.extract(pdf_bytes, context=context)
        regions: list[TableRegion] = []
        for table in result.tables:
            if table.bbox is None:
                regions.append(
                    TableRegion(
                        page=table.page,
                        bbox=None,
                        confidence=table.confidence,
                        method=self.name,
                        status=table.status,
                        warnings=table.warnings,
                    )
                )
            else:
                regions.append(
                    region_from_bbox(
                        page=table.page,
                        x0=table.bbox.x0,
                        y0=table.bbox.y0,
                        x1=table.bbox.x1,
                        y1=table.bbox.y1,
                        confidence=table.confidence,
                        method=self.name,
                        status=table.status,
                        warnings=table.warnings,
                    )
                )
        return tuple(regions)

    def extract(
        self,
        pdf_bytes: bytes,
        *,
        context: TableExtractionContext | None = None,
    ) -> TableExtractionResult:
        _validate_pdf_bytes(pdf_bytes)
        resolved = context or TableExtractionContext(source_sha256=_sha256(pdf_bytes))
        if resolved.source_sha256 is None:
            resolved = TableExtractionContext(
                document_id=resolved.document_id,
                artifact_id=resolved.artifact_id,
                source_sha256=_sha256(pdf_bytes),
                source_label=resolved.source_label,
            )

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:  # noqa: BLE001
            raise PDFParseError(f"Failed to open PDF for tables: {exc}") from exc

        extractor_version = _pymupdf_version()
        extracted: list[ExtractedTable] = []
        page_issues: list[PageTableExtractionIssue] = []
        try:
            if doc.page_count == 0:
                raise PDFParseError("PDF has zero pages for table extraction")
            # Encrypted without credentials.
            if doc.is_encrypted and not doc.authenticate(""):
                raise PDFParseError(
                    "PDF is encrypted and cannot be used for table extraction"
                )

            for page_index in range(doc.page_count):
                page = doc.load_page(page_index)
                page_number = page_index + 1
                try:
                    finder = page.find_tables()
                except Exception as exc:  # noqa: BLE001
                    page_issues.append(
                        PageTableExtractionIssue(
                            page=page_number,
                            status=TableExtractionStatus.NEEDS_REVIEW,
                            reason="find_tables_failed",
                            detail=f"{type(exc).__name__}: {exc}",
                        )
                    )
                    continue

                tables = getattr(finder, "tables", None)
                if tables is None:
                    try:
                        tables = list(finder)
                    except Exception as exc:  # noqa: BLE001
                        page_issues.append(
                            PageTableExtractionIssue(
                                page=page_number,
                                status=TableExtractionStatus.NEEDS_REVIEW,
                                reason="table_finder_iteration_failed",
                                detail=f"{type(exc).__name__}: {exc}",
                            )
                        )
                        continue

                table_list = list(tables)
                if not table_list and _page_has_raster_content(page):
                    page_issues.append(
                        PageTableExtractionIssue(
                            page=page_number,
                            status=TableExtractionStatus.NEEDS_REVIEW,
                            reason="no_tables_detected",
                            detail="page has embedded images but find_tables returned none",
                        )
                    )
                    continue

                for table_index, table in enumerate(table_list):
                    extracted.append(
                        self._convert_pymupdf_table(
                            table,
                            page_number=page_number,
                            table_index=table_index,
                            extractor_version=extractor_version,
                            context=resolved,
                        )
                    )
        finally:
            doc.close()

        return TableExtractionResult(
            tables=tuple(extracted),
            page_issues=tuple(page_issues),
            context=resolved,
        )

    def _convert_pymupdf_table(
        self,
        table: object,
        *,
        page_number: int,
        table_index: int,
        extractor_version: str,
        context: TableExtractionContext,
    ) -> ExtractedTable:
        warnings: list[str] = []
        table_id = _make_table_id(
            context=context, page=page_number, table_index=table_index
        )
        table_bbox = _bbox_from_tuple(getattr(table, "bbox", None))

        extract = getattr(table, "extract", None)
        grid = extract() if callable(extract) else None
        row_objs = list(getattr(table, "rows", None) or [])

        if not grid:
            confidence, status, warns = _assess_table_quality(
                rows=(), table_bbox=table_bbox, warnings=warnings
            )
            return ExtractedTable(
                page=page_number,
                rows=(),
                table_id=table_id,
                table_index=table_index,
                document_id=context.document_id,
                artifact_id=context.artifact_id,
                source_sha256=context.source_sha256,
                bbox=table_bbox,
                extractor_name=self.name,
                extractor_version=extractor_version,
                source_label=context.source_label,
                confidence=confidence,
                status=status,
                warnings=warns,
            )

        rows: list[ExtractedRow] = []
        for row_idx, row in enumerate(grid):
            row_cells_raw = None
            if row_idx < len(row_objs):
                row_cells_raw = getattr(row_objs[row_idx], "cells", None)

            cells: list[ExtractedCell] = []
            for col_idx, value in enumerate(row):
                cell_bbox: BoundingBox | None = None
                bbox_warning: str | None = None
                is_merged = False
                if row_cells_raw is not None and col_idx < len(row_cells_raw):
                    slot = row_cells_raw[col_idx]
                    if slot is None:
                        is_merged = True
                    else:
                        cell_bbox = _bbox_from_tuple(slot)
                        if cell_bbox is None:
                            bbox_warning = "unmapped_cell_bbox"
                            warnings.append(
                                f"unmapped_cell_bbox:r{row_idx}c{col_idx}"
                            )
                else:
                    bbox_warning = "cell_bbox_unavailable"
                    warnings.append(f"cell_bbox_unavailable:r{row_idx}c{col_idx}")

                raw = _cell_text(value)
                if is_merged and raw == "":
                    # Merged continuation — keep empty text but flag explicitly.
                    pass
                elif value is None and not is_merged:
                    raw = ""

                cells.append(
                    ExtractedCell(
                        raw_text=raw,
                        row=row_idx,
                        column=col_idx,
                        page=page_number,
                        table_id=table_id,
                        document_id=context.document_id,
                        artifact_id=context.artifact_id,
                        bbox=cell_bbox,
                        is_merged_continuation=is_merged,
                        bbox_missing_warning=bbox_warning,
                    )
                )
            rows.append(ExtractedRow(row_index=row_idx, cells=tuple(cells)))

        row_tuple = tuple(rows)
        confidence, status, warns = _assess_table_quality(
            rows=row_tuple, table_bbox=table_bbox, warnings=warnings
        )
        return ExtractedTable(
            page=page_number,
            rows=row_tuple,
            table_id=table_id,
            table_index=table_index,
            document_id=context.document_id,
            artifact_id=context.artifact_id,
            source_sha256=context.source_sha256,
            bbox=table_bbox,
            extractor_name=self.name,
            extractor_version=extractor_version,
            source_label=context.source_label,
            confidence=confidence,
            status=status,
            warnings=warns,
        )


class ExcelGridTableExtractor:
    """Treat each worksheet used range as one table (coordinate-preserving)."""

    @property
    def name(self) -> str:
        return EXCEL_EXTRACTOR_NAME

    def extract(
        self,
        workbook: ParsedWorkbook,
        *,
        context: TableExtractionContext | None = None,
    ) -> TableExtractionResult:
        resolved = context or TableExtractionContext(
            artifact_id=workbook.artifact_id,
            source_sha256=workbook.source_sha256,
            source_label=workbook.source_label,
        )
        tables: list[ExtractedTable] = []
        for sheet in workbook.sheets:
            page = sheet.index + 1
            table_index = 0
            table_id = _make_table_id(
                context=resolved, page=page, table_index=table_index
            )
            warnings: list[str] = []

            populated = [
                cell
                for cell in sheet.cells
                if cell.value is not None
                or cell.formula_text is not None
                or cell.is_merged
            ]
            if not any(
                cell.value is not None or cell.formula_text is not None
                for cell in sheet.cells
            ):
                confidence, status, warns = _assess_table_quality(
                    rows=(),
                    table_bbox=None,
                    warnings=["empty_sheet"],
                    expect_page_bboxes=False,
                )
                tables.append(
                    ExtractedTable(
                        page=page,
                        rows=(),
                        table_id=table_id,
                        table_index=table_index,
                        document_id=resolved.document_id,
                        artifact_id=resolved.artifact_id or workbook.artifact_id,
                        source_sha256=resolved.source_sha256 or workbook.source_sha256,
                        bbox=None,
                        extractor_name=self.name,
                        extractor_version="workbook",
                        source_label=sheet.name,
                        confidence=confidence,
                        status=status,
                        warnings=warns,
                    )
                )
                continue

            min_row = min(cell.row for cell in populated)
            max_row = max(cell.row for cell in populated)
            min_col = min(cell.column for cell in populated)
            max_col = max(cell.column for cell in populated)
            by_coord = {(cell.row, cell.column): cell for cell in sheet.cells}

            rows: list[ExtractedRow] = []
            for r in range(min_row, max_row + 1):
                cells: list[ExtractedCell] = []
                for c in range(min_col, max_col + 1):
                    src = by_coord.get((r, c))
                    is_merged_cont = False
                    if src is None:
                        raw = ""
                    elif src.is_merged and src.value is None and src.formula_text is None:
                        raw = ""
                        is_merged_cont = True
                        warnings.append(f"merged_continuation:{src.address}")
                    elif src.formula_text is not None:
                        raw = src.formula_text
                    elif src.value_text is not None:
                        raw = src.value_text
                    else:
                        raw = "" if src.value is None else str(src.value)
                    cells.append(
                        ExtractedCell(
                            raw_text=raw,
                            row=r - min_row,
                            column=c - min_col,
                            page=page,
                            table_id=table_id,
                            document_id=resolved.document_id,
                            artifact_id=resolved.artifact_id or workbook.artifact_id,
                            bbox=None,
                            is_merged_continuation=is_merged_cont,
                            bbox_missing_warning="excel_has_no_page_bbox",
                        )
                    )
                rows.append(ExtractedRow(row_index=r - min_row, cells=tuple(cells)))

            row_tuple = tuple(rows)
            confidence, status, warns = _assess_table_quality(
                rows=row_tuple,
                table_bbox=None,
                warnings=warnings,
                expect_page_bboxes=False,
            )
            # Surface that Excel has no page-space bbox without blocking OK grids.
            warns = warns + ("excel_no_page_bbox",)

            tables.append(
                ExtractedTable(
                    page=page,
                    rows=row_tuple,
                    table_id=table_id,
                    table_index=table_index,
                    document_id=resolved.document_id,
                    artifact_id=resolved.artifact_id or workbook.artifact_id,
                    source_sha256=resolved.source_sha256 or workbook.source_sha256,
                    bbox=None,
                    extractor_name=self.name,
                    extractor_version="workbook",
                    source_label=sheet.name,
                    confidence=confidence,
                    status=status,
                    warnings=warns,
                )
            )
        return TableExtractionResult(tables=tuple(tables), context=resolved)


class TableExtractionService:
    """Facade over PDF/Excel extractors."""

    def __init__(
        self,
        *,
        pdf: PyMuPDFTableExtractor | None = None,
        excel: ExcelGridTableExtractor | None = None,
    ) -> None:
        self._pdf = pdf or PyMuPDFTableExtractor()
        self._excel = excel or ExcelGridTableExtractor()

    def extract_pdf(
        self,
        pdf_bytes: bytes,
        *,
        context: TableExtractionContext | None = None,
        document_id: UUID | None = None,
        artifact_id: UUID | None = None,
    ) -> TableExtractionResult:
        ctx = context or TableExtractionContext(
            document_id=document_id, artifact_id=artifact_id
        )
        if document_id is not None or artifact_id is not None:
            ctx = TableExtractionContext(
                document_id=document_id or ctx.document_id,
                artifact_id=artifact_id or ctx.artifact_id,
                source_sha256=ctx.source_sha256,
                source_label=ctx.source_label,
            )
        return self._pdf.extract(pdf_bytes, context=ctx)

    def extract_workbook(
        self,
        workbook: ParsedWorkbook,
        *,
        context: TableExtractionContext | None = None,
        document_id: UUID | None = None,
        artifact_id: UUID | None = None,
    ) -> TableExtractionResult:
        ctx = context or TableExtractionContext(
            document_id=document_id,
            artifact_id=artifact_id or workbook.artifact_id,
            source_sha256=workbook.source_sha256,
            source_label=workbook.source_label,
        )
        return self._excel.extract(workbook, context=ctx)

    def extract_pdf_from_path(
        self,
        path: Path | str,
        *,
        context: TableExtractionContext | None = None,
    ) -> TableExtractionResult:
        path_obj = Path(path)
        data = path_obj.read_bytes()
        ctx = context or TableExtractionContext(source_label=str(path_obj))
        return self.extract_pdf(data, context=ctx)
