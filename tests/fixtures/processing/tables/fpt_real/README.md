# Real FPT PDF fixtures

PDFs here are exported from the local Postgres + MinIO corpus for offline
table/extraction testing.

## Export / refresh

With Docker Postgres + MinIO up:

```bash
# PowerShell: set env from .env.example values if needed
uv run python -m scripts.export_pdf_fixtures
```

Writes selected BCTC PDFs + `manifest.json` (sha256, artifact_id, object_path).

## Files

- `*.pdf` — gitignored (local only; large issuer documents)
- `manifest.json` — inventory of exported artifacts
- `*.expected.json` — optional exact table grids for DOC-11/DOC-14 assertions

## Tests

Raster pages yield `no_tables_detected` (not exact grids). Reconstruction goldens
are the vetted JSON grids in `../fpt_raw/`.

`test_fpt_real_fixtures_exact_grids` only runs if a `.pdf` has a matching
`.expected.json`. PDFs alone remain useful for manual / OCR checks:

```bash
uv run python -c "from pathlib import Path; from src.processing.tables import PyMuPDFTableExtractor; p=next(Path('tests/fixtures/processing/tables/fpt_real').glob('*.pdf')); r=PyMuPDFTableExtractor().extract(p.read_bytes()); print(p.name, len(r.tables), r.tables[0].row_count if r.tables else 0)"
```
