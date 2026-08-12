"""Content-based file type detection (never trust filename alone)."""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

import filetype  # type: ignore[import-untyped]

from src.domain.enums import DetectedFileType

PDF_MAGIC = b"%PDF"
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP_MAGIC = b"PK"
HTML_MARKERS = (b"<!doctype html", b"<html")

_MIME_TO_TYPE: dict[str, DetectedFileType] = {
    "application/pdf": DetectedFileType.PDF,
    "application/vnd.ms-excel": DetectedFileType.XLS,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": (
        DetectedFileType.XLSX
    ),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
        DetectedFileType.DOCX
    ),
}


@dataclass(frozen=True, slots=True)
class FileTypeDetection:
    file_type: DetectedFileType
    mime_type: str | None


class FileTypeDetector:
    """Detect actual file type from bytes. Filename is never authoritative."""

    def detect(self, data: bytes, *, filename: str | None = None) -> FileTypeDetection:
        # Filename is accepted for API symmetry with callers but MUST NOT decide type.
        _ = filename

        if not data:
            return FileTypeDetection(DetectedFileType.UNKNOWN, None)

        head = data[:256].lstrip().lower()
        if any(marker in head for marker in HTML_MARKERS):
            return FileTypeDetection(DetectedFileType.UNKNOWN, "text/html")

        if data.startswith(PDF_MAGIC):
            return FileTypeDetection(DetectedFileType.PDF, "application/pdf")

        ooxml = self._detect_ooxml(data)
        if ooxml is not None:
            return ooxml

        kind = filetype.guess(data)
        if kind is not None:
            mapped = _MIME_TO_TYPE.get(str(kind.mime))
            if mapped is not None:
                return FileTypeDetection(mapped, str(kind.mime))

        if data.startswith(OLE_MAGIC):
            # Old Office compound file. Prefer XLS only when filetype agrees;
            # otherwise stay unknown (could be .doc/.ppt).
            return FileTypeDetection(DetectedFileType.UNKNOWN, "application/x-ole-storage")

        return FileTypeDetection(DetectedFileType.UNKNOWN, None)

    def _detect_ooxml(self, data: bytes) -> FileTypeDetection | None:
        if not data.startswith(ZIP_MAGIC):
            return None
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = archive.namelist()
        except zipfile.BadZipFile:
            return None

        has_xlsx = any(name.startswith("xl/") for name in names) or (
            "xl/workbook.xml" in names
        )
        has_docx = any(name.startswith("word/") for name in names) or (
            "word/document.xml" in names
        )

        if has_xlsx and not has_docx:
            return FileTypeDetection(
                DetectedFileType.XLSX,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        if has_docx and not has_xlsx:
            return FileTypeDetection(
                DetectedFileType.DOCX,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        return None
