"""Fail-closed lifecycle checks for the frozen 12-cell reproduction suite."""

from __future__ import annotations

import argparse
import json
import math
import stat
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from repro.cache_contract import (
    OFFICIAL_CONFIG_SHA256,
    sha256_file,
    validate_manifest,
)
from repro.config_serialization import dump_full_config
from repro.configs.gdn_mqar_official import configs
from repro.numeric_contract import require_finite
from repro.runtime_attestation import compare_attestations


ROOT = Path(__file__).resolve().parents[1]
CELL_TIMEOUT_SECONDS = 10_800
DEFAULT_MIN_REMAINING_SECONDS = 11_460
MAX_ADMISSION_OBSERVATION_AGE_SECONDS = 600
SUITE_MANIFEST_NAME = "suite-manifest.json"


def require_suite_location(suite_dir: Path, root: Path = ROOT) -> Path:
    """Return a real suite directory strictly below the project-local runs root."""
    supplied = Path(suite_dir)
    if supplied.is_symlink():
        raise RuntimeError(f"suite directory cannot be a symlink: {supplied}")
    resolved = supplied.resolve()
    runs_root = (root / "runs").resolve()
    if resolved == runs_root or not resolved.is_relative_to(runs_root):
        raise RuntimeError(
            f"suite directory must be a strict child of {runs_root}: {resolved}"
        )
    try:
        mode = resolved.lstat().st_mode
    except OSError as error:
        raise RuntimeError(f"cannot stat suite directory {resolved}: {error}") from error
    if not stat.S_ISDIR(mode):
        raise RuntimeError(f"suite path is not a real directory: {resolved}")
    return resolved


def _require_regular_file(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise RuntimeError(f"required regular file is missing {path}: {error}") from error
    if not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError(f"required path is not a regular file: {path}")


def _require_real_directory(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise RuntimeError(f"required directory is missing {path}: {error}") from error
    if not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError(f"required path is not a real directory: {path}")


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *args],
        text=True,
    ).strip()


def _load_object(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"cannot read valid JSON object {path}: {error}") from error
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object in {path}")
    return payload


def _load_metric_rows(path: Path) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise RuntimeError(f"cannot read metrics log {path}: {error}") from error
    if not lines:
        raise RuntimeError(f"metrics log is empty: {path}")

    rows = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise RuntimeError(f"blank metrics row at {path}:{line_number}")
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"invalid metrics JSON at {path}:{line_number}: {error}"
            ) from error
        if not isinstance(row, dict) or not row:
            raise RuntimeError(
                f"metrics row must be a nonempty object at {path}:{line_number}"
            )
        try:
            require_finite(row)
        except FloatingPointError as error:
            raise RuntimeError(
                f"nonfinite metrics value at {path}:{line_number}: {error}"
            ) from error
        for key, value in row.items():
            if "accuracy" not in key or isinstance(value, bool):
                continue
            if not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
                raise RuntimeError(
                    f"invalid accuracy at {path}:{line_number}: {key}={value!r}"
                )
        rows.append(row)
    return rows


def _read_sidecar_hash(path: Path) -> str:
    try:
        fields = path.read_text(encoding="utf-8").split()
    except OSError as error:
        raise RuntimeError(f"cannot read hash sidecar {path}: {error}") from error
    if len(fields) < 1 or len(fields[0]) != 64:
        raise RuntimeError(f"invalid SHA-256 sidecar {path}")
    return fields[0]


def _current_source_contract(root: Path, cache_manifest_sha256: str) -> dict:
    return {
        "git_sha": _git(root, "rev-parse", "HEAD"),
        "git_tree": _git(root, "rev-parse", "HEAD^{tree}"),
        "official_config_sha256": OFFICIAL_CONFIG_SHA256,
        "cache_manifest_sha256": cache_manifest_sha256,
        "runtime_lock_sha256": sha256_file(root / "repro" / "runtime_lock.json"),
        "uv_lock_sha256": sha256_file(root / "uv.lock"),
    }


