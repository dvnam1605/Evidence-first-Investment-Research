"""Document processing job domain model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.enums import ProcessingStatus

_TERMINAL = frozenset(
    {
        ProcessingStatus.PROCESSED,
        ProcessingStatus.NEEDS_REVIEW,
        ProcessingStatus.FAILED,
    }
)


@dataclass(frozen=True, slots=True)
class DocumentProcessingJob:
    id: UUID
    artifact_id: UUID
    status: ProcessingStatus
    parser: str | None
    parser_version: str | None
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def validate_terminal_status(status: ProcessingStatus) -> ProcessingStatus:
        if status not in _TERMINAL:
            raise ValueError(
                "terminal status must be PROCESSED, NEEDS_REVIEW, or FAILED"
            )
        return status
