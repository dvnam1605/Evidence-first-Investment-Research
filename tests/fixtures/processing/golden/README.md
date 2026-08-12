# DOC-14 — Golden processing fixtures

Inventory for G2 document-processing review.

| Kind | Target | Status |
|---|---:|---|
| Digital PDFs | ≥10 | 10 committed + meaningful `expect` |
| Scanned PDFs | ≥3 | 3 needs_ocr synthetics + mixed OCR golden |
| Complex tables | ≥3 | 3 digital grids + 3 FPT raw JSON |
| Excel reports | ≥2 | 2 XLSX with section expects |
| Real-report pipeline goldens | ≥5 | 5 FPT reports: local PDF + committed `*.pipeline.expected.json` |

## Policy

- **Committed:** synthetic binaries, vetted raw-table JSON, expected JSON (pipeline / OCR / extraction).
- **Local-only:** real FPT issuer PDFs under `tables/fpt_real/` (gitignored). Catalog stores `sha256` + `artifact_id`; refresh with:

```bash
uv run python -m scripts.export_pdf_fixtures
uv run python scripts/build_golden_catalog.py   # refresh expects/sha when regenerating
```

## Layout

```text
golden/
  catalog.json
  digital/                 # extra digital PDFs
  scanned/                 # scan-like + mixed OCR golden
  excel/                   # XLSX statement sheets
  real_reports/            # committed expected outputs for local FPT PDFs
    *.pipeline.expected.json
    q2_2026_consol_bs_is_cf_pages.extraction.expected.json
```

## What tests assert

- Catalog minima (including ≥5 real-report pipeline goldens).
- Committed SHA256 integrity.
- Digital/Excel: page counts/order, text spans, sections, classes, table counts.
- Scanned: `needs_ocr` without engine → `NEEDS_REVIEW`.
- Mixed OCR golden: fake engine OCR text/lines/bbox/confidence; native page text preserved.
- Real FPT (when PDFs present): pipeline status, page count, OCR decision, zero native tables, issue reasons.
- Q2 consol pages 3/7/10: native `no_tables_detected` + linked `fpt_raw` reconstruction fixtures.
