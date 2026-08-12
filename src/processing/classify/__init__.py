"""Document classification package."""

from src.processing.classify.classifier import DocumentClassifier, LLMDocumentClassifier
from src.processing.classify.models import (
    ClassificationInput,
    ClassificationMethod,
    DocumentClass,
    DocumentClassification,
)

__all__ = [
    "ClassificationInput",
    "ClassificationMethod",
    "DocumentClass",
    "DocumentClassification",
    "DocumentClassifier",
    "LLMDocumentClassifier",
]
