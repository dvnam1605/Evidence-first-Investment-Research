"""Document block domain model (structured page content units)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from src.domain.enums import BlockType


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """Axis-aligned box in page coordinate space."""

    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError("bbox requires x1 >= x0 and y1 >= y0")

    def as_list(self) -> list[float]:
        return [self.x0, self.y0, self.x1, self.y1]

    @classmethod
    def from_list(cls, values: list[float] | tuple[float, ...]) -> BoundingBox:
        if len(values) != 4:
            raise ValueError("bbox list must have exactly 4 numbers")
        return cls(
            x0=float(values[0]),
            y0=float(values[1]),
            x1=float(values[2]),
            y1=float(values[3]),
        )


@dataclass(frozen=True, slots=True)
class DocumentBlock:
    """
    One structured content block on a persisted document page.

    Shape matches the DOC-07 contract:
    { "type": "text|table|image", "bbox": [...], "content": {...} }
    """

    id: UUID
    page_id: UUID
    block_index: int
    block_type: BlockType
    bbox: BoundingBox | None
    content: dict[str, Any]
    created_at: datetime

    def __post_init__(self) -> None:
        if self.block_index < 0:
            raise ValueError("block_index must be >= 0")
        if not isinstance(self.content, dict):
            raise ValueError("content must be a dict")

    def to_structure(self) -> dict[str, Any]:
        """Serialize to the plan's structured-block JSON shape."""
        return {
            "type": self.block_type.value,
            "bbox": self.bbox.as_list() if self.bbox is not None else [],
            "content": dict(self.content),
        }
