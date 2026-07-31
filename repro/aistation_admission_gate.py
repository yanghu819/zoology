"""Capture and validate local AIStation admission observations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


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
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
HOSTNAME_PATTERN = re.compile(r"[A-Za-z0-9._-]+")
BOOT_ID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}"
)


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
    return subprocess.run(
        [str(node), str(helper), *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=HELPER_TIMEOUT_SECONDS,
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


def _prepare_context(
    helper: Path,
    output_dir: Path,
    run_id: str,
    phase: str,
    node: Path | None,
    *,
    require_reserved_absent: bool = True,
) -> tuple[Path, Path, Path]:
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


HelperRunner = Callable[
    [Path, Path, tuple[str, ...]], subprocess.CompletedProcess
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
        else:
            observation = verify_observation(
                arguments.output_dir,
                arguments.run_id,
                arguments.phase,
                arguments.module_sha256,
            )
    except (AdmissionGateError, FileExistsError, OSError) as error:
        print(f"aistation admission gate: {error}", file=sys.stderr)
        return 1
    sys.stdout.buffer.write(_canonical_json(observation))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
