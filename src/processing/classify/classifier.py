"""Document classifier: patterns → metadata → optional LLM."""

from __future__ import annotations

from typing import Protocol

from src.domain.enums import DocumentType
from src.processing.classify.models import (
    ClassificationInput,
    ClassificationMethod,
    DocumentClass,
    DocumentClassification,
)
from src.processing.classify.patterns import match_patterns

DEFAULT_ACCEPT_CONFIDENCE = 0.60


class LLMDocumentClassifier(Protocol):
    def classify(self, document: ClassificationInput) -> DocumentClassification: ...


_METADATA_CLASS_KEYS = ("document_class", "classified_as", "doc_class")
_METADATA_TYPE_KEYS = ("document_type", "doc_type", "type")

_DOCUMENT_TYPE_TO_CLASS: dict[str, DocumentClass] = {
    DocumentType.FINANCIAL_STATEMENT.value: DocumentClass.FINANCIAL_STATEMENT,
    DocumentType.MATERIAL_DISCLOSURE.value: DocumentClass.MATERIAL_DISCLOSURE,
    DocumentType.PERIODIC_REPORT.value: DocumentClass.ANNUAL_REPORT,
    DocumentType.EVENT_DISCLOSURE.value: DocumentClass.MATERIAL_DISCLOSURE,
    DocumentType.OTHER.value: DocumentClass.OTHER,
    # Direct DOC-09 labels allowed in metadata too.
    **{c.value: c for c in DocumentClass},
}


class DocumentClassifier:
    """
    Classify filings without LLM by default.

    Pipeline: deterministic patterns → metadata mapping → optional LLM.
    """

    def __init__(
        self,
        *,
        llm: LLMDocumentClassifier | None = None,
        accept_confidence: float = DEFAULT_ACCEPT_CONFIDENCE,
    ) -> None:
        if not (0.0 <= accept_confidence <= 1.0):
            raise ValueError("accept_confidence must be in [0, 1]")
        self._llm = llm
        self._accept_confidence = accept_confidence

    def classify(self, document: ClassificationInput) -> DocumentClassification:
        pattern_hit = match_patterns(document.title, document.filename, document.text_sample)
        if pattern_hit is not None:
            document_class, confidence, rule_name = pattern_hit
            if confidence >= self._accept_confidence:
                return DocumentClassification(
                    document_class=document_class,
                    method=ClassificationMethod.PATTERN,
                    confidence=confidence,
                    matched_pattern=rule_name,
                    reason="pattern_match",
                )

        metadata_hit = self._classify_metadata(document)
        if metadata_hit is not None and metadata_hit.confidence >= self._accept_confidence:
            return metadata_hit

        if self._llm is not None:
            return self._llm.classify(document)

        if pattern_hit is not None:
            document_class, confidence, rule_name = pattern_hit
            return DocumentClassification(
                document_class=document_class,
                method=ClassificationMethod.PATTERN,
                confidence=confidence,
                matched_pattern=rule_name,
                reason="pattern_below_threshold",
            )

        return DocumentClassification(
            document_class=DocumentClass.OTHER,
            method=ClassificationMethod.PATTERN,
            confidence=0.0,
            matched_pattern=None,
            reason="unmatched_needs_llm" if self._llm is None else "unmatched",
        )

    def _classify_metadata(
        self, document: ClassificationInput
    ) -> DocumentClassification | None:
        meta = document.metadata
        if not meta:
            return None

        for key in _METADATA_CLASS_KEYS:
            raw = meta.get(key)
            if raw is None:
                continue
            mapped = _DOCUMENT_TYPE_TO_CLASS.get(str(raw).strip().lower())
            if mapped is not None:
                return DocumentClassification(
                    document_class=mapped,
                    method=ClassificationMethod.METADATA,
                    confidence=0.80,
                    matched_pattern=None,
                    reason=f"metadata:{key}",
                )

        for key in _METADATA_TYPE_KEYS:
            raw = meta.get(key)
            if raw is None:
                continue
            mapped = _DOCUMENT_TYPE_TO_CLASS.get(str(raw).strip().lower())
            if mapped is not None:
                return DocumentClassification(
                    document_class=mapped,
                    method=ClassificationMethod.METADATA,
                    confidence=0.75,
                    matched_pattern=None,
                    reason=f"metadata:{key}",
                )
        return None
