#!/usr/bin/env bash

# The worker records every nonzero step instead of exiting before terminal evidence exists.
set -u
set -o pipefail

REPO_ROOT="/huyang2/zoology"
FORMAL_SOURCE_SHA="13f880b5fe61619a1006ef33610de69fbabaaec1"
FORMAL_SOURCE_TREE="ed83a7188351ca2cce8aba46d1cb3b108ce31ec2"
SCRIPT_NAME="durable_preflight_v2.sh"
CONTROL_NAME="preflight-control"
FORMAL_LAUNCH_CONTROL_NAME="formal-launch-control"
INIT_CONTROL_NAME="init-baseline-control"

usage() {
  printf '%s\n' \
    "usage: $0 start|worker|verify --script-sha256 SHA256 --suite-dir PATH --control-dir PATH" >&2
  exit 64
}

die() {
  printf 'durable preflight v2: %s\n' "$1" >&2
  exit "${2:-1}"
}

sha256_file() {
  sha256sum -- "$1" | awk '{print $1}'
}

sha256_payload() {
  printf '%s\n' "$1" | sha256sum | awk '{print $1}'
}

require_real_directory() {
  local directory="$1"
  local label="$2"
  [[ -d "$directory" && ! -L "$directory" ]] || die "$label is not a real directory: $directory"
  [[ "$(realpath -e -- "$directory")" == "$directory" ]] || die "$label uses a symlink or path alias: $directory"
}

require_real_file() {
  local path="$1"
  local label="$2"
  [[ -f "$path" && ! -L "$path" ]] || die "$label is not a real regular file: $path"
  [[ "$(realpath -e -- "$path")" == "$path" ]] || die "$label uses a symlink or path alias: $path"
}

write_atomic() {
  local destination="$1"
  local payload="$2"
  local temporary
  temporary="${destination%/*}/.${destination##*/}.tmp.$$"
  (
    umask 077
    set -o noclobber
    printf '%s\n' "$payload" > "$temporary"
  ) || return 1
  if ! sync "$temporary"; then
    rm -- "$temporary" || true
    return 1
  fi
  if ! ln -- "$temporary" "$destination"; then
    rm -- "$temporary" || true
    return 1
  fi
  rm -- "$temporary" || return 1
  sync "${destination%/*}" || return 1
}

hash_or_null() {
  local evidence="$1"
  if [[ -f "$evidence" && ! -L "$evidence" ]]; then
    printf '"%s"' "$(sha256_file "$evidence")"
  else
    printf 'null'
  fi
}

verify_formal_source() {
  local head_sha head_tree
  head_sha="$(git -C "$REPO_ROOT" rev-parse HEAD)" || return 1
  head_tree="$(git -C "$REPO_ROOT" rev-parse 'HEAD^{tree}')" || return 1
  [[ "$head_sha" == "$FORMAL_SOURCE_SHA" ]] || return 1
  [[ "$head_tree" == "$FORMAL_SOURCE_TREE" ]] || return 1
  if git -C "$REPO_ROOT" symbolic-ref -q HEAD >/dev/null 2>&1; then
    return 1
  fi
  [[ -z "$(GIT_OPTIONAL_LOCKS=0 git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=all)" ]]
}

verify_source_and_formal_absence() {
  local forbidden
  verify_formal_source || return 1
  for forbidden in "$suite_dir" "$formal_controller" "$formal_launch_control" "$init_control"; do
    [[ ! -e "$forbidden" && ! -L "$forbidden" ]] || return 1
  done
}

verify_source_and_downstream_absence() {
  local forbidden
  verify_formal_source || return 1
  for forbidden in "$formal_controller" "$formal_launch_control"; do
    [[ ! -e "$forbidden" && ! -L "$forbidden" ]] || return 1
  done
}

mode="${1:-}"
[[ "$mode" == "start" || "$mode" == "worker" || "$mode" == "verify" ]] || usage
shift

script_sha256=""
suite_dir=""
control_dir=""
while (($#)); do
  (($# >= 2)) || usage
  case "$1" in
    --script-sha256)
      [[ -z "$script_sha256" ]] || usage
      script_sha256="$2"
      ;;
    --suite-dir)
      [[ -z "$suite_dir" ]] || usage
      suite_dir="$2"
      ;;
    --control-dir)
      [[ -z "$control_dir" ]] || usage
      control_dir="$2"
      ;;
    *) usage ;;
  esac
  shift 2
done

[[ -n "$script_sha256" && -n "$suite_dir" && -n "$control_dir" ]] || usage
[[ "$script_sha256" =~ ^[0-9a-f]{64}$ ]] || die "script SHA256 must be 64 lowercase hexadecimal characters"
suite_prefix="$REPO_ROOT/runs/"
[[ "$suite_dir" == "$suite_prefix"* ]] || die "suite directory is outside the formal repository"
run_id="${suite_dir#"$suite_prefix"}"
[[ "$run_id" =~ ^[a-z0-9][a-z0-9-]*$ ]] || die "suite directory has an invalid lowercase run id"
[[ "$suite_dir" == "$REPO_ROOT/runs/$run_id" ]] || die "suite directory is not the canonical run path"
run_artifact="$REPO_ROOT/artifacts/$run_id"
formal_controller="$run_artifact/controller"
formal_launch_control="$run_artifact/$FORMAL_LAUNCH_CONTROL_NAME"
init_control="$run_artifact/$INIT_CONTROL_NAME"
expected_control="$run_artifact/$CONTROL_NAME"
[[ "$control_dir" == "$expected_control" ]] || die "control directory is not the canonical preflight path for the suite run id"

