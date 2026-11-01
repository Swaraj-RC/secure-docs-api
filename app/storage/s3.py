import contextlib
from collections.abc import AsyncIterator
from typing import Any

from app.core.config import settings
from app.core.errors import NotFoundError

try:
    import aioboto3  # type: ignore[import-not-found]

    HAS_AIOBOTO3 = True
except ImportError:
    HAS_AIOBOTO3 = False


class S3Storage:
    """S3 storage backend using aioboto3 (optional dependency)."""

    def __init__(self) -> None:
        if not HAS_AIOBOTO3:
            raise RuntimeError(
                "S3Storage backend requested but 'aioboto3' is not installed. "
                "Install with 'pip install aioboto3' or switch SECURE_DOCS_STORAGE_BACKEND=local."
            )
        import aioboto3  # type: ignore[import-not-found]

        self.session = aioboto3.Session()
        self.bucket = settings.S3_BUCKET_NAME
        self.endpoint_url = settings.S3_ENDPOINT_URL or None
        self.region = settings.S3_REGION or None

    def _client_kwargs(self) -> dict[str, Any]:
        kw: dict[str, Any] = {}
        if self.endpoint_url:
            kw["endpoint_url"] = self.endpoint_url
        if self.region:
            kw["region_name"] = self.region
        if settings.S3_ACCESS_KEY_ID and settings.S3_SECRET_ACCESS_KEY:
            kw["aws_access_key_id"] = settings.S3_ACCESS_KEY_ID
            kw["aws_secret_access_key"] = settings.S3_SECRET_ACCESS_KEY
        return kw

    async def put(self, key: str, stream: AsyncIterator[bytes] | bytes) -> int:
        data: bytes
        if isinstance(stream, bytes):
            data = stream
        else:
            chunks = []
            async for chunk in stream:
                chunks.append(chunk)
            data = b"".join(chunks)

        async with self.session.client("s3", **self._client_kwargs()) as s3:
            await s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
            )
        return len(data)

    async def get(self, key: str) -> AsyncIterator[bytes]:
        async with self.session.client("s3", **self._client_kwargs()) as s3:
            try:
                response = await s3.get_object(Bucket=self.bucket, Key=key)
            except Exception as e:
                raise NotFoundError(f"Object {key} not found in S3", code="FILE_NOT_FOUND") from e

            body = response["Body"]

            async def _stream_reader() -> AsyncIterator[bytes]:
                while chunk := await body.read(64 * 1024):
                    yield chunk

            return _stream_reader()

    async def delete(self, key: str) -> None:
        async with self.session.client("s3", **self._client_kwargs()) as s3:
            with contextlib.suppress(Exception):
                await s3.delete_object(Bucket=self.bucket, Key=key)

    async def exists(self, key: str) -> bool:
        async with self.session.client("s3", **self._client_kwargs()) as s3:
            try:
                await s3.head_object(Bucket=self.bucket, Key=key)
                return True
            except Exception:
                return False
