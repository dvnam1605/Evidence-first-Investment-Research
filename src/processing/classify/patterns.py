"""Deterministic Vietnamese/English title-filename patterns for DOC-09."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from src.processing.classify.models import DocumentClass


@dataclass(frozen=True, slots=True)
class PatternRule:
    document_class: DocumentClass
    pattern: re.Pattern[str]
    confidence: float
    name: str


def fold_text(value: str) -> str:
    """Lowercase + strip combining marks for diacritic-insensitive matching."""
    # đ/Đ do not always decompose under NFKD; map them explicitly.
    mapped = value.replace("đ", "d").replace("Đ", "d").replace("Ð", "d")
    normalized = unicodedata.normalize("NFKD", mapped.casefold())
    folded = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    # Filename separators are word chars to `\b`; normalize them to spaces.
    return folded.replace("_", " ").replace("-", " ").replace(".", " ")


def _rule(document_class: DocumentClass, pattern: str, confidence: float, name: str) -> PatternRule:
    return PatternRule(
        document_class=document_class,
        pattern=re.compile(pattern, flags=re.IGNORECASE),
        confidence=confidence,
        name=name,
    )


# Separators in titles/filenames: spaces, underscores, hyphens.
_SEP = r"[\s_\-]+"

# Order matters: more specific classes first.
PATTERN_RULES: tuple[PatternRule, ...] = (
    _rule(
        DocumentClass.MANAGEMENT_EXPLANATION,
        rf"\b("
        rf"thuyet{_SEP}minh{_SEP}bao{_SEP}cao{_SEP}tai{_SEP}chinh|"
        rf"giai{_SEP}trinh|"
        rf"management{_SEP}discussion|"
        rf"md\s*&\s*a|"
        rf"explanation{_SEP}of{_SEP}(?:the{_SEP})?(?:board|management)"
        rf")\b",
        0.88,
        "management_explanation",
    ),
    _rule(
        DocumentClass.FINANCIAL_STATEMENT,
        rf"\b(bao{_SEP}cao{_SEP}tai{_SEP}chinh|bctc|financial{_SEP}statements?)\b",
        0.92,
        "financial_statement",
    ),
    _rule(
        DocumentClass.ANNUAL_REPORT,
        rf"\b(bao{_SEP}cao{_SEP}thuong{_SEP}nien|annual{_SEP}report)\b",
        0.90,
        "annual_report",
    ),
    _rule(
        DocumentClass.BOARD_RESOLUTION,
        rf"\b("
        rf"nghi{_SEP}quyet{_SEP}(?:hdqt|hoi{_SEP}dong{_SEP}quan{_SEP}tri)|"
        rf"board{_SEP}(?:of{_SEP}directors{_SEP})?resolution|"
        rf"resolution{_SEP}of{_SEP}the{_SEP}board"
        rf")\b",
        0.90,
        "board_resolution",
    ),
    _rule(
        DocumentClass.SHAREHOLDER_DOCUMENT,
        rf"\b("
        rf"dhcd|dai{_SEP}hoi{_SEP}co{_SEP}dong|"
        rf"co{_SEP}dong|"
        rf"shareholders?(?:{_SEP}meeting)?|"
        rf"agm\b"
        rf")\b",
        0.85,
        "shareholder_document",
    ),
    _rule(
        DocumentClass.MATERIAL_DISCLOSURE,
        rf"\b("
        rf"cong{_SEP}bo{_SEP}thong{_SEP}tin|cbtt|"
        rf"information{_SEP}disclosures?|"
        rf"material{_SEP}disclosure|"
        rf"unusual{_SEP}transaction"
        rf")\b",
        0.86,
        "material_disclosure",
    ),
)


def match_patterns(*texts: str | None) -> tuple[DocumentClass, float, str] | None:
    """Return first matching rule across provided text fields (rule order = priority)."""
    haystacks = [fold_text(text) for text in texts if text]
    if not haystacks:
        return None

    for rule in PATTERN_RULES:
        for haystack in haystacks:
            if rule.pattern.search(haystack):
                return (rule.document_class, rule.confidence, rule.name)
    return None
