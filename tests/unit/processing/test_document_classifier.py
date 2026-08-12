"""Unit tests for DOC-09 document classifier."""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.enums import DocumentType
from src.processing.classify import (
    ClassificationInput,
    ClassificationMethod,
    DocumentClass,
    DocumentClassification,
    DocumentClassifier,
)


@dataclass
class FakeLLM:
    result: DocumentClassification

    def classify(self, document: ClassificationInput) -> DocumentClassification:
        _ = document
        return self.result


def test_financial_statement_vietnamese_pattern() -> None:
    result = DocumentClassifier().classify(
        ClassificationInput(title="Báo cáo tài chính hợp nhất quý 1/2026")
    )
    assert result.document_class == DocumentClass.FINANCIAL_STATEMENT
    assert result.method == ClassificationMethod.PATTERN
    assert result.confidence >= 0.9
    assert result.matched_pattern == "financial_statement"


def test_financial_statement_english_and_filename() -> None:
    result = DocumentClassifier().classify(
        ClassificationInput(
            title=None,
            filename="FPT_audited_consolidated_financial_statements_2025.pdf",
        )
    )
    assert result.document_class == DocumentClass.FINANCIAL_STATEMENT
    assert result.method == ClassificationMethod.PATTERN


def test_annual_report_pattern() -> None:
    result = DocumentClassifier().classify(
        ClassificationInput(title="Báo cáo thường niên 2025")
    )
    assert result.document_class == DocumentClass.ANNUAL_REPORT


def test_board_resolution_pattern() -> None:
    result = DocumentClassifier().classify(
        ClassificationInput(title="Nghị quyết HĐQT về việc thông qua kế hoạch")
    )
    assert result.document_class == DocumentClass.BOARD_RESOLUTION


def test_shareholder_and_material_patterns() -> None:
    shareholder = DocumentClassifier().classify(
        ClassificationInput(title="Tài liệu Đại hội cổ đông thường niên 2026")
    )
    assert shareholder.document_class == DocumentClass.SHAREHOLDER_DOCUMENT

    material = DocumentClassifier().classify(
        ClassificationInput(title="Information disclosure about unusual transaction")
    )
    assert material.document_class == DocumentClass.MATERIAL_DISCLOSURE


def test_management_explanation_pattern() -> None:
    result = DocumentClassifier().classify(
        ClassificationInput(title="Thuyết minh báo cáo tài chính riêng năm 2025")
    )
    assert result.document_class == DocumentClass.MANAGEMENT_EXPLANATION


def test_metadata_used_when_patterns_miss() -> None:
    result = DocumentClassifier().classify(
        ClassificationInput(
            title="Untitled filing",
            metadata={"document_type": DocumentType.FINANCIAL_STATEMENT.value},
        )
    )
    assert result.document_class == DocumentClass.FINANCIAL_STATEMENT
    assert result.method == ClassificationMethod.METADATA
    assert result.confidence == 0.75


def test_patterns_beat_metadata() -> None:
    result = DocumentClassifier().classify(
        ClassificationInput(
            title="Báo cáo thường niên 2024",
            metadata={"document_type": DocumentType.OTHER.value},
        )
    )
    assert result.document_class == DocumentClass.ANNUAL_REPORT
    assert result.method == ClassificationMethod.PATTERN


def test_unmatched_returns_other_without_llm() -> None:
    result = DocumentClassifier().classify(
        ClassificationInput(title="Internal memo draft v3")
    )
    assert result.document_class == DocumentClass.OTHER
    assert result.method == ClassificationMethod.PATTERN
    assert result.confidence == 0.0
    assert result.reason == "unmatched_needs_llm"


def test_llm_fallback_only_when_needed() -> None:
    llm = FakeLLM(
        DocumentClassification(
            document_class=DocumentClass.MATERIAL_DISCLOSURE,
            method=ClassificationMethod.LLM,
            confidence=0.70,
            reason="llm",
        )
    )
    # Pattern already matches — LLM must not run (FakeLLM would still return if called;
    # assert method stays PATTERN).
    patterned = DocumentClassifier(llm=llm).classify(
        ClassificationInput(title="Financial statements Q2 2026")
    )
    assert patterned.method == ClassificationMethod.PATTERN

    unmatched = DocumentClassifier(llm=llm).classify(
        ClassificationInput(title="Internal memo draft v3")
    )
    assert unmatched.method == ClassificationMethod.LLM
    assert unmatched.document_class == DocumentClass.MATERIAL_DISCLOSURE
