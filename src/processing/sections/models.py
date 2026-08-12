"""Financial statement section detection models (DOC-10)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class StatementSection(StrEnum):
    BALANCE_SHEET = "balance_sheet"
    INCOME_STATEMENT = "income_statement"
    CASH_FLOW_STATEMENT = "cash_flow_statement"
    NOTES = "notes"


@dataclass(frozen=True, slots=True)
class SectionHit:
    section: StatementSection
    matched_rule: str
    matched_text: str
    confidence: float
    page_number: int | None = None
    start_char: int | None = None


@dataclass(frozen=True, slots=True)
class SectionDetectionResult:
    hits: tuple[SectionHit, ...]
    method: str = "vietnamese_heading_rules"

    @property
    def sections_found(self) -> tuple[StatementSection, ...]:
        seen: list[StatementSection] = []
        for hit in self.hits:
            if hit.section not in seen:
                seen.append(hit.section)
        return tuple(seen)

    def first_page(self, section: StatementSection) -> int | None:
        for hit in self.hits:
            if hit.section is section and hit.page_number is not None:
                return hit.page_number
        return None
