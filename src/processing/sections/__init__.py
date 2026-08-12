"""Financial statement section detection package."""

from src.processing.sections.detector import StatementSectionDetector
from src.processing.sections.models import (
    SectionDetectionResult,
    SectionHit,
    StatementSection,
)

__all__ = [
    "SectionDetectionResult",
    "SectionHit",
    "StatementSection",
    "StatementSectionDetector",
]