def _active_cache_manifest() -> Path:
    cache_dirs = {Path(config.data.cache_dir).resolve() for config in configs}
    if len(cache_dirs) != 1:
        raise RuntimeError(f"official cells disagree on cache directory: {cache_dirs}")
    cache_dir = next(iter(cache_dirs))
    validate_manifest(cache_dir)
    return cache_dir / "manifest.json"


def _validate_evidence(suite_dir: Path) -> tuple[str, str, str]:
    evidence = {
        "source": suite_dir / "source.tar.gz",
        "source_hash": suite_dir / "source.tar.gz.sha256",
        "cache": suite_dir / "cache-manifest.json",
        "cache_hash": suite_dir / "cache-manifest.json.sha256",
        "nvidia": suite_dir / "nvidia-smi.txt",
        "runtime": suite_dir / "runtime-attestation.json",
    }
    for path in evidence.values():
        _require_regular_file(path)
    for directory in (
        suite_dir / "logs",
        suite_dir / "claims",
        suite_dir / "launches",
    ):
        _require_real_directory(directory)

    source_expected = _read_sidecar_hash(evidence["source_hash"])
    if sha256_file(evidence["source"]) != source_expected:
        raise RuntimeError("source snapshot hash mismatch")
    cache_expected = _read_sidecar_hash(evidence["cache_hash"])
    if sha256_file(evidence["cache"]) != cache_expected:
        raise RuntimeError("suite cache-manifest hash mismatch")
    return (
        source_expected,
        cache_expected,
        sha256_file(evidence["runtime"]),
    )


def build_suite_manifest(
    source_snapshot_sha256: str,
    cache_manifest_sha256: str,
    nvidia_smi_sha256: str,
    runtime_attestation_sha256: str,
    root: Path = ROOT,
) -> dict:
    """Return the immutable suite manifest for the current checkout."""
    return {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "cell_count": len(configs),
        "cell_indices": list(range(len(configs))),
        "cell_timeout_seconds": CELL_TIMEOUT_SECONDS,
        "default_min_remaining_seconds": DEFAULT_MIN_REMAINING_SECONDS,
        "source_snapshot_sha256": source_snapshot_sha256,
        "nvidia_smi_sha256": nvidia_smi_sha256,
        "runtime_attestation_sha256": runtime_attestation_sha256,
        **_current_source_contract(root, cache_manifest_sha256),
    }


def initialize_suite(suite_dir: Path, root: Path = ROOT) -> dict:
    """Bind a new suite to its immutable source, cache, and runtime contract."""
    suite_dir = suite_dir.resolve()
    (
        source_snapshot_sha256,
        cache_manifest_sha256,
        runtime_attestation_sha256,
    ) = _validate_evidence(suite_dir)
    active_cache_manifest = _active_cache_manifest()
    if sha256_file(active_cache_manifest) != cache_manifest_sha256:
        raise RuntimeError("suite evidence does not match the active cache manifest")

    payload = build_suite_manifest(
        source_snapshot_sha256,
        cache_manifest_sha256,
        sha256_file(suite_dir / "nvidia-smi.txt"),
        runtime_attestation_sha256,
        root,
    )
    manifest_path = suite_dir / SUITE_MANIFEST_NAME
    with manifest_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, indent=2) + "\n")
    return payload


