"""Blob storage for original document bytes (S3) + an in-memory fake for tests."""

from pathlib import PurePosixPath
from typing import Protocol
from urllib.parse import quote

import aioboto3

from neurolegal.documents.config import DocumentsSettings


def content_disposition(filename: str) -> str:
    """`inline` c настоящим именем файла (RFC 5987 для кириллицы).

    Без него браузерный PDF-вьюер и «Скачать» показывают имя ключа S3
    («original.pdf») вместо имени документа пользователя.
    """
    suffix = PurePosixPath(filename).suffix
    fallback = "".join(ch if ch.isascii() and ch not in '"\\' else "_" for ch in filename)
    fallback = fallback.strip() or f"document{suffix}"
    encoded = quote(filename, safe="")
    return f"inline; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"


class BlobStore(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def presigned_url(
        self, key: str, expires_in: int = 900, *, filename: str | None = None
    ) -> str: ...
    async def delete(self, key: str) -> None: ...


class InMemoryBlobStore:
    """Test/dev fake. Not for production use."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def presigned_url(
        self, key: str, expires_in: int = 900, *, filename: str | None = None
    ) -> str:
        return f"memory://{key}?expires_in={expires_in}"

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)


class S3BlobStore:
    def __init__(
        self,
        *,
        endpoint: str | None,
        bucket: str,
        region: str,
        access_key: str,
        secret_key: str,
    ) -> None:
        self._bucket = bucket
        self._session = aioboto3.Session()
        self._client_kwargs = {
            "service_name": "s3",
            "endpoint_url": endpoint,
            "region_name": region,
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
        }

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        async with self._session.client(**self._client_kwargs) as client:  # type: ignore[call-overload]
            await client.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )

    async def presigned_url(
        self, key: str, expires_in: int = 900, *, filename: str | None = None
    ) -> str:
        params: dict[str, str] = {"Bucket": self._bucket, "Key": key}
        if filename:
            params["ResponseContentDisposition"] = content_disposition(filename)
        async with self._session.client(**self._client_kwargs) as client:  # type: ignore[call-overload]
            url: str = await client.generate_presigned_url(
                "get_object",
                Params=params,
                ExpiresIn=expires_in,
            )
            return url

    async def delete(self, key: str) -> None:
        async with self._session.client(**self._client_kwargs) as client:  # type: ignore[call-overload]
            await client.delete_object(Bucket=self._bucket, Key=key)


def build_blob_store(settings: DocumentsSettings) -> BlobStore:
    if not settings.s3_access_key or not settings.s3_secret_key:
        raise RuntimeError(
            "S3 credentials missing: set NEUROLEGAL_S3_ACCESS_KEY / NEUROLEGAL_S3_SECRET_KEY"
        )
    return S3BlobStore(
        endpoint=settings.s3_endpoint,
        bucket=settings.s3_bucket,
        region=settings.s3_region,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
    )
