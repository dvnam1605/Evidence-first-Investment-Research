"""CLI entrypoint for company ingestion."""

from __future__ import annotations

import argparse
import asyncio
from datetime import date

from src.config.settings import get_settings
from src.domain.enums import SourceType
from src.services.ingest_factory import build_ingest_service


def parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest company disclosures")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--source", required=True, choices=[s.value for s in SourceType])
    parser.add_argument("--from-date", dest="from_date")
    parser.add_argument("--to-date", dest="to_date")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-discovery", action="store_true")
    return parser


async def run(args: argparse.Namespace) -> None:
    _ = get_settings()
    service = build_ingest_service()
    result = await service.ingest(
        ticker=args.ticker,
        source=args.source,
        from_date=parse_date(args.from_date),
        to_date=parse_date(args.to_date),
        dry_run=args.dry_run,
    )
    print(
        f"run_id={result.run_id} status={result.status.value} "
        f"discovered={result.discovered} publications_created={result.publications_created} "
        f"artifacts_downloaded={result.artifacts_downloaded} "
        f"duplicates_skipped={result.duplicates_skipped} "
        f"downloaded={result.downloaded} skipped={result.skipped} failed={result.failed}"
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
