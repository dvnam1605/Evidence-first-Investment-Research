"""Export selected PDF artifacts from Postgres + MinIO to local test fixtures.

Usage (services up; env from .env.example defaults):

    uv run python -m scripts.export_pdf_fixtures

Optional:

    uv run python -m scripts.export_pdf_fixtures --limit 6 \\
        --out tests/fixtures/processing/tables/fpt_real
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from src.config.settings import ObjectStorageSettings, get_settings
from src.storage.minio_adapter import MinioObjectStorage

# Prefer true financial-statement binaries (filename-based; titles can be noisy).
DEFAULT_FILENAME_PATTERNS: tuple[str, ...] = (
    r"bctc_hop_nhat_nam_2025_da_kiem_toan",
    r"bctc_rieng_nam_2025_da_kiem_toan",
    r"bctc_hop_nhat_quy_1_nam_2026",
    r"bctc_rieng_quy_1_nam_2026",
    r"Consolidated_Financial_Statements_for_Q22026",
    r"Separarate_Financial_Statements_for_Q22026",  # source spelling
    r"tcbc_kqkd_quy_1_nam_2026",
)

DEFAULT_OUT = Path("tests/fixtures/processing/tables/fpt_real")


@dataclass(frozen=True)
class ExportedPdf:
    slug: str
    filename: str
    artifact_id: str
    publication_title: str | None
    sha256: str
    object_path: str
    size_bytes: int
    local_path: str


def _slug(filename: str, sha256: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("_")
    return f"{stem[:80]}_{sha256[:12]}"


async def _fetch_candidates(database_url: str) -> list[dict]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    """
                    SELECT DISTINCT ON (ro.sha256)
                           sp.title AS publication_title,
                           da.id::text AS artifact_id,
                           da.filename,
                           da.file_size,
                           ro.object_path,
                           ro.sha256,
                           ro.size_bytes,
                           ro.mime_type
                    FROM document_artifacts da
                    JOIN raw_objects ro ON ro.id = da.raw_object_id
                    JOIN source_publications sp ON sp.id = da.publication_id
                    WHERE (da.mime_type ILIKE '%pdf%' OR da.filename ILIKE '%.pdf')
                      AND ro.size_bytes > 1000
                    ORDER BY ro.sha256, da.created_at DESC
                    """
                )
            )
            return [dict(row._mapping) for row in result.fetchall()]
    finally:
        await engine.dispose()


def _select(
    rows: list[dict],
    *,
    patterns: tuple[str, ...],
    limit: int,
) -> list[dict]:
    selected: list[dict] = []
    seen: set[str] = set()
    for pattern in patterns:
        rx = re.compile(pattern, re.IGNORECASE)
        for row in rows:
            sha = row["sha256"]
            if sha in seen:
                continue
            if rx.search(row["filename"] or ""):
                selected.append(row)
                seen.add(sha)
                if len(selected) >= limit:
                    return selected
    return selected


async def export_pdfs(
    *,
    out_dir: Path,
    patterns: tuple[str, ...],
    limit: int,
) -> list[ExportedPdf]:
    settings = get_settings()
    rows = await _fetch_candidates(settings.database.url)
    chosen = _select(rows, patterns=patterns, limit=limit)
    if not chosen:
        raise SystemExit("No matching PDF artifacts found in the database.")

    storage = MinioObjectStorage(
        ObjectStorageSettings(
            endpoint=settings.object_storage.endpoint,
            access_key=settings.object_storage.access_key,
            secret_key=settings.object_storage.secret_key,
            bucket=settings.object_storage.bucket,
            secure=settings.object_storage.secure,
        )
    )
    await storage.ensure_ready()

    out_dir.mkdir(parents=True, exist_ok=True)
    exported: list[ExportedPdf] = []
    for row in chosen:
        slug = _slug(row["filename"], row["sha256"])
        local_name = f"{slug}.pdf"
        local_path = out_dir / local_name
        data = await storage.get(row["object_path"])
        if not data.startswith(b"%PDF"):
            raise SystemExit(
                f"Object {row['object_path']} is not a PDF (sha={row['sha256'][:12]})"
            )
        local_path.write_bytes(data)
        exported.append(
            ExportedPdf(
                slug=slug,
                filename=row["filename"],
                artifact_id=row["artifact_id"],
                publication_title=row["publication_title"],
                sha256=row["sha256"],
                object_path=row["object_path"],
                size_bytes=int(row["size_bytes"]),
                local_path=str(local_path).replace("\\", "/"),
            )
        )
        print(f"wrote {local_path} ({len(data)} bytes)")

    manifest = {
        "source": "postgres+minio export",
        "count": len(exported),
        "items": [asdict(item) for item in exported],
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {manifest_path}")
    return exported


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="Output directory for PDF fixtures",
    )
    parser.add_argument("--limit", type=int, default=7)
    args = parser.parse_args()
    asyncio.run(
        export_pdfs(
            out_dir=args.out,
            patterns=DEFAULT_FILENAME_PATTERNS,
            limit=args.limit,
        )
    )


if __name__ == "__main__":
    main()
