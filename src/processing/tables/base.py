"""Table extraction protocol."""

from __future__ import annotations

from typing import Protocol

from src.processing.tables.models import TableExtractionResult


class TableExtractor(Protocol):
    """Extract raw tables without financial normalization."""

    @property
    def name(self) -> str: ...

    def extract(self, source: object) -> TableExtractionResult: ...
