"""Downloader unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from src.config.settings import CrawlerSettings
from src.ingestion.downloader import DocumentDownloader
from src.ingestion.errors import DownloadError
from src.ingestion.models import SourceAttachment


@pytest.mark.asyncio
async def test_download_fixture_file() -> None:
    downloader = DocumentDownloader(crawler_settings=CrawlerSettings(_env_file=None))
    attachment = SourceAttachment(
        filename="fpt-q1-2024.pdf",
        download_reference="fixture://tests/fixtures/disclosures/fpt-q1-2024.pdf",
        reported_mime_type="application/pdf",
    )
    artifact = await downloader.download(
        attachment,
        object_path="raw/FPT/2024/fixture/pending/fpt-q1-2024.pdf",
    )
    assert artifact.sha256
    assert artifact.actual_mime_type == "application/pdf"
    assert artifact.content is not None


@pytest.mark.asyncio
async def test_reject_html_masquerading_as_pdf() -> None:
    downloader = DocumentDownloader(crawler_settings=CrawlerSettings(_env_file=None))
    html_path = Path("tests/fixtures/disclosures/fake.pdf")
    html_path.write_bytes(b"<!doctype html><html><body>error</body></html>")
    attachment = SourceAttachment(
        filename="fake.pdf",
        download_reference=f"fixture://{html_path.as_posix()}",
        reported_mime_type="application/pdf",
    )
    with pytest.raises(DownloadError):
        await downloader.download(attachment, object_path="raw/pending/fake.pdf")
