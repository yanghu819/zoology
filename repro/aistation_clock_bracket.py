"""Capture AIStation status using the target host's clock domain."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import math
import socket
import stat
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TARGET = "GPU2"
APPROVED_HELPER_PATH = Path(
    "/Users/torusmini/.codex/skills/aistation-skill/scripts/"
    "aistation_api.js"
)
APPROVED_HELPER_SHA256 = (
    "628aefaa2de3eb09ad5e6e1397e04280650e01847da2d9192566137405230226"
)
REMOTE_CLOCK_COMMAND = (
    "printf 'HOST='; hostname; "
    "printf 'BOOT_ID='; cat /proc/sys/kernel/random/boot_id; "
    "printf 'UNIX='; date -u +%s"
)
MAX_BRACKET_SECONDS = 15
MIN_CONTROLLER_REMAINING_SECONDS = 12_060
HELPER_TIMEOUT_SECONDS = 30
HELPER_WRAPPER = (
    "const fs=require('fs');"
    "const path=require('path');"
    "const Module=require('module');"
    "const filename=process.argv[1];"
    "const source=fs.readFileSync(0,'utf8');"
    "process.argv=[process.execPath,filename,...process.argv.slice(2)];"
    "const loaded=new Module(filename);"
    "loaded.filename=filename;"
    "loaded.paths=Module._nodeModulePaths(path.dirname(filename));"
    "loaded._compile(source,filename);"
)
REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_RELATIVE_PATH = "repro/aistation_clock_bracket.py"
FULL_GIT_OBJECT = re.compile(r"[0-9a-f]{40}")
MAX_PUBLISH_AGE_SECONDS = 60
CAPTURE_HASHED_FILE_NAMES = (
    "capture-attempt.json",
    "helper-snapshot.js",
    "remote-before.json",
    "aistation-status.json",
    "remote-after.json",
    "clock-bracket.json",
)
CAPTURE_FILE_NAMES = (
    *CAPTURE_HASHED_FILE_NAMES,
    "capture-terminal.json",
)
SUITE_CLOCK_FILE_MAP = {
    "capture-attempt.json": "clock-capture-attempt.json",
    "helper-snapshot.js": "clock-helper-snapshot.js",
    "remote-before.json": "clock-remote-before.json",
    "aistation-status.json": "aistation-status.json",
    "remote-after.json": "clock-remote-after.json",
    "clock-bracket.json": "clock-bracket.json",
    "capture-terminal.json": "clock-capture-terminal.json",
}
SUITE_CLOCK_FILE_NAMES = tuple(SUITE_CLOCK_FILE_MAP.values())


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _validate_run_id(run_id: str) -> str:
    if not run_id or re.fullmatch(r"[a-z0-9][a-z0-9-]*", run_id) is None:
        raise RuntimeError(
            "run id must contain lowercase letters, digits, or dashes"
        )
    return run_id


def _require_full_hex(value: str, length: int, label: str) -> str:
    if re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is None:
        raise RuntimeError(f"{label} must be {length} lowercase hex characters")
    return value


def _parse_utc(value: Any, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as error:
        raise RuntimeError(f"{label} is not a valid ISO timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(
        parsed
    ):
        raise RuntimeError(f"{label} is not an explicit UTC timestamp")
    return parsed


def _real_directory(path: Path, label: str) -> Path:
    absolute = Path(os.path.abspath(path))
    try:
        metadata = absolute.lstat()
    except OSError as error:
        raise RuntimeError(f"cannot stat {label}: {error}") from error
    if not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError(f"{label} is not a real directory")
    resolved = absolute.resolve(strict=True)
    if resolved != absolute:
        raise RuntimeError(f"{label} uses a symlink or path alias")
    return absolute


def _load_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"{label} helper output is not JSON") from error
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} helper output must be a JSON object")
    return payload


def _target(payload: dict[str, Any], command: str) -> dict[str, Any]:
    if payload.get("command") != command or payload.get("ok") is not True:
        raise RuntimeError(f"AIStation {command} helper call failed")
    targets = payload.get("targets")
    if not isinstance(targets, list) or len(targets) != 1:
        raise RuntimeError(f"AIStation {command} must return exactly one target")
    target = targets[0]
    if not isinstance(target, dict) or target.get("wpName") != TARGET:
        raise RuntimeError(f"AIStation {command} target must be literal {TARGET}")
    if target.get("wpStatus") != "Running":
        raise RuntimeError(f"AIStation {command} target is not Running")
    workspace_id = target.get("wpId")
    if not isinstance(workspace_id, str) or not workspace_id:
        raise RuntimeError(f"AIStation {command} workspace id is invalid")
    return target


def _remote_identity(
    payload: dict[str, Any],
    label: str,
) -> tuple[int, str, str, str]:
    target = _target(payload, "exec")
    result = target.get("exec")
    if (
        not isinstance(result, dict)
        or result.get("ok") is not True
        or result.get("exitCode") != 0
    ):
        raise RuntimeError(f"{label} remote clock command failed")
    stdout = result.get("stdout")
    if not isinstance(stdout, str):
        raise RuntimeError(f"{label} remote clock stdout is invalid")
    hostnames = set(re.findall(r"(?m)^HOST=([A-Za-z0-9._-]+)\s*$", stdout))
    boot_ids = set(
        re.findall(
            r"(?m)^BOOT_ID=([0-9a-fA-F]{8}-[0-9a-fA-F-]{27})\s*$",
            stdout,
        )
    )
    timestamps = {
        int(value)
        for value in re.findall(r"(?m)^UNIX=(\d{9,})\s*$", stdout)
    }
    if len(hostnames) != 1:
        raise RuntimeError(f"{label} remote hostname is missing or ambiguous")
    if len(boot_ids) != 1:
        raise RuntimeError(f"{label} remote boot id is missing or ambiguous")
    if len(timestamps) != 1:
        raise RuntimeError(
            f"{label} remote Unix timestamp is missing or ambiguous"
        )
    return (
        timestamps.pop(),
        str(target["wpId"]),
        hostnames.pop(),
        boot_ids.pop().lower(),
    )


def _status_values(payload: dict[str, Any]) -> tuple[str, int]:
    target = _target(payload, "status")
    try:
        remaining_seconds = int(target["remainTime"])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("AIStation GPU2 remainTime is not an integer") from error
    if remaining_seconds < MIN_CONTROLLER_REMAINING_SECONDS:
        raise RuntimeError(
            "AIStation GPU2 remaining time is below the frozen controller "
            f"floor: remaining={remaining_seconds} "
            f"required={MIN_CONTROLLER_REMAINING_SECONDS}"
        )
    return str(target["wpId"]), remaining_seconds


def build_evidence(
    before_payload: dict[str, Any],
    before_raw: bytes,
    status_payload: dict[str, Any],
    status_raw: bytes,
    after_payload: dict[str, Any],
    after_raw: bytes,
    *,
    run_id: str,
    formal_source_sha: str,
    formal_source_tree: str,
    helper_sha256: str,
    module_sha256: str,
    capture_started_utc: str,
    capture_ended_utc: str,
    capture_elapsed_seconds: float,
) -> dict[str, Any]:
    """Validate a remote-clock bracket and return canonical evidence."""
    _validate_run_id(run_id)
    _require_full_hex(formal_source_sha, 40, "formal source SHA")
    _require_full_hex(formal_source_tree, 40, "formal source tree")
    _require_full_hex(helper_sha256, 64, "AIStation helper SHA256")
    _require_full_hex(module_sha256, 64, "clock-bracket module SHA256")
    if not math.isfinite(capture_elapsed_seconds):
        raise RuntimeError("AIStation status capture elapsed time is nonfinite")
    capture_started = _parse_utc(
        capture_started_utc,
        "capture_started_utc",
    )
    capture_ended = _parse_utc(
        capture_ended_utc,
        "capture_ended_utc",
    )
    wall_elapsed_seconds = (capture_ended - capture_started).total_seconds()
    if wall_elapsed_seconds < 0:
        raise RuntimeError("AIStation status capture ended before it started")
    if wall_elapsed_seconds > MAX_BRACKET_SECONDS + 5:
        raise RuntimeError(
            "AIStation status capture wall-clock span is implausibly wide: "
            f"span={wall_elapsed_seconds:.6f}s"
        )
    before_unix, before_workspace, before_hostname, before_boot_id = (
        _remote_identity(
            before_payload,
            "before-status",
        )
    )
    status_workspace, remaining_seconds = _status_values(status_payload)
    after_unix, after_workspace, after_hostname, after_boot_id = (
        _remote_identity(
            after_payload,
            "after-status",
        )
    )
    if len({before_workspace, status_workspace, after_workspace}) != 1:
        raise RuntimeError("AIStation workspace changed during status capture")
    if before_hostname != after_hostname:
        raise RuntimeError("GPU2 hostname changed during status capture")
    if before_boot_id != after_boot_id:
        raise RuntimeError("GPU2 boot id changed during status capture")
    bracket_span = after_unix - before_unix
    if bracket_span < 0:
        raise RuntimeError("remote clock moved backwards during status capture")
    if bracket_span > MAX_BRACKET_SECONDS:
        raise RuntimeError(
            "AIStation status capture exceeded the frozen remote-clock "
            f"bracket: span={bracket_span}s max={MAX_BRACKET_SECONDS}s"
        )
    if capture_elapsed_seconds < 0 or capture_elapsed_seconds > MAX_BRACKET_SECONDS:
        raise RuntimeError(
            "AIStation status capture exceeded the frozen local elapsed "
            f"bound: elapsed={capture_elapsed_seconds:.6f}s "
            f"max={MAX_BRACKET_SECONDS}s"
        )

    return {
        "schema_version": 1,
        "run_id": run_id,
        "formal_source_sha": formal_source_sha,
        "formal_source_tree": formal_source_tree,
        "target": TARGET,
        "workspace_id": status_workspace,
        "workspace_status": "Running",
        "remote_hostname": before_hostname,
        "remote_boot_id": before_boot_id,
        "remote_clock_command": REMOTE_CLOCK_COMMAND,
        "remote_before_unix": before_unix,
        "remote_before_utc": datetime.fromtimestamp(
            before_unix,
            timezone.utc,
        ).isoformat(),
        "remote_after_unix": after_unix,
        "remote_after_utc": datetime.fromtimestamp(
            after_unix,
            timezone.utc,
        ).isoformat(),
        "bracket_span_seconds": bracket_span,
        "selected_observed_unix": before_unix,
        "selected_observed_utc": datetime.fromtimestamp(
            before_unix,
            timezone.utc,
        ).isoformat(),
        "selected_observed_policy": (
            "conservative lower bound from the target host before the "
            "status API call"
        ),
        "reported_remaining_seconds": remaining_seconds,
        "minimum_controller_remaining_seconds": (
            MIN_CONTROLLER_REMAINING_SECONDS
        ),
        "maximum_bracket_seconds": MAX_BRACKET_SECONDS,
        "capture_started_utc": capture_started_utc,
        "capture_ended_utc": capture_ended_utc,
        "capture_elapsed_seconds": round(capture_elapsed_seconds, 6),
        "helper_sha256": helper_sha256,
        "module_sha256": module_sha256,
        "before_response_sha256": _sha256_bytes(before_raw),
        "status_response_sha256": _sha256_bytes(status_raw),
        "after_response_sha256": _sha256_bytes(after_raw),
    }


def _run_helper(
    helper_source: bytes,
    helper_virtual_path: Path,
    *arguments: str,
) -> tuple[dict[str, Any], bytes]:
    try:
        completed = subprocess.run(
            [
                "node",
                "-e",
                HELPER_WRAPPER,
                str(helper_virtual_path),
                *arguments,
            ],
            check=False,
            input=helper_source,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=HELPER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("AIStation helper timed out") from error
    if completed.returncode != 0:
        raise RuntimeError(
            "AIStation helper exited nonzero: "
            f"command={arguments[0]} exit={completed.returncode}"
        )
    return _load_json(completed.stdout, arguments[0]), completed.stdout


def _module_sha256() -> str:
    return _sha256_bytes(Path(__file__).read_bytes())


def _git_output(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(REPO_ROOT), *arguments],
        text=True,
    ).strip()


def _resolve_formal_source(formal_source_sha: str) -> str:
    if FULL_GIT_OBJECT.fullmatch(formal_source_sha) is None:
        raise RuntimeError("formal source SHA must be a full Git object")
    resolved = _git_output("rev-parse", f"{formal_source_sha}^{{commit}}")
    if resolved != formal_source_sha:
        raise RuntimeError("formal source SHA does not resolve exactly")
    formal_tree = _git_output("rev-parse", f"{formal_source_sha}^{{tree}}")
    formal_module = subprocess.check_output(
        [
            "git",
            "-C",
            str(REPO_ROOT),
            "show",
            f"{formal_source_sha}:{MODULE_RELATIVE_PATH}",
        ]
    )
    if _sha256_bytes(formal_module) != _module_sha256():
        raise RuntimeError(
            "current clock-bracket module differs from the formal source"
        )
    return formal_tree


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )


def _write_exclusive(path: Path, payload: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _capture_hashes(output_dir: Path) -> dict[str, str]:
    return {
        name: _sha256_bytes((output_dir / name).read_bytes())
        for name in CAPTURE_HASHED_FILE_NAMES
        if (output_dir / name).is_file()
    }


def _current_host_identity() -> tuple[str, str]:
    boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(
        encoding="utf-8"
    ).strip()
    return socket.gethostname(), boot_id.lower()


def _current_unix() -> int:
    return math.ceil(time.time())


def capture(
    helper: Path,
    output_dir: Path,
    run_id: str,
    formal_source_sha: str,
) -> dict[str, Any]:
    """Run one before/status/after attempt and persist its terminal outcome."""
    helper = Path(os.path.abspath(helper))
    try:
        helper_metadata = helper.lstat()
    except OSError as error:
        raise RuntimeError(f"cannot stat AIStation helper: {error}") from error
    if not stat.S_ISREG(helper_metadata.st_mode):
        raise FileNotFoundError(f"AIStation helper is not a file: {helper}")
    if helper.resolve(strict=True) != helper:
        raise RuntimeError("AIStation helper path uses a symlink or path alias")
    if helper != APPROVED_HELPER_PATH:
        raise RuntimeError("AIStation helper path differs from approved source")
    _validate_run_id(run_id)
    _require_full_hex(formal_source_sha, 40, "formal source SHA")
    repo_root = REPO_ROOT.resolve(strict=True)
    expected_output_dir = (
        repo_root / "artifacts" / run_id / "controller"
    )
    supplied_output_dir = Path(os.path.abspath(output_dir))
    if supplied_output_dir != expected_output_dir:
        raise RuntimeError(
            "capture output must be the repo-local run controller directory"
        )
    output_dir = expected_output_dir
    formal_source_tree = _resolve_formal_source(formal_source_sha)
    helper_bytes = helper.read_bytes()
    helper_sha256 = _sha256_bytes(helper_bytes)
    if helper_sha256 != APPROVED_HELPER_SHA256:
        raise RuntimeError("AIStation helper differs from approved SHA256")
    module_sha256 = _module_sha256()
    started = datetime.now(timezone.utc)
    monotonic_started = time.monotonic()
    artifacts_root = repo_root / "artifacts"
    artifacts_root.mkdir(exist_ok=True)
    _real_directory(artifacts_root, "artifacts directory")
    output_dir.parent.mkdir()
    _real_directory(output_dir.parent, "capture output parent")
    output_dir.mkdir()
    attempt = {
        "schema_version": 1,
        "run_id": run_id,
        "formal_source_sha": formal_source_sha,
        "formal_source_tree": formal_source_tree,
        "target": TARGET,
        "helper_sha256": helper_sha256,
        "module_sha256": module_sha256,
        "capture_started_utc": started.isoformat(),
    }
    _write_exclusive(
        output_dir / "capture-attempt.json",
        _canonical_json(attempt),
    )
    try:
        helper_snapshot = output_dir / "helper-snapshot.js"
        _write_exclusive(helper_snapshot, helper_bytes)
        before_payload, before_raw = _run_helper(
            helper_bytes,
            helper,
            "exec",
            TARGET,
            "--",
            REMOTE_CLOCK_COMMAND,
        )
        _write_exclusive(output_dir / "remote-before.json", before_raw)
        status_payload, status_raw = _run_helper(
            helper_bytes,
            helper,
            "status",
            TARGET,
        )
        _write_exclusive(output_dir / "aistation-status.json", status_raw)
        after_payload, after_raw = _run_helper(
            helper_bytes,
            helper,
            "exec",
            TARGET,
            "--",
            REMOTE_CLOCK_COMMAND,
        )
        _write_exclusive(output_dir / "remote-after.json", after_raw)
        elapsed = time.monotonic() - monotonic_started
        ended = datetime.now(timezone.utc)
        evidence = build_evidence(
            before_payload,
            before_raw,
            status_payload,
            status_raw,
            after_payload,
            after_raw,
            run_id=run_id,
            formal_source_sha=formal_source_sha,
            formal_source_tree=formal_source_tree,
            helper_sha256=helper_sha256,
            module_sha256=module_sha256,
            capture_started_utc=started.isoformat(),
            capture_ended_utc=ended.isoformat(),
            capture_elapsed_seconds=elapsed,
        )
        _write_exclusive(
            output_dir / "clock-bracket.json",
            _canonical_json(evidence),
        )
        terminal = {
            "schema_version": 1,
            "run_id": run_id,
            "formal_source_sha": formal_source_sha,
            "formal_source_tree": formal_source_tree,
            "status": "completed",
            "capture_ended_utc": ended.isoformat(),
            "files_sha256": _capture_hashes(output_dir),
            "error_type": None,
            "error": None,
        }
        _write_exclusive(
            output_dir / "capture-terminal.json",
            _canonical_json(terminal),
        )
        return evidence
    except BaseException as error:
        ended = datetime.now(timezone.utc)
        terminal = {
            "schema_version": 1,
            "run_id": run_id,
            "formal_source_sha": formal_source_sha,
            "formal_source_tree": formal_source_tree,
            "status": "failed",
            "capture_ended_utc": ended.isoformat(),
            "files_sha256": _capture_hashes(output_dir),
            "error_type": type(error).__name__,
            "error": str(error),
        }
        terminal_path = output_dir / "capture-terminal.json"
        if not terminal_path.exists() and not terminal_path.is_symlink():
            _write_exclusive(terminal_path, _canonical_json(terminal))
        raise


def _read_regular_file(path: Path, label: str) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise RuntimeError(f"cannot stat {label}: {error}") from error
    if not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError(f"{label} is not a real regular file")
    try:
        return path.read_bytes()
    except OSError as error:
        raise RuntimeError(f"cannot read {label}: {error}") from error


def _validate_capture_files(
    directory: Path,
    file_map: dict[str, str],
    *,
    require_exact_directory: bool,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    directory = _real_directory(directory, "clock evidence directory")
    expected_names = set(file_map.values())
    if require_exact_directory:
        actual_names = {path.name for path in directory.iterdir()}
        if actual_names != expected_names:
            raise RuntimeError(
                "clock evidence file inventory drift: "
                f"expected={sorted(expected_names)} "
                f"actual={sorted(actual_names)}"
            )
    files = {
        source_name: _read_regular_file(
            directory / destination_name,
            f"clock evidence {destination_name}",
        )
        for source_name, destination_name in file_map.items()
    }
    attempt = _load_json(files["capture-attempt.json"], "capture-attempt")
    proof = _load_json(files["clock-bracket.json"], "clock-bracket")
    terminal = _load_json(
        files["capture-terminal.json"],
        "capture-terminal",
    )
    run_id = _validate_run_id(str(proof.get("run_id")))
    formal_source_sha = _require_full_hex(
        str(proof.get("formal_source_sha")),
        40,
        "formal source SHA",
    )
    formal_source_tree = _require_full_hex(
        str(proof.get("formal_source_tree")),
        40,
        "formal source tree",
    )
    helper_sha256 = _require_full_hex(
        str(proof.get("helper_sha256")),
        64,
        "AIStation helper SHA256",
    )
    if helper_sha256 != APPROVED_HELPER_SHA256:
        raise RuntimeError("AIStation helper differs from approved SHA256")
    module_sha256 = _module_sha256()
    if proof.get("module_sha256") != module_sha256:
        raise RuntimeError(
            "clock-bracket module differs from the captured source"
        )
    if _sha256_bytes(files["helper-snapshot.js"]) != helper_sha256:
        raise RuntimeError("AIStation helper snapshot hash drift")
    try:
        capture_elapsed_seconds = float(proof["capture_elapsed_seconds"])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("clock-bracket capture elapsed time is invalid") from error
    expected_proof = build_evidence(
        _load_json(files["remote-before.json"], "remote-before"),
        files["remote-before.json"],
        _load_json(files["aistation-status.json"], "aistation-status"),
        files["aistation-status.json"],
        _load_json(files["remote-after.json"], "remote-after"),
        files["remote-after.json"],
        run_id=run_id,
        formal_source_sha=formal_source_sha,
        formal_source_tree=formal_source_tree,
        helper_sha256=helper_sha256,
        module_sha256=module_sha256,
        capture_started_utc=str(proof.get("capture_started_utc")),
        capture_ended_utc=str(proof.get("capture_ended_utc")),
        capture_elapsed_seconds=capture_elapsed_seconds,
    )
    if proof != expected_proof:
        raise RuntimeError("clock-bracket evidence drift")
    expected_attempt = {
        "schema_version": 1,
        "run_id": run_id,
        "formal_source_sha": formal_source_sha,
        "formal_source_tree": formal_source_tree,
        "target": TARGET,
        "helper_sha256": helper_sha256,
        "module_sha256": module_sha256,
        "capture_started_utc": proof["capture_started_utc"],
    }
    if attempt != expected_attempt:
        raise RuntimeError("clock capture attempt evidence drift")
    expected_terminal = {
        "schema_version": 1,
        "run_id": run_id,
        "formal_source_sha": formal_source_sha,
        "formal_source_tree": formal_source_tree,
        "status": "completed",
        "capture_ended_utc": proof["capture_ended_utc"],
        "files_sha256": {
            name: _sha256_bytes(files[name])
            for name in CAPTURE_HASHED_FILE_NAMES
        },
        "error_type": None,
        "error": None,
    }
    if terminal != expected_terminal:
        raise RuntimeError("clock capture terminal evidence drift")
    resolved_tree = _resolve_formal_source(formal_source_sha)
    if resolved_tree != formal_source_tree:
        raise RuntimeError("clock-bracket formal source tree drift")
    return proof, files


def validate_bundle(bundle_dir: Path) -> tuple[dict[str, Any], bytes]:
    """Rebuild and verify a completed seven-file capture bundle."""
    bundle_dir = _real_directory(bundle_dir, "clock capture bundle")
    proof, files = _validate_capture_files(
        bundle_dir,
        {name: name for name in CAPTURE_FILE_NAMES},
        require_exact_directory=True,
    )
    repo_root = REPO_ROOT.resolve(strict=True)
    expected_bundle_dir = (
        repo_root
        / "artifacts"
        / _validate_run_id(str(proof["run_id"]))
        / "controller"
    )
    if bundle_dir != expected_bundle_dir:
        raise RuntimeError("clock-bracket bundle path disagrees with run id")
    return proof, files["aistation-status.json"]


def validate_suite_clock_evidence(
    suite_dir: Path,
) -> tuple[dict[str, Any], bytes]:
    """Validate the immutable seven-file clock evidence copied into a suite."""
    suite_dir = _real_directory(suite_dir, "single-baseline suite")
    proof, files = _validate_capture_files(
        suite_dir,
        SUITE_CLOCK_FILE_MAP,
        require_exact_directory=False,
    )
    if suite_dir.name != _validate_run_id(str(proof["run_id"])):
        raise RuntimeError("suite path disagrees with clock-bracket run id")
    suite_manifest = _load_json(
        _read_regular_file(
            suite_dir / "suite-manifest.json",
            "suite manifest",
        ),
        "suite-manifest",
    )
    if suite_manifest.get("git_sha") != proof["formal_source_sha"]:
        raise RuntimeError("suite manifest formal source SHA drift")
    if suite_manifest.get("git_tree") != proof["formal_source_tree"]:
        raise RuntimeError("suite manifest formal source tree drift")
    return proof, files["aistation-status.json"]


def _publish_immutable_file(
    source: bytes,
    destination: Path,
    expected_sha256: str,
) -> None:
    temporary = destination.with_name(f".{destination.name}.tmp")
    if (
        destination.exists()
        or destination.is_symlink()
        or temporary.exists()
        or temporary.is_symlink()
    ):
        raise FileExistsError(
            f"clock evidence publication target exists: {destination}"
        )
    temporary_created = False
    try:
        descriptor = os.open(
            temporary,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
            0o600,
        )
        temporary_created = True
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(source)
            stream.flush()
            os.fsync(stream.fileno())
        if _sha256_bytes(temporary.read_bytes()) != expected_sha256:
            raise RuntimeError(
                f"staged clock evidence hash drift: {destination.name}"
            )
        os.link(temporary, destination, follow_symlinks=False)
        temporary.unlink()
        temporary_created = False
    finally:
        if temporary_created:
            temporary.unlink(missing_ok=True)


def _validate_current_publish_context(
    proof: dict[str, Any],
) -> tuple[str, str, int, int]:
    current_hostname, current_boot_id = _current_host_identity()
    if current_hostname != proof["remote_hostname"]:
        raise RuntimeError("publishing host differs from captured GPU2 hostname")
    if current_boot_id != proof["remote_boot_id"]:
        raise RuntimeError("publishing host differs from captured GPU2 boot id")
    publish_unix = _current_unix()
    publish_age_seconds = publish_unix - int(
        proof["selected_observed_unix"]
    )
    if publish_age_seconds < 0:
        raise RuntimeError("captured GPU2 timestamp is in the future at publish")
    if publish_age_seconds > MAX_PUBLISH_AGE_SECONDS:
        raise RuntimeError(
            "clock evidence is too old to publish: "
            f"age={publish_age_seconds}s "
            f"max={MAX_PUBLISH_AGE_SECONDS}s"
        )
    return (
        current_hostname,
        current_boot_id,
        publish_unix,
        publish_age_seconds,
    )


def publish_status(bundle_dir: Path, suite_dir: Path) -> dict[str, Any]:
    """Bind a fresh GPU2 capture and publish all seven files into a suite."""
    proof, _ = validate_bundle(bundle_dir)
    bundle_dir = _real_directory(bundle_dir, "clock capture bundle")
    _, bundle_files = _validate_capture_files(
        bundle_dir,
        {name: name for name in CAPTURE_FILE_NAMES},
        require_exact_directory=True,
    )
    if _git_output("rev-parse", "HEAD") != proof["formal_source_sha"]:
        raise RuntimeError("status publication requires the formal source HEAD")
    suite_dir = _real_directory(suite_dir, "single-baseline suite")
    repo_root = REPO_ROOT.resolve(strict=True)
    expected_suite_dir = (
        repo_root / "runs" / _validate_run_id(str(proof["run_id"]))
    )
    if suite_dir != expected_suite_dir:
        raise RuntimeError("suite path disagrees with clock-bracket run id")
    _read_regular_file(
        suite_dir / "single-baseline-manifest.json",
        "single-baseline manifest",
    )
    suite_manifest = _load_json(
        _read_regular_file(
            suite_dir / "suite-manifest.json",
            "suite manifest",
        ),
        "suite-manifest",
    )
    if suite_manifest.get("git_sha") != proof["formal_source_sha"]:
        raise RuntimeError("suite manifest formal source SHA drift")
    if suite_manifest.get("git_tree") != proof["formal_source_tree"]:
        raise RuntimeError("suite manifest formal source tree drift")
    (
        current_hostname,
        current_boot_id,
        publish_unix,
        publish_age_seconds,
    ) = _validate_current_publish_context(proof)
    for source_name, destination_name in SUITE_CLOCK_FILE_MAP.items():
        source = bundle_files[source_name]
        _publish_immutable_file(
            source,
            suite_dir / destination_name,
            _sha256_bytes(source),
        )
    published_proof, published_status = validate_suite_clock_evidence(
        suite_dir
    )
    if published_proof != proof:
        raise RuntimeError("published clock-bracket proof differs from capture")
    if published_status != bundle_files["aistation-status.json"]:
        raise RuntimeError("published AIStation status differs from capture")
    return {
        "schema_version": 1,
        "suite_dir": str(suite_dir),
        "status_path": str(suite_dir / "aistation-status.json"),
        "status_sha256": proof["status_response_sha256"],
        "clock_bracket_sha256": _sha256_bytes(
            bundle_files["clock-bracket.json"]
        ),
        "capture_terminal_sha256": _sha256_bytes(
            bundle_files["capture-terminal.json"]
        ),
        "published_files_sha256": {
            destination_name: _sha256_bytes(bundle_files[source_name])
            for source_name, destination_name in SUITE_CLOCK_FILE_MAP.items()
        },
        "workspace_id": proof["workspace_id"],
        "run_id": proof["run_id"],
        "formal_source_sha": proof["formal_source_sha"],
        "formal_source_tree": proof["formal_source_tree"],
        "publishing_hostname": current_hostname,
        "publishing_boot_id": current_boot_id,
        "publish_unix": publish_unix,
        "publish_age_seconds": publish_age_seconds,
        "maximum_publish_age_seconds": MAX_PUBLISH_AGE_SECONDS,
        "reported_remaining_seconds": proof["reported_remaining_seconds"],
        "selected_observed_unix": proof["selected_observed_unix"],
    }


def publish_and_launch(
    bundle_dir: Path,
    suite_dir: Path,
) -> dict[str, Any]:
    """Publish fresh evidence and launch once in the same GPU2 process."""
    publication = publish_status(bundle_dir, suite_dir)
    resolved_suite_dir = Path(str(publication["suite_dir"]))
    proof, _ = validate_suite_clock_evidence(resolved_suite_dir)
    (
        launch_hostname,
        launch_boot_id,
        launch_unix,
        launch_age_seconds,
    ) = _validate_current_publish_context(proof)
    environment = os.environ.copy()
    environment.update(
        {
            "AISTATION_TARGET": TARGET,
            "ZOOLOGY_EXPECTED_GIT_SHA": str(proof["formal_source_sha"]),
            "ZOOLOGY_REMAINING_SECONDS": str(
                proof["reported_remaining_seconds"]
            ),
            "ZOOLOGY_REMAINING_OBSERVED_UNIX": str(
                proof["selected_observed_unix"]
            ),
        }
    )
    completed = subprocess.run(
        [
            str(REPO_ROOT / "run.sh"),
            "launch-baseline",
            str(resolved_suite_dir),
        ],
        check=False,
        cwd=REPO_ROOT,
        env=environment,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "single baseline launch command failed after publication: "
            f"exit={completed.returncode}"
        )
    return {
        **publication,
        "launch_hostname": launch_hostname,
        "launch_boot_id": launch_boot_id,
        "launch_unix": launch_unix,
        "launch_age_seconds": launch_age_seconds,
        "launch_exit_code": completed.returncode,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("--helper", type=Path, required=True)
    capture_parser.add_argument("--output-dir", type=Path, required=True)
    capture_parser.add_argument("--run-id", required=True)
    capture_parser.add_argument("--formal-source-sha", required=True)
    publish_parser = subparsers.add_parser("publish-status")
    publish_parser.add_argument("--bundle-dir", type=Path, required=True)
    publish_parser.add_argument("--suite-dir", type=Path, required=True)
    launch_parser = subparsers.add_parser("publish-and-launch")
    launch_parser.add_argument("--bundle-dir", type=Path, required=True)
    launch_parser.add_argument("--suite-dir", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.command == "capture":
        result = capture(
            arguments.helper,
            arguments.output_dir,
            arguments.run_id,
            arguments.formal_source_sha,
        )
    elif arguments.command == "publish-status":
        result = publish_status(arguments.bundle_dir, arguments.suite_dir)
    else:
        result = publish_and_launch(
            arguments.bundle_dir,
            arguments.suite_dir,
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
