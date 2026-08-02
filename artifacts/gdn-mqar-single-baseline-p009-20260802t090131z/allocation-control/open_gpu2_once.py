from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import tomli


RUN_ID = "gdn-mqar-single-baseline-p009-20260802t090131z"
WORKTREE = Path("/Users/torusmini/Documents/zoology-worktrees/baseline-002")
HELPER = Path(
    "/Users/torusmini/.codex/skills/aistation-skill/scripts/aistation_api.js"
)
HELPER_SHA256 = (
    "628aefaa2de3eb09ad5e6e1397e04280650e01847da2d9192566137405230226"
)
EVIDENCE = WORKTREE / "artifacts" / f"admission-{RUN_ID}"
WATCHER_LOCK = WORKTREE / "artifacts" / f"admission-{RUN_ID}.watcher.lock"
OLD_WORKSPACE_ID = "09747b2f-6916-4813-ab33-7aebb5ce3b3b"
EXPECTED_IMAGE = (
    "192.168.108.1:5000/pytorch/ptv-qianliujia:python310_torch2.7"
)
EXPECTED_RESOURCE = "NVIDIA-A100-SXM4-80GB:1"
ALLOWED_NEW_RESOURCES = {"GPU:1", EXPECTED_RESOURCE}
AUTOMATION_ID = "run-zoology-gpu2-single-baseline"
AUTOMATION_CONFIG = Path(
    "/Users/torusmini/.codex/automations/run-zoology-gpu2-single-baseline/automation.toml"
)
WATCHER_PROMPT = (
    WORKTREE
    / "artifacts"
    / RUN_ID
    / "watcher"
    / "heartbeat-prompt.txt"
)
WATCHER_PROMPT_SHA256 = (
    "b615ae0938fca8120633108d9c92796c532d3d2f15813503c53374aacb95b5b6"
)
REPORT = (
    WORKTREE
    / "research"
    / "reports"
    / "experiments"
    / f"{RUN_ID}.md"
)
REPOSITORY = "yanghu819/zoology"
BRANCH = "codex/repro-gdn-mqar-baseline-002"
TARGET_THREAD_ID = "019fa198-ccc3-76b2-8650-9e20e74b5ec4"
EXPECTED_RRULE = "FREQ=MINUTELY;INTERVAL=1"


class AllocationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AllocationError(message)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_sha(value: str, label: str) -> None:
    require(len(value) == 64, f"{label} is not a full SHA-256")
    require(all(character in "0123456789abcdef" for character in value), label)


