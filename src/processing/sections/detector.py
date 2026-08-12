"""Detect balance sheet / income / cash flow / notes sections."""

from __future__ import annotations

from collections.abc import Sequence

from src.processing.excel.models import ParsedWorkbook
from src.processing.pdf.models import ParsedDocument
from src.processing.sections.headings import collect_section_hits, match_heading_line
from src.processing.sections.models import SectionDetectionResult, SectionHit


class StatementSectionDetector:
    """
    Vietnamese-heading-first detector for core FS sections.

    Does not extract tables or normalize metrics — only locates section labels.
    """

    def detect_text(
        self,
        text: str,
        *,
        page_number: int | None = None,
    ) -> list[SectionHit]:
        return collect_section_hits(text, page_number=page_number)

    def detect_parsed_document(self, document: ParsedDocument) -> SectionDetectionResult:
        hits: list[SectionHit] = []
        for page in document.pages:
            hits.extend(
                collect_section_hits(
                    page.text,
                    page_number=page.page_number,
                    one_hit_per_section=True,
                )
            )
        return SectionDetectionResult(hits=tuple(hits))

    def detect_workbook(self, workbook: ParsedWorkbook) -> SectionDetectionResult:
        """Use worksheet names as heading candidates (common in Excel FS packs)."""
        hits: list[SectionHit] = []
        seen: set[str] = set()
        for sheet in workbook.sheets:
            rule = match_heading_line(sheet.name)
            if rule is None:
                continue
            key = rule.section.value
            if key in seen:
                continue
            seen.add(key)
            hits.append(
                SectionHit(
                    section=rule.section,
                    matched_rule=rule.name,
                    matched_text=sheet.name,
                    confidence=rule.confidence,
                    page_number=sheet.index + 1,
                    start_char=None,
                )
            )
        return SectionDetectionResult(hits=tuple(hits), method="sheet_name_heading_rules")

    def detect_page_texts(
        self, pages: Sequence[tuple[int, str]]
    ) -> SectionDetectionResult:
        hits: list[SectionHit] = []
        for page_number, text in pages:
            hits.extend(collect_section_hits(text, page_number=page_number))
        return SectionDetectionResult(hits=tuple(hits))
