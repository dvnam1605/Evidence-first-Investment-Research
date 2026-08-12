"""Document version resolver."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Protocol

from src.domain.enums import VersionResolutionType
from src.ingestion.models import DocumentCandidate, VersionResolution


class HasId(Protocol):
    id: uuid.UUID


class DocumentVersionResolver:
    async def resolve(
        self,
        incoming: DocumentCandidate,
        *,
        existing_by_source: HasId | None,
        parent_by_supersedes: HasId | None,
    ) -> VersionResolution:
        if existing_by_source is not None:
            return VersionResolution(
                resolution=VersionResolutionType.DUPLICATE,
                existing_document_id=str(existing_by_source.id),
            )

        # CORRECTION must be driven by the incoming candidate, not merely by whether
        # a predecessor exists.
        if incoming.source_document.is_correction:
            parent_id = (
                str(parent_by_supersedes.id) if parent_by_supersedes is not None else None
            )
            return VersionResolution(
                resolution=VersionResolutionType.CORRECTION,
                parent_document_id=parent_id,
            )

        if parent_by_supersedes is not None:
            return VersionResolution(
                resolution=VersionResolutionType.NEW_VERSION,
                parent_document_id=str(parent_by_supersedes.id),
            )

        return VersionResolution(resolution=VersionResolutionType.NEW_DOCUMENT)

    async def apply_parent_updates(
        self,
        *,
        parent_document_id: uuid.UUID | None,
        mark_not_latest: Callable[[uuid.UUID], Awaitable[None]],
    ) -> None:
        if parent_document_id is not None:
            await mark_not_latest(parent_document_id)
