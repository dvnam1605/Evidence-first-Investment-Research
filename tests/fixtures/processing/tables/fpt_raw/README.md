# Vetted FPT raw-table fixtures

Native `find_tables` returns no grids on the raster Q2 2026 consolidated PDF.
These JSON files are **visual transcriptions** of representative statement pages
into `ExtractedTable` cell grids (table-ready upstream for DOC-12).

| File | PDF page | Statement |
|---|---|---|
| `q2_2026_consol_bs_p3.json` | 3 (printed 2) | Balance sheet — current assets |
| `q2_2026_consol_is_p7.json` | 7 (printed 6) | Income statement |
| `q2_2026_consol_cf_p10.json` | 10 (printed 9) | Cash-flow statement |

Source PDF (gitignored, local export):

`tests/fixtures/processing/tables/fpt_real/20260727_FPT_Consolidated_Financial_Statements_for_Q22026_055fe1ecd3_024b14f8ceff.pdf`

Load via `JsonRawTableSource` / `load_raw_table_fixture`. Reconstruction goldens
live in each file's `expected` object and are asserted by
`tests/unit/processing/test_fpt_raw_reconstruction.py`.

Cell text was verified against the source PDF pages. Incomplete / unverified
rows are omitted rather than left blank. Cell bboxes are visual-layout
estimates (`bbox_estimated_from_visual_layout`), not OCR-measured.
