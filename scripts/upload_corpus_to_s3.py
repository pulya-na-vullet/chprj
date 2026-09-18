"""One-off: upload corpus .docx files to S3 and rewrite the manifest.

Читает манифест, заливает файл каждой записи, где задан `docx_path`, в бакет
и заменяет локальный путь на `docx_s3_key`. Идемпотентен: если ключ уже
проставлен, запись пропускается. Запускать из корня репозитория.

    uv run python -m scripts.upload_corpus_to_s3 [--dry-run]
"""

import argparse
import asyncio
from pathlib import Path

from neurolegal.core.config import settings
from neurolegal.rag.acquisition.corpus_store import build_corpus_store, corpus_key
from neurolegal.rag.acquisition.manifest import load_manifest, save_manifest


async def main(dry_run: bool) -> None:
    manifest_path = Path("corpus/manifest.yaml")
    manifest = load_manifest(manifest_path)
    store = build_corpus_store()
    uploaded = 0
    for code_id, entry in manifest.entries.items():
        if entry.docx_s3_key is not None:
            print(f"skip {code_id}: already in S3 ({entry.docx_s3_key})")
            continue
        if entry.docx_path is None:
            print(f"skip {code_id}: no docx_path (pravo-only entry)")
            continue
        path = Path(entry.docx_path)
        if not path.is_file():
            print(f"MISS {code_id}: {path} not found — оставляю как есть")
            continue
        key = corpus_key(code_id, settings.corpus_s3_prefix)
        print(f"{'would upload' if dry_run else 'upload'} {path} -> {key}")
        if dry_run:
            continue
        await store.put(key, path.read_bytes())
        manifest.entries[code_id] = entry.model_copy(update={"docx_s3_key": key, "docx_path": None})
        uploaded += 1
    if not dry_run and uploaded:
        save_manifest(manifest, manifest_path)
    print(f"done: {uploaded} uploaded")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    asyncio.run(main(parser.parse_args().dry_run))
