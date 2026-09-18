"""Pick the .docx source per manifest entry: S3 key wins, local path is the fallback.

Corpus files live in S3 (see the deploy spec); `docx_path` stays supported so a
developer without S3 credentials can still ingest from disk.
"""

from neurolegal.core.domain import RawDocument
from neurolegal.rag.acquisition.local_docx import LocalDocxAcquirer
from neurolegal.rag.acquisition.manifest import Manifest, get_entry
from neurolegal.rag.acquisition.s3_docx import S3DocxAcquirer


class DocxAcquirer:
    def __init__(
        self,
        manifest: Manifest,
        *,
        local: LocalDocxAcquirer,
        s3: S3DocxAcquirer | None = None,
    ) -> None:
        self._manifest = manifest
        self._local = local
        self._s3 = s3

    async def fetch(self, code_id: str) -> RawDocument:
        entry = get_entry(code_id, self._manifest)
        if entry.docx_s3_key is None:
            return await self._local.fetch(code_id)
        if self._s3 is None:
            raise RuntimeError(
                f"{code_id}: manifest points at S3 ({entry.docx_s3_key}) but S3 credentials "
                "are not configured — set NEUROLEGAL_S3_ACCESS_KEY / NEUROLEGAL_S3_SECRET_KEY"
            )
        return await self._s3.fetch(code_id)
