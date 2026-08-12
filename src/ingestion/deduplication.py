"""Document deduplication helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.ingestion.models import DocumentCandidate, SourceDocument


class HasObjectPath(Protocol):
    object_path: str


@dataclass(frozen=True, slots=True)
class DeduplicationResult:
    skip_download: bool
    skip_persist: bool
    existing_object_path: str | None = None
    reason: str | None = None


class DocumentDeduplicator:
    def evaluate(
        self,
        *,
        source_document: SourceDocument,
        sha256: str,
        existing_by_source: HasObjectPath | None,
        existing_by_sha256: HasObjectPath | None,
    ) -> DeduplicationResult:
        if existing_by_source is not None:
            return DeduplicationResult(
                skip_download=True,
                skip_persist=True,
                existing_object_path=existing_by_source.object_path,
                reason="source_document_id",
            )

        if existing_by_sha256 is not None:
            return DeduplicationResult(
                skip_download=True,
                skip_persist=False,
                existing_object_path=existing_by_sha256.object_path,
                reason="sha256",
            )

        return DeduplicationResult(skip_download=False, skip_persist=False)

    def candidate_key(self, candidate: DocumentCandidate) -> str:
        return (
            f"{candidate.source_document.source.value}:"
            f"{candidate.source_document.source_document_id}:"
            f"{candidate.attachment.download_reference}"
        )
