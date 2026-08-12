"""Intermediate parse models for FPT IR disclosures."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class FptDisclosureAttachment:
    filename: str
    download_reference: str


@dataclass(frozen=True, slots=True)
class FptDisclosure:
    title: str
    updated_date: date
    document_id: str
    scope: str
    audit_status: str
    attachments: list[FptDisclosureAttachment]