def validate_suite(suite_dir: Path, root: Path = ROOT) -> dict:
    """Validate suite evidence and require the current checkout to match it."""
    suite_dir = suite_dir.resolve()
    (
        source_snapshot_sha256,
        cache_manifest_sha256,
        runtime_attestation_sha256,
    ) = _validate_evidence(suite_dir)
    manifest_path = suite_dir / SUITE_MANIFEST_NAME
    _require_regular_file(manifest_path)
    manifest = _load_object(manifest_path)

    frozen_fields = {
        "schema_version": 1,
        "cell_count": len(configs),
        "cell_indices": list(range(len(configs))),
        "cell_timeout_seconds": CELL_TIMEOUT_SECONDS,
        "default_min_remaining_seconds": DEFAULT_MIN_REMAINING_SECONDS,
    }
    for key, expected in frozen_fields.items():
        if manifest.get(key) != expected:
            raise RuntimeError(
                f"suite manifest field {key} drifted: "
                f"expected={expected!r} actual={manifest.get(key)!r}"
            )

    evidence_hashes = {
        "source_snapshot_sha256": source_snapshot_sha256,
        "nvidia_smi_sha256": sha256_file(suite_dir / "nvidia-smi.txt"),
        "runtime_attestation_sha256": runtime_attestation_sha256,
    }
    for key, expected in evidence_hashes.items():
        if manifest.get(key) != expected:
            raise RuntimeError(
                f"suite evidence mismatch for {key}: "
                f"expected={expected!r} actual={manifest.get(key)!r}"
            )

    current = _current_source_contract(root, cache_manifest_sha256)
    for key, expected in current.items():
        if manifest.get(key) != expected:
            raise RuntimeError(
                f"suite/current contract mismatch for {key}: "
                f"suite={manifest.get(key)!r} current={expected!r}"
            )
    return manifest


def _cell_paths(suite_dir: Path, index: int) -> dict[str, Path]:
    config = configs[index]
    run_dir = suite_dir / (
        f"{index:02d}__d{config.model.d_model}"
        f"__lr{float(config.learning_rate):.10g}"
    )
    return {
        "metadata": suite_dir / f"run-{index:02d}-metadata.json",
        "run_dir": run_dir,
        "log": suite_dir / "logs" / f"run-{index:02d}.log",
        "claim": suite_dir / "claims" / f"run-{index:02d}",
        "launch_dir": suite_dir / "launches" / f"run-{index:02d}",
        "request": suite_dir / "launches" / f"run-{index:02d}" / "request.json",
        "launch": suite_dir / "launches" / f"run-{index:02d}" / "launch.json",
        "worker_pid": suite_dir / "launches" / f"run-{index:02d}" / "worker.pid",
        "launcher_log": (
            suite_dir / "launches" / f"run-{index:02d}" / "launcher.log"
        ),
        "terminal": suite_dir / "launches" / f"run-{index:02d}" / "terminal.json",
        "runtime_attestation": (
            suite_dir
            / "claims"
            / f"run-{index:02d}"
            / "runtime-attestation.json"
        ),
        "summary": run_dir / "summary.json",
        "resolved_config": run_dir / "resolved-config.json",
        "model_metadata": run_dir / "model-metadata.json",
        "metrics": run_dir / "metrics.jsonl",
        "failure": run_dir / "failure.json",
    }


