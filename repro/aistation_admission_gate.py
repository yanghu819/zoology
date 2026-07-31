"""Capture and validate local AIStation admission observations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from repro import aistation_clock_bracket as clock_bracket


TARGET = "GPU2"
EXPECTED_RESOURCE = "NVIDIA-A100-SXM4-80GB:1"
EXPECTED_GPU_NAME = "NVIDIA A100-SXM4-80GB"
APPROVED_HELPER_PATH = Path(
    "/Users/torusmini/.codex/skills/aistation-skill/scripts/"
    "aistation_api.js"
)
APPROVED_HELPER_SHA256 = (
    "628aefaa2de3eb09ad5e6e1397e04280650e01847da2d9192566137405230226"
)
HELPER_TIMEOUT_SECONDS = 30
PUSH_HELPER_TIMEOUT_SECONDS = 620
EXPECTED_PYTHON_EXECUTABLE = (
    "/Library/Developer/CommandLineTools/Library/Frameworks/"
    "Python3.framework/Versions/3.9/bin/python3.9"
)
EXPECTED_PYTHON_VERSION = "3.9.6"
REMOTE_IDENTITY_COMMAND = (
    "printf 'HOST='; hostname; "
    "printf 'BOOT_ID='; cat /proc/sys/kernel/random/boot_id; "
    "printf 'UNIX='; date -u +%s"
)
REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE_FLOORS = {"initial": 13_200, "pre-capture": 12_120}
PHASE_RAW_NAMES = {
    "initial": {
        "status": "status-running.json",
        "probe": "probe-running.json",
        "identity": "identity-running.json",
        "observation": "observation-initial.json",
    },
    "pre-capture": {
        "status": "status-pre-capture.json",
        "probe": "probe-pre-capture.json",
        "identity": "identity-pre-capture.json",
        "observation": "observation-pre-capture.json",
    },
}
RUN_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]*")
STAGE_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]*")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
GIT_OBJECT_PATTERN = re.compile(r"[0-9a-f]{40}")
HOSTNAME_PATTERN = re.compile(r"[A-Za-z0-9._-]+")
BOOT_ID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}"
)
CLOCK_BINDING_ATTEMPT_NAME = "clock-binding-attempt.json"
CLOCK_BINDING_NAME = "clock-binding.json"


class AdmissionGateError(RuntimeError):
    """Raised when an AIStation admission observation is invalid."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _validate_run_id(run_id: str) -> str:
    if RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise AdmissionGateError(
            "run id must contain lowercase letters, digits, or dashes"
        )
    return run_id


def _real_directory(path: Path, label: str) -> Path:
    absolute = Path(os.path.abspath(path))
    try:
        metadata = absolute.lstat()
    except OSError as error:
        raise AdmissionGateError(f"cannot stat {label}: {error}") from error
    if not stat.S_ISDIR(metadata.st_mode):
        raise AdmissionGateError(f"{label} is not a real directory")
    if absolute.resolve(strict=True) != absolute:
        raise AdmissionGateError(f"{label} uses a symlink or path alias")
    return absolute


def _real_file(path: Path, label: str) -> Path:
    absolute = Path(os.path.abspath(path))
    try:
        metadata = absolute.lstat()
    except OSError as error:
        raise AdmissionGateError(f"cannot stat {label}: {error}") from error
    if not stat.S_ISREG(metadata.st_mode):
        raise AdmissionGateError(f"{label} is not a real regular file")
    if absolute.resolve(strict=True) != absolute:
        raise AdmissionGateError(f"{label} uses a symlink or path alias")
    return absolute


def _write_exclusive(path: Path, payload: bytes) -> None:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _load_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AdmissionGateError(f"{label} is not valid JSON") from error
    if type(payload) is not dict:
        raise AdmissionGateError(f"{label} must be a JSON object")
    return payload


def _single_target(
    payload: dict[str, Any],
    command: str,
) -> dict[str, Any]:
    if payload.get("command") != command or payload.get("ok") is not True:
        raise AdmissionGateError(f"AIStation {command} helper call failed")
    targets = payload.get("targets")
    if type(targets) is not list or len(targets) != 1:
        raise AdmissionGateError(
            f"AIStation {command} must return exactly one target"
        )
    target = targets[0]
    if type(target) is not dict or target.get("wpName") != TARGET:
        raise AdmissionGateError(
            f"AIStation {command} target must be literal {TARGET}"
        )
    workspace_id = target.get("wpId")
    if type(workspace_id) is not str or not workspace_id:
        raise AdmissionGateError(
            f"AIStation {command} workspace id is invalid"
        )
    if target.get("wpStatus") != "Running":
        raise AdmissionGateError(
            f"AIStation {command} target is not Running"
        )
    return target


def _remaining_seconds(value: object) -> int:
    if type(value) is int:
        remaining = value
    elif type(value) is str and re.fullmatch(r"[0-9]+", value):
        remaining = int(value)
    else:
        raise AdmissionGateError("AIStation remainTime is not an integer")
    return remaining


def _validate_status(
    raw: bytes,
    minimum_remaining_seconds: int,
) -> tuple[str, int]:
    target = _single_target(_load_object(raw, "status response"), "status")
    if target.get("resource") != EXPECTED_RESOURCE:
        raise AdmissionGateError(
            "AIStation GPU2 resource differs from the frozen A100 resource"
        )
    remaining = _remaining_seconds(target.get("remainTime"))
    if remaining < minimum_remaining_seconds:
        raise AdmissionGateError(
            "AIStation GPU2 remaining time is below the admission floor: "
            f"remaining={remaining} required={minimum_remaining_seconds}"
        )
    return str(target["wpId"]), remaining


