import os
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, computed_field, model_validator

from neurolegal.core.domain import LegalActKind

_TRANSLIT: dict[str, str] = {
    "А": "a",
    "Б": "b",
    "В": "v",
    "Г": "g",
    "Д": "d",
    "Е": "e",
    "Ж": "zh",
    "З": "z",
    "И": "i",
    "Й": "y",
    "К": "k",
    "Л": "l",
    "М": "m",
    "Н": "n",
    "О": "o",
    "П": "p",
    "Р": "r",
    "С": "s",
    "Т": "t",
    "У": "u",
    "Ф": "f",
    "Х": "h",
    "Ц": "ts",
    "Ч": "ch",
    "Ш": "sh",
    "Щ": "sch",
    "Ъ": "",
    "Ы": "y",
    "Ь": "",
    "Э": "e",
    "Ю": "yu",
    "Я": "ya",
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def slugify_code_id(code_id: str) -> str:
    out: list[str] = []
    for ch in code_id:
        if ch == "-":
            out.append("-")
        elif ch.isascii() and (ch.isalnum() or ch == "-"):
            out.append(ch.lower())
        elif ch in _TRANSLIT:
            out.append(_TRANSLIT[ch])
        # silently drop other chars
    return "".join(out)


class ManifestEntry(BaseModel):
    code_id: str
    kind: LegalActKind
    short_name: str
    full_name: str
    redaction: str | None = None
    branch: str | None = None
    docx_path: Path | None = None
    docx_s3_key: str | None = None
    pravo_url: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def source_doc_id(self) -> str:
        return slugify_code_id(self.code_id)

    @model_validator(mode="after")
    def _at_least_one_locator(self) -> Self:
        if self.docx_path is None and self.docx_s3_key is None and self.pravo_url is None:
            raise ValueError(f"{self.code_id}: need docx_path, docx_s3_key or pravo_url")
        return self


class Manifest(BaseModel):
    entries: dict[str, ManifestEntry]


def load_manifest(path: Path = Path("corpus/manifest.yaml")) -> Manifest:
    raw = yaml.safe_load(path.read_text("utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"manifest must be a YAML list, got {type(raw).__name__}")
    entries: dict[str, ManifestEntry] = {}
    for item in raw:
        e = ManifestEntry.model_validate(item)
        if e.code_id in entries:
            raise ValueError(f"duplicate code_id in manifest: {e.code_id}")
        entries[e.code_id] = e
    return Manifest(entries=entries)


def manifest_to_yaml(manifest: Manifest) -> str:
    items: list[dict[str, object]] = []
    for e in manifest.entries.values():
        item: dict[str, object] = {
            "code_id": e.code_id,
            "kind": e.kind,
            "short_name": e.short_name,
            "full_name": e.full_name,
        }
        if e.redaction is not None:
            item["redaction"] = e.redaction
        if e.branch is not None:
            item["branch"] = e.branch
        if e.docx_path is not None:
            item["docx_path"] = str(e.docx_path)
        if e.docx_s3_key is not None:
            item["docx_s3_key"] = e.docx_s3_key
        if e.pravo_url is not None:
            item["pravo_url"] = e.pravo_url
        items.append(item)
    return yaml.safe_dump(items, allow_unicode=True, sort_keys=False)


def save_manifest(manifest: Manifest, path: Path = Path("corpus/manifest.yaml")) -> None:
    """Atomically rewrite the manifest file (tmp + os.replace).

    YAML comments are NOT preserved — accepted trade-off for UI edits
    (see the design spec, section 4).
    """
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(manifest_to_yaml(manifest), "utf-8")
    os.replace(tmp, path)


def get_entry(code_id: str, manifest: Manifest) -> ManifestEntry:
    if code_id not in manifest.entries:
        raise KeyError(f"unknown code_id={code_id!r}; known: {list(manifest.entries)}")
    return manifest.entries[code_id]
