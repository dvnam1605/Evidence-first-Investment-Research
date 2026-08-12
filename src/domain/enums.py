"""Domain enums."""

from enum import StrEnum


class Exchange(StrEnum):
    HOSE = "HOSE"
    HNX = "HNX"
    UPCOM = "UPCOM"


class SourceType(StrEnum):
    HOSE = "HOSE"
    HNX = "HNX"
    SSC = "SSC"
    ISSUER_IR = "ISSUER_IR"
    FIXTURE = "FIXTURE"


class DocumentType(StrEnum):
    PERIODIC_REPORT = "periodic_report"
    FINANCIAL_STATEMENT = "financial_statement"
    EVENT_DISCLOSURE = "event_disclosure"
    MATERIAL_DISCLOSURE = "material_disclosure"
    OTHER = "other"


class Scope(StrEnum):
    CONSOLIDATED = "consolidated"
    PARENT = "parent"
    STANDALONE = "standalone"
    UNKNOWN = "unknown"


class AuditStatus(StrEnum):
    AUDITED = "audited"
    UNAUDITED = "unaudited"
    UNKNOWN = "unknown"


class ProcessingStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


class DetectedFileType(StrEnum):
    PDF = "PDF"
    XLS = "XLS"
    XLSX = "XLSX"
    DOCX = "DOCX"
    UNKNOWN = "unknown"


class ExtractionMethod(StrEnum):
    """How page text was produced for persistence."""

    NATIVE = "native"
    OCR = "ocr"


class BlockType(StrEnum):
    """Structured page block kinds (DOC-07)."""

    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"


class IngestionRunStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class VersionResolutionType(StrEnum):
    NEW_DOCUMENT = "NEW_DOCUMENT"
    DUPLICATE = "DUPLICATE"
    NEW_VERSION = "NEW_VERSION"
    CORRECTION = "CORRECTION"