def require_git_sha(value: str, label: str) -> None:
    require(len(value) == 40, f"{label} is not a full Git object ID")
    require(all(character in "0123456789abcdef" for character in value), label)


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_exclusive(path: Path, raw: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    fsync_directory(path.parent)


def write_json_exclusive(path: Path, payload: dict[str, object]) -> None:
    write_exclusive(
        path,
        (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode(),
    )


def acquire_watcher_lock(controller_path: Path) -> Path:
    require(not WATCHER_LOCK.is_symlink(), "watcher lock is a symlink")
    try:
        os.mkdir(WATCHER_LOCK, 0o700)
    except FileExistsError as error:
        raise AllocationError(f"watcher lock is busy: {WATCHER_LOCK}") from error
    fsync_directory(WATCHER_LOCK.parent)
    owner_path = WATCHER_LOCK / "owner.json"
    write_json_exclusive(
        owner_path,
        {
            "schema_version": 1,
            "run_id": RUN_ID,
            "owner": "main-open-controller",
            "controller_sha256": sha256(controller_path),
            "acquired_utc": utc_now(),
            "acquired_unix": int(time.time()),
        },
    )
    return owner_path


def release_watcher_lock(owner_path: Path) -> None:
    require(owner_path.parent == WATCHER_LOCK, "watcher lock owner path mismatch")
    require(owner_path.is_file(), "watcher lock owner is absent")
    owner_path.unlink()
    fsync_directory(WATCHER_LOCK)
    os.rmdir(WATCHER_LOCK)
    fsync_directory(WATCHER_LOCK.parent)


def require_helper() -> None:
    require(HELPER.is_file(), f"helper is not a file: {HELPER}")
    require(not HELPER.is_symlink(), f"helper is a symlink: {HELPER}")
    require(sha256(HELPER) == HELPER_SHA256, "helper SHA-256 drift")


def run_text(arguments: list[str], label: str) -> str:
    result = subprocess.run(
        arguments,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    require(result.returncode == 0, f"{label} failed: {result.stderr.strip()}")
    value = result.stdout.strip()
    require(bool(value), f"{label} returned empty output")
    return value


def require_clean_worktree() -> None:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(WORKTREE),
            "status",
            "--porcelain=v1",
            "--untracked-files=no",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    require(result.returncode == 0, f"local status failed: {result.stderr.strip()}")
    require(result.stdout == "", "local tracked worktree is not clean")


def verify_approval_and_automation(
    approval_commit: str,
    approval_tree: str,
    prompt_sha256: str,
    automation_config_sha256: str,
    controller_path: Path,
) -> dict[str, object]:
    require(WATCHER_PROMPT.is_file(), "watcher prompt is absent")
    require(not WATCHER_PROMPT.is_symlink(), "watcher prompt is a symlink")
    require(sha256(WATCHER_PROMPT) == WATCHER_PROMPT_SHA256, "prompt hash drift")
    require(prompt_sha256 == WATCHER_PROMPT_SHA256, "prompt argument mismatch")

    require(AUTOMATION_CONFIG.is_file(), "automation config is absent")
    require(not AUTOMATION_CONFIG.is_symlink(), "automation config is a symlink")
    actual_config_sha256 = sha256(AUTOMATION_CONFIG)
    require(
        automation_config_sha256 == actual_config_sha256,
        "automation config hash mismatch",
    )
    automation = tomli.loads(AUTOMATION_CONFIG.read_text(encoding="utf-8"))
    require(automation.get("id") == AUTOMATION_ID, "automation ID mismatch")
    require(automation.get("kind") == "heartbeat", "automation kind mismatch")
    require(automation.get("status") == "ACTIVE", "automation is not ACTIVE")
    require(automation.get("rrule") == EXPECTED_RRULE, "automation cadence mismatch")
    require(
        automation.get("notification_policy") == "failed_runs_only",
        "automation notification policy mismatch",
    )
    require(
        automation.get("target_thread_id") == TARGET_THREAD_ID,
        "automation target thread mismatch",
    )
    prompt_text = WATCHER_PROMPT.read_text(encoding="utf-8")
    require(prompt_text.endswith("\n"), "watcher prompt lacks its canonical newline")
    require(
        automation.get("prompt") == prompt_text[:-1],
        "automation prompt content mismatch",
    )

    local_commit = run_text(
        ["git", "-C", str(WORKTREE), "rev-parse", "HEAD"],
        "local approval commit",
    )
    local_tree = run_text(
        ["git", "-C", str(WORKTREE), "rev-parse", "HEAD^{tree}"],
        "local approval tree",
    )
    require(local_commit == approval_commit, "local approval commit mismatch")
    require(local_tree == approval_tree, "local approval tree mismatch")
    require_clean_worktree()

    remote_commit = run_text(
        [
            "gh",
            "api",
            f"repos/{REPOSITORY}/git/ref/heads/{BRANCH}",
            "--jq",
            ".object.sha",
        ],
        "GitHub approval ref",
    )
    require(remote_commit == approval_commit, "GitHub approval commit mismatch")
    remote_tree = run_text(
        [
            "gh",
            "api",
            f"repos/{REPOSITORY}/git/commits/{remote_commit}",
            "--jq",
            ".tree.sha",
        ],
        "GitHub approval tree",
    )
    require(remote_tree == approval_tree, "GitHub approval tree mismatch")

    require(REPORT.is_file(), "P009 report is absent")
    require(not REPORT.is_symlink(), "P009 report is a symlink")
    report = REPORT.read_text(encoding="utf-8")
    require("- Watcher phase: `armed-unallocated`" in report, "report phase mismatch")
    require(WATCHER_PROMPT_SHA256 in report, "report does not bind prompt hash")
    require(sha256(controller_path) in report, "report does not bind controller hash")

    return {
        "local_commit": local_commit,
        "local_tree": local_tree,
        "remote_commit": remote_commit,
        "remote_tree": remote_tree,
        "automation_updated_at": automation.get("updated_at"),
        "automation_config_sha256": actual_config_sha256,
    }


def invoke(command: str, stdout_path: Path, stderr_path: Path) -> int:
    require(command in {"status", "open"}, f"command is not allowed: {command}")
    require_helper()
    node = shutil.which("node")
    require(node is not None, "node is unavailable")
    stdout_descriptor = os.open(
        stdout_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
    )
    stderr_descriptor = os.open(
        stderr_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
    )
    try:
        with os.fdopen(stdout_descriptor, "wb") as stdout_stream:
            with os.fdopen(stderr_descriptor, "wb") as stderr_stream:
                try:
                    result = subprocess.run(
                        [node, str(HELPER), command, "GPU2"],
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
                    fsync_directory(stdout_path.parent)
    finally:
        require_helper()
    return result.returncode


def parse_single_target(path: Path, command: str) -> tuple[dict, dict]:
    payload = json.loads(path.read_bytes())
    require(type(payload) is dict, f"{command} response is not an object")
    require(payload.get("command") == command, f"{command} field mismatch")
    require(payload.get("ok") is True, f"{command} response is not ok")
    targets = payload.get("targets")
    require(
        type(targets) is list and len(targets) == 1,
        f"{command} target cardinality mismatch",
    )
    target = targets[0]
    require(type(target) is dict, f"{command} target is not an object")
    require(target.get("wpName") == "GPU2", f"{command} literal target mismatch")
    return payload, target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approval-commit", required=True)
    parser.add_argument("--approval-tree", required=True)
    parser.add_argument("--prompt-sha256", required=True)
    parser.add_argument("--automation-config-sha256", required=True)
    arguments = parser.parse_args()

    require(sys.flags.optimize == 0, "Python optimization must be disabled")
    require_git_sha(arguments.approval_commit, "approval commit")
    require_git_sha(arguments.approval_tree, "approval tree")
    require_sha(arguments.prompt_sha256, "prompt SHA-256")
    require_sha(arguments.automation_config_sha256, "automation config SHA-256")
    controller_path = Path(__file__).resolve()
    verification = verify_approval_and_automation(
        arguments.approval_commit,
        arguments.approval_tree,
        arguments.prompt_sha256,
        arguments.automation_config_sha256,
        controller_path,
    )
    require(not EVIDENCE.exists(), f"evidence path already exists: {EVIDENCE}")
    require(not EVIDENCE.is_symlink(), f"evidence path is a symlink: {EVIDENCE}")
    owner_path = acquire_watcher_lock(controller_path)
    try:
        require(not EVIDENCE.exists(), f"evidence path already exists: {EVIDENCE}")
        require(not EVIDENCE.is_symlink(), f"evidence path is a symlink: {EVIDENCE}")
        os.mkdir(EVIDENCE, 0o700)
        fsync_directory(EVIDENCE.parent)
        activation_path = EVIDENCE / "watcher-activation-0001.json"
        write_json_exclusive(
            activation_path,
            {
                "schema_version": 1,
                "run_id": RUN_ID,
                "automation_id": AUTOMATION_ID,
                "state": "active_before_allocation",
                "automation_status": "ACTIVE",
                "automation_config_sha256": arguments.automation_config_sha256,
                "automation_updated_at": verification["automation_updated_at"],
                "approval_commit": arguments.approval_commit,
                "approval_tree": arguments.approval_tree,
                "prompt_sha256": arguments.prompt_sha256,
                "helper_sha256": HELPER_SHA256,
                "controller_sha256": sha256(controller_path),
                "started_utc": utc_now(),
                "started_unix": int(time.time()),
            },
        )
    except BaseException:
        release_watcher_lock(owner_path)
        raise

    status_path = EVIDENCE / "status-pre-open-0001.json"
    status_stderr_path = EVIDENCE / "status-pre-open-0001.stderr"
    open_path = EVIDENCE / "open-0001.json"
    open_stderr_path = EVIDENCE / "open-0001.stderr"
    attempt_path = EVIDENCE / "open-0001.attempt.json"
    failure_path = EVIDENCE / "open-0001.failure.json"
    receipt_path = EVIDENCE / "open-0001.receipt.json"

    try:
        require_helper()
        status_exit = invoke("status", status_path, status_stderr_path)
        require(status_exit == 0, f"status helper exit was {status_exit}")
        require(status_stderr_path.read_bytes() == b"", "status stderr is not empty")
        status_response, old_target = parse_single_target(status_path, "status")
        require(status_response.get("actions") == [], "status response contains actions")
        require(old_target.get("wpId") == OLD_WORKSPACE_ID, "old request mismatch")
        require(old_target.get("wpStatus") == "Halt", "old request is not Halt")
        require(old_target.get("image") == EXPECTED_IMAGE, "workspace image drift")
        require(old_target.get("resource") == "GPU:1", "Halt resource mismatch")
        require(type(old_target.get("remainTime")) is str, "remainTime is not a string")

        write_json_exclusive(
            attempt_path,
            {
                "schema_version": 1,
                "run_id": RUN_ID,
                "automation_id": AUTOMATION_ID,
                "target": "GPU2",
                "command": "open",
                "open_consumed": True,
                "approval_commit": arguments.approval_commit,
                "approval_tree": arguments.approval_tree,
                "automation_config_sha256": arguments.automation_config_sha256,
                "old_workspace_id": OLD_WORKSPACE_ID,
                "old_status": old_target.get("wpStatus"),
                "old_resource": old_target.get("resource"),
                "old_remaining_time": old_target.get("remainTime"),
                "image": EXPECTED_IMAGE,
                "status_stdout_sha256": sha256(status_path),
                "status_stderr_sha256": sha256(status_stderr_path),
                "watcher_activation_sha256": sha256(activation_path),
                "helper_sha256": HELPER_SHA256,
                "controller_sha256": sha256(controller_path),
                "created_utc": utc_now(),
                "created_unix": int(time.time()),
            },
        )
        open_exit = invoke("open", open_path, open_stderr_path)
        require(open_exit == 0, f"open helper exit was {open_exit}")
        require(open_stderr_path.read_bytes() == b"", "open stderr is not empty")
        open_response, new_target = parse_single_target(open_path, "open")
        new_workspace_id = new_target.get("wpId")
        require(
            type(new_workspace_id) is str and bool(new_workspace_id),
            "new request ID is absent",
        )
        require(new_workspace_id != OLD_WORKSPACE_ID, "request ID did not change")
        require(new_target.get("image") == EXPECTED_IMAGE, "new image drift")
        require(
            new_target.get("wpStatus")
            in {"Pending", "Queuing", "ImagePulling", "Running"},
            "new request state is not active",
        )
        require(
            new_target.get("resource") in ALLOWED_NEW_RESOURCES,
            "new resource is not an allowed placeholder or exact A100",
        )
        require(
            type(new_target.get("remainTime")) is str,
            "new remainTime is not a string",
        )
        require(
            open_response.get("actions")
            == [
                {
                    "target": "GPU2",
                    "action": "start_requested",
                    "previousStatus": "Halt",
                }
            ],
            "open action sequence mismatch",
        )
        require_helper()
        write_json_exclusive(
            receipt_path,
            {
                "schema_version": 1,
                "run_id": RUN_ID,
                "automation_id": AUTOMATION_ID,
                "target": "GPU2",
                "command": "open",
                "state": "complete",
                "open_consumed": True,
                "approval_commit": arguments.approval_commit,
                "approval_tree": arguments.approval_tree,
                "automation_config_sha256": arguments.automation_config_sha256,
                "old_workspace_id": OLD_WORKSPACE_ID,
                "new_workspace_id": new_workspace_id,
                "new_workspace_status": new_target.get("wpStatus"),
                "new_resource": new_target.get("resource"),
                "new_remaining_time": new_target.get("remainTime"),
                "image": EXPECTED_IMAGE,
                "actions": open_response.get("actions"),
                "watcher_activation_sha256": sha256(activation_path),
                "status_stdout_sha256": sha256(status_path),
                "status_stderr_sha256": sha256(status_stderr_path),
                "attempt_sha256": sha256(attempt_path),
                "open_stdout_sha256": sha256(open_path),
                "open_stderr_sha256": sha256(open_stderr_path),
                "helper_sha256": HELPER_SHA256,
                "controller_sha256": sha256(controller_path),
                "recorded_utc": utc_now(),
                "recorded_unix": int(time.time()),
            },
        )
    except BaseException as error:
        failure_payload = {
            "schema_version": 1,
            "run_id": RUN_ID,
            "automation_id": AUTOMATION_ID,
            "target": "GPU2",
            "state": "failed",
            "open_consumed": attempt_path.is_file(),
            "error_type": type(error).__name__,
            "error": str(error),
            "status_stdout_present": status_path.is_file(),
            "status_stdout_sha256": (
                sha256(status_path) if status_path.is_file() else None
            ),
            "status_stderr_present": status_stderr_path.is_file(),
            "status_stderr_sha256": (
                sha256(status_stderr_path) if status_stderr_path.is_file() else None
            ),
            "attempt_present": attempt_path.is_file(),
            "attempt_sha256": sha256(attempt_path) if attempt_path.is_file() else None,
            "open_stdout_present": open_path.is_file(),
            "open_stdout_sha256": sha256(open_path) if open_path.is_file() else None,
            "open_stderr_present": open_stderr_path.is_file(),
            "open_stderr_sha256": (
                sha256(open_stderr_path) if open_stderr_path.is_file() else None
            ),
            "complete_receipt_present": receipt_path.is_file(),
            "complete_receipt_sha256": (
                sha256(receipt_path) if receipt_path.is_file() else None
            ),
            "helper_sha256": sha256(HELPER) if HELPER.is_file() else None,
            "controller_sha256": sha256(controller_path),
            "recorded_utc": utc_now(),
            "recorded_unix": int(time.time()),
        }
        try:
            write_json_exclusive(failure_path, failure_payload)
        except BaseException as receipt_error:
            raise AllocationError(
                f"{error}; failure receipt write failed: {receipt_error}"
            ) from error
        release_watcher_lock(owner_path)
        raise

    release_watcher_lock(owner_path)
    print(receipt_path.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
