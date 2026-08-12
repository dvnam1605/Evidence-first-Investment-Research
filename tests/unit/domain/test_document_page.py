"""Unit tests for DOC-06 document page domain model."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from src.domain.document_page import DocumentPage
from src.domain.enums import ExtractionMethod


def _page(**overrides: object) -> DocumentPage:
    fields: dict[str, object] = {
        "id": uuid4(),
        "document_id": uuid4(),
        "page_number": 1,
        "text": "native text",
        "extraction_method": ExtractionMethod.NATIVE,
        "ocr_confidence": None,
        "width": 595.0,
        "height": 842.0,
        "created_at": datetime.now(tz=UTC),
    }
    fields.update(overrides)
    return DocumentPage(**fields)  # type: ignore[arg-type]


def test_extraction_method_values() -> None:
    assert {m.value for m in ExtractionMethod} == {"native", "ocr"}


def test_native_page_ok() -> None:
    page = _page()
    assert page.extraction_method is ExtractionMethod.NATIVE
    assert page.ocr_confidence is None


def test_ocr_page_requires_confidence() -> None:
    with pytest.raises(ValueError, match="ocr_confidence"):
        _page(extraction_method=ExtractionMethod.OCR, ocr_confidence=None, text="ocr")


def test_ocr_page_ok() -> None:
    page = _page(
        extraction_method=ExtractionMethod.OCR,
        ocr_confidence=0.91,
        text="ocr text",
    )
    assert page.ocr_confidence == pytest.approx(0.91)


def test_native_must_not_set_ocr_confidence() -> None:
    with pytest.raises(ValueError, match="native extraction"):
        _page(ocr_confidence=0.5)


def test_page_number_must_be_positive() -> None:
    with pytest.raises(ValueError, match="page_number"):
        _page(page_number=0)


def test_dimensions_must_be_positive() -> None:
    with pytest.raises(ValueError, match="width and height"):
        _page(width=0)
    with pytest.raises(ValueError, match="width and height"):
        _page(height=-1)
