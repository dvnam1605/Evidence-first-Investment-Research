"""Document processing pipeline (DOC-13). No ORM — bytes in, structured result out."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from src.domain.document_block import BoundingBox
from src.domain.enums import BlockType, DetectedFileType, ExtractionMethod, ProcessingStatus
from src.processing.classify.classifier import DocumentClassifier
from src.processing.classify.models import ClassificationInput, DocumentClassification
from src.processing.errors import ExcelParseError, PDFParseError, ProcessingError
from src.processing.excel.service import ExcelParser
from src.processing.file_type import FileTypeDetector
from src.processing.ocr.base import OCREngine
from src.processing.ocr.models import DocumentOCRFallbackResult, OCRResultStatus
from src.processing.pdf.detector import DocumentOCRDecision
from src.processing.pdf.models import ParsedDocument
from src.processing.pdf.service import PDFParser
from src.processing.sections.detector import StatementSectionDetector
from src.processing.sections.models import SectionDetectionResult, StatementSection
from src.processing.tables import (
    ExtractedTable,
    FinancialTableReconstructor,
    RawTableSource,
    ReconstructedTable,
    ReconstructionContext,
    ReconstructStatus,
    TableExtractionContext,
    TableExtractionResult,
    TableExtractionService,
    TableReconstructor,
)

PIPELINE_NAME = "document_processor"
PIPELINE_VERSION = "doc13-v1"


@dataclass(frozen=True, slots=True)
class PipelinePageDraft:
    """One page ready for persistence (document_pages)."""

    page_number: int
    text: str
    extraction_method: ExtractionMethod
    ocr_confidence: float | None
    width: float
    height: float


@dataclass(frozen=True, slots=True)
class PipelineBlockDraft:
    """One structured block ready for persistence (document_blocks)."""

    page_number: int
    block_index: int
    block_type: BlockType
    bbox: BoundingBox | None
    content: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DocumentProcessingResult:
    """In-memory processing outcome for one artifact."""

    artifact_id: UUID
    file_type: DetectedFileType
    mime_type: str | None
    parser: str
    parser_version: str
    status: ProcessingStatus
    warnings: tuple[str, ...]
    classification: DocumentClassification | None
    sections: SectionDetectionResult | None
    ocr_decision: DocumentOCRDecision | None
    ocr: DocumentOCRFallbackResult | None
    table_extraction: TableExtractionResult | None
    reconstructed_tables: tuple[ReconstructedTable, ...]
    pages: tuple[PipelinePageDraft, ...]
    blocks: tuple[PipelineBlockDraft, ...]
    error: str | None = None
    source_sha256: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DocumentProcessRequest:
    artifact_id: UUID
    data: bytes
    filename: str | None = None
    title: str | None = None
    document_type: str | None = None
    source_label: str | None = None


class DocumentProcessor:
    """
    Run DOC-02..DOC-12 for one binary.

    Does not touch the database or object storage. Callers persist pages/blocks/jobs.
    """

    def __init__(
        self,
        *,
        file_types: FileTypeDetector | None = None,
        pdf_parser: PDFParser | None = None,
        excel_parser: ExcelParser | None = None,
        classifier: DocumentClassifier | None = None,
        sections: StatementSectionDetector | None = None,
        tables: TableExtractionService | None = None,
        reconstructor: TableReconstructor | None = None,
        ocr_engine: OCREngine | None = None,
        raw_table_source: RawTableSource | None = None,
    ) -> None:
        self._file_types = file_types or FileTypeDetector()
        self._pdf = pdf_parser or PDFParser(ocr_engine=ocr_engine)
        self._excel = excel_parser or ExcelParser()
        self._classifier = classifier or DocumentClassifier()
        self._sections = sections or StatementSectionDetector()
        self._tables = tables or TableExtractionService()
        self._reconstructor = reconstructor or FinancialTableReconstructor()
        self._ocr_engine = ocr_engine
        self._raw_table_source = raw_table_source

    async def process(self, request: DocumentProcessRequest) -> DocumentProcessingResult:
        detected = self._file_types.detect(request.data, filename=request.filename)
        if detected.file_type is DetectedFileType.PDF:
            return await self._process_pdf(request, mime_type=detected.mime_type)
        if detected.file_type is DetectedFileType.XLSX:
            return await self._process_excel(request, mime_type=detected.mime_type)
        if detected.file_type is DetectedFileType.XLS:
            return DocumentProcessingResult(
                artifact_id=request.artifact_id,
                file_type=detected.file_type,
                mime_type=detected.mime_type,
                parser=PIPELINE_NAME,
                parser_version=PIPELINE_VERSION,
                status=ProcessingStatus.NEEDS_REVIEW,
                warnings=("xls_not_supported_use_xlsx",),
                classification=None,
                sections=None,
                ocr_decision=None,
                ocr=None,
                table_extraction=None,
                reconstructed_tables=(),
                pages=(),
                blocks=(),
                error="XLS is detected but only XLSX parsing is implemented",
            )
        return DocumentProcessingResult(
            artifact_id=request.artifact_id,
            file_type=detected.file_type,
            mime_type=detected.mime_type,
            parser=PIPELINE_NAME,
            parser_version=PIPELINE_VERSION,
            status=ProcessingStatus.FAILED,
            warnings=("unsupported_file_type",),
            classification=None,
            sections=None,
            ocr_decision=None,
            ocr=None,
            table_extraction=None,
            reconstructed_tables=(),
            pages=(),
            blocks=(),
            error=f"unsupported file type: {detected.file_type.value}",
        )

    async def _process_pdf(
        self,
        request: DocumentProcessRequest,
        *,
        mime_type: str | None,
    ) -> DocumentProcessingResult:
        warnings: list[str] = []
        try:
            parsed = await self._pdf.parse_bytes(
                request.data,
                artifact_id=request.artifact_id,
                source_label=request.source_label or request.filename or "bytes",
            )
        except PDFParseError as exc:
            return self._failed(
                request,
                file_type=DetectedFileType.PDF,
                mime_type=mime_type,
                error=str(exc),
                warnings=("pdf_parse_failed",),
            )
        except Exception as exc:  # noqa: BLE001 — surface unexpected parser failures
            return self._failed(
                request,
                file_type=DetectedFileType.PDF,
                mime_type=mime_type,
                error=f"{type(exc).__name__}: {exc}",
                warnings=("pdf_parse_failed",),
            )

        ocr_decision = self._pdf.assess_ocr(parsed)
        ocr_result: DocumentOCRFallbackResult | None = None
        if ocr_decision.needs_ocr:
            if self._ocr_engine is None:
                warnings.append("ocr_required_but_engine_not_configured")
            else:
                try:
                    ocr_result = await self._pdf.apply_ocr(
                        parsed, request.data, decision=ocr_decision
                    )
                    if ocr_result.needs_review:
                        warnings.append("ocr_needs_review")
                except ProcessingError as exc:
                    warnings.append(f"ocr_failed:{type(exc).__name__}")
                    warnings.append(str(exc)[:200])

        text_sample = _pdf_text_sample(parsed, ocr_result)
        classification = self._classifier.classify(
            ClassificationInput(
                title=request.title,
                filename=request.filename,
                text_sample=text_sample,
                metadata=_classification_metadata(request),
            )
        )
        if classification.reason in {"unmatched_needs_llm", "unmatched"}:
            warnings.append("classification_unmatched")

        sections = self._sections.detect_parsed_document(parsed)
        # Prefer OCR text for section detection when a page is image-only.
        if ocr_result is not None and ocr_result.pages:
            ocr_pages = [
                (page.page_number, page.text)
                for page in ocr_result.pages
                if page.text.strip()
            ]
            if ocr_pages:
                ocr_sections = self._sections.detect_page_texts(ocr_pages)
                if ocr_sections.hits:
                    sections = _merge_section_hits(sections, ocr_sections)

        table_context = TableExtractionContext(
            document_id=request.artifact_id,
            artifact_id=request.artifact_id,
            source_sha256=parsed.source_sha256,
            source_label=request.filename,
        )
        try:
            table_extraction = self._tables.extract_pdf(
                request.data,
                context=table_context,
            )
        except ProcessingError as exc:
            warnings.append(f"table_extraction_failed:{type(exc).__name__}")
            warnings.append(str(exc)[:200])
            table_extraction = TableExtractionResult(
                tables=(),
                context=table_context,
            )

        raw_tables = self._load_raw_tables(
            source_sha256=parsed.source_sha256,
            context=table_context,
            warnings=warnings,
        )
        if raw_tables is not None:
            warnings.extend(raw_tables.warnings)
            table_extraction = _merge_table_extractions(table_extraction, raw_tables)
            raw_sections = self._sections.detect_page_texts(_table_page_texts(raw_tables))
            if raw_sections.hits:
                sections = _merge_section_hits(sections, raw_sections)
        if table_extraction.needs_review:
            warnings.append("table_extraction_needs_review")

        reconstructed = self._reconstruct_tables(
            table_extraction,
            page_texts=_merge_page_texts(
                {page.page_number: page.text for page in parsed.pages},
                _table_page_texts(raw_tables) if raw_tables is not None else (),
            ),
            sections=sections,
            warnings=warnings,
        )

        pages = tuple(
            PipelinePageDraft(
                page_number=page.page_number,
                text=page.text,
                extraction_method=ExtractionMethod.NATIVE,
                ocr_confidence=None,
                width=page.width,
                height=page.height,
            )
            for page in parsed.pages
        )
        blocks = _pdf_blocks(parsed, ocr_result, reconstructed)

        status = _terminal_status(warnings)
        return DocumentProcessingResult(
            artifact_id=request.artifact_id,
            file_type=DetectedFileType.PDF,
            mime_type=mime_type,
            parser=parsed.parser_name,
            parser_version=f"{parsed.parser_version}|{PIPELINE_VERSION}",
            status=status,
            warnings=tuple(dict.fromkeys(warnings)),
            classification=classification,
            sections=sections,
            ocr_decision=ocr_decision,
            ocr=ocr_result,
            table_extraction=table_extraction,
            reconstructed_tables=reconstructed,
            pages=pages,
            blocks=blocks,
            source_sha256=parsed.source_sha256,
            metadata={
                "page_count": len(parsed.pages),
                "ocr_needed": ocr_decision.needs_ocr,
                "ocr_reason": ocr_decision.reason,
            },
        )

    async def _process_excel(
        self,
        request: DocumentProcessRequest,
        *,
        mime_type: str | None,
    ) -> DocumentProcessingResult:
        warnings: list[str] = []
        try:
            workbook = await self._excel.parse_bytes(
                request.data,
                artifact_id=request.artifact_id,
                source_label=request.source_label or request.filename or "bytes",
            )
        except ExcelParseError as exc:
            return self._failed(
                request,
                file_type=DetectedFileType.XLSX,
                mime_type=mime_type,
                error=str(exc),
                warnings=("excel_parse_failed",),
            )
        except Exception as exc:  # noqa: BLE001
            return self._failed(
                request,
                file_type=DetectedFileType.XLSX,
                mime_type=mime_type,
                error=f"{type(exc).__name__}: {exc}",
                warnings=("excel_parse_failed",),
            )

        sheet_sample = "\n".join(
            [sheet.name for sheet in workbook.sheets]
            + [
                cell.value_text or ""
                for sheet in workbook.sheets[:3]
                for cell in sheet.cells[:40]
                if cell.value_text
            ]
        )
        classification = self._classifier.classify(
            ClassificationInput(
                title=request.title,
                filename=request.filename,
                text_sample=sheet_sample[:4000],
                metadata=_classification_metadata(request),
            )
        )
        if classification.reason in {"unmatched_needs_llm", "unmatched"}:
            warnings.append("classification_unmatched")

        sections = self._sections.detect_workbook(workbook)
        table_extraction = self._tables.extract_workbook(
            workbook,
            context=TableExtractionContext(
                document_id=request.artifact_id,
                artifact_id=request.artifact_id,
                source_sha256=workbook.source_sha256,
                source_label=request.filename,
            ),
        )
        if table_extraction.needs_review:
            warnings.append("table_extraction_needs_review")

        page_texts = {
            sheet.index + 1: sheet.name for sheet in workbook.sheets
        }
        reconstructed = self._reconstruct_tables(
            table_extraction,
            page_texts=page_texts,
            sections=sections,
            warnings=warnings,
        )

        pages = tuple(
            PipelinePageDraft(
                page_number=sheet.index + 1,
                text=sheet.name,
                extraction_method=ExtractionMethod.NATIVE,
                ocr_confidence=None,
                width=1.0,
                height=1.0,
            )
            for sheet in workbook.sheets
        )
        blocks = _excel_blocks(reconstructed)

        status = _terminal_status(warnings)
        return DocumentProcessingResult(
            artifact_id=request.artifact_id,
            file_type=DetectedFileType.XLSX,
            mime_type=mime_type,
            parser=workbook.parser_name,
            parser_version=f"{workbook.parser_version}|{PIPELINE_VERSION}",
            status=status,
            warnings=tuple(dict.fromkeys(warnings)),
            classification=classification,
            sections=sections,
            ocr_decision=None,
            ocr=None,
            table_extraction=table_extraction,
            reconstructed_tables=reconstructed,
            pages=pages,
            blocks=blocks,
            source_sha256=workbook.source_sha256,
            metadata={"sheet_count": len(workbook.sheets)},
        )

    def _reconstruct_tables(
        self,
        extraction: TableExtractionResult,
        *,
        page_texts: dict[int, str],
        sections: SectionDetectionResult,
        warnings: list[str],
    ) -> tuple[ReconstructedTable, ...]:
        out: list[ReconstructedTable] = []
        for table in extraction.tables:
            hint = _section_hint_for_page(sections, table.page)
            context = ReconstructionContext(
                surrounding_text=page_texts.get(table.page),
                section_hint=hint,
            )
            rebuilt = self._reconstructor.reconstruct(table, context=context)
            if rebuilt.status is ReconstructStatus.NEEDS_REVIEW:
                warnings.append(f"table_reconstruction_needs_review:{table.table_id}")
            out.append(rebuilt)
        return tuple(out)

    def _load_raw_tables(
        self,
        *,
        source_sha256: str,
        context: TableExtractionContext,
        warnings: list[str],
    ) -> TableExtractionResult | None:
        if self._raw_table_source is None:
            return None
        try:
            return self._raw_table_source.load_for(
                source_sha256=source_sha256,
                context=context,
            )
        except Exception as exc:  # noqa: BLE001 - an external sidecar must be observable
            warnings.append(f"raw_table_source_failed:{type(exc).__name__}")
            warnings.append(str(exc)[:200])
            return None

    def _failed(
        self,
        request: DocumentProcessRequest,
        *,
        file_type: DetectedFileType,
        mime_type: str | None,
        error: str,
        warnings: tuple[str, ...],
    ) -> DocumentProcessingResult:
        return DocumentProcessingResult(
            artifact_id=request.artifact_id,
            file_type=file_type,
            mime_type=mime_type,
            parser=PIPELINE_NAME,
            parser_version=PIPELINE_VERSION,
            status=ProcessingStatus.FAILED,
            warnings=warnings,
            classification=None,
            sections=None,
            ocr_decision=None,
            ocr=None,
            table_extraction=None,
            reconstructed_tables=(),
            pages=(),
            blocks=(),
            error=error,
        )


def _classification_metadata(request: DocumentProcessRequest) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    if request.document_type:
        meta["document_type"] = request.document_type
    return meta


def _pdf_text_sample(
    parsed: ParsedDocument,
    ocr: DocumentOCRFallbackResult | None,
) -> str:
    parts = [page.text for page in parsed.pages[:5] if page.text.strip()]
    if ocr is not None:
        parts.extend(page.text for page in ocr.pages[:5] if page.text.strip())
    return "\n".join(parts)[:4000]


def _section_hint_for_page(
    sections: SectionDetectionResult, page: int
) -> StatementSection | None:
    found = {hit.section for hit in sections.hits if hit.page_number == page}
    if len(found) == 1:
        return next(iter(found))
    return None


def _merge_section_hits(
    primary: SectionDetectionResult,
    extra: SectionDetectionResult,
) -> SectionDetectionResult:
    merged = list(primary.hits)
    seen = {
        (hit.section, hit.page_number, hit.matched_text) for hit in merged
    }
    for hit in extra.hits:
        key = (hit.section, hit.page_number, hit.matched_text)
        if key in seen:
            continue
        merged.append(hit)
        seen.add(key)
    return SectionDetectionResult(
        hits=tuple(merged),
        method=f"{primary.method}+supplemental_text",
    )


def _merge_table_extractions(
    native: TableExtractionResult,
    raw: TableExtractionResult,
) -> TableExtractionResult:
    """Replace only overlapping full grids; partial sidecars supplement native output."""
    native_tables = tuple(
        table
        for table in native.tables
        if not any(_raw_table_replaces_native(candidate, table) for candidate in raw.tables)
    )
    return TableExtractionResult(
        tables=tuple(
            sorted(
                native_tables + raw.tables,
                key=lambda table: (table.page, table.table_index),
            )
        ),
        page_issues=native.page_issues + raw.page_issues,
        context=raw.context,
        warnings=native.warnings + raw.warnings,
    )


def _raw_table_replaces_native(raw: ExtractedTable, native: ExtractedTable) -> bool:
    if raw.page != native.page or "partial_statement_region" in raw.warnings:
        return False
    if raw.bbox is None or native.bbox is None:
        return False
    overlap_width = max(
        0.0,
        min(raw.bbox.x1, native.bbox.x1) - max(raw.bbox.x0, native.bbox.x0),
    )
    overlap_height = max(
        0.0,
        min(raw.bbox.y1, native.bbox.y1) - max(raw.bbox.y0, native.bbox.y0),
    )
    overlap = overlap_width * overlap_height
    raw_area = (raw.bbox.x1 - raw.bbox.x0) * (raw.bbox.y1 - raw.bbox.y0)
    native_area = (native.bbox.x1 - native.bbox.x0) * (native.bbox.y1 - native.bbox.y0)
    smaller_area = min(raw_area, native_area)
    return smaller_area > 0 and overlap / smaller_area >= 0.8


def _table_page_texts(
    extraction: TableExtractionResult,
) -> tuple[tuple[int, str], ...]:
    by_page: dict[int, list[str]] = {}
    for table in extraction.tables:
        lines = by_page.setdefault(table.page, [])
        for row in table.rows:
            text = " ".join(cell.raw_text for cell in row.cells if cell.raw_text)
            if text:
                lines.append(text)
    return tuple(
        (page, "\n".join(lines))
        for page, lines in sorted(by_page.items())
        if lines
    )


def _merge_page_texts(
    primary: dict[int, str],
    extra: tuple[tuple[int, str], ...],
) -> dict[int, str]:
    merged = dict(primary)
    for page, text in extra:
        if not text:
            continue
        merged[page] = "\n".join(part for part in (merged.get(page, ""), text) if part)
    return merged


def _terminal_status(warnings: list[str]) -> ProcessingStatus:
    review_prefixes = (
        "ocr_required_but_engine_not_configured",
        "ocr_needs_review",
        "ocr_failed",
        "raw_table_source_failed",
        "table_extraction_failed",
        "table_extraction_needs_review",
        "table_reconstruction_needs_review",
        "classification_unmatched",
        "xls_not_supported",
    )
    if any(
        warning == token or warning.startswith(f"{token}:") or warning.startswith(token)
        for warning in warnings
        for token in review_prefixes
    ):
        return ProcessingStatus.NEEDS_REVIEW
    return ProcessingStatus.PROCESSED


def _pdf_blocks(
    parsed: ParsedDocument,
    ocr: DocumentOCRFallbackResult | None,
    reconstructed: tuple[ReconstructedTable, ...],
) -> tuple[PipelineBlockDraft, ...]:
    drafts: list[PipelineBlockDraft] = []
    indexes: dict[int, int] = {}

    def next_index(page_number: int) -> int:
        idx = indexes.get(page_number, 0)
        indexes[page_number] = idx + 1
        return idx

    for page in parsed.pages:
        for block in page.blocks:
            bbox = None
            if block.bbox is not None:
                bbox = BoundingBox(
                    x0=block.bbox.x0,
                    y0=block.bbox.y0,
                    x1=block.bbox.x1,
                    y1=block.bbox.y1,
                )
            drafts.append(
                PipelineBlockDraft(
                    page_number=page.page_number,
                    block_index=next_index(page.page_number),
                    block_type=BlockType.TEXT,
                    bbox=bbox,
                    content={
                        "source": "native",
                        "text": block.text,
                        "parser_name": page.parser_name,
                        "parser_version": page.parser_version,
                    },
                )
            )

    if ocr is not None:
        for ocr_page in ocr.pages:
            drafts.append(
                PipelineBlockDraft(
                    page_number=ocr_page.page_number,
                    block_index=next_index(ocr_page.page_number),
                    block_type=BlockType.TEXT,
                    bbox=None,
                    content={
                        "source": "ocr",
                        "engine": ocr_page.engine,
                        "engine_version": ocr_page.engine_version,
                        "text": ocr_page.text,
                        "confidence": ocr_page.confidence,
                        "status": ocr_page.status.value,
                        "quality_reason": ocr_page.quality_reason,
                        "decision_reason": ocr_page.decision_reason,
                        "raw": list(ocr_page.raw),
                    },
                )
            )
            if ocr_page.status is OCRResultStatus.NEEDS_REVIEW:
                # Already flagged via ocr_needs_review at pipeline level.
                pass

    for table in reconstructed:
        drafts.append(
            PipelineBlockDraft(
                page_number=table.raw.page,
                block_index=next_index(table.raw.page),
                block_type=BlockType.TABLE,
                bbox=table.raw.bbox,
                content={
                    "source": "table_reconstruction",
                    "status": table.status.value,
                    "warnings": list(table.warnings),
                    "intermediate": table.to_intermediate_dict(),
                },
            )
        )
    return tuple(drafts)


def _excel_blocks(
    reconstructed: tuple[ReconstructedTable, ...],
) -> tuple[PipelineBlockDraft, ...]:
    drafts: list[PipelineBlockDraft] = []
    indexes: dict[int, int] = {}
    for table in reconstructed:
        page = table.raw.page
        idx = indexes.get(page, 0)
        indexes[page] = idx + 1
        drafts.append(
            PipelineBlockDraft(
                page_number=page,
                block_index=idx,
                block_type=BlockType.TABLE,
                bbox=None,
                content={
                    "source": "table_reconstruction",
                    "status": table.status.value,
                    "warnings": list(table.warnings),
                    "intermediate": table.to_intermediate_dict(),
                    "sheet_name": table.raw.source_label,
                },
            )
        )
    return tuple(drafts)
