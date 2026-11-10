from __future__ import annotations

from io import BytesIO
from typing import Protocol

from ..config import AppConfig


class ObjectStore(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> str: ...

    def get(self, key: str) -> tuple[bytes, str]: ...


class MemoryStore:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put(self, key: str, data: bytes, content_type: str) -> str:
        self.objects[key] = (data, content_type)
        return key

    def get(self, key: str) -> tuple[bytes, str]:
        return self.objects[key]


class MinioStore:
    def __init__(self, config: AppConfig) -> None:
        from minio import Minio

        self.client = Minio(
            config.minio.endpoint,
            access_key=config.minio.access_key,
            secret_key=config.minio.secret_key,
            secure=config.minio.secure,
        )
        self.bucket = config.minio.bucket
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def put(self, key: str, data: bytes, content_type: str) -> str:
        self.client.put_object(
            self.bucket,
            key,
            BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return key

    def get(self, key: str) -> tuple[bytes, str]:
        response = self.client.get_object(self.bucket, key)
        try:
            content_type = response.headers.get("Content-Type", "application/octet-stream")
            return response.read(), content_type
        finally:
            response.close()
            response.release_conn()
