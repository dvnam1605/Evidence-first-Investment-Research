"""Unit tests for DOC-01 processing job domain model."""

from __future__ import annotations

import pytest
from src.domain.enums import ProcessingStatus
from src.domain.processing_job import DocumentProcessingJob


def test_processing_status_values_match_plan() -> None:
    assert {s.value for s in ProcessingStatus} == {
        "PENDING",
        "PROCESSING",
        "PROCESSED",
        "NEEDS_REVIEW",
        "FAILED",
    }


def test_validate_terminal_status_accepts_terminals() -> None:
    for status in (
        ProcessingStatus.PROCESSED,
        ProcessingStatus.NEEDS_REVIEW,
        ProcessingStatus.FAILED,
    ):
        assert DocumentProcessingJob.validate_terminal_status(status) is status


def test_validate_terminal_status_rejects_non_terminal() -> None:
    with pytest.raises(ValueError, match="terminal status"):
        DocumentProcessingJob.validate_terminal_status(ProcessingStatus.PENDING)
    with pytest.raises(ValueError, match="terminal status"):
        DocumentProcessingJob.validate_terminal_status(ProcessingStatus.PROCESSING)
