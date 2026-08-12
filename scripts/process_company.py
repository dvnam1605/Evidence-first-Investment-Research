"""CLI: process all artifacts for a company ticker.

Usage:

    uv run python -m scripts.process_company --ticker FPT
"""

from __future__ import annotations

import argparse
import asyncio

from src.config.settings import get_settings
from src.services.process_document import ProcessDocumentError
from src.services.process_factory import build_process_service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Process all stored artifacts for a company"
    )
    parser.add_argument("--ticker", required=True)
    return parser


async def run(args: argparse.Namespace) -> int:
    _ = get_settings()
    service = build_process_service()
    try:
        outcome = await service.process_company(args.ticker)
    except ProcessDocumentError as exc:
        print(f"error={exc}")
        return 1

    print(
        f"ticker={outcome.ticker} processed={outcome.processed} "
        f"needs_review={outcome.needs_review} failed={outcome.failed} "
        f"skipped={outcome.skipped} total={len(outcome.outcomes)}"
    )
    for item in outcome.outcomes:
        print(
            f"  document_id={item.result.artifact_id} "
            f"status={item.job.status.value} "
            f"pages={len(item.result.pages)} "
            f"tables={len(item.result.reconstructed_tables)}"
        )
    return 0 if outcome.failed == 0 else 1


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
