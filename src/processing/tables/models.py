"""Extracted table models (DOC-11). Coordinates + provenance; no metric normalization."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from src.domain.document_block import BoundingBox


class TableExtractionStatus(StrEnum):
    OK = "OK"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class TableExtractionContext:
    """Caller-supplied identity for provenance across documents."""

    document_id: UUID | None = None
    artifact_id: UUID | None = None
    source_sha256: str | None = None
    source_label: str | None = None


@dataclass(frozen=True, slots=True)
class ExtractedCell:
    """One table cell with provenance."""

    raw_text: str
    row: int  # 0-based
    column: int  # 0-based
    page: int  # 1-based page / sheet ordinal used as page
    table_id: str
    document_id: UUID | None = None
    artifact_id: UUID | None = None
    bbox: BoundingBox | None = None
    # True when this grid slot is a visual continuation of a merged cell (no own text).
    is_merged_continuation: bool = False
    bbox_missing_warning: str | None = None


@dataclass(frozen=True, slots=True)
class ExtractedRow:
    row_index: int  # 0-based
    cells: tuple[ExtractedCell, ...]


@dataclass(frozen=True, slots=True)
class ExtractedTable:
    page: int  # 1-based
    rows: tuple[ExtractedRow, ...]
    table_id: str
    table_index: int = 0
    document_id: UUID | None = None
    artifact_id: UUID | None = None
    source_sha256: str | None = None
    bbox: BoundingBox | None = None
    extractor_name: str = ""
    extractor_version: str = ""
    source_label: str | None = None
    confidence: float | None = None
    status: TableExtractionStatus = TableExtractionStatus.NEEDS_REVIEW
    warnings: tuple[str, ...] = ()

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def column_count(self) -> int:
        if not self.rows:
            return 0
        return max((len(row.cells) for row in self.rows), default=0)


@dataclass(frozen=True, slots=True)
class PageTableExtractionIssue:
    """Observable per-page extraction problem (not silent omit)."""

    page: int
    status: TableExtractionStatus
    reason: str
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class TableExtractionResult:
    """Tables plus inspectable page-level issues / review signals."""

    tables: tuple[ExtractedTable, ...]
    page_issues: tuple[PageTableExtractionIssue, ...] = ()
    context: TableExtractionContext = field(default_factory=TableExtractionContext)

    @property
    def needs_review(self) -> bool:
        if any(t.status != TableExtractionStatus.OK for t in self.tables):
            return True
        return any(
            issue.status == TableExtractionStatus.NEEDS_REVIEW for issue in self.page_issues
        )
