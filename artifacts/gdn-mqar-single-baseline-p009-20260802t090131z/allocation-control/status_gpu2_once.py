from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


RUN_ID = "gdn-mqar-single-baseline-p009-20260802t090131z"
WORKTREE = Path("/Users/torusmini/Documents/zoology-worktrees/baseline-002")
HELPER = Path(
    "/Users/torusmini/.codex/skills/aistation-skill/scripts/aistation_api.js"
)
HELPER_SHA256 = (
    "628aefaa2de3eb09ad5e6e1397e04280650e01847da2d9192566137405230226"
)
EXPECTED_IMAGE = (
    "192.168.108.1:5000/pytorch/ptv-qianliujia:python310_torch2.7"
)
EXPECTED_RESOURCE = "NVIDIA-A100-SXM4-80GB:1"
ALLOWED_NONRUNNING_RESOURCES = {"GPU:1", EXPECTED_RESOURCE}
EVIDENCE = WORKTREE / "artifacts" / f"admission-{RUN_ID}"


class StatusError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise StatusError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_helper() -> None:
    require(HELPER.is_file(), f"helper is not a file: {HELPER}")
    require(not HELPER.is_symlink(), f"helper is a symlink: {HELPER}")
    require(sha256(HELPER) == HELPER_SHA256, "helper SHA-256 drift")


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_json_exclusive(path: Path, payload: dict[str, object]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write((json.dumps(payload, indent=2, sort_keys=True) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())
    fsync_directory(path.parent)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--sequence", required=True, type=int)
    arguments = parser.parse_args()

    require(sys.flags.optimize == 0, "Python optimization must be disabled")
    require(arguments.sequence >= 2, "post-ledger sequence must be at least 2")
    require(bool(arguments.workspace_id), "workspace ID is empty")
    require(EVIDENCE.is_dir(), f"evidence directory is absent: {EVIDENCE}")
    require(not EVIDENCE.is_symlink(), f"evidence directory is a symlink: {EVIDENCE}")

    stem = f"status-post-ledger-{arguments.sequence:04d}"
    status_path = EVIDENCE / f"{stem}.json"
    stderr_path = EVIDENCE / f"{stem}.stderr"
    receipt_path = EVIDENCE / f"{stem}.receipt.json"
    failure_path = EVIDENCE / f"{stem}.failure.json"
    require(not status_path.exists(), f"status output already exists: {status_path}")
    require(not stderr_path.exists(), f"stderr output already exists: {stderr_path}")
    require(not receipt_path.exists(), f"receipt already exists: {receipt_path}")
    require(not failure_path.exists(), f"failure receipt exists: {failure_path}")
    controller_path = Path(__file__).resolve()

    try:
        require_helper()
        node = shutil.which("node")
        require(node is not None, "node is unavailable")
        stdout_descriptor = os.open(
            status_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        stderr_descriptor = os.open(
            stderr_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        try:
            with os.fdopen(stdout_descriptor, "wb") as stdout_stream:
                with os.fdopen(stderr_descriptor, "wb") as stderr_stream:
                    try:
                        result = subprocess.run(
                            [node, str(HELPER), "status", "GPU2"],
                            stdout=stdout_stream,
                            stderr=stderr_stream,
                            check=False,
                            timeout=60,
                        )
                    finally:
                        stdout_stream.flush()
                        stderr_stream.flush()
                        os.fsync(stdout_stream.fileno())
                        os.fsync(stderr_stream.fileno())
                        fsync_directory(status_path.parent)
        finally:
            require_helper()

        require(result.returncode == 0, f"helper exit was {result.returncode}")
        require(stderr_path.read_bytes() == b"", "helper stderr is not empty")
        payload = json.loads(status_path.read_bytes())
        require(type(payload) is dict, "status response is not an object")
        require(payload.get("command") == "status", "status command mismatch")
        require(payload.get("ok") is True, "status response is not ok")
        require(payload.get("actions") == [], "status response contains actions")
        targets = payload.get("targets")
        require(
            type(targets) is list and len(targets) == 1,
            "target cardinality mismatch",
        )
        target = targets[0]
        require(type(target) is dict, "target is not an object")
        require(target.get("wpName") == "GPU2", "literal target mismatch")
        require(
            target.get("wpId") == arguments.workspace_id,
            "workspace request mismatch",
        )
        require(target.get("image") == EXPECTED_IMAGE, "workspace image drift")
        require(
            target.get("wpStatus")
            in {"Pending", "Queuing", "ImagePulling", "Running", "Halt"},
            "workspace state is unknown",
        )
        status = target.get("wpStatus")
        resource = target.get("resource")
        require(type(resource) is str, "resource is not a string")
        if status == "Running":
            require(resource == EXPECTED_RESOURCE, "Running resource is not exact A100")
        else:
            require(
                resource in ALLOWED_NONRUNNING_RESOURCES,
                "non-Running resource is not an allowed placeholder or exact A100",
            )
        require(type(target.get("remainTime")) is str, "remainTime is not a string")
        require_helper()
        write_json_exclusive(
            receipt_path,
            {
                "schema_version": 1,
                "run_id": RUN_ID,
                "workspace_id": arguments.workspace_id,
                "sequence": arguments.sequence,
                "status": target.get("wpStatus"),
                "resource": target.get("resource"),
                "remain_time": target.get("remainTime"),
                "image": target.get("image"),
                "status_stdout_sha256": sha256(status_path),
                "status_stderr_sha256": sha256(stderr_path),
                "helper_sha256": HELPER_SHA256,
                "controller_sha256": sha256(controller_path),
            },
        )
    except BaseException as error:
        failure_payload = {
            "schema_version": 1,
            "run_id": RUN_ID,
            "workspace_id": arguments.workspace_id,
            "sequence": arguments.sequence,
            "state": "failed",
            "error_type": type(error).__name__,
            "error": str(error),
            "status_stdout_present": status_path.is_file(),
            "status_stdout_sha256": (
                sha256(status_path) if status_path.is_file() else None
            ),
            "status_stderr_present": stderr_path.is_file(),
            "status_stderr_sha256": (
                sha256(stderr_path) if stderr_path.is_file() else None
            ),
            "success_receipt_present": receipt_path.is_file(),
            "success_receipt_sha256": (
                sha256(receipt_path) if receipt_path.is_file() else None
            ),
            "helper_sha256": sha256(HELPER) if HELPER.is_file() else None,
            "controller_sha256": sha256(controller_path),
        }
        try:
            write_json_exclusive(failure_path, failure_payload)
        except BaseException as receipt_error:
            raise StatusError(
                f"{error}; failure receipt write failed: {receipt_error}"
            ) from error
        raise

    print(receipt_path.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
