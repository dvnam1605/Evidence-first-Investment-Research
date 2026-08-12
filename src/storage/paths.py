"""Object storage path helpers."""

from __future__ import annotations

import re


def sanitize_filename(filename: str) -> str:
    cleaned = filename.strip().replace("\\", "/").split("/")[-1]
    cleaned = re.sub(r"[^\w.\-() ]+", "_", cleaned)
    if not cleaned:
        raise ValueError("filename must not be empty after sanitization")
    return cleaned


def build_raw_object_path(
    *, ticker: str, year: int, source: str, sha256: str, filename: str
) -> str:
    safe_name = sanitize_filename(filename)
    return f"raw/{ticker.upper()}/{year}/{source.lower()}/{sha256}/{safe_name}"


def build_raw_object_path_by_sha(*, sha256: str) -> str:
    """
    Canonical raw-object path derived ONLY from SHA256.

    This is required so that identical bytes uploaded from different publications
    map to the same immutable raw object record.
    """

    safe_sha = sha256.strip().lower()
    if not safe_sha or len(safe_sha) < 8:
        raise ValueError("sha256 must be non-empty")
    # Include a stable suffix for readability; do not include original filename.
    short = safe_sha[:8]
    return f"raw_objects/{short}/{safe_sha}/blob"
