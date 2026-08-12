"""Secure document downloader."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path

import filetype  # type: ignore[import-untyped]
import httpx
from src.config.settings import CrawlerSettings
from src.ingestion.errors import DownloadError
from src.ingestion.models import DownloadedArtifact, SourceAttachment
from src.storage.paths import sanitize_filename

PDF_MAGIC = b"%PDF"
HTML_MARKERS = (b"<!doctype html", b"<html", b"<HTML")


@dataclass(frozen=True, slots=True)
class DownloaderConfig:
    timeout_seconds: float = 30.0
    max_retries: int = 3
    backoff_base_seconds: float = 1.0
    max_file_size_bytes: int = 50 * 1024 * 1024


class DocumentDownloader:
    def __init__(
        self,
        *,
        crawler_settings: CrawlerSettings,
        config: DownloaderConfig | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = crawler_settings
        self._config = config or DownloaderConfig()
        self._client = client

    async def download(
        self,
        attachment: SourceAttachment,
        *,
        object_path: str,
    ) -> DownloadedArtifact:
        client = self._client or httpx.AsyncClient(
            timeout=self._config.timeout_seconds,
            headers={"User-Agent": self._settings.user_agent},
            follow_redirects=True,
        )
        owns_client = self._client is None
        try:
            data = await self._download_with_retry(client, attachment.download_reference)
            actual_mime = self._detect_mime(data, attachment.reported_mime_type)
            self._reject_html_masquerading_as_pdf(data, actual_mime, attachment.filename)
            sha256 = hashlib.sha256(data).hexdigest()
            return DownloadedArtifact(
                filename=sanitize_filename(attachment.filename),
                actual_mime_type=actual_mime,
                size_bytes=len(data),
                sha256=sha256,
                object_path=object_path,
                content=data,
            )
        finally:
            if owns_client:
                await client.aclose()

    async def _download_with_retry(self, client: httpx.AsyncClient, url: str) -> bytes:
        last_error: Exception | None = None
        for attempt in range(self._config.max_retries):
            try:
                return await self._stream_download(client, url)
            except (httpx.HTTPError, DownloadError) as exc:
                last_error = exc
                if attempt + 1 >= self._config.max_retries:
                    break
                await asyncio.sleep(self._config.backoff_base_seconds * (2**attempt))
        raise DownloadError(f"Download failed for {url}: {last_error}") from last_error

    async def _stream_download(self, client: httpx.AsyncClient, url: str) -> bytes:
        if url.startswith("fixture://"):
            path = Path(url.removeprefix("fixture://"))
            if not path.exists():
                raise DownloadError(f"Fixture file not found: {path}")
            data = path.read_bytes()
            if len(data) > self._config.max_file_size_bytes:
                raise DownloadError(f"File exceeds max size {self._config.max_file_size_bytes}")
            return data

        chunks: list[bytes] = []
        total = 0
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > self._config.max_file_size_bytes:
                    raise DownloadError(f"File exceeds max size {self._config.max_file_size_bytes}")
                chunks.append(chunk)
        return b"".join(chunks)

    def _detect_mime(self, data: bytes, reported: str | None) -> str:
        kind = filetype.guess(data)
        if kind is not None:
            return str(kind.mime)
        if reported:
            return reported
        if data.startswith(PDF_MAGIC):
            return "application/pdf"
        return "application/octet-stream"

    def _reject_html_masquerading_as_pdf(self, data: bytes, mime_type: str, filename: str) -> None:
        lower_name = filename.lower()
        looks_like_pdf = lower_name.endswith(".pdf") or mime_type == "application/pdf"
        if not looks_like_pdf:
            return
        head = data[:256].lower()
        if any(marker in head for marker in HTML_MARKERS):
            raise DownloadError("Rejected HTML content masquerading as PDF")
        if mime_type.startswith("text/html"):
            raise DownloadError("Rejected HTML content masquerading as PDF")