if [[ "$mode" == "verify" ]]; then
  source_script="$run_artifact/launcher/$SCRIPT_NAME"
  snapshot="$control_dir/script-snapshot.sh"
  [[ "$0" == "$source_script" ]] || die "verifier is not the canonical uploaded artifact"
  require_real_directory "$REPO_ROOT" "formal repository"
  require_real_directory "$REPO_ROOT/runs" "formal runs directory"
  require_real_directory "$run_artifact" "run artifact directory"
  require_real_directory "${source_script%/*}" "launcher artifact directory"
  require_real_directory "$control_dir" "completed preflight control directory"
  require_real_file "$0" "preflight verifier"
  [[ "$(sha256_file "$0")" == "$script_sha256" ]] || die "verifier SHA256 differs from the frozen value"
  verify_source_and_downstream_absence || die "formal source or downstream path gate failed during verification"
  python_path="$(realpath -e -- "$REPO_ROOT/.venv/bin/python")" || die "cannot resolve formal project Python"
  [[ -f "$python_path" && ! -L "$python_path" ]] || die "resolved formal project Python is not a real regular file"
  [[ -x "$python_path" ]] || die "formal project Python is not executable"

  PYTHONDONTWRITEBYTECODE=1 "$python_path" - \
    "$REPO_ROOT" "$run_id" "$suite_dir" "$control_dir" "$source_script" \
    "$script_sha256" "$FORMAL_SOURCE_SHA" "$FORMAL_SOURCE_TREE" <<'PY'
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path


repo_root = Path(sys.argv[1])
run_id = sys.argv[2]
suite_dir = Path(sys.argv[3])
control_dir = Path(sys.argv[4])
source_script = Path(sys.argv[5])
script_sha256 = sys.argv[6]
formal_source_sha = sys.argv[7]
formal_source_tree = sys.argv[8]

SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
UTC_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def real_file(path: Path) -> Path:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or path.resolve(strict=True) != path:
        raise RuntimeError(f"evidence is not a canonical regular file: {path}")
    return path


def load_object(path: Path) -> dict:
    payload = json.loads(real_file(path).read_text(encoding="utf-8"))
    if type(payload) is not dict:
        raise RuntimeError(f"evidence is not a JSON object: {path}")
    return payload


def require_keys(payload: dict, expected: set[str], label: str) -> None:
    if set(payload) != expected:
        raise RuntimeError(
            f"{label} schema drift: expected={sorted(expected)} "
            f"actual={sorted(payload)}"
        )


def require_field(payload: dict, key: str, expected, label: str) -> None:
    actual = payload.get(key)
    if type(actual) is not type(expected) or actual != expected:
        raise RuntimeError(
            f"{label} {key} drift: expected={expected!r} actual={actual!r}"
        )


def require_positive_integer(payload: dict, key: str, label: str) -> int:
    value = payload.get(key)
    if type(value) is not int or value <= 0:
        raise RuntimeError(f"{label} {key} is not a positive integer")
    return value


def require_unix_time(payload: dict, key: str, label: str) -> int:
    value = payload.get(key)
    if type(value) is not int or value < 0:
        raise RuntimeError(f"{label} {key} is not a nonnegative integer")
    return value


def require_utc(payload: dict, key: str, label: str) -> str:
    value = payload.get(key)
    if type(value) is not str or UTC_PATTERN.fullmatch(value) is None:
        raise RuntimeError(f"{label} {key} is not canonical UTC")
    return value


def require_sha256(value, label: str) -> str:
    if type(value) is not str or SHA256_PATTERN.fullmatch(value) is None:
        raise RuntimeError(f"{label} is not lowercase SHA256")
    return value


def require_exited(pid: int, label: str) -> None:
    if Path(f"/proc/{pid}").exists():
        raise RuntimeError(f"{label} PID is still present: {pid}")


if not Path("/proc/self/stat").is_file():
    raise RuntimeError("preflight verification requires Linux /proc")

expected_control_names = {
    "01-setup.exit",
    "01-setup.json",
    "01-setup.log",
    "02-check.exit",
    "02-check.json",
    "02-check.log",
    "03-cache.exit",
    "03-cache.json",
    "03-cache.log",
    "04-smoke.exit",
    "04-smoke.json",
    "04-smoke.log",
    "attempt.json",
    "envelope.log",
    "script-snapshot.sh",
    "start.json",
    "terminal.json",
    "worker-claim.json",
    "worker-start.json",
}
actual_control_names = {path.name for path in control_dir.iterdir()}
if actual_control_names != expected_control_names:
    raise RuntimeError(
        "preflight control inventory drift: "
        f"expected={sorted(expected_control_names)} "
        f"actual={sorted(actual_control_names)}"
    )
for name in expected_control_names:
    real_file(control_dir / name)

snapshot = control_dir / "script-snapshot.sh"
attempt_path = control_dir / "attempt.json"
start_path = control_dir / "start.json"
worker_claim_path = control_dir / "worker-claim.json"
worker_start_path = control_dir / "worker-start.json"
terminal_path = control_dir / "terminal.json"

attempt = load_object(attempt_path)
start = load_object(start_path)
worker_claim = load_object(worker_claim_path)
worker = load_object(worker_start_path)
terminal = load_object(terminal_path)

