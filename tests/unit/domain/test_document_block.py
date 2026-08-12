"""Unit tests for DOC-07 structured document block model."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from src.domain.document_block import BoundingBox, DocumentBlock
from src.domain.enums import BlockType


def _block(**overrides: object) -> DocumentBlock:
    fields: dict[str, object] = {
        "id": uuid4(),
        "page_id": uuid4(),
        "block_index": 0,
        "block_type": BlockType.TEXT,
        "bbox": BoundingBox(10.0, 20.0, 100.0, 40.0),
        "content": {"text": "Doanh thu thuần"},
        "created_at": datetime.now(tz=UTC),
    }
    fields.update(overrides)
    return DocumentBlock(**fields)  # type: ignore[arg-type]


def test_block_type_values() -> None:
    assert {t.value for t in BlockType} == {"text", "table", "image"}


def test_to_structure_matches_plan_shape() -> None:
    block = _block(
        block_type=BlockType.TABLE,
        content={"rows": [["A", "1"]], "cols": 2},
    )
    assert block.to_structure() == {
        "type": "table",
        "bbox": [10.0, 20.0, 100.0, 40.0],
        "content": {"rows": [["A", "1"]], "cols": 2},
    }


def test_missing_bbox_serializes_as_empty_list() -> None:
    block = _block(bbox=None, content={"text": "x"})
    assert block.to_structure()["bbox"] == []


def test_bbox_rejects_inverted_corners() -> None:
    with pytest.raises(ValueError, match="bbox"):
        BoundingBox(10.0, 20.0, 5.0, 40.0)


def test_block_index_must_be_non_negative() -> None:
    with pytest.raises(ValueError, match="block_index"):
        _block(block_index=-1)


def test_content_must_be_dict() -> None:
    with pytest.raises(ValueError, match="content"):
        _block(content=["not", "a", "dict"])  # type: ignore[arg-type]


def test_bbox_from_list_roundtrip() -> None:
    box = BoundingBox.from_list([1.0, 2.0, 3.0, 4.0])
    assert box.as_list() == [1.0, 2.0, 3.0, 4.0]
