import json
from base64 import b64decode, b64encode
from datetime import datetime
from pathlib import Path

from neurolegal.core.domain import RawDocument


class RawCache:
    """Filesystem cache for fetched raw documents (one JSON file per (source, source_doc_id))."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, source: str, source_doc_id: str) -> Path:
        safe_source = source.replace("/", "_")
        safe_id = source_doc_id.replace("/", "_")
        return self._root / safe_source / f"{safe_id}.json"

    def get(self, source: str, source_doc_id: str) -> RawDocument | None:
        path = self._path(source, source_doc_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text("utf-8"))
        return RawDocument(
            source=data["source"],
            source_doc_id=data["source_doc_id"],
            fetched_at=datetime.fromisoformat(data["fetched_at"]),
            content_type=data["content_type"],
            body_bytes=b64decode(data["body_b64"]),
        )

    def put(self, source: str, source_doc_id: str, doc: RawDocument) -> None:
        path = self._path(source, source_doc_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "source": doc.source,
                    "source_doc_id": doc.source_doc_id,
                    "fetched_at": doc.fetched_at.isoformat(),
                    "content_type": doc.content_type,
                    "body_b64": b64encode(doc.body_bytes).decode("ascii"),
                }
            ),
            "utf-8",
        )
