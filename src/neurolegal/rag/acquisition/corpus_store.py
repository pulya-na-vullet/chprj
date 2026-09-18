"""S3 storage for corpus source files (.docx).

`rag/` must not import `neurolegal.documents.*` (boundary guard), so the hub's
`S3BlobStore` cannot be reused. This is a deliberate small sibling of it, shaped
for corpus needs: get/head instead of presigned URLs.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import aioboto3
from botocore.exceptions import ClientError

from neurolegal.core.config import Settings, settings
from neurolegal.rag.acquisition.manifest import slugify_code_id

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@dataclass(frozen=True)
class ObjectInfo:
    size: int
    last_modified: datetime


class MissingS3CredentialsError(RuntimeError):
    """No S3 access/secret key configured — corpus storage is unavailable."""


def normalize_prefix(prefix: str) -> str:
    """A non-empty prefix always ends with `/` — otherwise keys glue together.

    `NEUROLEGAL_CORPUS_S3_PREFIX=corpus` (no slash) would otherwise produce
    `corpusgk-1.docx` instead of `corpus/gk-1.docx`.
    """
    return prefix if not prefix or prefix.endswith("/") else prefix + "/"


def corpus_key(code_id: str, prefix: str) -> str:
    # Ключ строится тем же slugify_code_id, который даёт
    # ManifestEntry.source_doc_id, поэтому имя объекта в бакете всегда равно
    # идентичности акта в БД. Своей нормализации здесь быть не должно: она
    # разводила бы ключ и source_doc_id для code_id, содержащих пробелы, и
    # объект перестал бы сопоставляться акту.
    return f"{normalize_prefix(prefix)}{slugify_code_id(code_id)}.docx"


class CorpusStore(Protocol):
    async def get(self, key: str) -> bytes: ...
    async def put(self, key: str, data: bytes, content_type: str = DOCX_CONTENT_TYPE) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def head(self, key: str) -> ObjectInfo | None: ...
    async def list_prefix(self, prefix: str) -> dict[str, ObjectInfo]: ...


class InMemoryCorpusStore:
    """Test/dev fake. Not for production use."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self._modified: dict[str, datetime] = {}

    async def get(self, key: str) -> bytes:
        if key not in self.objects:
            raise FileNotFoundError(key)
        return self.objects[key]

    async def put(self, key: str, data: bytes, content_type: str = DOCX_CONTENT_TYPE) -> None:
        self.objects[key] = data
        self._modified[key] = datetime.now(UTC)

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)
        self._modified.pop(key, None)

    async def head(self, key: str) -> ObjectInfo | None:
        if key not in self.objects:
            return None
        return ObjectInfo(size=len(self.objects[key]), last_modified=self._modified[key])

    async def list_prefix(self, prefix: str) -> dict[str, ObjectInfo]:
        return {
            key: ObjectInfo(size=len(data), last_modified=self._modified[key])
            for key, data in self.objects.items()
            if key.startswith(prefix)
        }


class S3CorpusStore:
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

    async def get(self, key: str) -> bytes:
        async with self._session.client(**self._client_kwargs) as client:  # type: ignore[call-overload]
            try:
                response = await client.get_object(Bucket=self._bucket, Key=key)
            except ClientError as exc:
                if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
                    raise FileNotFoundError(key) from exc
                raise
            body: bytes = await response["Body"].read()
            return body

    async def put(self, key: str, data: bytes, content_type: str = DOCX_CONTENT_TYPE) -> None:
        async with self._session.client(**self._client_kwargs) as client:  # type: ignore[call-overload]
            await client.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )

    async def delete(self, key: str) -> None:
        async with self._session.client(**self._client_kwargs) as client:  # type: ignore[call-overload]
            await client.delete_object(Bucket=self._bucket, Key=key)

    async def head(self, key: str) -> ObjectInfo | None:
        async with self._session.client(**self._client_kwargs) as client:  # type: ignore[call-overload]
            try:
                response = await client.head_object(Bucket=self._bucket, Key=key)
            except ClientError as exc:
                if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
                    return None
                raise
            return ObjectInfo(
                size=int(response["ContentLength"]),
                last_modified=response["LastModified"].astimezone(UTC),
            )

    async def list_prefix(self, prefix: str) -> dict[str, ObjectInfo]:
        """One paginated LIST instead of N HEADs — the admin list is O(1) calls."""
        out: dict[str, ObjectInfo] = {}
        async with self._session.client(**self._client_kwargs) as client:  # type: ignore[call-overload]
            paginator = client.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    out[obj["Key"]] = ObjectInfo(
                        size=int(obj["Size"]),
                        last_modified=obj["LastModified"].astimezone(UTC),
                    )
        return out


def build_corpus_store(s: Settings = settings) -> CorpusStore:
    if not s.s3_access_key or not s.s3_secret_key:
        raise MissingS3CredentialsError(
            "S3 credentials missing: set NEUROLEGAL_S3_ACCESS_KEY / NEUROLEGAL_S3_SECRET_KEY"
        )
    return S3CorpusStore(
        endpoint=s.s3_endpoint,
        bucket=s.s3_bucket,
        region=s.s3_region,
        access_key=s.s3_access_key,
        secret_key=s.s3_secret_key,
    )


def build_corpus_store_or_none(s: Settings = settings) -> CorpusStore | None:
    """Soft variant: `None` instead of an exception when S3 isn't configured.

    Callers that can degrade (CLI/ingest on local `docx_path`, the admin
    document list without file stats) use this; anything that genuinely needs
    the bucket checks for `None` and says so.
    """
    try:
        return build_corpus_store(s)
    except MissingS3CredentialsError:
        return None
