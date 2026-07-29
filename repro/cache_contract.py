"""Create and validate the normalized synthetic-data cache manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


EXPECTED_FILE_COUNT = 12
OFFICIAL_CONFIG_SHA256 = (
    "dc29c0d5c908c60768f905afb3a683c6b14ad4774810d807fc1abcdbc767e672"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cache_files(cache_dir: Path) -> list[Path]:
    return sorted(cache_dir.glob("data_*.pt"))


def validate_manifest(cache_dir: Path) -> dict[str, Any]:
    manifest_path = cache_dir / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"cache manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise RuntimeError("unsupported cache-manifest schema")
    if manifest.get("origin") != "generated_by_frozen_prewarm":
        raise RuntimeError(f"untrusted cache origin: {manifest.get('origin')}")
    if manifest.get("official_config_sha256") != OFFICIAL_CONFIG_SHA256:
        raise RuntimeError("cache manifest is bound to a different config")

    entries = manifest.get("files")
    if not isinstance(entries, list) or len(entries) != EXPECTED_FILE_COUNT:
        raise RuntimeError(
            f"expected {EXPECTED_FILE_COUNT} cache entries, found "
            f"{len(entries) if isinstance(entries, list) else 'invalid'}"
        )
    names = [entry.get("name") for entry in entries]
    if len(set(names)) != EXPECTED_FILE_COUNT:
        raise RuntimeError("cache manifest contains duplicate filenames")
    actual_files = cache_files(cache_dir)
    if [path.name for path in actual_files] != sorted(names):
        raise RuntimeError("cache files do not match the frozen manifest")

    entries_by_name = {entry["name"]: entry for entry in entries}
    for path in actual_files:
        entry = entries_by_name[path.name]
        if path.stat().st_size != int(entry["bytes"]):
            raise RuntimeError(f"cache size drift: {path}")
        if sha256_file(path) != entry["sha256"]:
            raise RuntimeError(f"cache hash drift: {path}")
    return manifest
