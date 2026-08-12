"""Table extraction package."""

from src.processing.tables.base import TableExtractor
from src.processing.tables.detector import TableRegion, region_from_bbox
from src.processing.tables.extractor import (
    ExcelGridTableExtractor,
    PyMuPDFTableExtractor,
    TableExtractionService,
)
from src.processing.tables.models import (
    ExtractedCell,
    ExtractedRow,
    ExtractedTable,
    PageTableExtractionIssue,
    TableExtractionContext,
    TableExtractionResult,
    TableExtractionStatus,
)
from src.processing.tables.raw_source import (
    JsonRawTableSource,
    RawTableSource,
    load_raw_table_fixture,
)
from src.processing.tables.reconstruction import (
    ColumnRole,
    FinancialTableReconstructor,
    PassthroughTableReconstructor,
    RawTableSnapshot,
    ReconstructedColumn,
    ReconstructedRow,
    ReconstructedTable,
    ReconstructionContext,
    ReconstructStatus,
    RowKind,
    TableReconstructor,
    TableType,
)

__all__ = [
    "ExcelGridTableExtractor",
    "ExtractedCell",
    "ExtractedRow",
    "ExtractedTable",
    "PageTableExtractionIssue",
    "ColumnRole",
    "JsonRawTableSource",
    "FinancialTableReconstructor",
    "PassthroughTableReconstructor",
    "PyMuPDFTableExtractor",
    "RawTableSnapshot",
    "RawTableSource",
    "load_raw_table_fixture",
    "ReconstructStatus",
    "ReconstructionContext",
    "ReconstructedColumn",
    "ReconstructedRow",
    "ReconstructedTable",
    "RowKind",
    "TableType",
    "TableExtractionContext",
    "TableExtractionResult",
    "TableExtractionService",
    "TableExtractionStatus",
    "TableExtractor",
    "TableReconstructor",
    "TableRegion",
    "region_from_bbox",
]
