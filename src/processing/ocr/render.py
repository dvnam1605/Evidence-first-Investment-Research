"""PDF page rasterization for OCR (PyMuPDF)."""

from __future__ import annotations

import fitz  # type: ignore[import-untyped]

from src.processing.errors import OCRFailure
from src.processing.ocr.models import PageImage

DEFAULT_OCR_DPI = 200


def render_pdf_page(
    pdf_bytes: bytes,
    page_number: int,
    *,
    dpi: int = DEFAULT_OCR_DPI,
) -> PageImage:
    """Render a 1-based PDF page to PNG bytes."""
    if not pdf_bytes:
        raise OCRFailure("Cannot rasterize empty PDF bytes")
    if page_number < 1:
        raise OCRFailure(f"Invalid page_number {page_number}; must be >= 1")
    if dpi <= 0:
        raise OCRFailure(f"Invalid dpi {dpi}; must be > 0")

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 - PyMuPDF raises varied types
        raise OCRFailure(f"Failed to open PDF for OCR rasterization: {exc}") from exc

    try:
        if page_number > doc.page_count:
            raise OCRFailure(
                f"page_number {page_number} out of range (page_count={doc.page_count})"
            )
        page = doc.load_page(page_number - 1)
        pix = page.get_pixmap(dpi=dpi)
        return PageImage(
            page_number=page_number,
            width=int(pix.width),
            height=int(pix.height),
            png_bytes=pix.tobytes("png"),
            dpi=dpi,
        )
    except OCRFailure:
        raise
    except Exception as exc:  # noqa: BLE001 - PyMuPDF raises varied types
        raise OCRFailure(f"Failed to rasterize page {page_number}: {exc}") from exc
    finally:
        doc.close()
