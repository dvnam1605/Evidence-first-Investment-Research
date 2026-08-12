"""Excel parsing service (async facade over openpyxl)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

from src.processing.excel.models import ParsedWorkbook
from src.processing.excel.parser import OpenpyxlExcelParser


class ExcelParser:
    """Plan interface: async parse(Path) -> ParsedWorkbook."""

    def __init__(self, *, native: OpenpyxlExcelParser | None = None) -> None:
        self._native = native or OpenpyxlExcelParser()

    async def parse(
        self,
        path: Path,
        *,
        artifact_id: UUID | None = None,
    ) -> ParsedWorkbook:
        return await asyncio.to_thread(
            self._native.parse_path, path, artifact_id=artifact_id
        )

    async def parse_bytes(
        self,
        data: bytes,
        *,
        artifact_id: UUID | None = None,
        source_label: str | None = "bytes",
    ) -> ParsedWorkbook:
        return await asyncio.to_thread(
            self._native.parse_bytes,
            data,
            artifact_id=artifact_id,
            source_label=source_label,
        )
