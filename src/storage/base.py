"""Object storage interface."""

from __future__ import annotations

from typing import Protocol


class ObjectStorage(Protocol):
    async def ensure_ready(self) -> None: ...

    async def put(self, object_path: str, data: bytes, content_type: str) -> None: ...

    async def get(self, object_path: str) -> bytes: ...

    async def exists(self, object_path: str) -> bool: ...

    async def delete(self, object_path: str) -> None: ...
