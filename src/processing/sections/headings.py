"""Vietnamese-first heading rules for financial statement sections."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.processing.classify.patterns import fold_text
from src.processing.sections.models import SectionHit, StatementSection

# Headings are usually short labels, not long paragraphs.
_MAX_HEADING_CHARS = 180
_SEP = r"[\s_\-]+"


@dataclass(frozen=True, slots=True)
class HeadingRule:
    section: StatementSection
    pattern: re.Pattern[str]
    confidence: float
    name: str
    priority: int


def _rule(
    section: StatementSection,
    pattern: str,
    confidence: float,
    name: str,
    *,
    priority: int,
) -> HeadingRule:
    return HeadingRule(
        section=section,
        pattern=re.compile(pattern, flags=re.IGNORECASE),
        confidence=confidence,
        name=name,
        priority=priority,
    )


# Vietnamese rules first (higher priority), English fallbacks after.
HEADING_RULES: tuple[HeadingRule, ...] = tuple(
    sorted(
        (
            _rule(
                StatementSection.NOTES,
                rf"\b("
                rf"thuyet{_SEP}minh{_SEP}bao{_SEP}cao{_SEP}tai{_SEP}chinh|"
                rf"thuyet{_SEP}minh"
                rf")\b",
                0.92,
                "vi_notes",
                priority=100,
            ),
            _rule(
                StatementSection.BALANCE_SHEET,
                rf"\b("
                rf"bang{_SEP}can{_SEP}doi{_SEP}ke{_SEP}toan|"
                rf"bao{_SEP}cao{_SEP}tinh{_SEP}hinh{_SEP}tai{_SEP}chinh"
                rf")\b",
                0.95,
                "vi_balance_sheet",
                priority=90,
            ),
            _rule(
                StatementSection.INCOME_STATEMENT,
                rf"\b("
                rf"bao{_SEP}cao{_SEP}ket{_SEP}qua{_SEP}hoat{_SEP}dong{_SEP}kinh{_SEP}doanh|"
                rf"bao{_SEP}cao{_SEP}lai{_SEP}lo|"
                rf"ket{_SEP}qua{_SEP}hoat{_SEP}dong{_SEP}kinh{_SEP}doanh"
                rf")\b",
                0.95,
                "vi_income_statement",
                priority=90,
            ),
            _rule(
                StatementSection.CASH_FLOW_STATEMENT,
                rf"\b("
                rf"bao{_SEP}cao{_SEP}luu{_SEP}chuyen{_SEP}tien{_SEP}te|"
                rf"luu{_SEP}chuyen{_SEP}tien{_SEP}te"
                rf")\b",
                0.95,
                "vi_cash_flow",
                priority=90,
            ),
            _rule(
                StatementSection.NOTES,
                rf"\bnotes{_SEP}to{_SEP}(?:the{_SEP})?financial{_SEP}statements?\b",
                0.82,
                "en_notes",
                priority=50,
            ),
            _rule(
                StatementSection.BALANCE_SHEET,
                rf"\b("
                rf"balance{_SEP}sheet|"
                rf"statement{_SEP}of{_SEP}financial{_SEP}position"
                rf")\b",
                0.85,
                "en_balance_sheet",
                priority=40,
            ),
            _rule(
                StatementSection.INCOME_STATEMENT,
                rf"\b("
                rf"income{_SEP}statement|"
                rf"statement{_SEP}of{_SEP}profit|"
                rf"statement{_SEP}of{_SEP}comprehensive{_SEP}income|"
                rf"p\s*&\s*l"
                rf")\b",
                0.85,
                "en_income_statement",
                priority=40,
            ),
            _rule(
                StatementSection.CASH_FLOW_STATEMENT,
                rf"\b("
                rf"cash{_SEP}flow{_SEP}statements?|"
                rf"statement{_SEP}of{_SEP}cash{_SEP}flows?"
                rf")\b",
                0.85,
                "en_cash_flow",
                priority=40,
            ),
        ),
        key=lambda rule: rule.priority,
        reverse=True,
    )
)


def match_heading_line(line: str) -> HeadingRule | None:
    """Return the highest-priority heading rule matching a single line."""
    stripped = line.strip()
    if not stripped or len(stripped) > _MAX_HEADING_CHARS:
        return None
    folded = fold_text(stripped)
    for rule in HEADING_RULES:
        if rule.pattern.search(folded):
            return rule
    return None


def collect_section_hits(
    text: str,
    *,
    page_number: int | None = None,
    one_hit_per_section: bool = True,
) -> list[SectionHit]:
    """Scan text lines for section headings (Vietnamese rules preferred)."""
    hits: list[SectionHit] = []
    seen: set[StatementSection] = set()
    offset = 0
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        rule = match_heading_line(content)
        if rule is not None and not (one_hit_per_section and rule.section in seen):
            hits.append(
                SectionHit(
                    section=rule.section,
                    matched_rule=rule.name,
                    matched_text=content.strip(),
                    confidence=rule.confidence,
                    page_number=page_number,
                    start_char=offset,
                )
            )
            seen.add(rule.section)
        offset += len(line)
    return hits