hash_paths = {
    "script_sha256": snapshot,
    "attempt_sha256": attempt_path,
    "start_sha256": start_path,
    "worker_claim_sha256": worker_claim_path,
    "worker_start_sha256": worker_start_path,
    "envelope_log_sha256": control_dir / "envelope.log",
}
for index, name in (
    ("01", "setup"),
    ("02", "check"),
    ("03", "cache"),
    ("04", "smoke"),
):
    for suffix in ("log", "exit", "json"):
        hash_paths[f"step_{index}_{suffix}_sha256"] = (
            control_dir / f"{index}-{name}.{suffix}"
        )

terminal_keys = {
    "schema_version",
    "run_id",
    "suite_dir",
    "status",
    "exit_code",
    "completed_steps",
    "failed_step",
    "reason",
    "worker_pid",
    "worker_sid",
    "worker_tty",
    "started_utc",
    "started_unix",
    "ended_utc",
    "ended_unix",
    "formal_source_sha",
    "formal_source_tree",
} | set(hash_paths)
require_keys(terminal, terminal_keys, "terminal")
for key, expected in {
    "schema_version": 2,
    "run_id": run_id,
    "suite_dir": str(suite_dir),
    "status": "completed",
    "exit_code": 0,
    "completed_steps": 4,
    "failed_step": "none",
    "reason": "none",
    "formal_source_sha": formal_source_sha,
    "formal_source_tree": formal_source_tree,
    "script_sha256": script_sha256,
    "worker_tty": "?",
}.items():
    require_field(terminal, key, expected, "terminal")
terminal_worker_pid = require_positive_integer(terminal, "worker_pid", "terminal")
terminal_worker_sid = require_positive_integer(terminal, "worker_sid", "terminal")
if terminal_worker_sid != terminal_worker_pid:
    raise RuntimeError("terminal worker is not a session leader")
terminal_started_unix = require_unix_time(terminal, "started_unix", "terminal")
terminal_ended_unix = require_unix_time(terminal, "ended_unix", "terminal")
require_utc(terminal, "started_utc", "terminal")
require_utc(terminal, "ended_utc", "terminal")
if terminal_ended_unix < terminal_started_unix:
    raise RuntimeError("terminal time order drift")

for key, path in hash_paths.items():
    expected_sha256 = require_sha256(terminal.get(key), f"terminal {key}")
    actual_sha256 = sha256_file(real_file(path))
    if actual_sha256 != expected_sha256:
        raise RuntimeError(
            f"terminal hash drift for {key}: "
            f"expected={expected_sha256} actual={actual_sha256}"
        )

attempt_keys = {
    "schema_version",
    "run_id",
    "kind",
    "formal_source_sha",
    "formal_source_tree",
    "suite_dir",
    "control_dir",
    "source_script",
    "snapshot",
    "script_sha256",
    "starter_pid",
    "started_utc",
    "started_unix",
    "hostname",
    "boot_id",
}
require_keys(attempt, attempt_keys, "attempt")
for key, expected in {
    "schema_version": 2,
    "run_id": run_id,
    "kind": "durable-preflight-v2",
    "formal_source_sha": formal_source_sha,
    "formal_source_tree": formal_source_tree,
    "suite_dir": str(suite_dir),
    "control_dir": str(control_dir),
    "source_script": str(source_script),
    "snapshot": str(snapshot),
    "script_sha256": script_sha256,
}.items():
    require_field(attempt, key, expected, "attempt")
require_positive_integer(attempt, "starter_pid", "attempt")
attempt_started_unix = require_unix_time(attempt, "started_unix", "attempt")
require_utc(attempt, "started_utc", "attempt")
if type(attempt.get("hostname")) is not str or not attempt["hostname"]:
    raise RuntimeError("attempt hostname is invalid")
if type(attempt.get("boot_id")) is not str or re.fullmatch(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    attempt["boot_id"],
) is None:
    raise RuntimeError("attempt boot id is invalid")

start_keys = {
    "schema_version",
    "run_id",
    "suite_dir",
    "envelope_supervisor_pid",
    "nohup_path",
    "setsid_path",
    "bash_path",
    "stdin",
    "envelope_log",
    "worker_command",
    "recorded_utc",
    "recorded_unix",
}
require_keys(start, start_keys, "start")
for key, expected in {
    "schema_version": 2,
    "run_id": run_id,
    "suite_dir": str(suite_dir),
    "stdin": "/dev/null",
    "envelope_log": str(control_dir / "envelope.log"),
}.items():
    require_field(start, key, expected, "start")
envelope_supervisor_pid = require_positive_integer(
    start,
    "envelope_supervisor_pid",
    "start",
)
start_recorded_unix = require_unix_time(start, "recorded_unix", "start")
require_utc(start, "recorded_utc", "start")
for key in ("nohup_path", "setsid_path", "bash_path"):
    value = start.get(key)
    if type(value) is not str:
        raise RuntimeError(f"start {key} is not a string")
    executable = real_file(Path(value))
    if not os.access(executable, os.X_OK):
        raise RuntimeError(f"start {key} is not executable")
expected_worker_command = [
    start["bash_path"],
    str(snapshot),
    "worker",
    "--script-sha256",
    script_sha256,
    "--suite-dir",
    str(suite_dir),
    "--control-dir",
    str(control_dir),
]
require_field(start, "worker_command", expected_worker_command, "start")