def _validate_probe(raw: bytes, workspace_id: str) -> str:
    target = _single_target(_load_object(raw, "probe response"), "probe")
    if target["wpId"] != workspace_id:
        raise AdmissionGateError("AIStation workspace changed before probe")
    result = target.get("probe")
    if (
        type(result) is not dict
        or result.get("ok") is not True
        or type(result.get("exitCode")) is not int
        or result.get("exitCode") != 0
        or type(result.get("stdout")) is not str
        or type(result.get("stderr")) is not str
    ):
        raise AdmissionGateError("AIStation GPU2 probe failed")
    lines = [line.strip() for line in result["stdout"].splitlines() if line.strip()]
    if len(lines) != 2 or HOSTNAME_PATTERN.fullmatch(lines[0]) is None:
        raise AdmissionGateError("AIStation GPU2 probe hostname is invalid")
    fields = [field.strip() for field in lines[1].split(",")]
    if len(fields) != 4 or fields[0] != EXPECTED_GPU_NAME:
        raise AdmissionGateError("AIStation GPU2 probe did not report the A100")
    return lines[0]


def _validate_identity(
    raw: bytes,
    workspace_id: str,
    probe_hostname: str,
) -> tuple[str, str, int]:
    target = _single_target(_load_object(raw, "identity response"), "exec")
    if target["wpId"] != workspace_id:
        raise AdmissionGateError("AIStation workspace changed before identity")
    result = target.get("exec")
    if (
        type(result) is not dict
        or result.get("ok") is not True
        or type(result.get("exitCode")) is not int
        or result.get("exitCode") != 0
        or type(result.get("stdout")) is not str
        or type(result.get("stderr")) is not str
    ):
        raise AdmissionGateError("AIStation GPU2 identity command failed")
    lines = [line.strip() for line in result["stdout"].splitlines() if line.strip()]
    if len(lines) != 3:
        raise AdmissionGateError("AIStation GPU2 identity output is invalid")
    host_match = re.fullmatch(r"HOST=([A-Za-z0-9._-]+)", lines[0])
    boot_match = re.fullmatch(
        r"BOOT_ID=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
        r"[0-9a-f]{4}-[0-9a-f]{12})",
        lines[1],
    )
    unix_match = re.fullmatch(r"UNIX=([0-9]{9,})", lines[2])
    if host_match is None or boot_match is None or unix_match is None:
        raise AdmissionGateError("AIStation GPU2 identity output is invalid")
    hostname = host_match.group(1)
    boot_id = boot_match.group(1)
    remote_unix_raw = unix_match.group(1)
    if hostname != probe_hostname:
        raise AdmissionGateError("GPU2 hostname changed between probe and identity")
    return hostname, boot_id, int(remote_unix_raw)


def _resolve_node() -> Path:
    candidate = shutil.which("node")
    if candidate is None:
        raise AdmissionGateError("node is unavailable")
    node = Path(candidate).resolve(strict=True)
    if not node.is_file() or not os.access(node, os.X_OK):
        raise AdmissionGateError("resolved node is not executable")
    return node


def _run_helper(
    node: Path,
    helper: Path,
    arguments: tuple[str, ...],
) -> subprocess.CompletedProcess:
    return _run_helper_with_timeout(
        node, helper, arguments, HELPER_TIMEOUT_SECONDS
    )


def _run_helper_with_timeout(
    node: Path,
    helper: Path,
    arguments: tuple[str, ...],
    timeout_seconds: int,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(node), str(helper), *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_seconds,
    )


def _clock_sample() -> tuple[int, int]:
    return time.time_ns(), time.monotonic_ns()


