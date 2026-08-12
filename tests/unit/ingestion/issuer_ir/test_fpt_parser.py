from __future__ import annotations

from datetime import date

from src.domain.enums import AuditStatus, Scope
from src.ingestion.issuer_ir.fpt.parser import parse_fpt_information_disclosures_html


def test_parse_consolidated_and_separate_scopes() -> None:
    html = """
    <div>
      <span class="t">information disclosure consolidated financial statement</span>
      <span class="u">Updated<!-- -->: <!-- -->4/24/2026</span>
      <a href="/api/download?url=https%3A%2F%2Fexample.com%2Fconsolidated.pdf">Download</a>
    </div>
    <div>
      <span class="t">information disclosure separate financial statements</span>
      <span class="u">Updated<!-- -->: <!-- -->4/24/2026</span>
      <a href="/api/download?url=https%3A%2F%2Fexample.com%2Fseparate.pdf">Download</a>
    </div>
    <div>
      <span class="t">information disclosure audited annual report</span>
      <span class="u">Updated<!-- -->: <!-- -->3/19/2026</span>
      <a href="/api/download?url=https%3A%2F%2Fexample.com%2Fannual-audited.pdf">Download</a>
    </div>
    """

    disclosures = parse_fpt_information_disclosures_html(html, ticker="FPT")
    assert len(disclosures) == 3

    d0 = disclosures[0]
    assert "consolidated financial statement" in d0.title.lower()
    assert d0.scope == Scope.CONSOLIDATED.value
    assert d0.audit_status == AuditStatus.UNKNOWN.value
    assert d0.updated_date == date(2026, 4, 24)
    assert d0.attachments[0].filename.endswith("consolidated.pdf")

    d1 = disclosures[1]
    assert d1.scope == Scope.STANDALONE.value

    d2 = disclosures[2]
    assert "audited" in d2.title.lower()
    assert d2.audit_status == AuditStatus.AUDITED.value


def test_parse_audited_titles_without_information_disclosure_prefix() -> None:
    html = """
    <div>
      <span class="t">audited consolidated financial statements of 2025</span>
      <span class="u">Updated<!-- -->: <!-- -->3/19/2026</span>
      <a href="/api/download?url=https%3A%2F%2Fexample.com%2Faudited-c.pdf">Download</a>
    </div>
    <div>
      <span class="t">audited separate financial statements of 2025</span>
      <span class="u">Updated<!-- -->: <!-- -->3/19/2026</span>
      <a href="/api/download?url=https%3A%2F%2Fexample.com%2Faudited-s.pdf">Download</a>
    </div>
    """

    disclosures = parse_fpt_information_disclosures_html(html, ticker="FPT")
    assert len(disclosures) == 2
    assert disclosures[0].scope == Scope.CONSOLIDATED.value
    assert disclosures[0].audit_status == AuditStatus.AUDITED.value
    assert disclosures[0].updated_date == date(2026, 3, 19)
    assert disclosures[1].scope == Scope.STANDALONE.value
    assert disclosures[1].audit_status == AuditStatus.AUDITED.value

