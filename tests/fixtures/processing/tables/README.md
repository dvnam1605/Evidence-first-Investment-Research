# Table extraction fixtures (DOC-11)

Synthetic lined-grid PDFs with UTF-8 Vietnamese labels embedded via TrueType.
Each `*.pdf` has a paired `*.expected.json` capturing the exact cell matrix,
table bbox, and per-cell bboxes produced by `PyMuPDFTableExtractor`.

## Files

| Fixture | Purpose |
|---|---|
| `exact_vi_grid` | Exact `[row][col]` VI labels + parenthesized/locale/empty cells |
| `multiline_vi_label` | Multiline Vietnamese label must not collapse/swap |
| `narrative_adjacent` | Table between narrative paragraphs (single table only) |
| `large_8x4` | Larger grid row/column relationships |
| `page_spanning` | Continuation across pages (page-local tables, not auto-stitched) |
| `false_positive_layout` | Spaced columns + ruled callout → zero tables |
| `two_tables_page` | Two tables, deterministic order + exact matrices |

## Note on ASCII hyphen

PyMuPDF `find_tables` may emit U+00AD (soft hyphen) for ASCII `-` in numeric
cells. Expected JSON stores the **extracted** form (raw preservation), not the
source glyph. Parenthesized negatives like `(1,234.50)` are unaffected.

## Real FPT documents

Export real issuer PDFs from local Postgres + MinIO:

```bash
uv run python -m scripts.export_pdf_fixtures
```

Output: `fpt_real/*.pdf` (gitignored) + `fpt_real/manifest.json`.
Raster FPT statements have no native `find_tables` grids. Production can load
vetted SHA-bound raw-table sidecars from `PROCESSING_RAW_TABLE_DIR`; the
pipeline rejects sidecars whose declared SHA does not match the active PDF.
The committed examples live under `fpt_raw/` (`JsonRawTableSource`).