def _utc_from_ns(unix_ns: int) -> str:
    return (
        datetime.fromtimestamp(unix_ns / 1_000_000_000, timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _phase_paths(output_dir: Path, phase: str) -> dict[str, Path]:
    return {
        role: output_dir / name
        for role, name in PHASE_RAW_NAMES[phase].items()
    }


def _require_python_runtime() -> tuple[str, str]:
    try:
        executable = str(Path(sys.executable).resolve(strict=True))
    except OSError as error:
        raise AdmissionGateError(
            f"cannot resolve Python executable: {error}"
        ) from error
    version = platform.python_version()
    if executable != EXPECTED_PYTHON_EXECUTABLE:
        raise AdmissionGateError(
            "Python executable differs from the frozen local runtime"
        )
    if version != EXPECTED_PYTHON_VERSION:
        raise AdmissionGateError(
            "Python version differs from the frozen local runtime"
        )
    return executable, version


def _prepare_context(
    helper: Path,
    output_dir: Path,
    run_id: str,
    phase: str,
    node: Path | None,
    *,
    require_reserved_absent: bool = True,
) -> tuple[Path, Path, Path]:
    _require_python_runtime()
    _validate_run_id(run_id)
    if phase not in PHASE_FLOORS:
        raise AdmissionGateError(f"unsupported admission phase: {phase}")
    repo_root = REPO_ROOT.resolve(strict=True)
    output_dir = Path(os.path.abspath(output_dir))
    expected_output = repo_root / "artifacts" / f"admission-{run_id}"
    if output_dir != expected_output:
        raise AdmissionGateError(
            "admission output must be the canonical repo-local path"
        )
    output_dir = _real_directory(output_dir, "admission output directory")
    reserved_capture = repo_root / "artifacts" / run_id
    if require_reserved_absent and (
        reserved_capture.exists() or reserved_capture.is_symlink()
    ):
        raise AdmissionGateError("reserved local capture path already exists")
    helper = _real_file(helper, "AIStation helper")
    if helper != APPROVED_HELPER_PATH:
        raise AdmissionGateError("AIStation helper path differs from approved source")
    _require_helper_sha256(helper)
    node = _resolve_node() if node is None else _real_file(node, "node executable")
    if not os.access(node, os.X_OK):
        raise AdmissionGateError("node executable is not executable")
    return helper, output_dir, node


def _module_sha256() -> str:
    return _sha256_file(Path(__file__).resolve(strict=True))


def _require_helper_sha256(helper: Path) -> None:
    if _sha256_file(helper) != APPROVED_HELPER_SHA256:
        raise AdmissionGateError("AIStation helper differs from approved SHA256")


def _require_module_sha256(expected: str) -> str:
    if type(expected) is not str or SHA256_PATTERN.fullmatch(expected) is None:
        raise AdmissionGateError(
            "module SHA256 must be 64 lowercase hexadecimal characters"
        )
    actual = _module_sha256()
    if actual != expected:
        raise AdmissionGateError(
            "admission-gate module differs from the frozen SHA256"
        )
    return actual


def _validate_observation(
    output_dir: Path,
    run_id: str,
    phase: str,
    *,
    expected_initial: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bytes]:
    paths = _phase_paths(output_dir, phase)
    observation_raw = _real_file(
        paths["observation"], f"{phase} observation"
    ).read_bytes()
    observation = _load_object(observation_raw, f"{phase} observation")
    if observation_raw != _canonical_json(observation):
        raise AdmissionGateError(f"{phase} observation is not canonical JSON")
    expected_keys = {
        "schema_version",
        "kind",
        "run_id",
        "phase",
        "target",
        "workspace_id",
        "workspace_status",
        "resource",
        "reported_remaining_seconds",
        "minimum_remaining_seconds",
        "remote_hostname",
        "remote_boot_id",
        "remote_unix",
        "local_before_utc",
        "local_before_unix_ns",
        "local_after_utc",
        "local_after_unix_ns",
        "elapsed_monotonic_ns",
        "helper_path",
        "helper_sha256",
        "node_path",
        "python_executable",
        "python_version",
        "module_sha256",
        "raw_files_sha256",
        "initial_observation_sha256",
    }
    if set(observation) != expected_keys:
        raise AdmissionGateError(f"{phase} observation schema drift")
    expected_values = {
        "schema_version": 1,
        "kind": "aistation-admission-observation",
        "run_id": run_id,
        "phase": phase,
        "target": TARGET,
        "workspace_status": "Running",
        "resource": EXPECTED_RESOURCE,
        "minimum_remaining_seconds": PHASE_FLOORS[phase],
        "helper_path": str(APPROVED_HELPER_PATH),
        "helper_sha256": APPROVED_HELPER_SHA256,
        "python_executable": EXPECTED_PYTHON_EXECUTABLE,
        "python_version": EXPECTED_PYTHON_VERSION,
        "module_sha256": _module_sha256(),
    }
    for key, expected in expected_values.items():
        if type(observation.get(key)) is not type(expected) or observation[key] != expected:
            raise AdmissionGateError(f"{phase} observation field drift: {key}")
    raw_hashes = observation.get("raw_files_sha256")
    raw_names = PHASE_RAW_NAMES[phase]
    expected_raw_keys = {
        raw_names["status"],
        raw_names["probe"],
        raw_names["identity"],
    }
    if type(raw_hashes) is not dict or set(raw_hashes) != expected_raw_keys:
        raise AdmissionGateError(f"{phase} raw-file hash schema drift")
    raw_payloads: dict[str, bytes] = {}
    for role in ("status", "probe", "identity"):
        name = raw_names[role]
        expected_hash = raw_hashes.get(name)
        if type(expected_hash) is not str or SHA256_PATTERN.fullmatch(expected_hash) is None:
            raise AdmissionGateError(f"{phase} raw-file hash is invalid: {name}")
        raw = _real_file(paths[role], f"{phase} {role} response").read_bytes()
        if _sha256_bytes(raw) != expected_hash:
            raise AdmissionGateError(f"{phase} raw-file hash drift: {name}")
        raw_payloads[role] = raw
    workspace_id, remaining = _validate_status(
        raw_payloads["status"], PHASE_FLOORS[phase]
    )
    probe_hostname = _validate_probe(raw_payloads["probe"], workspace_id)
    hostname, boot_id, remote_unix = _validate_identity(
        raw_payloads["identity"], workspace_id, probe_hostname
    )
    derived = {
        "workspace_id": workspace_id,
        "reported_remaining_seconds": remaining,
        "remote_hostname": hostname,
        "remote_boot_id": boot_id,
        "remote_unix": remote_unix,
    }
    for key, expected in derived.items():
        if type(observation.get(key)) is not type(expected) or observation[key] != expected:
            raise AdmissionGateError(f"{phase} observation/raw drift: {key}")
    before_ns = observation.get("local_before_unix_ns")
    after_ns = observation.get("local_after_unix_ns")
    elapsed_ns = observation.get("elapsed_monotonic_ns")
    if (
        type(before_ns) is not int
        or type(after_ns) is not int
        or type(elapsed_ns) is not int
        or before_ns <= 0
        or after_ns < before_ns
        or elapsed_ns < 0
        or observation.get("local_before_utc") != _utc_from_ns(before_ns)
        or observation.get("local_after_utc") != _utc_from_ns(after_ns)
    ):
        raise AdmissionGateError(f"{phase} local clock evidence drift")
    if expected_initial is None:
        if observation.get("initial_observation_sha256") is not None:
            raise AdmissionGateError("initial observation has an unexpected parent")
    else:
        initial_hash = observation.get("initial_observation_sha256")
        if (
            type(initial_hash) is not str
            or SHA256_PATTERN.fullmatch(initial_hash) is None
            or initial_hash != _sha256_bytes(_canonical_json(expected_initial))
        ):
            raise AdmissionGateError("pre-capture initial-observation hash drift")
        for key in ("workspace_id", "remote_hostname", "remote_boot_id", "node_path"):
            if observation.get(key) != expected_initial.get(key):
                raise AdmissionGateError(f"pre-capture identity drift: {key}")
        if observation["remote_unix"] < expected_initial["remote_unix"]:
            raise AdmissionGateError(
                "pre-capture remote Unix time moved backwards"
            )
    return observation, observation_raw


def verify_observation(
    output_dir: Path,
    run_id: str,
    phase: str,
    module_sha256: str,
) -> dict[str, Any]:
    _require_module_sha256(module_sha256)
    _, output_dir, _ = _prepare_context(
        APPROVED_HELPER_PATH,
        output_dir,
        run_id,
        phase,
        _resolve_node(),
        require_reserved_absent=False,
    )
    initial = None
    if phase == "pre-capture":
        initial, _ = _validate_observation(output_dir, run_id, "initial")
    observation, _ = _validate_observation(
        output_dir, run_id, phase, expected_initial=initial
    )
    return observation


def _require_git_object(value: str, label: str) -> str:
    if type(value) is not str or GIT_OBJECT_PATTERN.fullmatch(value) is None:
        raise AdmissionGateError(
            f"{label} must be 40 lowercase hexadecimal characters"
        )
    return value


def _clock_binding_paths(output_dir: Path) -> tuple[Path, Path]:
    return (
        output_dir / CLOCK_BINDING_ATTEMPT_NAME,
        output_dir / CLOCK_BINDING_NAME,
    )


def _clock_binding_attempt(
    run_id: str,
    formal_source_sha: str,
    formal_source_tree: str,
    module_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "aistation-clock-binding-attempt",
        "run_id": run_id,
        "target": TARGET,
        "formal_source_sha": formal_source_sha,
        "formal_source_tree": formal_source_tree,
        "python_executable": EXPECTED_PYTHON_EXECUTABLE,
        "python_version": EXPECTED_PYTHON_VERSION,
        "admission_module_sha256": module_sha256,
    }


def _prepare_clock_binding_context(
    output_dir: Path,
    run_id: str,
    formal_source_sha: str,
    formal_source_tree: str,
    module_sha256: str,
) -> tuple[Path, str, str, str]:
    module_sha256 = _require_module_sha256(module_sha256)
    formal_source_sha = _require_git_object(
        formal_source_sha, "formal source SHA"
    )
    formal_source_tree = _require_git_object(
        formal_source_tree, "formal source tree"
    )
    _, output_dir, _ = _prepare_context(
        APPROVED_HELPER_PATH,
        output_dir,
        run_id,
        "pre-capture",
        _resolve_node(),
        require_reserved_absent=False,
    )
    return output_dir, formal_source_sha, formal_source_tree, module_sha256


def _load_clock_binding_attempt(
    attempt_path: Path,
    expected: dict[str, Any],
) -> bytes:
    raw = _real_file(attempt_path, "clock-binding attempt").read_bytes()
    payload = _load_object(raw, "clock-binding attempt")
    if raw != _canonical_json(payload) or payload != expected:
        raise AdmissionGateError("clock-binding attempt evidence drift")
    return raw


def _validated_clock_bundle(
    bundle_dir: Path,
) -> tuple[dict[str, Any], dict[str, bytes], dict[str, str]]:
    try:
        proof, _ = clock_bracket.validate_bundle(bundle_dir)
    except Exception as error:
        raise AdmissionGateError(
            f"formal clock bundle validation failed: {error}"
        ) from error
    raw_files = {
        name: _real_file(
            bundle_dir / name, f"clock bundle {name}"
        ).read_bytes()
        for name in clock_bracket.CAPTURE_FILE_NAMES
    }
    for name in (
        "capture-attempt.json",
        "clock-bracket.json",
        "capture-terminal.json",
    ):
        payload = _load_object(raw_files[name], f"clock bundle {name}")
        if raw_files[name] != clock_bracket._canonical_json(payload):
            raise AdmissionGateError(
                f"formal clock bundle file is not canonical: {name}"
            )
    hashes = {
        name: _sha256_bytes(raw) for name, raw in raw_files.items()
    }
    try:
        refreshed_proof, _ = clock_bracket.validate_bundle(bundle_dir)
    except Exception as error:
        raise AdmissionGateError(
            f"formal clock bundle revalidation failed: {error}"
        ) from error
    refreshed_raw = {
        name: _real_file(
            bundle_dir / name, f"refreshed clock bundle {name}"
        ).read_bytes()
        for name in clock_bracket.CAPTURE_FILE_NAMES
    }
    if refreshed_proof != proof or refreshed_raw != raw_files:
        raise AdmissionGateError("formal clock bundle drifted during binding")
    return proof, raw_files, hashes


def _build_clock_binding(
    output_dir: Path,
    bundle_dir: Path,
    run_id: str,
    formal_source_sha: str,
    formal_source_tree: str,
    module_sha256: str,
    attempt_raw: bytes,
) -> dict[str, Any]:
    initial, initial_raw = _validate_observation(
        output_dir, run_id, "initial"
    )
    pre_capture, pre_capture_raw = _validate_observation(
        output_dir,
        run_id,
        "pre-capture",
        expected_initial=initial,
    )
    proof, _, bundle_hashes = _validated_clock_bundle(bundle_dir)
    expected_proof = {
        "run_id": run_id,
        "target": TARGET,
        "workspace_id": pre_capture["workspace_id"],
        "remote_hostname": pre_capture["remote_hostname"],
        "remote_boot_id": pre_capture["remote_boot_id"],
        "formal_source_sha": formal_source_sha,
        "formal_source_tree": formal_source_tree,
        "helper_sha256": pre_capture["helper_sha256"],
    }
    for key, expected in expected_proof.items():
        if type(proof.get(key)) is not type(expected) or proof[key] != expected:
            raise AdmissionGateError(f"clock/admission binding drift: {key}")
    selected_unix = proof.get("selected_observed_unix")
    if type(selected_unix) is not int:
        raise AdmissionGateError("clock selected Unix time is invalid")
    if selected_unix < pre_capture["remote_unix"]:
        raise AdmissionGateError(
            "formal clock time precedes the pre-capture observation"
        )
    refreshed_initial, refreshed_initial_raw = _validate_observation(
        output_dir, run_id, "initial"
    )
    refreshed_pre, refreshed_pre_raw = _validate_observation(
        output_dir,
        run_id,
        "pre-capture",
        expected_initial=refreshed_initial,
    )
    if (
        refreshed_initial != initial
        or refreshed_initial_raw != initial_raw
        or refreshed_pre != pre_capture
        or refreshed_pre_raw != pre_capture_raw
    ):
        raise AdmissionGateError(
            "admission observations drifted during clock binding"
        )
    return {
        "schema_version": 1,
        "kind": "aistation-clock-binding",
        "run_id": run_id,
        "target": TARGET,
        "workspace_id": pre_capture["workspace_id"],
        "remote_hostname": pre_capture["remote_hostname"],
        "remote_boot_id": pre_capture["remote_boot_id"],
        "pre_capture_remote_unix": pre_capture["remote_unix"],
        "clock_selected_observed_unix": selected_unix,
        "formal_source_sha": formal_source_sha,
        "formal_source_tree": formal_source_tree,
        "helper_sha256": pre_capture["helper_sha256"],
        "python_executable": pre_capture["python_executable"],
        "python_version": pre_capture["python_version"],
        "admission_module_sha256": module_sha256,
        "clock_module_sha256": proof["module_sha256"],
        "binding_attempt_sha256": _sha256_bytes(attempt_raw),
        "initial_observation_sha256": _sha256_bytes(initial_raw),
        "pre_capture_observation_sha256": _sha256_bytes(pre_capture_raw),
        "clock_bracket_sha256": bundle_hashes["clock-bracket.json"],
        "capture_terminal_sha256": bundle_hashes["capture-terminal.json"],
        "bundle_files_sha256": bundle_hashes,
    }


def bind_clock(
    output_dir: Path,
    bundle_dir: Path,
    run_id: str,
    formal_source_sha: str,
    formal_source_tree: str,
    module_sha256: str,
) -> dict[str, Any]:
    (
        output_dir,
        formal_source_sha,
        formal_source_tree,
        module_sha256,
    ) = _prepare_clock_binding_context(
        output_dir,
        run_id,
        formal_source_sha,
        formal_source_tree,
        module_sha256,
    )
    attempt_path, binding_path = _clock_binding_paths(output_dir)
    for path in (attempt_path, binding_path):
        if path.exists() or path.is_symlink():
            raise FileExistsError(f"clock-binding output already exists: {path}")
    attempt = _clock_binding_attempt(
        run_id,
        formal_source_sha,
        formal_source_tree,
        module_sha256,
    )
    attempt_raw = _canonical_json(attempt)
    _write_exclusive(attempt_path, attempt_raw)
    binding = _build_clock_binding(
        output_dir,
        bundle_dir,
        run_id,
        formal_source_sha,
        formal_source_tree,
        module_sha256,
        attempt_raw,
    )
    if _load_clock_binding_attempt(attempt_path, attempt) != attempt_raw:
        raise AdmissionGateError("clock-binding attempt changed before commit")
    _write_exclusive(binding_path, _canonical_json(binding))
    return verify_clock_binding(
        output_dir,
        bundle_dir,
        run_id,
        formal_source_sha,
        formal_source_tree,
        module_sha256,
    )


def verify_clock_binding(
    output_dir: Path,
    bundle_dir: Path,
    run_id: str,
    formal_source_sha: str,
    formal_source_tree: str,
    module_sha256: str,
) -> dict[str, Any]:
    (
        output_dir,
        formal_source_sha,
        formal_source_tree,
        module_sha256,
    ) = _prepare_clock_binding_context(
        output_dir,
        run_id,
        formal_source_sha,
        formal_source_tree,
        module_sha256,
    )
    attempt_path, binding_path = _clock_binding_paths(output_dir)
    expected_attempt = _clock_binding_attempt(
        run_id,
        formal_source_sha,
        formal_source_tree,
        module_sha256,
    )
    attempt_raw = _load_clock_binding_attempt(
        attempt_path, expected_attempt
    )
    expected_binding = _build_clock_binding(
        output_dir,
        bundle_dir,
        run_id,
        formal_source_sha,
        formal_source_tree,
        module_sha256,
        attempt_raw,
    )
    binding_raw = _real_file(binding_path, "clock binding").read_bytes()
    binding = _load_object(binding_raw, "clock binding")
    if (
        binding_raw != _canonical_json(binding)
        or binding != expected_binding
    ):
        raise AdmissionGateError("clock-binding evidence drift")
    return binding


HelperRunner = Callable[
    [Path, Path, tuple[str, ...]], subprocess.CompletedProcess
]
OperationRunner = Callable[
    [Path, Path, tuple[str, ...], int], subprocess.CompletedProcess
]
ClockSampler = Callable[[], tuple[int, int]]


def _invoke_helper(
    runner: HelperRunner,
    node: Path,
    helper: Path,
    arguments: tuple[str, ...],
    output_path: Path,
    label: str,
) -> bytes:
    _require_helper_sha256(helper)
    try:
        result = runner(node, helper, arguments)
    except subprocess.TimeoutExpired as error:
        raw = error.stdout if type(error.stdout) is bytes else b""
        _write_exclusive(output_path, raw)
        _require_helper_sha256(helper)
        raise AdmissionGateError(f"{label} helper process timed out") from error
    raw = result.stdout
    if type(raw) is not bytes:
        raise AdmissionGateError(f"{label} helper stdout is not bytes")
    _write_exclusive(output_path, raw)
    _require_helper_sha256(helper)
    if type(result.returncode) is not int or result.returncode != 0:
        raise AdmissionGateError(f"{label} helper process failed")
    if type(result.stderr) is not bytes or result.stderr:
        raise AdmissionGateError(f"{label} helper process stderr is not empty")
    return raw


def capture_observation(
    helper: Path,
    output_dir: Path,
    run_id: str,
    phase: str,
    module_sha256: str,
    *,
    runner: HelperRunner = _run_helper,
    clock: ClockSampler = _clock_sample,
    node: Path | None = None,
) -> dict[str, Any]:
    _require_module_sha256(module_sha256)
    helper, output_dir, node = _prepare_context(
        helper, output_dir, run_id, phase, node
    )
    paths = _phase_paths(output_dir, phase)
    for path in paths.values():
        if path.exists() or path.is_symlink():
            raise FileExistsError(f"admission phase output already exists: {path}")
    initial = None
    initial_raw = None
    if phase == "pre-capture":
        initial, initial_raw = _validate_observation(
            output_dir, run_id, "initial"
        )

    before_unix_ns, before_monotonic_ns = clock()
    status_raw = _invoke_helper(
        runner,
        node,
        helper,
        ("status", TARGET),
        paths["status"],
        "status",
    )
    workspace_id, remaining = _validate_status(
        status_raw, PHASE_FLOORS[phase]
    )
    if initial is not None and workspace_id != initial["workspace_id"]:
        raise AdmissionGateError("pre-capture workspace differs from initial")

    probe_raw = _invoke_helper(
        runner,
        node,
        helper,
        ("probe", TARGET),
        paths["probe"],
        "probe",
    )
    probe_hostname = _validate_probe(probe_raw, workspace_id)
    if initial is not None and probe_hostname != initial["remote_hostname"]:
        raise AdmissionGateError("pre-capture probe hostname differs from initial")

    identity_raw = _invoke_helper(
        runner,
        node,
        helper,
        ("exec", TARGET, "--", REMOTE_IDENTITY_COMMAND),
        paths["identity"],
        "identity",
    )
    hostname, boot_id, remote_unix = _validate_identity(
        identity_raw, workspace_id, probe_hostname
    )
    if initial is not None:
        if hostname != initial["remote_hostname"]:
            raise AdmissionGateError("pre-capture hostname differs from initial")
        if boot_id != initial["remote_boot_id"]:
            raise AdmissionGateError("pre-capture boot id differs from initial")
        if remote_unix < initial["remote_unix"]:
            raise AdmissionGateError("pre-capture remote Unix time moved backwards")

    after_unix_ns, after_monotonic_ns = clock()
    if after_unix_ns < before_unix_ns or after_monotonic_ns < before_monotonic_ns:
        raise AdmissionGateError("local observation clock moved backwards")
    raw_payloads = {
        paths["status"]: status_raw,
        paths["probe"]: probe_raw,
        paths["identity"]: identity_raw,
    }
    raw_hashes = {
        path.name: _sha256_bytes(raw) for path, raw in raw_payloads.items()
    }
    for path, original in raw_payloads.items():
        persisted = _real_file(path, f"persisted {path.name}").read_bytes()
        if persisted != original or _sha256_bytes(persisted) != raw_hashes[path.name]:
            raise AdmissionGateError(f"raw helper response drifted: {path.name}")
    if initial is not None:
        refreshed_initial, refreshed_raw = _validate_observation(
            output_dir, run_id, "initial"
        )
        if refreshed_initial != initial or refreshed_raw != initial_raw:
            raise AdmissionGateError("initial observation drifted during capture")
    _require_helper_sha256(helper)
    observation = {
        "schema_version": 1,
        "kind": "aistation-admission-observation",
        "run_id": run_id,
        "phase": phase,
        "target": TARGET,
        "workspace_id": workspace_id,
        "workspace_status": "Running",
        "resource": EXPECTED_RESOURCE,
        "reported_remaining_seconds": remaining,
        "minimum_remaining_seconds": PHASE_FLOORS[phase],
        "remote_hostname": hostname,
        "remote_boot_id": boot_id,
        "remote_unix": remote_unix,
        "local_before_utc": _utc_from_ns(before_unix_ns),
        "local_before_unix_ns": before_unix_ns,
        "local_after_utc": _utc_from_ns(after_unix_ns),
        "local_after_unix_ns": after_unix_ns,
        "elapsed_monotonic_ns": after_monotonic_ns - before_monotonic_ns,
        "helper_path": str(helper),
        "helper_sha256": APPROVED_HELPER_SHA256,
        "node_path": str(node),
        "python_executable": EXPECTED_PYTHON_EXECUTABLE,
        "python_version": EXPECTED_PYTHON_VERSION,
        "module_sha256": module_sha256,
        "raw_files_sha256": raw_hashes,
        "initial_observation_sha256": (
            _sha256_bytes(initial_raw) if initial_raw is not None else None
        ),
    }
    _write_exclusive(paths["observation"], _canonical_json(observation))
    verified, _ = _validate_observation(
        output_dir, run_id, phase, expected_initial=initial
    )
    return verified


def _validate_stage(stage: str) -> str:
    if type(stage) is not str or STAGE_PATTERN.fullmatch(stage) is None:
        raise AdmissionGateError(
            "operation stage must contain lowercase letters, digits, or dashes"
        )
    return stage


def _operation_paths(
    output_dir: Path,
    stage: str,
) -> tuple[Path, Path, Path]:
    prefix = f"operation-{_validate_stage(stage)}"
    return (
        output_dir / f"{prefix}-attempt.json",
        output_dir / f"{prefix}-raw.json",
        output_dir / f"{prefix}-receipt.json",
    )


def _real_push_source(path_value: str) -> str:
    if type(path_value) is not str or not path_value:
        raise AdmissionGateError("push local path is missing")
    path = Path(path_value)
    if not path.is_absolute() or str(path) != path_value:
        raise AdmissionGateError("push local path must be exact and absolute")
    try:
        metadata = path.lstat()
    except OSError as error:
        raise AdmissionGateError(f"cannot stat push local path: {error}") from error
    if not (stat.S_ISREG(metadata.st_mode) or stat.S_ISDIR(metadata.st_mode)):
        raise AdmissionGateError("push local path is not a real file or directory")
    if path.resolve(strict=True) != path:
        raise AdmissionGateError("push local path uses a symlink or path alias")
    repo_root = REPO_ROOT.resolve(strict=True)
    if path != repo_root and repo_root not in path.parents:
        raise AdmissionGateError("push local path is outside the repository")
    return path_value


def _exact_remote_path(path_value: str) -> str:
    if type(path_value) is not str or not path_value:
        raise AdmissionGateError("push remote path is missing")
    path = PurePosixPath(path_value)
    if not path.is_absolute() or str(path) != path_value or ".." in path.parts:
        raise AdmissionGateError("push remote path must be exact and absolute")
    remote_root = PurePosixPath("/huyang2/zoology")
    if path != remote_root and remote_root not in path.parents:
        raise AdmissionGateError(
            "push remote path is outside /huyang2/zoology"
        )
    return path_value


def _operation_arguments(
    command: str,
    remote_command: str | None,
    local_path: str | None,
    remote_path: str | None,
) -> tuple[tuple[str, ...], int, str | None, str | None, str | None]:
    if command == "exec":
        if type(remote_command) is not str or not remote_command:
            raise AdmissionGateError("exec remote command is missing")
        if local_path is not None or remote_path is not None:
            raise AdmissionGateError("exec operation received push paths")
        return (
            ("exec", TARGET, "--", remote_command),
            HELPER_TIMEOUT_SECONDS,
            remote_command,
            None,
            None,
        )
    if command == "push":
        if remote_command is not None:
            raise AdmissionGateError("push operation received an exec command")
        if local_path is None or remote_path is None:
            raise AdmissionGateError("push operation paths are missing")
        local_path = _real_push_source(local_path)
        remote_path = _exact_remote_path(remote_path)
        return (
            ("push", TARGET, "--", local_path, remote_path),
            PUSH_HELPER_TIMEOUT_SECONDS,
            None,
            local_path,
            remote_path,
        )
    raise AdmissionGateError("operation command must be exec or push")


def _operation_parent(
    output_dir: Path,
    bundle_dir: Path | None,
    run_id: str,
    identity_parent: str,
    formal_source_sha: str | None,
    formal_source_tree: str | None,
    module_sha256: str,
) -> tuple[dict[str, Any], bytes]:
    if identity_parent == "initial":
        return _validate_observation(output_dir, run_id, "initial")
    if identity_parent == "pre-capture":
        initial, _ = _validate_observation(output_dir, run_id, "initial")
        return _validate_observation(
            output_dir,
            run_id,
            "pre-capture",
            expected_initial=initial,
        )
    if identity_parent != "binding":
        raise AdmissionGateError(
            "identity parent must be initial, pre-capture, or binding"
        )
    if (
        bundle_dir is None
        or formal_source_sha is None
        or formal_source_tree is None
    ):
        raise AdmissionGateError(
            "binding parent requires bundle and formal source arguments"
        )
    binding = verify_clock_binding(
        output_dir,
        bundle_dir,
        run_id,
        formal_source_sha,
        formal_source_tree,
        module_sha256,
    )
    binding_path = output_dir / CLOCK_BINDING_NAME
    return binding, _real_file(binding_path, "clock binding").read_bytes()


def _invoke_operation_helper(
    runner: OperationRunner,
    node: Path,
    helper: Path,
    arguments: tuple[str, ...],
    timeout_seconds: int,
    raw_path: Path,
    stage: str,
) -> bytes:
    _require_helper_sha256(helper)
    try:
        result = runner(node, helper, arguments, timeout_seconds)
    except subprocess.TimeoutExpired as error:
        raw = error.stdout if type(error.stdout) is bytes else b""
        _write_exclusive(raw_path, raw)
        _require_helper_sha256(helper)
        raise AdmissionGateError(
            f"operation {stage} helper process timed out"
        ) from error
    raw = result.stdout
    if type(raw) is not bytes:
        raise AdmissionGateError(
            f"operation {stage} helper stdout is not bytes"
        )
    _write_exclusive(raw_path, raw)
    _require_helper_sha256(helper)
    if type(result.returncode) is not int or result.returncode != 0:
        raise AdmissionGateError(
            f"operation {stage} helper process failed"
        )
    if type(result.stderr) is not bytes or result.stderr:
        raise AdmissionGateError(
            f"operation {stage} helper process stderr is not empty"
        )
    return raw


def _validate_operation_response(
    raw: bytes,
    command: str,
    workspace_id: str,
    local_path: str | None,
    remote_path: str | None,
) -> None:
    target = _single_target(_load_object(raw, "operation response"), command)
    if target["wpId"] != workspace_id:
        raise AdmissionGateError("operation workspace differs from its parent")
    operation = target.get(command)
    if (
        type(operation) is not dict
        or operation.get("ok") is not True
        or type(operation.get("exitCode")) is not int
        or operation.get("exitCode") != 0
        or type(operation.get("stdout")) is not str
        or type(operation.get("stderr")) is not str
    ):
        raise AdmissionGateError(f"AIStation {command} operation failed")
    if command == "push" and (
        operation.get("localPath") != local_path
        or operation.get("remotePath") != remote_path
    ):
        raise AdmissionGateError("AIStation push path echo differs from request")


def _operation_attempt(
    run_id: str,
    stage: str,
    command: str,
    identity_parent: str,
    parent_sha256: str,
    workspace_id: str,
    remote_command: str | None,
    local_path: str | None,
    remote_path: str | None,
    timeout_seconds: int,
    module_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "aistation-operation-attempt",
        "run_id": run_id,
        "stage": stage,
        "command": command,
        "target": TARGET,
        "workspace_id": workspace_id,
        "identity_parent": identity_parent,
        "identity_parent_sha256": parent_sha256,
        "remote_command": remote_command,
        "local_path": local_path,
        "remote_path": remote_path,
        "timeout_seconds": timeout_seconds,
        "helper_path": str(APPROVED_HELPER_PATH),
        "helper_sha256": APPROVED_HELPER_SHA256,
        "python_executable": EXPECTED_PYTHON_EXECUTABLE,
        "python_version": EXPECTED_PYTHON_VERSION,
        "admission_module_sha256": module_sha256,
    }


def _operation_receipt(
    attempt: dict[str, Any],
    attempt_raw: bytes,
    raw: bytes,
) -> dict[str, Any]:
    return {
        **attempt,
        "kind": "aistation-operation-receipt",
        "attempt_sha256": _sha256_bytes(attempt_raw),
        "raw_response_sha256": _sha256_bytes(raw),
    }


def run_operation(
    helper: Path,
    output_dir: Path,
    run_id: str,
    stage: str,
    command: str,
    identity_parent: str,
    module_sha256: str,
    *,
    remote_command: str | None = None,
    local_path: str | None = None,
    remote_path: str | None = None,
    bundle_dir: Path | None = None,
    formal_source_sha: str | None = None,
    formal_source_tree: str | None = None,
    runner: OperationRunner = _run_helper_with_timeout,
    node: Path | None = None,
) -> dict[str, Any]:
    module_sha256 = _require_module_sha256(module_sha256)
    helper, output_dir, node = _prepare_context(
        helper,
        output_dir,
        run_id,
        "initial" if identity_parent == "initial" else "pre-capture",
        node,
        require_reserved_absent=False,
    )
    stage = _validate_stage(stage)
    arguments, timeout_seconds, remote_command, local_path, remote_path = (
        _operation_arguments(
            command, remote_command, local_path, remote_path
        )
    )
    parent, parent_raw = _operation_parent(
        output_dir,
        bundle_dir,
        run_id,
        identity_parent,
        formal_source_sha,
        formal_source_tree,
        module_sha256,
    )
    attempt_path, raw_path, receipt_path = _operation_paths(
        output_dir, stage
    )
    for path in (attempt_path, raw_path, receipt_path):
        if path.exists() or path.is_symlink():
            raise FileExistsError(f"operation stage output already exists: {path}")
    attempt = _operation_attempt(
        run_id,
        stage,
        command,
        identity_parent,
        _sha256_bytes(parent_raw),
        str(parent["workspace_id"]),
        remote_command,
        local_path,
        remote_path,
        timeout_seconds,
        module_sha256,
    )
    attempt_raw = _canonical_json(attempt)
    _write_exclusive(attempt_path, attempt_raw)
    raw = _invoke_operation_helper(
        runner,
        node,
        helper,
        arguments,
        timeout_seconds,
        raw_path,
        stage,
    )
    _validate_operation_response(
        raw,
        command,
        str(parent["workspace_id"]),
        local_path,
        remote_path,
    )
    refreshed_parent, refreshed_parent_raw = _operation_parent(
        output_dir,
        bundle_dir,
        run_id,
        identity_parent,
        formal_source_sha,
        formal_source_tree,
        module_sha256,
    )
    if refreshed_parent != parent or refreshed_parent_raw != parent_raw:
        raise AdmissionGateError("operation identity parent drifted")
    _require_helper_sha256(helper)
    persisted_attempt = _real_file(
        attempt_path, "operation attempt"
    ).read_bytes()
    persisted_raw = _real_file(raw_path, "operation raw response").read_bytes()
    if persisted_attempt != attempt_raw or persisted_raw != raw:
        raise AdmissionGateError("operation evidence drifted before receipt")
    receipt = _operation_receipt(attempt, attempt_raw, raw)
    _write_exclusive(receipt_path, _canonical_json(receipt))
    _require_helper_sha256(helper)
    refreshed_attempt = _real_file(
        attempt_path, "operation attempt"
    ).read_bytes()
    refreshed_raw = _real_file(raw_path, "operation raw response").read_bytes()
    persisted_receipt = _real_file(
        receipt_path, "operation receipt"
    ).read_bytes()
    if (
        refreshed_attempt != attempt_raw
        or refreshed_raw != raw
        or persisted_receipt != _canonical_json(receipt)
    ):
        raise AdmissionGateError("operation evidence drifted after commit")
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("capture", "verify"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--output-dir", type=Path, required=True)
        command_parser.add_argument("--run-id", required=True)
        command_parser.add_argument(
            "--phase", choices=tuple(PHASE_FLOORS), required=True
        )
        command_parser.add_argument("--module-sha256", required=True)
        if command == "capture":
            command_parser.add_argument("--helper", type=Path, required=True)
    for command in ("bind-clock", "verify-binding"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--output-dir", type=Path, required=True)
        command_parser.add_argument("--bundle-dir", type=Path, required=True)
        command_parser.add_argument("--run-id", required=True)
        command_parser.add_argument("--formal-source-sha", required=True)
        command_parser.add_argument("--formal-source-tree", required=True)
        command_parser.add_argument("--module-sha256", required=True)
    operation_parser = subparsers.add_parser("run-operation")
    operation_parser.add_argument("--helper", type=Path, required=True)
    operation_parser.add_argument("--output-dir", type=Path, required=True)
    operation_parser.add_argument("--run-id", required=True)
    operation_parser.add_argument("--stage", required=True)
    operation_parser.add_argument(
        "--command",
        dest="operation_command",
        choices=("exec", "push"),
        required=True,
    )
    operation_parser.add_argument(
        "--identity-parent",
        choices=("initial", "pre-capture", "binding"),
        required=True,
    )
    operation_parser.add_argument("--module-sha256", required=True)
    operation_parser.add_argument("--remote-command")
    operation_parser.add_argument("--local-path")
    operation_parser.add_argument("--remote-path")
    operation_parser.add_argument("--bundle-dir", type=Path)
    operation_parser.add_argument("--formal-source-sha")
    operation_parser.add_argument("--formal-source-tree")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "capture":
            observation = capture_observation(
                arguments.helper,
                arguments.output_dir,
                arguments.run_id,
                arguments.phase,
                arguments.module_sha256,
            )
        elif arguments.command == "verify":
            observation = verify_observation(
                arguments.output_dir,
                arguments.run_id,
                arguments.phase,
                arguments.module_sha256,
            )
        elif arguments.command == "bind-clock":
            observation = bind_clock(
                arguments.output_dir,
                arguments.bundle_dir,
                arguments.run_id,
                arguments.formal_source_sha,
                arguments.formal_source_tree,
                arguments.module_sha256,
            )
        elif arguments.command == "verify-binding":
            observation = verify_clock_binding(
                arguments.output_dir,
                arguments.bundle_dir,
                arguments.run_id,
                arguments.formal_source_sha,
                arguments.formal_source_tree,
                arguments.module_sha256,
            )
        else:
            observation = run_operation(
                arguments.helper,
                arguments.output_dir,
                arguments.run_id,
                arguments.stage,
                arguments.operation_command,
                arguments.identity_parent,
                arguments.module_sha256,
                remote_command=arguments.remote_command,
                local_path=arguments.local_path,
                remote_path=arguments.remote_path,
                bundle_dir=arguments.bundle_dir,
                formal_source_sha=arguments.formal_source_sha,
                formal_source_tree=arguments.formal_source_tree,
            )
    except (AdmissionGateError, FileExistsError, OSError) as error:
        print(f"aistation admission gate: {error}", file=sys.stderr)
        return 1
    sys.stdout.buffer.write(_canonical_json(observation))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
