"""Run exactly one cell of the frozen 3 x 4 official GDN sweep."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import traceback
from datetime import datetime, timezone
from pathlib import Path

import zoology.train as train_module

from repro.cache_contract import sha256_file, validate_manifest
from repro.configs.gdn_mqar_official import configs
from repro.local_logger import LocalArtifactLogger


ROOT = Path(__file__).resolve().parents[1]


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(ROOT), *args],
        text=True,
    ).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--suite-dir", type=Path, required=True)
    args = parser.parse_args()

    if not 0 <= args.index < len(configs):
        raise ValueError(f"index must be in [0, {len(configs) - 1}]")
    config = configs[args.index]
    suite_dir = args.suite_dir.resolve()
    run_dir = suite_dir / (
        f"{args.index:02d}__d{config.model.d_model}"
        f"__lr{float(config.learning_rate):.10g}"
    )
    metadata_path = suite_dir / f"run-{args.index:02d}-metadata.json"
    if run_dir.exists() or metadata_path.exists():
        raise FileExistsError(
            f"refusing to overwrite existing cell {args.index}: "
            f"{run_dir} or {metadata_path}"
        )

    cache_dir = Path(config.data.cache_dir).resolve()
    validate_manifest(cache_dir)
    cache_manifest_path = cache_dir / "manifest.json"
    os.environ["ZOOLOGY_LOCAL_RUN_DIR"] = str(run_dir)
    os.environ.setdefault("WANDB_MODE", "offline")
    os.environ["WANDB_RUN_ID"] = (
        f"zoo-gdn-d{config.model.d_model}-"
        f"lr{float(config.learning_rate):.3g}-i{args.index:02d}"
    )

    metadata = {
        "schema_version": 1,
        "index": args.index,
        "git_sha": _git("rev-parse", "HEAD"),
        "git_tree": _git("rev-parse", "HEAD^{tree}"),
        "git_describe": _git("describe", "--always", "--dirty"),
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "d_model": config.model.d_model,
        "learning_rate": float(config.learning_rate),
        "seed": config.seed,
        "upstream_result_snapshot": (
            "b386338b37ce46a9257afc0a64786b0dc5a37676"
        ),
        "vendored_fla_sha": "d30c0833f9286bd5bf43c20395db53c6bab97a2d",
        "official_config_sha256": sha256_file(
            ROOT / "zoology" / "experiments" / "030325_new_arch" / "configs.py"
        ),
        "cache_manifest_sha256": sha256_file(cache_manifest_path),
        "runtime_lock_sha256": sha256_file(ROOT / "repro" / "runtime_lock.json"),
        "uv_lock_sha256": sha256_file(ROOT / "uv.lock"),
    }
    suite_dir.mkdir(parents=True, exist_ok=True)
    with metadata_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(metadata, sort_keys=True, indent=2) + "\n")

    train_module.WandbLogger = LocalArtifactLogger
    try:
        train_module.train(config)
    except BaseException as error:
        run_dir.mkdir(parents=True, exist_ok=True)
        failure = {
            "status": "failed",
            "ended_utc": datetime.now(timezone.utc).isoformat(),
            "error_type": type(error).__name__,
            "error": str(error),
            "traceback": traceback.format_exc(),
        }
        (run_dir / "failure.json").write_text(
            json.dumps(failure, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        raise


if __name__ == "__main__":
    main()
