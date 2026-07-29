"""Materialize the frozen MQAR data before any scored model initialization."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import torch

from zoology.data.utils import prepare_data
from zoology.utils import set_determinism

from repro.cache_contract import (
    OFFICIAL_CONFIG_SHA256,
    cache_files,
    ensure_frozen_cache_directory,
    sha256_file,
    validate_manifest,
)
from repro.configs.gdn_mqar_official import configs


def main() -> None:
    config = configs[0]
    cache_dir = ensure_frozen_cache_directory()
    if cache_dir != Path(config.data.cache_dir):
        raise RuntimeError("frozen config/cache directory contract drifted")
    manifest_path = cache_dir / "manifest.json"
    existing_files = cache_files(cache_dir)
    if manifest_path.exists():
        validate_manifest(cache_dir)
        print(f"cache_manifest={manifest_path} status=validated")
        return
    if existing_files:
        raise RuntimeError(
            "refusing unmanifested pre-existing cache files; move them aside "
            "or use a new project-local cache directory"
        )

    started_utc = datetime.now(timezone.utc).isoformat()
    set_determinism(config.seed)
    prepare_data(config.data)

    generated_files = cache_files(cache_dir)
    if len(generated_files) != 12:
        raise RuntimeError(
            f"expected 12 frozen cache files, found {len(generated_files)}"
        )
    manifest = {
        "schema_version": 1,
        "origin": "generated_by_frozen_prewarm",
        "cache_dir": str(cache_dir),
        "official_config_sha256": OFFICIAL_CONFIG_SHA256,
        "generation_seed": int(config.seed),
        "torch_version": torch.__version__,
        "started_utc": started_utc,
        "ended_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
        ).strip(),
        "git_tree": subprocess.check_output(
            ["git", "rev-parse", "HEAD^{tree}"],
            text=True,
        ).strip(),
        "files": [
            {
                "name": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in generated_files
        ],
    }
    temporary_path = manifest_path.with_suffix(".json.tmp")
    temporary_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_path, manifest_path)
    validate_manifest(cache_dir)
    print(f"cache_manifest={manifest_path} status=generated")


if __name__ == "__main__":
    main()
