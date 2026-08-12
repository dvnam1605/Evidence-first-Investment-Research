"""Table region detection helpers (bbox candidates)."""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.document_block import BoundingBox
from src.processing.tables.models import TableExtractionStatus


@dataclass(frozen=True, slots=True)
class TableRegion:
    """Detected table region on a page before cell extraction."""

    page: int
    bbox: BoundingBox | None
    confidence: float | None
    method: str
    status: TableExtractionStatus = TableExtractionStatus.NEEDS_REVIEW
    warnings: tuple[str, ...] = ()


def region_from_bbox(
    *,
    page: int,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    confidence: float | None = None,
    method: str = "pymupdf_find_tables",
    status: TableExtractionStatus = TableExtractionStatus.NEEDS_REVIEW,
    warnings: tuple[str, ...] = (),
) -> TableRegion:
    """Build a region without fabricating certainty (confidence defaults to None)."""
    return TableRegion(
        page=page,
        bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1),
        confidence=confidence,
        method=method,
        status=status,
        warnings=warnings,
    )
