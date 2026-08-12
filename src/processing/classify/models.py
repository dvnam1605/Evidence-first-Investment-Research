"""Document classification models (DOC-09)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DocumentClass(StrEnum):
    """Processing-layer document classes (distinct from ingestion DocumentType)."""

    FINANCIAL_STATEMENT = "financial_statement"
    ANNUAL_REPORT = "annual_report"
    MANAGEMENT_EXPLANATION = "management_explanation"
    BOARD_RESOLUTION = "board_resolution"
    SHAREHOLDER_DOCUMENT = "shareholder_document"
    MATERIAL_DISCLOSURE = "material_disclosure"
    OTHER = "other"


class ClassificationMethod(StrEnum):
    PATTERN = "pattern"
    METADATA = "metadata"
    LLM = "llm"


@dataclass(frozen=True, slots=True)
class ClassificationInput:
    """Signals available before / during processing."""

    title: str | None = None
    filename: str | None = None
    text_sample: str | None = None
    # Caller-supplied metadata (e.g. ingestion DocumentType, IR labels).
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DocumentClassification:
    document_class: DocumentClass
    method: ClassificationMethod
    confidence: float
    matched_pattern: str | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence must be in [0, 1]")
