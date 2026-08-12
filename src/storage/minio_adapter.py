"""MinIO object storage adapter."""

from __future__ import annotations

import asyncio
from io import BytesIO

from minio import Minio
from minio.error import S3Error
from src.config.settings import ObjectStorageSettings
from src.storage.errors import StorageError


class MinioObjectStorage:
    def __init__(self, settings: ObjectStorageSettings) -> None:
        self._settings = settings
        self._client = Minio(
            settings.endpoint,
            access_key=settings.access_key,
            secret_key=settings.secret_key,
            secure=settings.secure,
        )
        self._bucket = settings.bucket

    async def ensure_ready(self) -> None:
        try:
            exists = await asyncio.to_thread(self._client.bucket_exists, self._bucket)
            if not exists:
                await asyncio.to_thread(self._client.make_bucket, self._bucket)
        except S3Error as exc:
            raise StorageError(f"Failed to prepare bucket {self._bucket}: {exc}") from exc
        except Exception as exc:
            raise StorageError(f"Failed to prepare bucket {self._bucket}: {exc}") from exc

    async def ensure_bucket(self) -> None:
        """Backward-compatible alias for local setup callers."""
        await self.ensure_ready()

    async def put(self, object_path: str, data: bytes, content_type: str) -> None:
        try:
            await asyncio.to_thread(
                self._client.put_object,
                self._bucket,
                object_path,
                BytesIO(data),
                len(data),
                content_type=content_type,
            )
        except S3Error as exc:
            raise StorageError(f"Failed to store object {object_path}: {exc}") from exc
        except Exception as exc:
            # Map all transport/MinIO operational errors into StorageError so ingestion
            # failure recovery can consistently mark runs as FAILED/PARTIAL.
            raise StorageError(f"Failed to store object {object_path}: {exc}") from exc

    async def get(self, object_path: str) -> bytes:
        try:
            response = await asyncio.to_thread(
                self._client.get_object,
                self._bucket,
                object_path,
            )
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()
        except S3Error as exc:
            raise StorageError(f"Failed to read object {object_path}: {exc}") from exc
        except Exception as exc:
            raise StorageError(f"Failed to read object {object_path}: {exc}") from exc

    async def exists(self, object_path: str) -> bool:
        try:
            await asyncio.to_thread(self._client.stat_object, self._bucket, object_path)
            return True
        except S3Error as exc:
            # Only treat explicit "not found" as a missing object.
            status_code = getattr(exc, "status_code", None)
            code = getattr(exc, "code", None)
            if status_code == 404 or code in {"NoSuchKey", "NoSuchBucket"}:
                return False
            raise StorageError(f"Failed to stat object {object_path}: {exc}") from exc
        except Exception as exc:
            raise StorageError(f"Failed to stat object {object_path}: {exc}") from exc

    async def delete(self, object_path: str) -> None:
        try:
            await asyncio.to_thread(self._client.remove_object, self._bucket, object_path)
        except S3Error as exc:
            raise StorageError(f"Failed to delete object {object_path}: {exc}") from exc
        except Exception as exc:
            raise StorageError(f"Failed to delete object {object_path}: {exc}") from exc