worker_claim_keys = {
    "schema_version",
    "run_id",
    "suite_dir",
    "worker_pid",
    "claimed_utc",
    "claimed_unix",
    "script_sha256",
    "attempt_sha256",
}
require_keys(worker_claim, worker_claim_keys, "worker claim")
for key, expected in {
    "schema_version": 2,
    "run_id": run_id,
    "suite_dir": str(suite_dir),
    "script_sha256": script_sha256,
    "attempt_sha256": terminal["attempt_sha256"],
}.items():
    require_field(worker_claim, key, expected, "worker claim")
claim_worker_pid = require_positive_integer(
    worker_claim,
    "worker_pid",
    "worker claim",
)
claim_unix = require_unix_time(worker_claim, "claimed_unix", "worker claim")
require_utc(worker_claim, "claimed_utc", "worker claim")

worker_keys = {
    "schema_version",
    "run_id",
    "suite_dir",
    "role",
    "pid",
    "ppid",
    "sid",
    "tty",
    "cwd",
    "started_utc",
    "started_unix",
    "attempt_sha256",
    "start_sha256",
    "worker_claim_sha256",
}
require_keys(worker, worker_keys, "worker")
for key, expected in {
    "schema_version": 2,
    "run_id": run_id,
    "suite_dir": str(suite_dir),
    "role": "durable-preflight-v2-worker",
    "pid": terminal_worker_pid,
    "ppid": envelope_supervisor_pid,
    "sid": terminal_worker_pid,
    "tty": "?",
    "cwd": str(repo_root),
    "started_utc": terminal["started_utc"],
    "started_unix": terminal_started_unix,
    "attempt_sha256": terminal["attempt_sha256"],
    "start_sha256": terminal["start_sha256"],
    "worker_claim_sha256": terminal["worker_claim_sha256"],
}.items():
    require_field(worker, key, expected, "worker")
worker_pid = require_positive_integer(worker, "pid", "worker")
require_positive_integer(worker, "ppid", "worker")
require_positive_integer(worker, "sid", "worker")
require_unix_time(worker, "started_unix", "worker")
require_utc(worker, "started_utc", "worker")
if claim_worker_pid != worker_pid:
    raise RuntimeError("worker claim PID binding drift")

if not (attempt_started_unix <= start_recorded_unix <= terminal_started_unix):
    raise RuntimeError("attempt/start/worker time order drift")
if claim_unix < attempt_started_unix or claim_unix > terminal_started_unix:
    raise RuntimeError("worker claim time order drift")

previous_ended_unix = terminal_started_unix
for index, name, command in (
    ("01", "setup", ["./setup.sh"]),
    ("02", "check", ["./run.sh", "check"]),
    ("03", "cache", ["./run.sh", "cache"]),
    ("04", "smoke", ["./run.sh", "smoke"]),
):
    step_path = control_dir / f"{index}-{name}.json"
    log_path = control_dir / f"{index}-{name}.log"
    exit_path = control_dir / f"{index}-{name}.exit"
    step = load_object(step_path)
    step_keys = {
        "schema_version",
        "run_id",
        "suite_dir",
        "index",
        "name",
        "command",
        "command_exit_code",
        "step_exit_code",
        "started_utc",
        "started_unix",
        "ended_utc",
        "ended_unix",
        "log_sha256",
        "exit_sha256",
    }
    require_keys(step, step_keys, f"step {index}")
    for key, expected in {
        "schema_version": 2,
        "run_id": run_id,
        "suite_dir": str(suite_dir),
        "index": index,
        "name": name,
        "command": command,
        "command_exit_code": 0,
        "step_exit_code": 0,
        "log_sha256": terminal[f"step_{index}_log_sha256"],
        "exit_sha256": terminal[f"step_{index}_exit_sha256"],
    }.items():
        require_field(step, key, expected, f"step {index}")
    if real_file(exit_path).read_bytes() != b"0\n":
        raise RuntimeError(f"step {index} exit evidence is not exact zero")
    if sha256_file(real_file(log_path)) != step["log_sha256"]:
        raise RuntimeError(f"step {index} log hash binding drift")
    if sha256_file(exit_path) != step["exit_sha256"]:
        raise RuntimeError(f"step {index} exit hash binding drift")
    if sha256_file(step_path) != terminal[f"step_{index}_json_sha256"]:
        raise RuntimeError(f"step {index} JSON hash binding drift")
    step_started_unix = require_unix_time(step, "started_unix", f"step {index}")
    step_ended_unix = require_unix_time(step, "ended_unix", f"step {index}")
    require_utc(step, "started_utc", f"step {index}")
    require_utc(step, "ended_utc", f"step {index}")
    if step_started_unix < previous_ended_unix or step_ended_unix < step_started_unix:
        raise RuntimeError(f"step {index} time order drift")
    previous_ended_unix = step_ended_unix
if terminal_ended_unix < previous_ended_unix:
    raise RuntimeError("terminal ended before final step")

if sha256_file(real_file(source_script)) != script_sha256:
    raise RuntimeError("uploaded preflight script hash drift")
if sha256_file(snapshot) != script_sha256:
    raise RuntimeError("preflight script snapshot hash drift")
if worker_claim["attempt_sha256"] != sha256_file(attempt_path):
    raise RuntimeError("worker claim attempt-hash binding drift")
