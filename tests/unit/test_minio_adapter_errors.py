from __future__ import annotations

from unittest.mock import Mock

import pytest
from src.config.settings import ObjectStorageSettings
from src.storage.errors import StorageError
from src.storage.minio_adapter import MinioObjectStorage


@pytest.mark.asyncio
async def test_minio_adapter_put_maps_non_s3_error_to_storage_error() -> None:
    storage = MinioObjectStorage(
        ObjectStorageSettings(
            endpoint="localhost:9000",
            access_key="access",
            secret_key="secret",
            bucket="test",
            secure=False,
        )
    )

    storage._client.put_object = Mock(side_effect=RuntimeError("boom"))  # type: ignore[attr-defined]

    with pytest.raises(StorageError):
        await storage.put("raw_objects/x/blob", b"data", "application/pdf")


@pytest.mark.asyncio
async def test_minio_adapter_exists_maps_non_s3_error_to_storage_error() -> None:
    storage = MinioObjectStorage(
        ObjectStorageSettings(
            endpoint="localhost:9000",
            access_key="access",
            secret_key="secret",
            bucket="test",
            secure=False,
        )
    )

    storage._client.stat_object = Mock(side_effect=RuntimeError("boom"))  # type: ignore[attr-defined]

    with pytest.raises(StorageError):
        await storage.exists("raw_objects/x/blob")

