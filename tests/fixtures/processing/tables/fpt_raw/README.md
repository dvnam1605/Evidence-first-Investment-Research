# Vetted FPT raw-table fixtures

Native `find_tables` returns no grids on the raster FPT statement PDFs. These
JSON files are **visual transcriptions** of representative statement regions
into `ExtractedTable` cell grids (table-ready upstream for DOC-12).

| File | PDF page | Statement |
|---|---|---|
| `q2_2026_consol_bs_p3.json` | 3 (printed 2) | Balance sheet — current assets |
| `q2_2026_consol_is_p7.json` | 7 (printed 6) | Income statement |
| `q2_2026_consol_cf_p10.json` | 10 (printed 9) | Cash-flow statement |
| `fy_2025_consol_bs_p8.json` | 8 (printed 5) | Consolidated balance-sheet region |
| `fy_2025_separate_bs_p8.json` | 8 (printed 5) | Separate balance-sheet region |
| `q1_2026_consol_bs_p3.json` | 3 (printed 2) | Consolidated balance-sheet region |
| `q1_2026_separate_bs_p4.json` | 4 (printed 3) | Separate balance-sheet region |
| `q2_2026_separate_bs_p4.json` | 4 (printed 3) | Separate balance-sheet region |

Source PDF (gitignored, local export):

`tests/fixtures/processing/tables/fpt_real/20260727_FPT_Consolidated_Financial_Statements_for_Q22026_055fe1ecd3_024b14f8ceff.pdf`

Load via `JsonRawTableSource` / `load_raw_table_fixture`. Reconstruction goldens
live in each file's `expected` object and are asserted by
`tests/unit/processing/test_fpt_raw_reconstruction.py`.

Cell text was verified against the source PDF pages. Full Q2-consolidated
statement fixtures include exact reconstruction expectations. The five
additional compact `matrix` fixtures are intentionally bounded visual regions,
not claims that the whole statement was captured: they retain
`status=NEEDS_REVIEW` and `partial_statement_region`. At load time each matrix
is expanded to provenance-bearing raw cells. Each generated cell bbox carries
`bbox_estimated=true`; these are visual-layout estimates, not OCR measurements.