if worker["attempt_sha256"] != sha256_file(attempt_path):
    raise RuntimeError("worker attempt-hash binding drift")
if worker["start_sha256"] != sha256_file(start_path):
    raise RuntimeError("worker start-hash binding drift")
if worker["worker_claim_sha256"] != sha256_file(worker_claim_path):
    raise RuntimeError("worker claim-hash binding drift")

require_exited(envelope_supervisor_pid, "preflight envelope supervisor")
require_exited(worker_pid, "preflight worker")
try:
    os.killpg(worker_pid, 0)
except ProcessLookupError:
    pass
except PermissionError as error:
    raise RuntimeError("preflight worker process group still exists") from error
else:
    raise RuntimeError("preflight worker process group still exists")
PY
  verify_evidence_exit=$?
  ((verify_evidence_exit == 0)) || die "durable preflight evidence verification failed" "$verify_evidence_exit"
  [[ "$(sha256_file "$0")" == "$script_sha256" ]] || die "verifier drifted during verification"
  verify_source_and_downstream_absence || die "formal source or downstream path drifted during verification"
  printf '{"control_dir":"%s","run_id":"%s","status":"verified","suite_dir":"%s"}\n' \
    "$control_dir" "$run_id" "$suite_dir"
  exit 0
fi

if [[ "$mode" == "start" ]]; then
  source_script="$run_artifact/launcher/$SCRIPT_NAME"
  [[ "$0" == "$source_script" ]] || die "preflight script is not the canonical uploaded artifact"
  require_real_directory "$REPO_ROOT" "formal repository"
  require_real_directory "$REPO_ROOT/runs" "formal runs directory"
  require_real_directory "$run_artifact" "run artifact directory"
  require_real_directory "${source_script%/*}" "launcher artifact directory"
  [[ -f "$0" && ! -L "$0" ]] || die "preflight script is not a real regular file"
  [[ "$(realpath -e -- "$0")" == "$source_script" ]] || die "preflight script uses a symlink or path alias"
  [[ "$(sha256_file "$0")" == "$script_sha256" ]] || die "preflight script SHA256 differs from the frozen value"
  [[ ! -e "$control_dir" && ! -L "$control_dir" ]] || die "preflight control path exists; attempt is consumed"
  verify_source_and_formal_absence || die "formal source or preflight path gate failed"

  nohup_path="$(command -v nohup)" || die "nohup is unavailable"
  setsid_path="$(command -v setsid)" || die "setsid is unavailable"
  bash_path="$(command -v bash)" || die "bash is unavailable"
  nohup_path="$(realpath -e -- "$nohup_path")" || die "cannot resolve nohup"
  setsid_path="$(realpath -e -- "$setsid_path")" || die "cannot resolve setsid"
  bash_path="$(realpath -e -- "$bash_path")" || die "cannot resolve bash"
  [[ -f "$nohup_path" && -x "$nohup_path" ]] || die "resolved nohup is not executable"
  [[ -f "$setsid_path" && -x "$setsid_path" ]] || die "resolved setsid is not executable"
  [[ -f "$bash_path" && -x "$bash_path" ]] || die "resolved bash is not executable"

  # No -p: this directory is the immutable claim on the only preflight attempt.
  mkdir -- "$control_dir" || die "preflight control directory already exists; attempt is consumed"
  require_real_directory "$control_dir" "preflight control directory"
  chmod 700 -- "$control_dir" || die "cannot restrict preflight control directory"

  snapshot="$control_dir/script-snapshot.sh"
  (
    umask 077
    cp -- "$0" "$snapshot"
  ) || die "cannot snapshot preflight script"
  chmod 500 -- "$snapshot" || die "cannot make preflight snapshot executable"
  [[ "$(sha256_file "$snapshot")" == "$script_sha256" ]] || die "preflight snapshot SHA256 drifted"

  started_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)" || die "cannot read start UTC"
  started_unix="$(date -u +%s)" || die "cannot read start Unix time"
  hostname_value="$(hostname)" || die "cannot read hostname"
  boot_id="$(tr '[:upper:]' '[:lower:]' < /proc/sys/kernel/random/boot_id)" || die "cannot read boot id"
  [[ "$hostname_value" =~ ^[A-Za-z0-9._-]+$ ]] || die "hostname cannot be represented safely"
  [[ "$boot_id" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || die "boot id is invalid"
  attempt_json="$(printf '{\n  "schema_version": 2,\n  "run_id": "%s",\n  "kind": "durable-preflight-v2",\n  "formal_source_sha": "%s",\n  "formal_source_tree": "%s",\n  "suite_dir": "%s",\n  "control_dir": "%s",\n  "source_script": "%s",\n  "snapshot": "%s",\n  "script_sha256": "%s",\n  "starter_pid": %s,\n  "started_utc": "%s",\n  "started_unix": %s,\n  "hostname": "%s",\n  "boot_id": "%s"\n}' \
    "$run_id" "$FORMAL_SOURCE_SHA" "$FORMAL_SOURCE_TREE" "$suite_dir" "$control_dir" "$source_script" \
    "$snapshot" "$script_sha256" "$$" "$started_utc" "$started_unix" "$hostname_value" "$boot_id")" || die "cannot build preflight attempt record"
  write_atomic "$control_dir/attempt.json" "$attempt_json" || die "cannot persist preflight attempt record"

  : > "$control_dir/envelope.log" || die "cannot create preflight envelope log"
  chmod 600 -- "$control_dir/envelope.log" || die "cannot restrict preflight envelope log"
  cd "$REPO_ROOT" || die "cannot enter formal repository"
  "$nohup_path" "$setsid_path" --fork --wait "$bash_path" "$snapshot" worker \
    --script-sha256 "$script_sha256" \
    --suite-dir "$suite_dir" \
    --control-dir "$control_dir" \
    </dev/null >"$control_dir/envelope.log" 2>&1 &
  envelope_supervisor_pid=$!
  [[ "$envelope_supervisor_pid" =~ ^[0-9]+$ ]] || die "nohup did not return a preflight envelope PID"

  recorded_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)" || die "cannot read start-record UTC"
  recorded_unix="$(date -u +%s)" || die "cannot read start-record Unix time"
  start_json="$(printf '{\n  "schema_version": 2,\n  "run_id": "%s",\n  "suite_dir": "%s",\n  "envelope_supervisor_pid": %s,\n  "nohup_path": "%s",\n  "setsid_path": "%s",\n  "bash_path": "%s",\n  "stdin": "/dev/null",\n  "envelope_log": "%s",\n  "worker_command": ["%s", "%s", "worker", "--script-sha256", "%s", "--suite-dir", "%s", "--control-dir", "%s"],\n  "recorded_utc": "%s",\n  "recorded_unix": %s\n}' \
    "$run_id" "$suite_dir" "$envelope_supervisor_pid" "$nohup_path" "$setsid_path" "$bash_path" \
    "$control_dir/envelope.log" "$bash_path" "$snapshot" "$script_sha256" "$suite_dir" "$control_dir" \
    "$recorded_utc" "$recorded_unix")" || die "cannot build preflight start record"
  write_atomic "$control_dir/start.json" "$start_json" || die "cannot persist preflight start record"
  printf '{"control_dir":"%s","envelope_supervisor_pid":%s,"run_id":"%s","script_sha256":"%s","suite_dir":"%s"}\n' \
    "$control_dir" "$envelope_supervisor_pid" "$run_id" "$script_sha256" "$suite_dir"
  exit 0
fi

snapshot="$control_dir/script-snapshot.sh"
require_real_directory "$REPO_ROOT" "formal repository"
require_real_directory "$control_dir" "preflight control directory"
[[ "$0" == "$snapshot" ]] || die "worker is not the canonical preflight snapshot"
[[ -f "$0" && ! -L "$0" ]] || die "preflight snapshot is not a real regular file"
[[ "$(realpath -e -- "$0")" == "$snapshot" ]] || die "preflight snapshot uses a symlink or path alias"
worker_claim_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || printf unknown)"
worker_claim_unix="$(date -u +%s 2>/dev/null || printf 0)"
attempt_sha256_claimed="$(hash_or_null "$control_dir/attempt.json")"
worker_claim_json="$(printf '{\n  "schema_version": 2,\n  "run_id": "%s",\n  "suite_dir": "%s",\n  "worker_pid": %s,\n  "claimed_utc": "%s",\n  "claimed_unix": %s,\n  "script_sha256": "%s",\n  "attempt_sha256": %s\n}' \
  "$run_id" "$suite_dir" "$$" "$worker_claim_utc" "$worker_claim_unix" "$script_sha256" \
  "$attempt_sha256_claimed")" || die "cannot build preflight worker claim"
