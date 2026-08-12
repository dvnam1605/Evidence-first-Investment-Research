"""Failure recovery unit tests."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from src.config.settings import CrawlerSettings
from src.ingestion.downloader import DocumentDownloader, DownloaderConfig
from src.ingestion.errors import DownloadError
from src.ingestion.models import SourceAttachment


@pytest.mark.asyncio
async def test_bounded_retry_on_http_failure() -> None:
    client = AsyncMock()

    @asynccontextmanager
    async def failing_stream(*_args: object, **_kwargs: object):
        raise httpx.HTTPError("timeout")
        yield Mock()

    client.stream = failing_stream
    client.aclose = AsyncMock()

    downloader = DocumentDownloader(
        crawler_settings=CrawlerSettings(_env_file=None),
        config=DownloaderConfig(max_retries=2, backoff_base_seconds=0),
        client=client,
    )
    attachment = SourceAttachment(
        filename="x.pdf",
        download_reference="https://example.com/x.pdf",
    )
    with pytest.raises(DownloadError):
        await downloader.download(attachment, object_path="raw/pending/x.pdf")
