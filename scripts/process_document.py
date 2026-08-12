"""CLI: process one document artifact.

Usage:

    uv run python -m scripts.process_document --document-id UUID
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

from src.config.settings import get_settings
from src.services.process_document import ProcessDocumentError
from src.services.process_factory import build_process_service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Process one document artifact")
    parser.add_argument(
        "--document-id",
        required=True,
        help="document_artifacts.id (same id used by document_pages / processing jobs)",
    )
    return parser


async def run(args: argparse.Namespace) -> int:
    _ = get_settings()
    try:
        document_id = uuid.UUID(args.document_id)
    except ValueError:
        print(f"invalid document-id: {args.document_id}")
        return 2

    service = build_process_service()
    try:
        outcome = await service.process_document(document_id)
    except ProcessDocumentError as exc:
        print(f"error={exc}")
        return 1

    result = outcome.result
    job = outcome.job
    print(
        f"job_id={job.id} document_id={document_id} status={job.status.value} "
        f"parser={job.parser} pages={len(result.pages)} blocks={len(result.blocks)} "
        f"tables={len(result.reconstructed_tables)} "
        f"file_type={result.file_type.value}"
    )
    if result.classification is not None:
        print(
            f"classification={result.classification.document_class.value} "
            f"method={result.classification.method.value} "
            f"confidence={result.classification.confidence:.2f}"
        )
    if result.sections is not None and result.sections.sections_found:
        print(
            "sections="
            + ",".join(section.value for section in result.sections.sections_found)
        )
    if result.warnings:
        print("warnings=" + ";".join(result.warnings))
    if result.error:
        print(f"error={result.error}")
    return 0 if job.status.value != "FAILED" else 1


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
