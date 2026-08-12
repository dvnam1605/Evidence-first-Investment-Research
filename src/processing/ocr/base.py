"""OCR engine protocol."""

from __future__ import annotations

from typing import Protocol

from src.processing.ocr.models import OCRPageResult, PageImage


class OCREngine(Protocol):
    async def recognize(self, image: PageImage) -> OCRPageResult: ...
