"""Aggregate the 12 frozen runs and compare with the published raster plot."""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import stat
import uuid
from pathlib import Path

from repro.cache_contract import OFFICIAL_CONFIG_SHA256, sha256_file
from repro.configs.gdn_mqar_official import configs
from repro.suite_contract import assert_complete, require_suite_location


ROOT = Path(__file__).resolve().parents[1]


def _read_regular_file_nofollow(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise RuntimeError(
            f"cannot safely read aggregate output {path}: {error}"
        ) from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError(f"aggregate output is not a regular file: {path}")
        chunks = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _publish_immutable_text(path: Path, content: str) -> None:
    """Atomically create an output, or accept an identical prior publication."""
    encoded = content.encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(temporary, flags, 0o644)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError:
            if _read_regular_file_nofollow(path) != encoded:
                raise RuntimeError(
                    f"refusing to overwrite existing aggregate output: {path}"
                )
    finally:
        os.close(descriptor)
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite-dir", type=Path, required=True)
    args = parser.parse_args()
    suite_dir = require_suite_location(args.suite_dir)
    assert_complete(suite_dir)

    baseline = json.loads(
        (ROOT / "repro" / "official_baseline.json").read_text(encoding="utf-8")
    )
    official_by_d = {
        int(point["d_model"]): point for point in baseline["plot_points"]
    }
    expected_metadata_names = {
        f"run-{index:02d}-metadata.json" for index in range(len(configs))
    }
    metadata_paths = sorted(suite_dir.glob("run-??-metadata.json"))
    if {path.name for path in metadata_paths} != expected_metadata_names:
        raise RuntimeError("suite metadata does not contain exact indices 0..11")

    evidence_paths = [
        suite_dir / "source.tar.gz",
        suite_dir / "source.tar.gz.sha256",
        suite_dir / "cache-manifest.json",
        suite_dir / "cache-manifest.json.sha256",
        suite_dir / "nvidia-smi.txt",
        suite_dir / "runtime-attestation.json",
        suite_dir / "suite-manifest.json",
    ]
    missing_evidence = [str(path) for path in evidence_paths if not path.is_file()]
    if missing_evidence:
        raise RuntimeError(f"suite evidence is missing: {missing_evidence}")
    source_expected_sha = (
        (suite_dir / "source.tar.gz.sha256")
        .read_text(encoding="utf-8")
        .split()[0]
    )
    if sha256_file(suite_dir / "source.tar.gz") != source_expected_sha:
        raise RuntimeError("source snapshot hash mismatch")
    cache_expected_sha = (
        (suite_dir / "cache-manifest.json.sha256")
        .read_text(encoding="utf-8")
        .split()[0]
    )
    if sha256_file(suite_dir / "cache-manifest.json") != cache_expected_sha:
        raise RuntimeError("suite cache-manifest hash mismatch")

    rows = []
    common_contract = None
    for index, config in enumerate(configs):
        metadata_path = suite_dir / f"run-{index:02d}-metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        expected_run_dir = suite_dir / (
            f"{index:02d}__d{config.model.d_model}"
            f"__lr{float(config.learning_rate):.10g}"
        )
        if int(metadata["index"]) != index:
            raise RuntimeError(f"metadata index drift for cell {index}")
        if int(metadata["d_model"]) != int(config.model.d_model) or not math.isclose(
            float(metadata["learning_rate"]),
            float(config.learning_rate),
            rel_tol=0,
            abs_tol=1e-15,
        ):
            raise RuntimeError(f"official grid drift for cell {index}")

        contract = {
            key: metadata[key]
            for key in (
                "git_sha",
                "git_tree",
                "official_config_sha256",
                "cache_manifest_sha256",
                "runtime_lock_sha256",
                "uv_lock_sha256",
            )
        }
        if common_contract is None:
            common_contract = contract
        elif contract != common_contract:
            raise RuntimeError(f"mixed source/cache contract at cell {index}")
        if metadata["official_config_sha256"] != OFFICIAL_CONFIG_SHA256:
            raise RuntimeError("official config hash mismatch")
        if metadata["cache_manifest_sha256"] != cache_expected_sha:
            raise RuntimeError("cell is bound to a different cache manifest")

        required_run_paths = [
            expected_run_dir / "summary.json",
            expected_run_dir / "resolved-config.json",
            expected_run_dir / "model-metadata.json",
            expected_run_dir / "metrics.jsonl",
            suite_dir / "logs" / f"run-{index:02d}.log",
        ]
        missing_run_paths = [
            str(path) for path in required_run_paths if not path.is_file()
        ]
        if missing_run_paths:
            raise RuntimeError(
                f"cell {index} evidence is missing: {missing_run_paths}"
            )
        if (expected_run_dir / "failure.json").exists():
            raise RuntimeError(f"cell {index} has a failure record")

        summary = json.loads(
            (expected_run_dir / "summary.json").read_text(encoding="utf-8")
        )
        if summary.get("status") != "completed":
            raise RuntimeError(f"cell {index} is not completed")
        final_accuracy = summary["final_metrics"].get("valid/accuracy")
        if final_accuracy is None:
            raise RuntimeError(f"run {index} has no final valid/accuracy")
        numeric_summary = {
            "final_valid_accuracy": float(final_accuracy),
            "best_valid_accuracy": float(summary["best_valid_accuracy"]),
            "elapsed_seconds": float(summary["elapsed_seconds"]),
        }
        if not all(math.isfinite(value) for value in numeric_summary.values()):
            raise RuntimeError(f"cell {index} contains nonfinite summary values")

        resolved = json.loads(
            (expected_run_dir / "resolved-config.json").read_text(encoding="utf-8")
        )
        if int(resolved["model"]["d_model"]) != int(config.model.d_model):
            raise RuntimeError(f"resolved d_model drift for cell {index}")
        if not math.isclose(
            float(resolved["learning_rate"]),
            float(config.learning_rate),
            rel_tol=0,
            abs_tol=1e-15,
        ):
            raise RuntimeError(f"resolved learning-rate drift for cell {index}")

        model_metadata = json.loads(
            (expected_run_dir / "model-metadata.json").read_text(encoding="utf-8")
        )
        if int(model_metadata["state_size"]) != int(
            official_by_d[int(config.model.d_model)]["state_size_bytes"]
        ):
            raise RuntimeError(f"state-size proxy drift for cell {index}")
        rows.append(
            {
                **metadata,
                **numeric_summary,
                "num_parameters": int(model_metadata["num_parameters"]),
                "state_size_bytes": int(model_metadata["state_size"]),
                "resolved_config_sha256": sha256_file(
                    expected_run_dir / "resolved-config.json"
                ),
                "run_dir": str(expected_run_dir.relative_to(suite_dir)),
            }
        )
    if len(rows) != 12:
        raise RuntimeError(f"expected 12 completed runs, found {len(rows)}")

    frontier = []
    for d_model in (64, 128, 256):
        candidates = [row for row in rows if int(row["d_model"]) == d_model]
        best = max(candidates, key=lambda row: row["final_valid_accuracy"])
        official = official_by_d[d_model]
        frontier.append(
            {
                "d_model": d_model,
                "state_size_bytes": official["state_size_bytes"],
                "best_learning_rate": best["learning_rate"],
                "reproduced_accuracy": best["final_valid_accuracy"],
                "official_accuracy_exact": None,
                "official_accuracy_visual_approx": official[
                    "official_accuracy_visual_approx"
                ],
                "delta_vs_visual_approx": (
                    best["final_valid_accuracy"]
                    - official["official_accuracy_visual_approx"]
                ),
                "within_visual_tolerance": abs(
                    best["final_valid_accuracy"]
                    - official["official_accuracy_visual_approx"]
                )
                <= official["visual_tolerance"],
                "source_run_dir": best["run_dir"],
            }
        )

    payload = {
        "schema_version": 1,
        "comparison_boundary": (
            "Official exact W&B values are unavailable; deltas use digitized "
            "two-decimal visual approximations and are not exact-score claims."
        ),
        "runs": rows,
        "frontier": frontier,
    }
    _publish_immutable_text(
        suite_dir / "aggregate.json",
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
    )
    csv_handle = io.StringIO(newline="")
    writer = csv.DictWriter(csv_handle, fieldnames=list(frontier[0]))
    writer.writeheader()
    writer.writerows(frontier)
    _publish_immutable_text(suite_dir / "frontier.csv", csv_handle.getvalue())
    print(json.dumps(frontier, sort_keys=True))


if __name__ == "__main__":
    main()