def validate_launch_terminal(suite_dir: Path, index: int) -> None:
    paths = _cell_paths(suite_dir, index)
    _require_real_directory(paths["launch_dir"])
    for path in (
        paths["request"],
        paths["launch"],
        paths["worker_pid"],
        paths["launcher_log"],
        paths["terminal"],
    ):
        _require_regular_file(path)

    request = _load_object(paths["request"])
    launch = _load_object(paths["launch"])
    terminal = _load_object(paths["terminal"])
    try:
        recorded_pid = int(paths["worker_pid"].read_text(encoding="utf-8").strip())
    except (OSError, TypeError, ValueError) as error:
        raise RuntimeError(f"invalid worker PID for cell {index}") from error
    if recorded_pid <= 0:
        raise RuntimeError(f"invalid worker PID for cell {index}")

    expected_suite = str(suite_dir.resolve())
    expected = {
        "request": (1, "requested", index, expected_suite),
        "launch": (1, "launched", index, expected_suite),
        "terminal": (1, "completed", index, recorded_pid, 0),
    }
    actual = {
        "request": (
            request.get("schema_version"),
            request.get("state"),
            request.get("cell_index"),
            str(Path(request.get("suite_dir", "")).resolve()),
        ),
        "launch": (
            launch.get("schema_version"),
            launch.get("state"),
            launch.get("cell_index"),
            str(Path(launch.get("suite_dir", "")).resolve()),
        ),
        "terminal": (
            terminal.get("schema_version"),
            terminal.get("state"),
            terminal.get("cell_index"),
            terminal.get("worker_pid"),
            terminal.get("exit_code"),
        ),
    }
    if actual != expected:
        raise RuntimeError(
            f"cell {index} launch/terminal contract mismatch: "
            f"expected={expected} actual={actual}"
        )
    if launch.get("worker_pid") != recorded_pid:
        raise RuntimeError(f"cell {index} launch PID disagrees with worker.pid")
    if launch.get("expected_git_sha") != _git(ROOT, "rev-parse", "HEAD"):
        raise RuntimeError(f"cell {index} launch expected Git SHA drifted")
    if launch.get("aistation_target") != "GPU2":
        raise RuntimeError(f"cell {index} launch target is not GPU2")
    if request.get("command") != launch.get("command"):
        raise RuntimeError(f"cell {index} launch command drifted")
    try:
        if not paths["launcher_log"].read_text(encoding="utf-8").strip():
            raise RuntimeError(f"cell {index} launcher log is empty")
    except OSError as error:
        raise RuntimeError(f"cannot read cell {index} launcher log: {error}") from error


def validate_active_launch(suite_dir: Path, index: int) -> None:
    """Validate the launcher handshake before the worker creates its cell claim."""
    paths = _cell_paths(suite_dir, index)
    _require_real_directory(paths["launch_dir"])
    for path in (
        paths["request"],
        paths["launch"],
        paths["worker_pid"],
        paths["launcher_log"],
    ):
        _require_regular_file(path)
    if paths["terminal"].exists() or paths["terminal"].is_symlink():
        raise RuntimeError(f"cell {index} active launch already has a terminal record")
    for path in (
        paths["metadata"],
        paths["run_dir"],
        paths["log"],
        paths["claim"],
    ):
        if path.exists() or path.is_symlink():
            raise RuntimeError(
                f"cell {index} active launch already has cell evidence: {path}"
            )

    request = _load_object(paths["request"])
    launch = _load_object(paths["launch"])
    try:
        recorded_pid = int(paths["worker_pid"].read_text(encoding="utf-8").strip())
    except (OSError, TypeError, ValueError) as error:
        raise RuntimeError(f"invalid active worker PID for cell {index}") from error
    if recorded_pid <= 0:
        raise RuntimeError(f"invalid active worker PID for cell {index}")
    expected_suite = str(suite_dir.resolve())
    if (
        request.get("schema_version") != 1
        or request.get("state") != "requested"
        or request.get("cell_index") != index
        or str(Path(request.get("suite_dir", "")).resolve()) != expected_suite
        or launch.get("schema_version") != 1
        or launch.get("state") != "launched"
        or launch.get("cell_index") != index
        or str(Path(launch.get("suite_dir", "")).resolve()) != expected_suite
        or launch.get("worker_pid") != recorded_pid
        or launch.get("expected_git_sha") != _git(ROOT, "rev-parse", "HEAD")
        or launch.get("aistation_target") != "GPU2"
        or request.get("command") != launch.get("command")
    ):
        raise RuntimeError(f"cell {index} active launch handshake drifted")