worker_claim_sha256_expected="$(sha256_payload "$worker_claim_json")" || die "cannot hash preflight worker claim"
write_atomic "$control_dir/worker-claim.json" "$worker_claim_json" || die "preflight worker attempt is consumed"

worker_terminal_written=0
worker_started_utc="unknown"
worker_started_unix=0
worker_sid=0
worker_tty="unknown"
completed_steps=0
failed_step="worker-initialization"
overall_exit=65
failure_reason="worker initialization failed"

write_worker_terminal() {
  local terminal_status="$1"
  local terminal_exit="$2"
  local ended_utc ended_unix terminal_json
  ((worker_terminal_written == 0)) || return 0
  ended_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || printf unknown)"
  ended_unix="$(date -u +%s 2>/dev/null || printf 0)"
  terminal_json="$(printf '{\n  "schema_version": 2,\n  "run_id": "%s",\n  "suite_dir": "%s",\n  "status": "%s",\n  "exit_code": %s,\n  "completed_steps": %s,\n  "failed_step": "%s",\n  "reason": "%s",\n  "worker_pid": %s,\n  "worker_sid": %s,\n  "worker_tty": "%s",\n  "started_utc": "%s",\n  "started_unix": %s,\n  "ended_utc": "%s",\n  "ended_unix": %s,\n  "formal_source_sha": "%s",\n  "formal_source_tree": "%s",\n  "script_sha256": "%s",\n  "attempt_sha256": %s,\n  "start_sha256": %s,\n  "worker_claim_sha256": %s,\n  "worker_start_sha256": %s,\n  "envelope_log_sha256": %s,\n  "step_01_log_sha256": %s,\n  "step_01_exit_sha256": %s,\n  "step_01_json_sha256": %s,\n  "step_02_log_sha256": %s,\n  "step_02_exit_sha256": %s,\n  "step_02_json_sha256": %s,\n  "step_03_log_sha256": %s,\n  "step_03_exit_sha256": %s,\n  "step_03_json_sha256": %s,\n  "step_04_log_sha256": %s,\n  "step_04_exit_sha256": %s,\n  "step_04_json_sha256": %s\n}' \
    "$run_id" "$suite_dir" "$terminal_status" "$terminal_exit" "$completed_steps" "$failed_step" "$failure_reason" \
    "$$" "$worker_sid" "$worker_tty" "$worker_started_utc" "$worker_started_unix" "$ended_utc" "$ended_unix" \
    "$FORMAL_SOURCE_SHA" "$FORMAL_SOURCE_TREE" "$script_sha256" \
    "$(hash_or_null "$control_dir/attempt.json")" "$(hash_or_null "$control_dir/start.json")" \
    "$(hash_or_null "$control_dir/worker-claim.json")" "$(hash_or_null "$control_dir/worker-start.json")" \
    "$(hash_or_null "$control_dir/envelope.log")" \
    "$(hash_or_null "$control_dir/01-setup.log")" "$(hash_or_null "$control_dir/01-setup.exit")" "$(hash_or_null "$control_dir/01-setup.json")" \
    "$(hash_or_null "$control_dir/02-check.log")" "$(hash_or_null "$control_dir/02-check.exit")" "$(hash_or_null "$control_dir/02-check.json")" \
    "$(hash_or_null "$control_dir/03-cache.log")" "$(hash_or_null "$control_dir/03-cache.exit")" "$(hash_or_null "$control_dir/03-cache.json")" \
    "$(hash_or_null "$control_dir/04-smoke.log")" "$(hash_or_null "$control_dir/04-smoke.exit")" "$(hash_or_null "$control_dir/04-smoke.json")")" || return 1
  write_atomic "$control_dir/terminal.json" "$terminal_json" || return 1
  worker_terminal_written=1
}

