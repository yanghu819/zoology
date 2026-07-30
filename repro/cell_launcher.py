"""Launch one formal suite cell independently of the caller's SSH session."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_create_text(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_create_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_create_text(
        path,
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
    )


def _launch_dir(suite_dir: Path, index: int) -> Path:
    if not 0 <= index <= 11:
        raise ValueError("cell index must be in [0, 11]")
    return suite_dir / "launches" / f"run-{index:02d}"


def record_terminal(
    launch_dir: Path,
    index: int,
    worker_pid: int,
    exit_code: int,
    *,
    error: str | None = None,
    worker_admission_sha256: str | None = None,
) -> dict[str, Any]:
    """Atomically create the immutable terminal record for one worker."""
    payload: dict[str, Any] = {
        "schema_version": 1,
        "state": "completed" if exit_code == 0 else "failed",
        "cell_index": index,
        "worker_pid": worker_pid,
        "exit_code": exit_code,
        "ended_utc": _utc_now(),
    }
    if error is not None:
        payload["error"] = error
    if worker_admission_sha256 is not None:
        payload["worker_admission_sha256"] = worker_admission_sha256
    _atomic_create_json(launch_dir / "terminal.json", payload)
    return payload


def launch_cell(
    root: Path,
    suite_dir: Path,
    index: int,
    worker_mode: str = "_cell-worker",
) -> dict[str, Any]:
    """Start one worker in a new session and return its durable launch record."""
    if worker_mode not in {"_cell-worker", "_baseline-worker"}:
        raise ValueError(f"unsupported worker mode: {worker_mode}")
    root = root.resolve()
    suite_dir = suite_dir.resolve()
    launches_dir = suite_dir / "launches"
    launches_dir.mkdir(exist_ok=True)
    launch_dir = _launch_dir(suite_dir, index)
    launch_dir.mkdir()
    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"

    command = [
        str(root / "run.sh"),
        worker_mode,
        str(index),
        str(suite_dir),
        str(launch_dir),
    ]
    request = {
        "schema_version": 1,
        "state": "requested",
        "cell_index": index,
        "requested_utc": _utc_now(),
        "suite_dir": str(suite_dir),
        "worker_mode": worker_mode,
        "baseline_manifest_sha256": environment.get(
            "ZOOLOGY_BASELINE_MANIFEST_SHA256"
        ),
        "controller_admission_sha256": environment.get(
            "ZOOLOGY_CONTROLLER_ADMISSION_SHA256"
        ),
        "command": command,
    }
    _atomic_create_json(launch_dir / "request.json", request)

    launcher_log = launch_dir / "launcher.log"
    try:
        with launcher_log.open("xb", buffering=0) as log_handle:
            worker = subprocess.Popen(
                command,
                cwd=root,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
    except BaseException as error:
        record_terminal(
            launch_dir,
            index,
            0,
            127,
            error=f"launcher failed before worker start: {error}",
        )
        raise

    _atomic_create_text(launch_dir / "worker.pid", f"{worker.pid}\n")
    launch = {
        "schema_version": 1,
        "state": "launched",
        "cell_index": index,
        "worker_pid": worker.pid,
        "launched_utc": _utc_now(),
        "suite_dir": str(suite_dir),
        "worker_mode": worker_mode,
        "baseline_manifest_sha256": environment.get(
            "ZOOLOGY_BASELINE_MANIFEST_SHA256"
        ),
        "controller_admission_sha256": environment.get(
            "ZOOLOGY_CONTROLLER_ADMISSION_SHA256"
        ),
        "launcher_log": str(launcher_log),
        "cell_log": str(suite_dir / "logs" / f"run-{index:02d}.log"),
        "terminal_record": str(launch_dir / "terminal.json"),
        "command": command,
        "expected_git_sha": environment.get("ZOOLOGY_EXPECTED_GIT_SHA"),
        "aistation_target": environment.get("AISTATION_TARGET"),
        "reported_remaining_seconds": environment.get(
            "ZOOLOGY_REMAINING_SECONDS"
        ),
        "remaining_observed_unix": environment.get(
            "ZOOLOGY_REMAINING_OBSERVED_UNIX"
        ),
        "minimum_remaining_seconds": environment.get(
            "ZOOLOGY_MIN_REMAINING_SECONDS",
            "11460",
        ),
        "controller_minimum_remaining_seconds": environment.get(
            "ZOOLOGY_CONTROLLER_MIN_REMAINING_SECONDS"
        ),
    }
    _atomic_create_json(launch_dir / "launch.json", launch)
    return {**launch, "launch_dir": str(launch_dir)}


def verify_worker(
    launch_dir: Path,
    suite_dir: Path,
    index: int,
    worker_pid: int,
) -> None:
    """Bind a detached worker to the launch record written by its parent."""
    launch_dir = launch_dir.resolve()
    suite_dir = suite_dir.resolve()
    if launch_dir != _launch_dir(suite_dir, index):
        raise RuntimeError("worker launch directory does not match suite/index")
    launch = json.loads((launch_dir / "launch.json").read_text(encoding="utf-8"))
    recorded_pid = int((launch_dir / "worker.pid").read_text(encoding="utf-8"))
    expected = {
        "cell_index": index,
        "worker_pid": worker_pid,
        "suite_dir": str(suite_dir),
    }
    actual = {
        "cell_index": int(launch["cell_index"]),
        "worker_pid": int(launch["worker_pid"]),
        "suite_dir": str(Path(launch["suite_dir"]).resolve()),
    }
    if actual != expected or recorded_pid != worker_pid:
        raise RuntimeError(
            f"worker/launch binding mismatch: expected={expected} actual={actual}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    launch_parser = subparsers.add_parser("launch")
    launch_parser.add_argument("--root", type=Path, required=True)
    launch_parser.add_argument("--suite-dir", type=Path, required=True)
    launch_parser.add_argument("--index", type=int, required=True)
    launch_parser.add_argument(
        "--worker-mode",
        choices=("_cell-worker", "_baseline-worker"),
        default="_cell-worker",
    )

    verify_parser = subparsers.add_parser("verify-worker")
    verify_parser.add_argument("--launch-dir", type=Path, required=True)
    verify_parser.add_argument("--suite-dir", type=Path, required=True)
    verify_parser.add_argument("--index", type=int, required=True)
    verify_parser.add_argument("--worker-pid", type=int, required=True)

    terminal_parser = subparsers.add_parser("terminal")
    terminal_parser.add_argument("--launch-dir", type=Path, required=True)
    terminal_parser.add_argument("--index", type=int, required=True)
    terminal_parser.add_argument("--worker-pid", type=int, required=True)
    terminal_parser.add_argument("--exit-code", type=int, required=True)
    terminal_parser.add_argument("--worker-admission-sha256")
    args = parser.parse_args()

    if args.command == "launch":
        print(
            json.dumps(
                launch_cell(
                    args.root,
                    args.suite_dir,
                    args.index,
                    args.worker_mode,
                ),
                sort_keys=True,
            ),
            flush=True,
        )
    elif args.command == "verify-worker":
        verify_worker(
            args.launch_dir,
            args.suite_dir,
            args.index,
            args.worker_pid,
        )
    elif args.command == "terminal":
        print(
            json.dumps(
                record_terminal(
                    args.launch_dir,
                    args.index,
                    args.worker_pid,
                    args.exit_code,
                    worker_admission_sha256=args.worker_admission_sha256,
                ),
                sort_keys=True,
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
