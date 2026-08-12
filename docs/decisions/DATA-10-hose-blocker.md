# DATA-10 — HOSE connector blocker

Date: 2026-08-11

## Status

**BLOCKED** — production HOSE ingestion cannot proceed with the current public site.

## Evidence

Requests to the legacy disclosure endpoint now return a React SPA shell instead of JSON:

- URL tested: `https://www.hsx.vn/Modules/Listed/Web/DisclosureList`
- Response: `text/html` with `<div id="HOSE">` and bundled JS (`/static/js/main.*.js`)
- Sample saved during investigation: project root `hose_sample.txt` (local artifact)

Historical jqgrid-style endpoints documented in community posts (pre-2025 KRX migration) no longer return structured disclosure rows.

## Impact

- `DATA-10` acceptance criteria (FPT bounded interval, >=95% recall vs manual sample) **cannot be met** without an alternate strategy.
- `HoseConnector` is registered but raises `SourceUnavailableError` with this reference.
- Pipeline validation uses `FixtureConnector` (`SourceType.FIXTURE`) instead.

## Options for human review (G1)

1. **Browser automation** against hsx.vn SPA (Playwright/CDP) — higher maintenance, must respect robots/terms.
2. **Licensed third-party API** (e.g. FinancialReports.eu, FiinGroup) — requires API key and ADR for Tier B/C usage policy.
3. **Manual seed + issuer IR** for MVP tickers while exchange connector is developed.
4. **Official data agreement** with HOSE/SSC if available.

## Decision requested

Do not silently scrape unofficial third-party sites. Choose one of the above before enabling `SourceType.HOSE` in production ingestion.

## Repro command

```bash
python scripts/probe_hose.py
```

Expected: HTTP 200 with HTML SPA shell, not JSON disclosure rows.
