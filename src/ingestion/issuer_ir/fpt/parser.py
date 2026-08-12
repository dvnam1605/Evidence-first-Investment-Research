"""Parse FPT IR disclosure HTML (HTTP-first, no browser automation)."""

from __future__ import annotations

import re
from datetime import date, datetime
from html import unescape
from urllib.parse import unquote, urlparse

from src.domain.enums import AuditStatus, DocumentType, Scope

from .models import FptDisclosure, FptDisclosureAttachment

# Disclosure cards on /information-disclosures use either:
# - "Information disclosure ..."
# - "Audited consolidated/separate financial statements of YYYY" (no prefix)
_TITLE_SPAN_RE = re.compile(
    r"<span[^>]*>\s*("
    r"information\s+disclosures?\b[^<]*"
    r"|audited\s+(?:consolidated|separate)\s+financial\s+statements?\b[^<]*"
    r")</span>",
    flags=re.IGNORECASE,
)


def _extract_download_hrefs(card_html: str) -> list[str]:
    # Example href:
    # /api/download?url=https%3A%2F%2Ffpt-prod.s3-han02.fptcloud.com%2F...pdf
    return re.findall(r'href="(/api/download\?url=[^"]+)"', card_html, flags=re.IGNORECASE)


def _download_url_to_filename(download_url: str) -> str:
    # download_url = /api/download?url=<encoded_original_url>
    # we want the last path segment of the decoded original URL.
    try:
        parsed = urlparse(download_url)
        qs = parsed.query
        m = re.search(r"url=([^&]+)", qs)
        if m is None:
            return "download.pdf"
        original_encoded = m.group(1)
        original = unquote(original_encoded)
        original_parsed = urlparse(original)
        return original_parsed.path.split("/")[-1] or "download.pdf"
    except Exception:
        return "download.pdf"


def _parse_updated_date(card_html: str) -> date | None:
    # Server HTML sometimes contains: updated<!-- -->: <!-- -->4/24/2026
    # Normalize by removing the comment marker used by Next/React.
    normalized = card_html.replace("<!-- -->", "")
    m = re.search(
        r"updated[^0-9]*(\d{1,2}/\d{1,2}/\d{4})",
        normalized,
        flags=re.IGNORECASE,
    )
    if not m:
        return None
    return datetime.strptime(m.group(1), "%m/%d/%Y").date()


def _map_scope_and_audit(title: str) -> tuple[str, str]:
    # FPT IR titles use both singular and plural: "financial statement(s)".
    tl = title.lower()
    if re.search(r"consolidated financial statements?\b", tl):
        scope = Scope.CONSOLIDATED.value
    elif re.search(r"separate financial statements?\b", tl):
        scope = Scope.STANDALONE.value
    else:
        scope = Scope.UNKNOWN.value

    if "audited" in tl:
        audit = AuditStatus.AUDITED.value
    elif "unaudited" in tl:
        audit = AuditStatus.UNAUDITED.value
    else:
        audit = AuditStatus.UNKNOWN.value
    return scope, audit


def _map_document_type(title: str) -> DocumentType:
    tl = title.lower()
    if re.search(r"financial statements?\b", tl):
        return DocumentType.FINANCIAL_STATEMENT
    return DocumentType.OTHER


def parse_fpt_information_disclosures_html(
    html: str,
    *,
    ticker: str,
) -> list[FptDisclosure]:
    """
    Minimal DOM parsing using regex windows on stable server-rendered HTML.

    We rely on the observed server HTML structure:
    - title in a <span> for disclosure / audited financial statement cards
    - updated date in a <span> containing "Updated: M/D/YYYY"
    - PDF download links as <a href="/api/download?url=..."> inside same card window
    """

    normalized = unescape(html.replace("<!-- -->", ""))
    matches = list(_TITLE_SPAN_RE.finditer(normalized))
    disclosures: list[FptDisclosure] = []

    for i, m in enumerate(matches):
        card_start = m.start()
        card_end = matches[i + 1].start() if i + 1 < len(matches) else len(normalized)
        card_html = normalized[card_start:card_end]
        title = m.group(1).strip()

        updated = _parse_updated_date(card_html)
        if updated is None:
            continue

        hrefs = _extract_download_hrefs(card_html)
        if not hrefs:
            continue

        scope, audit = _map_scope_and_audit(title)

        # Stable publication natural key per card:
        # title + updated date is stable enough for idempotency in the initial MVP.
        # (Download filenames are unique too, but we keep multi-attachment cards
        # as one publication natural key.)
        safe_title = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")
        source_doc_id = f"fpt-ir-{ticker.upper()}-{safe_title}-{updated.isoformat()}"

        attachments = [
            FptDisclosureAttachment(
                filename=_download_url_to_filename(href),
                download_reference=("https://fpt.com" + href),
            )
            for href in hrefs
        ]

        disclosures.append(
            FptDisclosure(
                title=title,
                updated_date=updated,
                document_id=source_doc_id,
                scope=scope,
                audit_status=audit,
                attachments=attachments,
            )
        )

    return disclosures
