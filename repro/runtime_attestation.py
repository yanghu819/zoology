"""Capture and compare the live runtime used by a reproduction cell."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import io
import json
import os
import platform
import re
import socket
import stat
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_LOCK_PATH = ROOT / "repro" / "runtime_lock.json"
SCHEMA_VERSION = 1
VOLATILE_FIELDS = frozenset({"captured_utc", "hostname"})
ATTESTATION_FIELDS = frozenset(
    {
        "schema_version",
        "captured_utc",
        "aistation_target",
        "git_sha",
        "git_tree",
        "hostname",
        "python",
        "torch",
        "torchvision",
        "triton",
        "causal_conv1d",
        "torch_cxx11_abi",
        "torch_cuda_runtime",
        "cuda_available",
        "cuda_device_count",
        "gpu",
    }
)
GPU_FIELDS = frozenset({"name", "uuid", "driver_version"})


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise RuntimeError(f"cannot stat JSON input {path}: {error}") from error
    if stat.S_ISLNK(metadata.st_mode):
        raise RuntimeError(f"refusing symlink JSON input: {path}")
    if not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError(f"JSON input is not a regular file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"cannot read valid JSON input {path}: {error}") from error
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected a JSON object in {path}")
    return payload


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(ROOT), *args],
        text=True,
    ).strip()


def _expected_cuda_runtime(torch_version: str) -> str:
    match = re.search(r"\+cu(\d{2})(\d)$", torch_version)
    if match is None:
        raise RuntimeError(
            "runtime lock torch version does not encode a CUDA runtime: "
            f"{torch_version!r}"
        )
    return f"{int(match.group(1))}.{int(match.group(2))}"


def _query_gpu() -> dict[str, str]:
    command = [
        "nvidia-smi",
        "--query-gpu=name,uuid,driver_version",
        "--format=csv,noheader,nounits",
    ]
    try:
        output = subprocess.check_output(
            command,
            text=True,
            stderr=subprocess.STDOUT,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "output", None)
        raise RuntimeError(f"nvidia-smi query failed: {detail or error}") from error

    rows = [
        [field.strip() for field in row]
        for row in csv.reader(io.StringIO(output))
        if any(field.strip() for field in row)
    ]
    if len(rows) != 1:
        raise RuntimeError(
            f"expected exactly one nvidia-smi GPU row, found {len(rows)}"
        )
    if len(rows[0]) != 3 or not all(rows[0]):
        raise RuntimeError(f"invalid nvidia-smi GPU row: {rows[0]!r}")
    return dict(zip(("name", "uuid", "driver_version"), rows[0], strict=True))


def _validate_attestation_shape(payload: dict[str, Any]) -> None:
    fields = frozenset(payload)
    if fields != ATTESTATION_FIELDS:
        raise RuntimeError(
            "runtime attestation fields differ from the frozen schema: "
            f"missing={sorted(ATTESTATION_FIELDS - fields)} "
            f"unexpected={sorted(fields - ATTESTATION_FIELDS)}"
        )
    if payload["schema_version"] != SCHEMA_VERSION:
        raise RuntimeError(
            f"unsupported runtime-attestation schema: {payload['schema_version']!r}"
        )

    timestamp = payload["captured_utc"]
    if not isinstance(timestamp, str):
        raise RuntimeError("captured_utc must be a string")
    try:
        parsed_timestamp = datetime.fromisoformat(timestamp)
    except ValueError as error:
        raise RuntimeError(f"invalid captured_utc: {timestamp!r}") from error
    if parsed_timestamp.tzinfo is None:
        raise RuntimeError("captured_utc must include a timezone")
    if parsed_timestamp.utcoffset() != timedelta(0):
        raise RuntimeError("captured_utc must be UTC")

    string_fields = (
        "aistation_target",
        "git_sha",
        "git_tree",
        "hostname",
        "python",
        "torch",
        "torchvision",
        "triton",
        "causal_conv1d",
        "torch_cuda_runtime",
    )
    for field in string_fields:
        if not isinstance(payload[field], str) or not payload[field]:
            raise RuntimeError(f"{field} must be a nonempty string")
    for field in ("git_sha", "git_tree"):
        value = payload[field]
        if len(value) != 40 or re.fullmatch(r"[0-9a-f]{40}", value) is None:
            raise RuntimeError(f"{field} is not a full lowercase Git object ID")

    if type(payload["torch_cxx11_abi"]) is not bool:
        raise RuntimeError("torch_cxx11_abi must be a boolean")
    if type(payload["cuda_available"]) is not bool:
        raise RuntimeError("cuda_available must be a boolean")
    if (
        type(payload["cuda_device_count"]) is not int
        or payload["cuda_device_count"] < 0
    ):
        raise RuntimeError("cuda_device_count must be a nonnegative integer")

    gpu = payload["gpu"]
    if not isinstance(gpu, dict):
        raise RuntimeError("gpu must be a JSON object")
    gpu_fields = frozenset(gpu)
    if gpu_fields != GPU_FIELDS:
        raise RuntimeError(
            "GPU fields differ from the frozen schema: "
            f"missing={sorted(GPU_FIELDS - gpu_fields)} "
            f"unexpected={sorted(gpu_fields - GPU_FIELDS)}"
        )
    for field in sorted(GPU_FIELDS):
        if not isinstance(gpu[field], str) or not gpu[field]:
            raise RuntimeError(f"gpu.{field} must be a nonempty string")


def _validate_against_lock(
    payload: dict[str, Any],
    runtime_lock: dict[str, Any],
) -> None:
    _validate_attestation_shape(payload)
    expected_target = runtime_lock.get("expected_target")
    if expected_target != "GPU2":
        raise RuntimeError(
            "runtime lock expected_target must be literal GPU2, "
            f"got {expected_target!r}"
        )
    if payload["aistation_target"] != expected_target:
        raise RuntimeError(
            "runtime attestation is not bound to logical GPU2: "
            f"{payload['aistation_target']!r}"
        )

    exact_fields = {
        "torch": runtime_lock.get("torch"),
        "torchvision": runtime_lock.get("torchvision"),
        "triton": runtime_lock.get("triton"),
        "causal_conv1d": runtime_lock.get("causal_conv1d"),
        "torch_cxx11_abi": runtime_lock.get("torch_cxx11_abi"),
        "torch_cuda_runtime": _expected_cuda_runtime(str(runtime_lock.get("torch"))),
    }
    for field, expected in exact_fields.items():
        if payload[field] != expected:
            raise RuntimeError(
                f"runtime mismatch for {field}: "
                f"expected={expected!r} actual={payload[field]!r}"
            )

    python_prefix = runtime_lock.get("python_prefix")
    if not isinstance(python_prefix, str) or not payload["python"].startswith(
        python_prefix
    ):
        raise RuntimeError(
            "Python runtime mismatch: "
            f"expected_prefix={python_prefix!r} actual={payload['python']!r}"
        )
    if payload["cuda_available"] is not True:
        raise RuntimeError("CUDA must be available for a scored cell")
    if payload["cuda_device_count"] != 1:
        raise RuntimeError(
            "exactly one CUDA device is required, got "
            f"{payload['cuda_device_count']!r}"
        )


def capture_attestation() -> dict[str, Any]:
    """Capture and validate the live runtime against the committed lock."""
    import causal_conv1d  # noqa: F401
    import torch
    import torchvision
    import triton

    runtime_lock = _load_json_object(RUNTIME_LOCK_PATH)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "aistation_target": os.environ.get("AISTATION_TARGET", ""),
        "git_sha": _git("rev-parse", "HEAD"),
        "git_tree": _git("rev-parse", "HEAD^{tree}"),
        "hostname": socket.gethostname(),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "torchvision": torchvision.__version__,
        "triton": triton.__version__,
        "causal_conv1d": importlib.metadata.version("causal-conv1d"),
        "torch_cxx11_abi": bool(torch._C._GLIBCXX_USE_CXX11_ABI),
        "torch_cuda_runtime": torch.version.cuda or "",
        "cuda_available": bool(torch.cuda.is_available()),
        "cuda_device_count": int(torch.cuda.device_count()),
        "gpu": _query_gpu(),
    }
    _validate_against_lock(payload, runtime_lock)
    return payload


def _publish_exclusive_json(path: Path, payload: dict[str, Any]) -> str:
    path = path.absolute()
    parent = path.parent
    try:
        parent_metadata = parent.lstat()
    except OSError as error:
        raise RuntimeError(f"cannot stat output directory {parent}: {error}") from error
    if stat.S_ISLNK(parent_metadata.st_mode):
        raise RuntimeError(f"refusing symlink output directory: {parent}")
    if not stat.S_ISDIR(parent_metadata.st_mode):
        raise RuntimeError(f"output parent is not a directory: {parent}")
    try:
        path.lstat()
    except FileNotFoundError:
        pass
    except OSError as error:
        raise RuntimeError(f"cannot stat output path {path}: {error}") from error
    else:
        raise FileExistsError(f"refusing to overwrite runtime attestation: {path}")

    encoded = (
        json.dumps(
            payload,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
        directory_descriptor = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return hashlib.sha256(encoded).hexdigest()


def compare_attestations(baseline_path: Path, candidate_path: Path) -> None:
    """Require two attestations to match on every stable field."""
    runtime_lock = _load_json_object(RUNTIME_LOCK_PATH)
    baseline = _load_json_object(baseline_path)
    candidate = _load_json_object(candidate_path)
    _validate_against_lock(baseline, runtime_lock)
    _validate_against_lock(candidate, runtime_lock)

    stable_baseline = {
        key: value for key, value in baseline.items() if key not in VOLATILE_FIELDS
    }
    stable_candidate = {
        key: value for key, value in candidate.items() if key not in VOLATILE_FIELDS
    }
    stable_baseline["gpu"] = {
        key: value for key, value in baseline["gpu"].items() if key != "uuid"
    }
    stable_candidate["gpu"] = {
        key: value for key, value in candidate["gpu"].items() if key != "uuid"
    }
    if stable_candidate != stable_baseline:
        differences = {
            key: {
                "baseline": stable_baseline.get(key),
                "candidate": stable_candidate.get(key),
            }
            for key in sorted(stable_baseline.keys() | stable_candidate.keys())
            if stable_baseline.get(key) != stable_candidate.get(key)
        }
        raise RuntimeError(
            "stable runtime or hardware fields drifted: "
            + json.dumps(differences, sort_keys=True)
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("--output", type=Path, required=True)

    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("--baseline", type=Path, required=True)
    compare_parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "capture":
        payload = capture_attestation()
        digest = _publish_exclusive_json(args.output, payload)
        print(f"runtime_attestation={args.output.absolute()} sha256={digest}")
    elif args.command == "compare":
        compare_attestations(args.baseline, args.candidate)
        print(
            "runtime_attestation_compare=pass "
            f"baseline={args.baseline.absolute()} "
            f"candidate={args.candidate.absolute()}"
        )


if __name__ == "__main__":
    main()
