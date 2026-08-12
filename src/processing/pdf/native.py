"""Native digital PDF parsing via PyMuPDF."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
from uuid import UUID

import fitz  # type: ignore[import-untyped]

from src.processing.errors import PDFParseError
from src.processing.pdf.models import BoundingBox, ParsedDocument, ParsedPage, TextBlock

PARSER_NAME = "pymupdf"


def _pymupdf_version() -> str:
    try:
        return version("pymupdf")
    except PackageNotFoundError:
        return "unknown"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _extract_blocks(page: fitz.Page) -> list[TextBlock]:
    """Extract text blocks with bboxes; preserve span text without strip()."""
    blocks: list[TextBlock] = []
    raw = page.get_text("dict")
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            # Skip image blocks in native text extraction.
            continue
        lines: list[str] = []
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            # Keep exact span concatenation (no strip) for fidelity.
            line_text = "".join(str(span.get("text", "")) for span in spans)
            if line_text:
                lines.append(line_text)
        text = "\n".join(lines)
        if text == "":
            continue
        bbox_raw = block.get("bbox")
        bbox = (
            BoundingBox(
                x0=float(bbox_raw[0]),
                y0=float(bbox_raw[1]),
                x1=float(bbox_raw[2]),
                y1=float(bbox_raw[3]),
            )
            if bbox_raw is not None and len(bbox_raw) >= 4
            else None
        )
        blocks.append(TextBlock(text=text, bbox=bbox))
    return blocks


@dataclass(frozen=True, slots=True)
class ImageCoverageSignal:
    """Measured image coverage; coverage=None means unavailable/failed."""

    coverage: float | None
    image_count: int
    error: str | None = None


def _image_coverage(page: fitz.Page) -> ImageCoverageSignal:
    """Approximate fraction of page area covered by raster images."""
    page_area = abs(float(page.rect.width) * float(page.rect.height))
    images = list(page.get_images(full=True))
    image_count = len(images)
    if image_count == 0:
        return ImageCoverageSignal(coverage=0.0, image_count=0, error=None)
    if page_area <= 0:
        return ImageCoverageSignal(
            coverage=None,
            image_count=image_count,
            error="page_area_non_positive",
        )

    covered = 0.0
    geometry_errors: list[str] = []
    geometry_ok = 0
    for image in images:
        xref = int(image[0])
        try:
            rects = page.get_image_rects(xref)
        except Exception as exc:  # noqa: BLE001 - PyMuPDF raises varied types
            geometry_errors.append(f"xref={xref}:{type(exc).__name__}")
            continue
        if not rects:
            geometry_errors.append(f"xref={xref}:no_rects")
            continue
        geometry_ok += 1
        for rect in rects:
            covered += abs(float(rect.width) * float(rect.height))

    if geometry_ok == 0:
        return ImageCoverageSignal(
            coverage=None,
            image_count=image_count,
            error="; ".join(geometry_errors) or "image_geometry_unavailable",
        )

    return ImageCoverageSignal(
        coverage=min(covered / page_area, 1.0),
        image_count=image_count,
        error="; ".join(geometry_errors) if geometry_errors else None,
    )


def _document_metadata(doc: fitz.Document) -> dict[str, Any]:
    meta = dict(doc.metadata or {})
    return {str(k): v for k, v in meta.items() if v not in (None, "")}


def _open_pdf_from_bytes(data: bytes) -> fitz.Document:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 - PyMuPDF raises varied types
        raise PDFParseError(f"Failed to open PDF bytes: {exc}") from exc

    # Encrypted without credentials: treat as parse failure.
    if doc.is_encrypted and not doc.authenticate(""):
        doc.close()
        raise PDFParseError("PDF is encrypted and cannot be parsed without a password")
    return doc


class NativePDFParser:
    """Synchronous PyMuPDF extractor used by the async PDFParser service."""

    def parse_path(
        self,
        path: Path,
        *,
        artifact_id: UUID | None = None,
    ) -> ParsedDocument:
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")
        data = path.read_bytes()
        return self.parse_bytes(
            data,
            artifact_id=artifact_id,
            source_label=str(path),
        )

    def parse_bytes(
        self,
        data: bytes,
        *,
        artifact_id: UUID | None = None,
        source_label: str | None = "bytes",
    ) -> ParsedDocument:
        if not data:
            raise PDFParseError("PDF bytes must not be empty")

        source_sha256 = _sha256(data)
        parser_version = _pymupdf_version()
        doc = _open_pdf_from_bytes(data)
        try:
            return self._parse_document(
                doc,
                source_sha256=source_sha256,
                parser_version=parser_version,
                source_label=source_label,
                artifact_id=artifact_id,
            )
        finally:
            doc.close()

    def _parse_document(
        self,
        doc: fitz.Document,
        *,
        source_sha256: str,
        parser_version: str,
        source_label: str | None,
        artifact_id: UUID | None,
    ) -> ParsedDocument:
        if doc.page_count == 0:
            raise PDFParseError("PDF has zero pages")

        pages: list[ParsedPage] = []
        for index in range(doc.page_count):
            page = doc.load_page(index)
            rect = page.rect
            raw_text = page.get_text("text")
            blocks = _extract_blocks(page)
            coverage = _image_coverage(page)
            pages.append(
                ParsedPage(
                    page_number=index + 1,
                    text=raw_text,
                    text_normalized=raw_text.strip(),
                    blocks=blocks,
                    width=float(rect.width),
                    height=float(rect.height),
                    parser_name=PARSER_NAME,
                    parser_version=parser_version,
                    source_sha256=source_sha256,
                    image_coverage=coverage.coverage,
                    image_count=coverage.image_count,
                    image_coverage_error=coverage.error,
                )
            )
        return ParsedDocument(
            pages=pages,
            source_sha256=source_sha256,
            metadata=_document_metadata(doc),
            parser_name=PARSER_NAME,
            parser_version=parser_version,
            source_label=source_label,
            artifact_id=artifact_id,
        )