def validate_completed_cell(
    suite_dir: Path,
    index: int,
    suite_manifest: dict,
) -> None:
    """Require all evidence that aggregation needs for a completed cell."""
    config = configs[index]
    paths = _cell_paths(suite_dir, index)
    if paths["failure"].exists() or paths["failure"].is_symlink():
        raise RuntimeError(f"cell {index} has a failure record")

    _require_real_directory(paths["run_dir"])
    required = [
        paths["metadata"],
        paths["summary"],
        paths["resolved_config"],
        paths["model_metadata"],
        paths["metrics"],
        paths["log"],
        paths["runtime_attestation"],
    ]
    for path in required:
        _require_regular_file(path)
    _require_real_directory(paths["claim"])

    metadata = _load_object(paths["metadata"])
    try:
        schema_version = int(metadata["schema_version"])
        metadata_index = int(metadata["index"])
        metadata_d_model = int(metadata["d_model"])
        learning_rate = float(metadata["learning_rate"])
        seed = int(metadata["seed"])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(f"invalid metadata for cell {index}") from error
    if schema_version != 1:
        raise RuntimeError(f"metadata schema drift for cell {index}")
    if metadata_index != index:
        raise RuntimeError(f"metadata index drift for cell {index}")
    if metadata_d_model != int(config.model.d_model):
        raise RuntimeError(f"metadata d_model drift for cell {index}")
    if seed != int(config.seed):
        raise RuntimeError(f"metadata seed drift for cell {index}")
    if not math.isclose(
        learning_rate,
        float(config.learning_rate),
        rel_tol=0,
        abs_tol=1e-15,
    ):
        raise RuntimeError(f"metadata learning-rate drift for cell {index}")

    contract_keys = (
        "git_sha",
        "git_tree",
        "official_config_sha256",
        "cache_manifest_sha256",
        "runtime_lock_sha256",
        "uv_lock_sha256",
    )
    for key in contract_keys:
        if metadata.get(key) != suite_manifest.get(key):
            raise RuntimeError(f"cell {index} contract mismatch for {key}")
    expected_metadata = {
        "upstream_result_snapshot": (
            "b386338b37ce46a9257afc0a64786b0dc5a37676"
        ),
        "vendored_fla_sha": "d30c0833f9286bd5bf43c20395db53c6bab97a2d",
    }
    for key, expected in expected_metadata.items():
        if metadata.get(key) != expected:
            raise RuntimeError(f"cell {index} metadata drift for {key}")
    runtime_attestation_sha256 = sha256_file(paths["runtime_attestation"])
    if metadata.get("runtime_attestation_sha256") != runtime_attestation_sha256:
        raise RuntimeError(f"cell {index} runtime-attestation hash mismatch")
    compare_attestations(
        suite_dir / "runtime-attestation.json",
        paths["runtime_attestation"],
    )

    summary = _load_object(paths["summary"])
    if summary.get("status") != "completed":
        raise RuntimeError(f"cell {index} summary is not completed")
    try:
        numeric = (
            float(summary["elapsed_seconds"]),
            float(summary["best_valid_accuracy"]),
            float(summary["final_metrics"]["valid/accuracy"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(f"cell {index} summary is incomplete") from error
    if not all(math.isfinite(value) for value in numeric):
        raise RuntimeError(f"cell {index} summary contains nonfinite values")
    elapsed_seconds, best_valid_accuracy, final_valid_accuracy = numeric
    if elapsed_seconds <= 0:
        raise RuntimeError(f"cell {index} elapsed time is not positive")
    if not 0.0 <= best_valid_accuracy <= 1.0:
        raise RuntimeError(f"cell {index} best accuracy is outside [0, 1]")
    if not 0.0 <= final_valid_accuracy <= 1.0:
        raise RuntimeError(f"cell {index} final accuracy is outside [0, 1]")

    resolved = _load_object(paths["resolved_config"])
    expected_resolved = dump_full_config(config)
    if resolved != expected_resolved:
        raise RuntimeError(f"resolved config drift for cell {index}")

    baseline = _load_object(ROOT / "repro" / "official_baseline.json")
    expected_state_size = {
        int(point["d_model"]): int(point["state_size_bytes"])
        for point in baseline["plot_points"]
    }[int(config.model.d_model)]
    model_metadata = _load_object(paths["model_metadata"])
    try:
        state_size = int(model_metadata["state_size"])
        num_parameters = model_metadata["num_parameters"]
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(
            f"cell {index} model metadata is incomplete"
        ) from error
    if state_size != expected_state_size:
        raise RuntimeError(f"state-size proxy drift for cell {index}")
    if (
        isinstance(num_parameters, bool)
        or not isinstance(num_parameters, int)
        or num_parameters <= 0
    ):
        raise RuntimeError(f"cell {index} num_parameters is not a positive integer")

    metrics = _load_metric_rows(paths["metrics"])
    valid_accuracies = [
        float(row["valid/accuracy"])
        for row in metrics
        if "valid/accuracy" in row
    ]
    if not valid_accuracies:
        raise RuntimeError(f"cell {index} metrics have no valid/accuracy")
    if not math.isclose(
        final_valid_accuracy,
        valid_accuracies[-1],
        rel_tol=0,
        abs_tol=1e-15,
    ):
        raise RuntimeError(f"cell {index} final accuracy disagrees with metrics")
    if not math.isclose(
        best_valid_accuracy,
        max(valid_accuracies),
        rel_tol=0,
        abs_tol=1e-15,
    ):
        raise RuntimeError(f"cell {index} best accuracy disagrees with metrics")
    try:
        if not paths["log"].read_text(encoding="utf-8").strip():
            raise RuntimeError(f"cell {index} execution log is empty")
    except OSError as error:
        raise RuntimeError(f"cannot read cell {index} execution log: {error}") from error


def next_pending_index(
    suite_dir: Path,
    root: Path = ROOT,
    active_launch_index: int | None = None,
) -> int | None:
    """Return the next cell, rejecting any partial or non-contiguous history."""
    suite_dir = suite_dir.resolve()
    suite_manifest = validate_suite(suite_dir, root)
    expected_metadata_names = {
        f"run-{index:02d}-metadata.json" for index in range(len(configs))
    }
    unexpected_metadata = sorted(
        path.name
        for path in suite_dir.glob("run-*-metadata.json")
        if path.name not in expected_metadata_names
    )
    if unexpected_metadata:
        raise RuntimeError(
            f"suite contains unexpected cell metadata: {unexpected_metadata}"
        )
    first_pending = None
    for index in range(len(configs)):
        paths = _cell_paths(suite_dir, index)
        started = any(
            path.exists() or path.is_symlink()
            for path in (
                paths["metadata"],
                paths["run_dir"],
                paths["log"],
                paths["claim"],
                paths["launch_dir"],
            )
        )
        if index == active_launch_index:
            validate_active_launch(suite_dir, index)
            if first_pending is None:
                first_pending = index
            continue
        if not started:
            if first_pending is None:
                first_pending = index
            continue
        try:
            validate_completed_cell(suite_dir, index, suite_manifest)
            validate_launch_terminal(suite_dir, index)
        except RuntimeError as error:
            raise RuntimeError(
                f"cell {index} is partial, failed, or invalid: {error}"
            ) from error
        if first_pending is not None:
            raise RuntimeError(
                f"completed cell {index} appears after pending cell {first_pending}"
            )
    return first_pending


def prepare_cell(suite_dir: Path, index: int, root: Path = ROOT) -> None:
    """Validate cache and require ``index`` to be the exact next cell."""
    suite_dir = suite_dir.resolve()
    suite_manifest = validate_suite(suite_dir, root)
    active_cache_manifest = _active_cache_manifest()
    if sha256_file(active_cache_manifest) != suite_manifest["cache_manifest_sha256"]:
        raise RuntimeError("active cache no longer matches the suite contract")
    expected = next_pending_index(
        suite_dir,
        root,
        active_launch_index=index,
    )
    if expected is None:
        raise RuntimeError("suite is already complete")
    if index != expected:
        raise RuntimeError(f"next cell must be {expected}, got {index}")


def validate_cell(suite_dir: Path, index: int, root: Path = ROOT) -> None:
    if not 0 <= index < len(configs):
        raise ValueError(f"cell index must be in [0, {len(configs) - 1}]")
    suite_manifest = validate_suite(suite_dir, root)
    validate_completed_cell(suite_dir, index, suite_manifest)
    validate_launch_terminal(suite_dir, index)


def assert_complete(suite_dir: Path, root: Path = ROOT) -> None:
    next_index = next_pending_index(suite_dir, root)
    if next_index is not None:
        raise RuntimeError(f"suite is incomplete; next cell is {next_index}")


def validate_admission(
    remaining_seconds: int,
    observed_unix: int,
    minimum_seconds: int = DEFAULT_MIN_REMAINING_SECONDS,
    now_unix: int | None = None,
) -> int:
    if remaining_seconds < 0 or minimum_seconds < 0:
        raise ValueError("remaining and minimum seconds must be nonnegative")
    if minimum_seconds < DEFAULT_MIN_REMAINING_SECONDS:
        raise ValueError(
            "minimum seconds cannot be lower than the frozen "
            f"{DEFAULT_MIN_REMAINING_SECONDS}s admission floor"
        )
    if now_unix is None:
        now_unix = math.ceil(time.time())
    age_seconds = now_unix - observed_unix
    if age_seconds < -30:
        raise ValueError(
            "AIStation observation timestamp is implausibly in the future: "
            f"observed={observed_unix} now={now_unix}"
        )
    age_seconds = max(age_seconds, 0)
    if age_seconds > MAX_ADMISSION_OBSERVATION_AGE_SECONDS:
        raise RuntimeError(
            "AIStation observation is stale: "
            f"age={age_seconds}s max={MAX_ADMISSION_OBSERVATION_AGE_SECONDS}s"
        )
    adjusted_remaining = max(remaining_seconds - age_seconds, 0)
    if adjusted_remaining < minimum_seconds:
        raise RuntimeError(
            "insufficient AIStation time for a cell: "
            f"reported={remaining_seconds}s age={age_seconds}s "
            f"adjusted={adjusted_remaining}s required={minimum_seconds}s"
        )
    return adjusted_remaining


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("initialize", "next-index", "assert-complete"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--suite-dir", type=Path, required=True)

    for name in ("prepare-cell", "validate-artifacts", "validate-cell"):
        cell_parser = subparsers.add_parser(name)
        cell_parser.add_argument("--suite-dir", type=Path, required=True)
        cell_parser.add_argument("--index", type=int, required=True)

    admit_parser = subparsers.add_parser("admit")
    admit_parser.add_argument("--remaining-seconds", type=int, required=True)
    admit_parser.add_argument("--observed-unix", type=int, required=True)
    admit_parser.add_argument(
        "--minimum-seconds",
        type=int,
        default=DEFAULT_MIN_REMAINING_SECONDS,
    )
    args = parser.parse_args()
    if hasattr(args, "suite_dir"):
        args.suite_dir = require_suite_location(args.suite_dir)

    if args.command == "initialize":
        payload = initialize_suite(args.suite_dir)
        print(json.dumps(payload, sort_keys=True))
    elif args.command == "next-index":
        next_index = next_pending_index(args.suite_dir)
        print("complete" if next_index is None else next_index)
    elif args.command == "prepare-cell":
        prepare_cell(args.suite_dir, args.index)
    elif args.command == "validate-artifacts":
        suite_manifest = validate_suite(args.suite_dir)
        validate_completed_cell(args.suite_dir, args.index, suite_manifest)
    elif args.command == "validate-cell":
        validate_cell(args.suite_dir, args.index)
    elif args.command == "assert-complete":
        assert_complete(args.suite_dir)
    elif args.command == "admit":
        adjusted = validate_admission(
            args.remaining_seconds,
            args.observed_unix,
            args.minimum_seconds,
        )
        print(adjusted)


if __name__ == "__main__":
    main()