on_worker_exit() {
  local worker_exit=$?
  trap - EXIT
  if ((worker_terminal_written == 0)); then
    ((worker_exit != 0)) || worker_exit=70
    write_worker_terminal "failed" "$worker_exit" || true
  fi
  exit "$worker_exit"
}

on_worker_signal() {
  local signal_exit="$1"
  local signal_name="$2"
  failure_reason="worker received $signal_name"
  failed_step="worker-signal"
  exit "$signal_exit"
}

trap on_worker_exit EXIT
trap 'on_worker_signal 129 SIGHUP' HUP
trap 'on_worker_signal 130 SIGINT' INT
trap 'on_worker_signal 143 SIGTERM' TERM

[[ "$(sha256_file "$0")" == "$script_sha256" ]] || die "preflight worker SHA256 drifted"
[[ -f "$control_dir/attempt.json" && ! -L "$control_dir/attempt.json" ]] || die "preflight attempt record is missing"
attempt_sha256_bound="$(sha256_file "$control_dir/attempt.json")" || die "cannot bind preflight attempt record"
[[ "$attempt_sha256_claimed" == "\"$attempt_sha256_bound\"" ]] || die "preflight attempt record drifted before worker binding"
worker_claim_sha256_bound="$(sha256_file "$control_dir/worker-claim.json")" || die "cannot bind preflight worker claim"
[[ "$worker_claim_sha256_bound" == "$worker_claim_sha256_expected" ]] || die "preflight worker claim drifted before binding"

start_ready=0
for _ in $(seq 1 100); do
  if [[ -f "$control_dir/start.json" && ! -L "$control_dir/start.json" ]]; then
    start_ready=1
    break
  fi
  sleep 0.05
done
if ((start_ready == 0)); then
  failure_reason="starter start record did not arrive within five seconds"
  failed_step="start-record-gate"
  die "$failure_reason" 65
fi
start_sha256_bound="$(sha256_file "$control_dir/start.json")" || die "cannot bind preflight start record"
verify_source_and_formal_absence || die "worker source or formal-path gate failed"

worker_started_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)" || die "cannot read worker start UTC"
worker_started_unix="$(date -u +%s)" || die "cannot read worker start Unix time"
worker_sid="$(ps -o sid= -p "$$" | tr -d ' ')" || die "cannot read worker session"
worker_tty="$(ps -o tty= -p "$$" | tr -d ' ')" || die "cannot read worker tty"
worker_cwd="$(readlink -e -- "/proc/$$/cwd")" || die "cannot read worker cwd"
[[ "$worker_sid" == "$$" ]] || die "preflight worker is not a session leader"
[[ "$worker_tty" == "?" ]] || die "preflight worker retained a controlling terminal"
[[ "$worker_cwd" == "$REPO_ROOT" ]] || die "preflight worker cwd drifted"
worker_json="$(printf '{\n  "schema_version": 2,\n  "run_id": "%s",\n  "suite_dir": "%s",\n  "role": "durable-preflight-v2-worker",\n  "pid": %s,\n  "ppid": %s,\n  "sid": %s,\n  "tty": "%s",\n  "cwd": "%s",\n  "started_utc": "%s",\n  "started_unix": %s,\n  "attempt_sha256": "%s",\n  "start_sha256": "%s",\n  "worker_claim_sha256": "%s"\n}' \
  "$run_id" "$suite_dir" "$$" "$PPID" "$worker_sid" "$worker_tty" "$worker_cwd" \
  "$worker_started_utc" "$worker_started_unix" "$attempt_sha256_bound" "$start_sha256_bound" \
  "$worker_claim_sha256_bound")" || die "cannot build preflight worker record"
