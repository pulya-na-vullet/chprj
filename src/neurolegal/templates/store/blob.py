"""S3 storage for template .docx files + an in-memory fake for tests.

`templates/` must not import `neurolegal.documents.*` or `neurolegal.rag.*`
(boundary guard), so neither the hub's `S3BlobStore` nor the RAG `CorpusStore`
can be reused. This is a deliberate small sibling shaped for template needs:
raw get/put/delete, no presigned URLs (the .docx is streamed to the caller by
the render route, originals are downloaded only by the operator).
"""

from typing import Protocol

import aioboto3
from botocore.exceptions import ClientError

from neurolegal.templates.config import TemplatesSettings

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class UnsafeTemplateKeyError(ValueError):
    """S3 key escapes the templates prefix (or isn't a plain .docx key)."""


class TemplateBlobMissingError(RuntimeError):
    """The S3 object a template row points at does not exist."""


def normalize_prefix(prefix: str) -> str:
    """A non-empty prefix always ends with `/` — otherwise keys glue together
    (`templatesarenda.docx` instead of `templates/arenda.docx`)."""
    return prefix if not prefix or prefix.endswith("/") else prefix + "/"


def template_key(slug: str, prefix: str) -> str:
    return f"{normalize_prefix(prefix)}{slug}.docx"


def safe_template_key(raw: str, prefix: str) -> str:
    """Confine a template S3 key to the templates prefix of our own bucket.

    The bucket is shared with the documents hub (`owner/<uid>/<doc>/...`) and
    the RAG corpus (`corpus/...`), so an unvalidated key would let a crafted
    row read — or, with the admin CRUD, overwrite/delete — someone else's
    object.
    """
    safe = normalize_prefix(prefix)
    if (
        not raw.startswith(safe)
        or len(raw) <= len(safe)
        or not raw.lower().endswith(".docx")
        or ".." in raw
        or raw.startswith("/")
    ):
        raise UnsafeTemplateKeyError(
            f"S3 key must be a .docx under {safe!r} and contain no '..': {raw!r}"
        )
    return raw


class TemplatesBlobStore(Protocol):
    async def get(self, key: str) -> bytes: ...
    async def put(self, key: str, data: bytes, content_type: str = DOCX_CONTENT_TYPE) -> None: ...
    async def delete(self, key: str) -> None: ...


class InMemoryTemplatesBlobStore:
    """Test/dev fake. Not for production use."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def get(self, key: str) -> bytes:
        try:
            return self.objects[key]
        except KeyError as exc:
            raise TemplateBlobMissingError(key) from exc

    async def put(self, key: str, data: bytes, content_type: str = DOCX_CONTENT_TYPE) -> None:
        self.objects[key] = data

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)


class S3TemplatesBlobStore:
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
                code = exc.response.get("Error", {}).get("Code", "")
                if code in ("NoSuchKey", "404"):
                    raise TemplateBlobMissingError(key) from exc
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


def build_templates_blob_store(settings: TemplatesSettings) -> TemplatesBlobStore | None:
    """`None` when S3 credentials are absent — read-only routes keep working,
    render answers 503 (same degradation pattern as the RAG corpus store)."""
    if not settings.s3_access_key or not settings.s3_secret_key:
        return None
    return S3TemplatesBlobStore(
        endpoint=settings.s3_endpoint,
        bucket=settings.s3_bucket,
        region=settings.s3_region,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
    )
