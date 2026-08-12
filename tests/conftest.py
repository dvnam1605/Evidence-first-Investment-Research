"""Shared pytest configuration."""

from __future__ import annotations

import os
from pathlib import Path


def _load_env_file(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def pytest_configure() -> None:
    env_file = Path(".env")
    example_file = Path(".env.example")

    if env_file.exists():
        _load_env_file(env_file)
    elif example_file.exists():
        _load_env_file(example_file)
