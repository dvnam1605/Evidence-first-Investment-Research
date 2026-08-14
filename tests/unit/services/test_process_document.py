"""Service lifecycle tests for DOC-01/DOC-13 processing persistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from uuid import UUID, uuid4

import fitz
import pytest
from src.domain.enums import ProcessingStatus
from src.processing.pipeline import DocumentProcessor
from src.services import process_document as service_module
from src.services.process_document import ProcessDocumentError, ProcessDocumentService
from src.storage.errors import StorageError


def _pdf_bytes() -> bytes:
    doc = fitz.open()
    try:
        page = doc.new_page()
        page.insert_text((72, 72), "CONSOLIDATED INCOME STATEMENT\nRevenue 1000")
        return doc.tobytes()
    finally:
        doc.close()


@dataclass
class _Store:
    document_id: UUID = field(default_factory=uuid4)
    publication_id: UUID = field(default_factory=uuid4)
    raw_object_id: UUID = field(default_factory=uuid4)
    jobs: list[SimpleNamespace] = field(default_factory=list)
    job_states: list[ProcessingStatus] = field(default_factory=list)
    pages: list[SimpleNamespace] = field(default_factory=list)
    blocks: list[SimpleNamespace] = field(default_factory=list)
    commits: int = 0
    rollbacks: int = 0

    @property
    def artifact(self) -> SimpleNamespace:
        return SimpleNamespace(
            id=self.document_id,
            publication_id=self.publication_id,
            raw_object_id=self.raw_object_id,
            filename="statement.pdf",
        )


class _Session:
    def __init__(self, store: _Store) -> None:
        self._store = store

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def get(self, *_: object) -> SimpleNamespace:
        return SimpleNamespace(title="FPT financial statement", document_type="financial_statement")

    async def commit(self) -> None:
        self._store.commits += 1

    async def rollback(self) -> None:
        self._store.rollbacks += 1


class _SessionFactory:
    def __init__(self, store: _Store) -> None:
        self._store = store

    def __call__(self) -> _Session:
        return _Session(self._store)


class _ArtifactRepo:
    def __init__(self, store: _Store) -> None:
        self._store = store

    async def get_by_id(self, document_id: UUID) -> SimpleNamespace | None:
        return self._store.artifact if document_id == self._store.document_id else None


class _RawRepo:
    def __init__(self, store: _Store) -> None:
        self._store = store

    async def get_by_id(self, raw_object_id: UUID) -> SimpleNamespace | None:
        if raw_object_id != self._store.raw_object_id:
            return None
        return SimpleNamespace(object_path="raw/statement.pdf")


class _JobRepo:
    def __init__(self, store: _Store) -> None:
        self._store = store

    async def create_pending(self, *, artifact_id: UUID) -> SimpleNamespace:
        job = SimpleNamespace(
            id=uuid4(), artifact_id=artifact_id, status=ProcessingStatus.PENDING
        )
        self._store.jobs.append(job)
        self._store.job_states.append(job.status)
        return job

    async def mark_stale_processing_failed(self, **_: object) -> int:
        count = 0
        for job in self._store.jobs:
            if job.status is ProcessingStatus.PROCESSING:
                job.status = ProcessingStatus.FAILED
                self._store.job_states.append(job.status)
                count += 1
        return count

    async def mark_processing(self, **_: object) -> SimpleNamespace:
        job = self._store.jobs[-1]
        job.status = ProcessingStatus.PROCESSING
        self._store.job_states.append(job.status)
        return job

    async def mark_finished(self, *, status: ProcessingStatus, **_: object) -> SimpleNamespace:
        job = self._store.jobs[-1]
        job.status = status
        self._store.job_states.append(job.status)
        return job


class _FailingStartJobRepo(_JobRepo):
    async def mark_processing(self, **_: object) -> SimpleNamespace:
        raise RuntimeError("job start transition failed")


class _PageRepo:
    def __init__(self, store: _Store) -> None:
        self._store = store

    async def delete_by_document(self, **_: object) -> int:
        count = len(self._store.pages)
        self._store.pages.clear()
        return count

    async def create(self, **fields: object) -> SimpleNamespace:
        page = SimpleNamespace(id=uuid4(), **fields)
        self._store.pages.append(page)
        return page


class _BlockRepo:
    def __init__(self, store: _Store) -> None:
        self._store = store

    async def delete_for_document(self, **_: object) -> int:
        count = len(self._store.blocks)
        self._store.blocks.clear()
        return count

    async def create(self, **fields: object) -> SimpleNamespace:
        block = SimpleNamespace(id=uuid4(), **fields)
        self._store.blocks.append(block)
        return block


class _Storage:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def get(self, _: str) -> bytes:
        return self._data


class _FailingStorage:
    async def get(self, _: str) -> bytes:
        raise StorageError("object storage unavailable")


class _FailingPageRepo(_PageRepo):
    async def create(self, **_: object) -> SimpleNamespace:
        raise RuntimeError("page persistence failed")


class _FailingProcessor:
    async def process(self, _: object) -> object:
        raise RuntimeError("processor exploded")


def _service(
    monkeypatch: pytest.MonkeyPatch,
    store: _Store,
    *,
    processor: object,
    storage: object | None = None,
    page_repository: type[_PageRepo] = _PageRepo,
    job_repository: type[_JobRepo] = _JobRepo,
) -> ProcessDocumentService:
    monkeypatch.setattr(
        service_module, "DocumentArtifactRepository", lambda _: _ArtifactRepo(store)
    )
    monkeypatch.setattr(service_module, "RawObjectRepository", lambda _: _RawRepo(store))
    monkeypatch.setattr(
        service_module, "DocumentProcessingJobRepository", lambda _: job_repository(store)
    )
    monkeypatch.setattr(
        service_module, "DocumentPageRepository", lambda _: page_repository(store)
    )
    monkeypatch.setattr(service_module, "DocumentBlockRepository", lambda _: _BlockRepo(store))
    return ProcessDocumentService(
        session_factory=_SessionFactory(store),  # type: ignore[arg-type]
        storage=storage or _Storage(_pdf_bytes()),  # type: ignore[arg-type]
        processor=processor,  # type: ignore[arg-type]
    )


async def test_processor_exception_marks_committed_job_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _Store()
    service = _service(monkeypatch, store, processor=_FailingProcessor())

    with pytest.raises(ProcessDocumentError, match="processor exploded"):
        await service.process_document(store.document_id)

    assert store.job_states == [
        ProcessingStatus.PENDING,
        ProcessingStatus.PROCESSING,
        ProcessingStatus.FAILED,
    ]
    assert store.rollbacks == 1
    assert store.commits == 3


async def test_start_transition_exception_marks_committed_job_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _Store()
    service = _service(
        monkeypatch,
        store,
        processor=DocumentProcessor(ocr_engine=None),
        job_repository=_FailingStartJobRepo,
    )

    with pytest.raises(ProcessDocumentError, match="job start transition failed"):
        await service.process_document(store.document_id)

    assert store.job_states == [ProcessingStatus.PENDING, ProcessingStatus.FAILED]
    assert store.rollbacks == 1


async def test_storage_exception_marks_committed_job_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _Store()
    service = _service(
        monkeypatch,
        store,
        processor=DocumentProcessor(ocr_engine=None),
        storage=_FailingStorage(),
    )

    with pytest.raises(ProcessDocumentError, match="object storage unavailable"):
        await service.process_document(store.document_id)

    assert store.job_states[-1] is ProcessingStatus.FAILED
    assert store.rollbacks == 1


async def test_persistence_exception_marks_committed_job_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _Store()
    service = _service(
        monkeypatch,
        store,
        processor=DocumentProcessor(ocr_engine=None),
        page_repository=_FailingPageRepo,
    )

    with pytest.raises(ProcessDocumentError, match="page persistence failed"):
        await service.process_document(store.document_id)

    assert store.job_states[-1] is ProcessingStatus.FAILED
    assert store.rollbacks == 1


async def test_rerun_replaces_page_and_block_output_without_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _Store()
    service = _service(monkeypatch, store, processor=DocumentProcessor(ocr_engine=None))

    first = await service.process_document(store.document_id)
    first_page_count = len(store.pages)
    first_block_count = len(store.blocks)
    second = await service.process_document(store.document_id)

    assert first.job.status in {ProcessingStatus.PROCESSED, ProcessingStatus.NEEDS_REVIEW}
    assert second.job.status in {ProcessingStatus.PROCESSED, ProcessingStatus.NEEDS_REVIEW}
    assert len(store.pages) == first_page_count == 1
    assert len(store.blocks) == first_block_count
    assert [page.page_number for page in store.pages] == [1]


async def test_next_attempt_recovers_stale_processing_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _Store()
    store.jobs.append(
        SimpleNamespace(
            id=uuid4(),
            artifact_id=store.document_id,
            status=ProcessingStatus.PROCESSING,
        )
    )
    service = _service(monkeypatch, store, processor=DocumentProcessor(ocr_engine=None))

    outcome = await service.process_document(store.document_id)

    assert store.jobs[0].status is ProcessingStatus.FAILED
    assert outcome.job.status in {
        ProcessingStatus.PROCESSED,
        ProcessingStatus.NEEDS_REVIEW,
    }