worker_start_sha256_expected="$(sha256_payload "$worker_json")" || die "cannot hash preflight worker record"
write_atomic "$control_dir/worker-start.json" "$worker_json" || die "cannot persist preflight worker record"
worker_start_sha256_bound="$(sha256_file "$control_dir/worker-start.json")" || die "cannot bind preflight worker record"
[[ "$worker_start_sha256_bound" == "$worker_start_sha256_expected" ]] || die "preflight worker record drifted before binding"

export AISTATION_TARGET="GPU2"
export ZOOLOGY_EXPECTED_GIT_SHA="$FORMAL_SOURCE_SHA"
completed_steps=0
failed_step="none"
overall_exit=0
failure_reason="none"

run_step() {
  local index="$1"
  local name="$2"
  local command_json="$3"
  local log_path="$control_dir/$index-$name.log"
  local exit_path="$control_dir/$index-$name.exit"
  local step_path="$control_dir/$index-$name.json"
  local started_utc started_unix ended_utc ended_unix command_exit step_exit step_json

  verify_source_and_formal_absence || return 65
  : > "$log_path" || return 74
  chmod 600 -- "$log_path" || return 74
  started_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)" || return 74
  started_unix="$(date -u +%s)" || return 74
  case "$index" in
    01) ./setup.sh >"$log_path" 2>&1 ;;
    02) ./run.sh check >"$log_path" 2>&1 ;;
    03) ./run.sh cache >"$log_path" 2>&1 ;;
    04) ./run.sh smoke >"$log_path" 2>&1 ;;
    *) return 64 ;;
  esac
  command_exit=$?
  step_exit="$command_exit"
  if ! verify_source_and_formal_absence; then
    step_exit=65
  fi
  ended_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)" || step_exit=74
  ended_unix="$(date -u +%s)" || step_exit=74
  write_atomic "$exit_path" "$step_exit" || return 74
  step_json="$(printf '{\n  "schema_version": 2,\n  "run_id": "%s",\n  "suite_dir": "%s",\n  "index": "%s",\n  "name": "%s",\n  "command": %s,\n  "command_exit_code": %s,\n  "step_exit_code": %s,\n  "started_utc": "%s",\n  "started_unix": %s,\n  "ended_utc": "%s",\n  "ended_unix": %s,\n  "log_sha256": "%s",\n  "exit_sha256": "%s"\n}' \
    "$run_id" "$suite_dir" "$index" "$name" "$command_json" "$command_exit" "$step_exit" \
    "$started_utc" "$started_unix" "$ended_utc" "$ended_unix" \
    "$(sha256_file "$log_path")" "$(sha256_file "$exit_path")")" || return 74
  write_atomic "$step_path" "$step_json" || return 74
  return "$step_exit"
}

step_specs=(
  '01 setup ["./setup.sh"]'
  '02 check ["./run.sh", "check"]'
  '03 cache ["./run.sh", "cache"]'
  '04 smoke ["./run.sh", "smoke"]'
)
for spec in "${step_specs[@]}"; do
  read -r step_index step_name step_command <<< "$spec"
  run_step "$step_index" "$step_name" "$step_command"
  step_exit=$?
  if ((step_exit != 0)); then
    failed_step="$step_index-$step_name"
    overall_exit="$step_exit"
    break
  fi
  completed_steps=$((completed_steps + 1))
done

verify_source_and_formal_absence || {
  [[ "$failed_step" != "none" ]] || failed_step="postflight-source-gate"
  ((overall_exit != 0)) || overall_exit=65
}
if [[ ! -f "$control_dir/start.json" \
      || -L "$control_dir/start.json" \
      || "$(sha256_file "$control_dir/start.json")" != "$start_sha256_bound" ]]; then
  [[ "$failed_step" != "none" ]] || failed_step="start-record-drift"
  ((overall_exit != 0)) || overall_exit=65
fi
if [[ ! -f "$control_dir/attempt.json" \
      || -L "$control_dir/attempt.json" \
      || "$(sha256_file "$control_dir/attempt.json")" != "$attempt_sha256_bound" ]]; then
  [[ "$failed_step" != "none" ]] || failed_step="attempt-record-drift"
  ((overall_exit != 0)) || overall_exit=65
fi
if [[ ! -f "$control_dir/worker-claim.json" \
      || -L "$control_dir/worker-claim.json" \
      || "$(sha256_file "$control_dir/worker-claim.json")" != "$worker_claim_sha256_bound" ]]; then
  [[ "$failed_step" != "none" ]] || failed_step="worker-claim-drift"
  ((overall_exit != 0)) || overall_exit=65
fi
if [[ ! -f "$control_dir/worker-start.json" \
      || -L "$control_dir/worker-start.json" \
      || "$(sha256_file "$control_dir/worker-start.json")" != "$worker_start_sha256_bound" ]]; then
  [[ "$failed_step" != "none" ]] || failed_step="worker-start-record-drift"
  ((overall_exit != 0)) || overall_exit=65
fi
terminal_status="completed"
((overall_exit == 0 && completed_steps == 4)) || terminal_status="failed"
if [[ "$terminal_status" == "completed" ]]; then
  failure_reason="none"
elif [[ "$failure_reason" == "none" ]]; then
  failure_reason="preflight step or postflight gate failed"
fi
write_worker_terminal "$terminal_status" "$overall_exit" || die "cannot persist preflight terminal record"
exit "$overall_exit"
