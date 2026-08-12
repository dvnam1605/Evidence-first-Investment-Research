"""Processing-layer errors (no ORM coupling)."""

from __future__ import annotations


class ProcessingError(Exception):
    """Base processing error."""


class PDFParseError(ProcessingError):
    """Native or digital PDF parsing failed."""


class OCRFailure(ProcessingError):
    """OCR engine or page rasterization failed."""


class ExcelParseError(ProcessingError):
    """XLSX / spreadsheet parsing failed."""


class TableExtractionError(ProcessingError):
    """Table extraction failed or input was not a reliable PDF/table source."""
