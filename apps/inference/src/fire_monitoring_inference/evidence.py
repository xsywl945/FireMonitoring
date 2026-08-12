from __future__ import annotations

from io import BytesIO
from typing import Any, Protocol
from uuid import UUID


class EvidenceStore(Protocol):
    def put_jpeg(self, *, trace_id: UUID, captured_at: str, data: bytes) -> str:
        """Persist one private JPEG and return its stable object key."""


class MinioEvidenceStore:
    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
        client: Any | None = None,
    ) -> None:
        if not endpoint or not access_key or not secret_key or not bucket:
            raise ValueError("MinIO endpoint, credentials, and bucket are required")
        if client is None:
            try:
                from minio import Minio
            except ImportError as exc:  # pragma: no cover - optional integration dependency
                raise RuntimeError("install the minio Python package for evidence storage") from exc
            client = Minio(
                endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=secure,
            )
        self._client = client
        self.bucket = bucket

    def put_jpeg(self, *, trace_id: UUID, captured_at: str, data: bytes) -> str:
        timestamp = captured_at.replace(":", "-").replace("+", "_")
        object_key = f"incidents/{trace_id}/{timestamp}.jpg"
        self._client.put_object(
            self.bucket,
            object_key,
            BytesIO(data),
            length=len(data),
            content_type="image/jpeg",
        )
        return object_key
