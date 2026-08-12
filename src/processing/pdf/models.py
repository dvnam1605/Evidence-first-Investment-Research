"""Parsed PDF domain models (in-memory; persistence is DOC-06)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class BoundingBox:
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True, slots=True)
class TextBlock:
    text: str
    bbox: BoundingBox | None


@dataclass(frozen=True, slots=True)
class ParsedPage:
    page_number: int
    # Raw extractor output; do not strip/normalize this field.
    text: str
    # Convenience normalization (strip only); never replace `text` for evidence.
    text_normalized: str
    blocks: list[TextBlock]
    width: float
    height: float
    parser_name: str
    parser_version: str
    source_sha256: str
    # Fraction of page area covered by images; None = measurement unavailable.
    image_coverage: float | None = 0.0
    image_count: int = 0
    image_coverage_error: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    pages: list[ParsedPage]
    source_sha256: str
    metadata: dict[str, Any] = field(default_factory=dict)
    parser_name: str = "pymupdf"
    parser_version: str = ""
    # Non-ORM source identity: path label, "bytes", or caller-supplied artifact id.
    source_label: str | None = None
    artifact_id: UUID | None = None
