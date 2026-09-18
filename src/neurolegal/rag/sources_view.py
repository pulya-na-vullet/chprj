"""Pure assembly of the client «Источники права» catalog.

Merges the manifest (names, kind, branch, redaction) with DB ingest stats to
derive a client-safe per-source status. No DB or I/O here — caller supplies
both inputs. Mirrors documents_view.build_documents but strips operator-only
fields.
"""

from neurolegal.contracts import SourceSummary
from neurolegal.rag.acquisition.manifest import Manifest
from neurolegal.rag.store.admin import ActDbStats


def build_sources(manifest: Manifest, stats: list[ActDbStats]) -> list[SourceSummary]:
    ingested = {s.source_doc_id for s in stats}
    out: list[SourceSummary] = []
    for entry in manifest.entries.values():
        out.append(
            SourceSummary(
                source_doc_id=entry.source_doc_id,
                short_name=entry.short_name,
                full_name=entry.full_name,
                kind=entry.kind,
                branch=entry.branch,
                redaction=entry.redaction,
                status="in_corpus" if entry.source_doc_id in ingested else "planned",
            )
        )
    out.sort(key=lambda s: (s.short_name, s.full_name))
    return out
