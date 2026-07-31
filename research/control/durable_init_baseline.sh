#!/usr/bin/env bash

# The worker must record nonzero commands instead of exiting at `wait`.
set -u
set -o pipefail

REPO_ROOT="/huyang2/zoology"
FORMAL_SOURCE_SHA="13f880b5fe61619a1006ef33610de69fbabaaec1"
FORMAL_SOURCE_TREE="ed83a7188351ca2cce8aba46d1cb3b108ce31ec2"
PREFLIGHT_V2_SHA256="3b1d5b682624be4149ae1ff30e9860f2904c794f047c579e00131bf7e25c93cd"
SCRIPT_NAME="durable_init_baseline.sh"
PREFLIGHT_V2_NAME="durable_preflight_v2.sh"
CONTROL_NAME="init-baseline-control"
FORMAL_LAUNCH_CONTROL_NAME="formal-launch-control"

usage() {
  printf '%s\n' \
    "usage: $0 start|worker|verify --script-sha256 SHA256 --suite-dir PATH --control-dir PATH [--bash-path PATH --preflight-terminal-sha256 SHA256]" >&2
  exit 64
}

die() {
  printf 'durable init-baseline: %s\n' "$1" >&2
  exit "${2:-1}"
}

sha256_file() {
  sha256sum -- "$1" | awk '{print $1}'
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
  sync "$temporary" || return 1
  ln -- "$temporary" "$destination" || return 1
  rm -- "$temporary" || return 1
  sync "${destination%/*}" || return 1
}

capture_timestamp() {
  local captured_unix captured_utc
  captured_unix="$(date -u +%s)" || return 1
  [[ "$captured_unix" =~ ^[0-9]+$ ]] || return 1
  captured_utc="$(date -u -d "@$captured_unix" +%Y-%m-%dT%H:%M:%SZ)" || return 1
  [[ "$captured_utc" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]] || return 1
  printf '%s %s\n' "$captured_utc" "$captured_unix"
}

write_starter_terminal() {
  local exit_code="$1"
  local ended_utc ended_unix terminal_json timestamp_pair
  timestamp_pair="$(capture_timestamp 2>/dev/null || printf 'unknown 0')"
  read -r ended_utc ended_unix <<< "$timestamp_pair"
  terminal_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "kind": "durable-init-baseline-starter",\n  "status": "failed",\n  "exit_code": %s,\n  "reason": "starter failed after init-baseline control claim",\n  "formal_source_sha": "%s",\n  "formal_source_tree": "%s",\n  "suite_dir": "%s",\n  "control_dir": "%s",\n  "script_sha256": "%s",\n  "ended_utc": "%s",\n  "ended_unix": %s\n}' \
    "$run_id" "$exit_code" "$FORMAL_SOURCE_SHA" "$FORMAL_SOURCE_TREE" \
    "$suite_dir" "$control_dir" "$script_sha256" "$ended_utc" "$ended_unix")" || return 1
  write_atomic "$control_dir/starter-terminal.json" "$terminal_json"
}

on_starter_exit() {
  local starter_exit=$?
  trap - EXIT
  if ((starter_handoff == 0 && starter_exit != 0)); then
    write_starter_terminal "$starter_exit" || true
  fi
  exit "$starter_exit"
}

hash_or_null() {
  local evidence="$1"
  if [[ -f "$evidence" && ! -L "$evidence" ]]; then
    printf '"%s"' "$(sha256_file "$evidence")"
  else
    printf 'null'
  fi
}

proc_stat_identity() {
  local pid="$1"
  local line tail
  local -a fields
  IFS= read -r line < "/proc/$pid/stat" || return 1
  tail="${line##*) }"
  read -r -a fields <<< "$tail"
  ((${#fields[@]} >= 20)) || return 1
  printf '%s %s %s %s %s' \
    "${fields[1]}" "${fields[2]}" "${fields[3]}" "${fields[4]}" "${fields[19]}"
}

proc_cmdline_text() {
  local pid="$1"
  tr '\0' ' ' < "/proc/$pid/cmdline"
}

proc_cmdline_hex() {
  local pid="$1"
  od -An -v -tx1 "/proc/$pid/cmdline" | tr -d ' \n'
}

proc_state() {
  local pid="$1"
  local line tail
  IFS= read -r line < "/proc/$pid/stat" || return 1
  tail="${line##*) }"
  printf '%s' "${tail%% *}"
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

verify_preinit_absence() {
  local forbidden
  for forbidden in "$suite_dir" "$bundle_dir" "$formal_launch_control"; do
    [[ ! -e "$forbidden" && ! -L "$forbidden" ]] || return 1
  done
}

fresh_suite_inventory() {
  LC_ALL=C find "$suite_dir" -mindepth 1 -maxdepth 1 -printf '%f\n' | LC_ALL=C sort
}

verify_fresh_suite_inventory() {
  local actual expected directory
  expected="$(printf '%s\n' \
    cache-manifest.json \
    cache-manifest.json.sha256 \
    claims \
    launches \
    logs \
    nvidia-smi.txt \
    runtime-attestation.json \
    single-baseline-manifest.json \
    source.tar.gz \
    source.tar.gz.sha256 \
    suite-manifest.json | LC_ALL=C sort)"
  actual="$(fresh_suite_inventory)" || return 1
  [[ "$actual" == "$expected" ]] || return 1
  for directory in "$suite_dir/logs" "$suite_dir/claims" "$suite_dir/launches"; do
    [[ -d "$directory" && ! -L "$directory" ]] || return 1
    [[ "$(realpath -e -- "$directory")" == "$directory" ]] || return 1
    [[ -z "$(find "$directory" -mindepth 1 -print -quit)" ]] || return 1
  done
}

wait_without_signal() {
  local pid="$1"
  wait "$pid" 2>/dev/null
  init_exit_code=$?
}

process_group_exists() {
  local process_group="$1"
  kill -0 -- "-$process_group" 2>/dev/null
}

terminate_remaining_process_group() {
  local process_group="$1"
  local _
  process_group_exists "$process_group" || return 0
  kill -TERM -- "-$process_group" 2>/dev/null || true
  for _ in $(seq 1 50); do
    process_group_exists "$process_group" || return 0
    sleep 0.1
  done
  kill -KILL -- "-$process_group" 2>/dev/null || true
  for _ in $(seq 1 50); do
    process_group_exists "$process_group" || return 0
    sleep 0.1
  done
  return 1
}

terminate_bound_process_group() {
  local pid="$1"
  local expected_start_ticks="$2"
  local current_identity=""
  local current_ppid=""
  local current_pgrp=""
  local current_sid=""
  local current_tty_nr=""
  local current_start_ticks=""
  local state=""
  local _

  current_identity="$(proc_stat_identity "$pid" 2>/dev/null)" || {
    wait_without_signal "$pid"
    return 1
  }
  read -r current_ppid current_pgrp current_sid current_tty_nr current_start_ticks <<< "$current_identity"
  if [[ "$current_ppid" != "$$" \
        || "$current_pgrp" != "$pid" \
        || "$current_sid" != "$pid" \
        || "$current_start_ticks" != "$expected_start_ticks" ]]; then
    wait_without_signal "$pid"
    return 1
  fi
  kill -TERM -- "-$pid" 2>/dev/null || true
  for _ in $(seq 1 50); do
    current_identity="$(proc_stat_identity "$pid" 2>/dev/null)" || break
    read -r current_ppid current_pgrp current_sid current_tty_nr current_start_ticks <<< "$current_identity"
    if [[ "$current_ppid" != "$$" \
          || "$current_pgrp" != "$pid" \
          || "$current_sid" != "$pid" \
          || "$current_start_ticks" != "$expected_start_ticks" ]]; then
      wait_without_signal "$pid"
      return 1
    fi
    state="$(proc_state "$pid" 2>/dev/null)" || break
    [[ "$state" == "Z" ]] && break
    sleep 0.1
  done
  current_identity="$(proc_stat_identity "$pid" 2>/dev/null)" || current_identity=""
  if [[ -n "$current_identity" ]]; then
    read -r current_ppid current_pgrp current_sid current_tty_nr current_start_ticks <<< "$current_identity"
    state="$(proc_state "$pid" 2>/dev/null)" || state="gone"
    if [[ "$current_ppid" == "$$" \
          && "$current_pgrp" == "$pid" \
          && "$current_sid" == "$pid" \
          && "$current_start_ticks" == "$expected_start_ticks" \
          && "$state" != "gone" \
          && "$state" != "Z" ]]; then
      kill -KILL -- "-$pid" 2>/dev/null || true
    fi
  fi
  wait_without_signal "$pid"
  terminate_remaining_process_group "$pid"
}

mode="${1:-}"
[[ "$mode" == "start" || "$mode" == "worker" || "$mode" == "verify" ]] || usage
shift

script_sha256=""
suite_dir=""
control_dir=""
bash_path=""
preflight_terminal_sha256=""
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
    --bash-path)
      [[ "$mode" == "worker" && -z "$bash_path" ]] || usage
      bash_path="$2"
      ;;
    --preflight-terminal-sha256)
      [[ "$mode" == "worker" && -z "$preflight_terminal_sha256" ]] || usage
      preflight_terminal_sha256="$2"
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
[[ "$run_id" =~ ^[a-z0-9][a-z0-9-]*$ ]] || die "suite directory has an invalid run id"
[[ "$suite_dir" == "$REPO_ROOT/runs/$run_id" ]] || die "suite directory is not the canonical run path"
run_artifact="$REPO_ROOT/artifacts/$run_id"
preflight_control="$run_artifact/preflight-control"
preflight_terminal="$preflight_control/terminal.json"
preflight_verifier="$run_artifact/launcher/$PREFLIGHT_V2_NAME"
bundle_dir="$run_artifact/controller"
formal_launch_control="$run_artifact/$FORMAL_LAUNCH_CONTROL_NAME"
expected_control="$run_artifact/$CONTROL_NAME"
[[ "$control_dir" == "$expected_control" ]] || die "control directory is not the canonical init-baseline path"

verify_preflight_v2() {
  local actual_sha256 expected_output verifier_output
  [[ -f "$preflight_verifier" && ! -L "$preflight_verifier" ]] || return 1
  [[ "$(realpath -e -- "$preflight_verifier")" == "$preflight_verifier" ]] || return 1
  [[ -x "$preflight_verifier" ]] || return 1
  actual_sha256="$(sha256_file "$preflight_verifier")" || return 1
  [[ "$actual_sha256" == "$PREFLIGHT_V2_SHA256" ]] || return 1
  verifier_output="$("$preflight_verifier" verify \
    --script-sha256 "$PREFLIGHT_V2_SHA256" \
    --suite-dir "$suite_dir" \
    --control-dir "$preflight_control")" || return 1
  expected_output="$(printf '{"control_dir":"%s","run_id":"%s","status":"verified","suite_dir":"%s"}' \
    "$preflight_control" "$run_id" "$suite_dir")" || return 1
  [[ "$verifier_output" == "$expected_output" ]] || return 1
  [[ "$(sha256_file "$preflight_verifier")" == "$PREFLIGHT_V2_SHA256" ]]
}

if [[ "$mode" == "verify" ]]; then
  [[ -z "$bash_path" && -z "$preflight_terminal_sha256" ]] || usage
  source_script="$run_artifact/launcher/$SCRIPT_NAME"
  [[ "$0" == "$source_script" ]] || die "verifier is not the canonical uploaded artifact"
  require_real_directory "$REPO_ROOT" "formal repository"
  require_real_directory "$REPO_ROOT/runs" "formal runs directory"
  require_real_directory "$run_artifact" "run artifact directory"
  require_real_directory "$preflight_control" "completed preflight control directory"
  require_real_directory "${source_script%/*}" "launcher artifact directory"
  require_real_directory "$control_dir" "init-baseline control directory"
  require_real_directory "$suite_dir" "single-baseline suite"
  require_real_file "$0" "init-baseline verifier"
  require_real_file "$preflight_terminal" "completed preflight terminal"
  [[ "$(sha256_file "$0")" == "$script_sha256" ]] || die "verifier SHA256 differs from the frozen value"
  verify_preflight_v2 || die "canonical preflight-v2 evidence verification failed during init verification"
  verify_formal_source || die "formal source gate failed during verification"
  [[ ! -e "$bundle_dir" && ! -L "$bundle_dir" ]] || die "controller bundle exists during init verification"
  [[ ! -e "$formal_launch_control" && ! -L "$formal_launch_control" ]] || die "formal launch control exists during init verification"
  verify_fresh_suite_inventory || die "single-baseline suite is not exactly fresh during verification"
  project_python="$(realpath -e -- "$REPO_ROOT/.venv/bin/python")" || die "cannot resolve formal project Python"
  [[ -f "$project_python" && ! -L "$project_python" && -x "$project_python" ]] || die "resolved formal project Python is not a regular executable"

  PYTHONDONTWRITEBYTECODE=1 "$project_python" - \
    "$REPO_ROOT" "$run_id" "$suite_dir" "$control_dir" "$script_sha256" \
    "$PREFLIGHT_V2_SHA256" "$FORMAL_SOURCE_SHA" "$FORMAL_SOURCE_TREE" <<'PY'
import hashlib
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path


repo_root = Path(sys.argv[1])
run_id = sys.argv[2]
suite_dir = Path(sys.argv[3])
control_dir = Path(sys.argv[4])
script_sha256 = sys.argv[5]
preflight_v2_sha256 = sys.argv[6]
formal_source_sha = sys.argv[7]
formal_source_tree = sys.argv[8]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def real_file(path: Path) -> Path:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or path.resolve(strict=True) != path:
        raise RuntimeError(f"evidence is not a canonical regular file: {path}")
    return path


def load_object(path: Path) -> dict:
    payload = json.loads(real_file(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"evidence is not a JSON object: {path}")
    return payload


def require_exited(pid: int, label: str) -> None:
    if pid <= 0:
        raise RuntimeError(f"{label} PID is invalid")
    if Path(f"/proc/{pid}").exists():
        raise RuntimeError(f"{label} PID is still present: {pid}")


def require_exact_fields(payload: dict, expected: set[str], label: str) -> None:
    actual = set(payload)
    if actual != expected:
        raise RuntimeError(
            f"{label} field inventory drift: "
            f"expected={sorted(expected)} actual={sorted(actual)}"
        )


def require_int(value: object, label: str, *, positive: bool = False) -> int:
    if type(value) is not int:
        raise RuntimeError(f"{label} is not an exact integer")
    if positive and value <= 0:
        raise RuntimeError(f"{label} is not positive")
    return value


def require_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise RuntimeError(f"{label} is not a string")
    return value


def require_timestamp(payload: dict, prefix: str, label: str) -> int:
    utc_value = require_string(payload.get(f"{prefix}_utc"), f"{label} UTC")
    unix_value = require_int(payload.get(f"{prefix}_unix"), f"{label} Unix")
    try:
        parsed = datetime.strptime(utc_value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as error:
        raise RuntimeError(f"{label} UTC is not canonical") from error
    if int(parsed.timestamp()) != unix_value:
        raise RuntimeError(f"{label} UTC/Unix binding drift")
    return unix_value


def require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise RuntimeError(f"{label} is not lowercase SHA256")
    return value


expected_control_names = {
    "attempt.json",
    "envelope.log",
    "init-command.json",
    "init.stderr.log",
    "init.stdout.log",
    "script-snapshot.sh",
    "start.json",
    "suite-inventory.txt",
    "terminal.json",
    "validator-command.json",
    "validator.stderr.log",
    "validator.stdout.log",
    "worker-claim.json",
    "worker-start.json",
}
actual_control_names = {path.name for path in control_dir.iterdir()}
if actual_control_names != expected_control_names:
    raise RuntimeError(
        "init control inventory drift: "
        f"expected={sorted(expected_control_names)} "
        f"actual={sorted(actual_control_names)}"
    )

attempt = load_object(control_dir / "attempt.json")
start = load_object(control_dir / "start.json")
worker_claim = load_object(control_dir / "worker-claim.json")
worker = load_object(control_dir / "worker-start.json")
init_command = load_object(control_dir / "init-command.json")
validator = load_object(control_dir / "validator-command.json")
terminal = load_object(control_dir / "terminal.json")
preflight_terminal_path = control_dir.parent / "preflight-control" / "terminal.json"
preflight_verifier_path = control_dir.parent / "launcher" / "durable_preflight_v2.sh"
preflight_terminal = load_object(preflight_terminal_path)

attempt_fields = {
    "schema_version",
    "run_id",
    "kind",
    "formal_source_sha",
    "formal_source_tree",
    "suite_dir",
    "bundle_dir",
    "formal_launch_control",
    "control_dir",
    "source_script",
    "snapshot",
    "script_sha256",
    "run_sh_sha256",
    "path_contract_sha256",
    "preflight_verifier",
    "preflight_verifier_sha256",
    "preflight_terminal",
    "preflight_terminal_sha256",
    "path_contract_command",
    "init_command",
    "validator_command",
    "starter_pid",
    "started_utc",
    "started_unix",
    "hostname",
    "boot_id",
}
start_fields = {
    "schema_version",
    "run_id",
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
worker_fields = {
    "schema_version",
    "run_id",
    "role",
    "pid",
    "proc_ppid",
    "proc_pgrp",
    "proc_sid",
    "proc_tty_nr",
    "proc_start_ticks",
    "proc_exe",
    "proc_cmdline_text",
    "proc_cmdline_hex",
    "proc_cmdline_sha256",
    "proc_cwd",
    "envelope_supervisor_pid",
    "tty",
    "hostname",
    "boot_id",
    "started_utc",
    "started_unix",
    "preflight_verifier_sha256",
    "preflight_terminal_sha256",
    "attempt_sha256",
    "start_sha256",
    "worker_claim_sha256",
}
worker_claim_fields = {
    "schema_version",
    "run_id",
    "role",
    "pid",
    "ppid",
    "script_sha256",
    "attempt_sha256",
    "claimed_utc",
    "claimed_unix",
}
init_command_fields = {
    "schema_version",
    "run_id",
    "pid",
    "proc_ppid",
    "proc_pgrp",
    "proc_sid",
    "proc_tty_nr",
    "proc_start_ticks",
    "proc_exe",
    "proc_cwd",
    "proc_cmdline_text",
    "proc_cmdline_hex",
    "proc_cmdline_sha256",
    "spawn_command",
    "command",
    "started_utc",
    "started_unix",
}
validator_fields = {
    "schema_version",
    "run_id",
    "command",
    "exit_code",
    "stdout_sha256",
    "stderr_sha256",
    "stdout_hex",
    "started_utc",
    "started_unix",
}
require_exact_fields(attempt, attempt_fields, "attempt")
require_exact_fields(start, start_fields, "start")
require_exact_fields(worker_claim, worker_claim_fields, "worker claim")
require_exact_fields(worker, worker_fields, "worker start")
require_exact_fields(init_command, init_command_fields, "init command")
require_exact_fields(validator, validator_fields, "validator command")

expected_attempt = {
    "schema_version": 1,
    "run_id": run_id,
    "kind": "durable-init-baseline",
    "formal_source_sha": formal_source_sha,
    "formal_source_tree": formal_source_tree,
    "suite_dir": str(suite_dir),
    "bundle_dir": str(control_dir.parent / "controller"),
    "formal_launch_control": str(control_dir.parent / "formal-launch-control"),
    "control_dir": str(control_dir),
    "source_script": str(control_dir.parent / "launcher" / "durable_init_baseline.sh"),
    "snapshot": str(control_dir / "script-snapshot.sh"),
    "script_sha256": script_sha256,
    "run_sh_sha256": sha256_file(real_file(repo_root / "run.sh")),
    "path_contract_sha256": sha256_file(
        real_file(repo_root / "repro" / "path_contract.py")
    ),
    "preflight_verifier": str(preflight_verifier_path),
    "preflight_verifier_sha256": preflight_v2_sha256,
    "preflight_terminal": str(preflight_terminal_path),
    "preflight_terminal_sha256": sha256_file(preflight_terminal_path),
}
for key, expected in expected_attempt.items():
    if type(attempt.get(key)) is not type(expected) or attempt.get(key) != expected:
        raise RuntimeError(
            f"attempt {key} drift: expected={expected!r} "
            f"actual={attempt.get(key)!r}"
        )
starter_pid = require_int(attempt.get("starter_pid"), "attempt starter PID", positive=True)
hostname = require_string(attempt.get("hostname"), "attempt hostname")
boot_id = require_string(attempt.get("boot_id"), "attempt boot ID")
if re.fullmatch(r"[A-Za-z0-9._-]+", hostname) is None:
    raise RuntimeError("attempt hostname is not canonical")
if re.fullmatch(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    boot_id,
) is None:
    raise RuntimeError("attempt boot ID is not canonical")

expected_terminal = {
    "schema_version": 1,
    "run_id": run_id,
    "kind": "durable-init-baseline",
    "status": "completed",
    "exit_code": 0,
    "reason": "none",
    "formal_source_sha": formal_source_sha,
    "formal_source_tree": formal_source_tree,
    "init_exit_code": 0,
    "validator_exit_code": 0,
    "script_sha256": script_sha256,
}
terminal_fields = {
    "schema_version",
    "run_id",
    "kind",
    "status",
    "exit_code",
    "reason",
    "formal_source_sha",
    "formal_source_tree",
    "worker_pid",
    "worker_sid",
    "worker_tty",
    "init_pid",
    "init_exit_code",
    "validator_exit_code",
    "script_sha256",
    "run_sh_sha256",
    "preflight_verifier_sha256",
    "preflight_terminal_sha256",
    "worker_started_utc",
    "worker_started_unix",
    "ended_utc",
    "ended_unix",
    "attempt_sha256",
    "start_sha256",
    "worker_claim_sha256",
    "worker_start_sha256",
    "init_command_sha256",
    "envelope_log_sha256",
    "init_stdout_sha256",
    "init_stderr_sha256",
    "validator_command_sha256",
    "validator_stdout_sha256",
    "validator_stderr_sha256",
    "suite_inventory_sha256",
    "suite_manifest_sha256",
    "single_baseline_manifest_sha256",
    "source_archive_sha256",
    "source_archive_checksum_sha256",
    "cache_manifest_sha256",
    "cache_manifest_checksum_sha256",
    "nvidia_smi_sha256",
    "runtime_attestation_sha256",
}
require_exact_fields(terminal, terminal_fields, "terminal")
for key, expected in expected_terminal.items():
    if type(terminal.get(key)) is not type(expected) or terminal.get(key) != expected:
        raise RuntimeError(
            f"terminal {key} drift: expected={expected!r} "
            f"actual={terminal.get(key)!r}"
        )

expected_preflight_terminal = {
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
}
for key, expected in expected_preflight_terminal.items():
    if type(preflight_terminal.get(key)) is not type(expected) or preflight_terminal.get(key) != expected:
        raise RuntimeError(f"preflight terminal field drift during verify: {key}")
preflight_terminal_actual_sha256 = sha256_file(preflight_terminal_path)
if attempt.get("preflight_terminal_sha256") != preflight_terminal_actual_sha256:
    raise RuntimeError("attempt preflight-terminal hash binding drift")
if terminal.get("preflight_terminal_sha256") != preflight_terminal_actual_sha256:
    raise RuntimeError("terminal preflight-terminal hash binding drift")
if worker.get("preflight_terminal_sha256") != preflight_terminal_actual_sha256:
    raise RuntimeError("worker preflight-terminal hash binding drift")
if worker.get("preflight_verifier_sha256") != preflight_v2_sha256:
    raise RuntimeError("worker preflight-verifier hash binding drift")

worker_pid = require_int(terminal.get("worker_pid"), "terminal worker PID", positive=True)
worker_sid = require_int(terminal.get("worker_sid"), "terminal worker SID", positive=True)
worker_tty = require_string(terminal.get("worker_tty"), "terminal worker TTY")
init_pid = require_int(terminal.get("init_pid"), "terminal init PID", positive=True)
require_int(terminal.get("init_exit_code"), "terminal init exit code")
require_int(terminal.get("validator_exit_code"), "terminal validator exit code")
require_int(terminal.get("ended_unix"), "terminal ended Unix")
require_int(terminal.get("worker_started_unix"), "terminal worker-started Unix")
if worker_pid != worker.get("pid"):
    raise RuntimeError("terminal worker PID drift")
if worker_sid != worker.get("proc_sid"):
    raise RuntimeError("terminal worker SID drift")
if worker_tty != worker.get("tty"):
    raise RuntimeError("terminal worker TTY drift")
if init_pid != init_command.get("pid"):
    raise RuntimeError("terminal init PID drift")
if worker.get("proc_ppid") != start.get("envelope_supervisor_pid"):
    raise RuntimeError("worker parent differs from envelope supervisor")
if worker.get("envelope_supervisor_pid") != start.get(
    "envelope_supervisor_pid"
):
    raise RuntimeError("worker supervisor binding drift")
if worker.get("proc_pgrp") != worker.get("pid"):
    raise RuntimeError("worker process-group identity drift")
if worker.get("proc_sid") != worker.get("pid"):
    raise RuntimeError("worker session identity drift")
if worker.get("proc_tty_nr") != 0 or worker.get("tty") != "?":
    raise RuntimeError("worker TTY identity drift")
if init_command.get("proc_pgrp") != init_command.get("pid"):
    raise RuntimeError("init process-group identity drift")
if init_command.get("proc_sid") != init_command.get("pid"):
    raise RuntimeError("init session identity drift")
if init_command.get("proc_tty_nr") != 0:
    raise RuntimeError("init TTY identity drift")
if init_command.get("proc_ppid") != worker.get("pid"):
    raise RuntimeError("init parent differs from worker PID")

attempt_time = require_timestamp(attempt, "started", "attempt start")
start_time = require_timestamp(start, "recorded", "start record")
worker_time = require_timestamp(worker, "started", "worker start")
worker_claim_time = require_timestamp(worker_claim, "claimed", "worker claim")
init_time = require_timestamp(init_command, "started", "init start")
validator_time = require_timestamp(validator, "started", "validator start")
terminal_worker_time = require_timestamp(
    terminal, "worker_started", "terminal worker start"
)
terminal_end_time = require_timestamp(terminal, "ended", "terminal end")
if terminal_worker_time != worker_time:
    raise RuntimeError("terminal worker timestamp drift")
if not (attempt_time <= worker_claim_time <= worker_time):
    raise RuntimeError("worker-claim timestamp order drift")
if not (
    attempt_time
    <= start_time
    <= worker_time
    <= init_time
    <= validator_time
    <= terminal_end_time
):
    raise RuntimeError("init-baseline timestamp order drift")

for key in ("nohup_path", "setsid_path", "bash_path"):
    executable_value = require_string(start.get(key), f"start {key}")
    executable_path = real_file(Path(executable_value))
    if not os.access(executable_path, os.X_OK):
        raise RuntimeError(f"start {key} is not executable")
expected_start = {
    "schema_version": 1,
    "run_id": run_id,
    "stdin": "/dev/null",
    "envelope_log": str(control_dir / "envelope.log"),
}
for key, expected in expected_start.items():
    if type(start.get(key)) is not type(expected) or start.get(key) != expected:
        raise RuntimeError(f"start {key} drift")
supervisor_pid = require_int(
    start.get("envelope_supervisor_pid"),
    "start envelope supervisor PID",
    positive=True,
)

path_contract_command = attempt.get("path_contract_command")
if type(path_contract_command) is not list or len(path_contract_command) != 6:
    raise RuntimeError("attempt path-contract argv schema drift")
path_contract_python = require_string(
    path_contract_command[0], "attempt path-contract Python"
)
path_contract_python_path = real_file(Path(path_contract_python))
if not os.access(path_contract_python_path, os.X_OK):
    raise RuntimeError("attempt path-contract Python is not executable")
expected_path_contract_command = [
    path_contract_python,
    str(repo_root / "repro" / "path_contract.py"),
    "--root",
    str(repo_root),
    "--require-environments",
    "--validate-source",
]
if path_contract_command != expected_path_contract_command:
    raise RuntimeError("attempt path-contract argv drift")

expected_worker_command = [
    start["bash_path"],
    str(control_dir / "script-snapshot.sh"),
    "worker",
    "--script-sha256",
    script_sha256,
    "--suite-dir",
    str(suite_dir),
    "--control-dir",
    str(control_dir),
    "--bash-path",
    start["bash_path"],
    "--preflight-terminal-sha256",
    preflight_terminal_actual_sha256,
]
if type(start.get("worker_command")) is not list or start.get("worker_command") != expected_worker_command:
    raise RuntimeError("start-record worker argv drift")
expected_worker_cmdline = b"\0".join(
    argument.encode() for argument in expected_worker_command
) + b"\0"
if worker.get("proc_cmdline_hex") != expected_worker_cmdline.hex():
    raise RuntimeError("worker encoded argv drift")
if worker.get("proc_cmdline_sha256") != hashlib.sha256(
    expected_worker_cmdline
).hexdigest():
    raise RuntimeError("worker argv hash drift")
expected_worker = {
    "schema_version": 1,
    "run_id": run_id,
    "role": "durable-init-baseline-worker",
    "pid": worker_pid,
    "proc_ppid": supervisor_pid,
    "proc_pgrp": worker_pid,
    "proc_sid": worker_pid,
    "proc_tty_nr": 0,
    "proc_exe": start["bash_path"],
    "proc_cmdline_text": " ".join(expected_worker_command) + " ",
    "proc_cmdline_hex": expected_worker_cmdline.hex(),
    "proc_cmdline_sha256": hashlib.sha256(expected_worker_cmdline).hexdigest(),
    "proc_cwd": str(repo_root),
    "envelope_supervisor_pid": supervisor_pid,
    "tty": "?",
    "hostname": hostname,
    "boot_id": boot_id,
    "preflight_verifier_sha256": preflight_v2_sha256,
    "preflight_terminal_sha256": preflight_terminal_actual_sha256,
    "attempt_sha256": terminal["attempt_sha256"],
    "start_sha256": terminal["start_sha256"],
    "worker_claim_sha256": terminal["worker_claim_sha256"],
}
for key, expected in expected_worker.items():
    if type(worker.get(key)) is not type(expected) or worker.get(key) != expected:
        raise RuntimeError(f"worker {key} drift")
require_int(worker.get("proc_start_ticks"), "worker start ticks", positive=True)
expected_worker_claim = {
    "schema_version": 1,
    "run_id": run_id,
    "role": "durable-init-baseline-worker-claim",
    "pid": worker_pid,
    "ppid": supervisor_pid,
    "script_sha256": script_sha256,
    "attempt_sha256": terminal["attempt_sha256"],
}
for key, expected in expected_worker_claim.items():
    if type(worker_claim.get(key)) is not type(expected) or worker_claim.get(key) != expected:
        raise RuntimeError(f"worker claim {key} drift")

expected_init_command = [
    start["bash_path"],
    "./run.sh",
    "init-baseline",
    str(suite_dir),
]
if attempt.get("init_command") != expected_init_command:
    raise RuntimeError("attempt init argv drift")
if init_command.get("command") != expected_init_command:
    raise RuntimeError("bound init argv drift")
if init_command.get("proc_exe") != start["bash_path"]:
    raise RuntimeError("init executable drift")
expected_init_cmdline = b"\0".join(
    argument.encode() for argument in expected_init_command
) + b"\0"
if init_command.get("proc_cmdline_hex") != expected_init_cmdline.hex():
    raise RuntimeError("init encoded argv drift")
if init_command.get("proc_cmdline_sha256") != hashlib.sha256(
    expected_init_cmdline
).hexdigest():
    raise RuntimeError("init argv hash drift")
expected_init = {
    "schema_version": 1,
    "run_id": run_id,
    "pid": init_pid,
    "proc_ppid": worker_pid,
    "proc_pgrp": init_pid,
    "proc_sid": init_pid,
    "proc_tty_nr": 0,
    "proc_exe": start["bash_path"],
    "proc_cwd": str(repo_root),
    "proc_cmdline_text": " ".join(expected_init_command) + " ",
    "proc_cmdline_hex": expected_init_cmdline.hex(),
    "proc_cmdline_sha256": hashlib.sha256(expected_init_cmdline).hexdigest(),
    "spawn_command": [start["setsid_path"], *expected_init_command],
    "command": expected_init_command,
}
for key, expected in expected_init.items():
    if type(init_command.get(key)) is not type(expected) or init_command.get(key) != expected:
        raise RuntimeError(f"init command {key} drift")
require_int(init_command.get("proc_start_ticks"), "init start ticks", positive=True)

for key, value in terminal.items():
    if not key.endswith("_sha256"):
        continue
    require_sha256(value, f"completed terminal {key}")

hash_paths = {
    "preflight_terminal_sha256": preflight_terminal_path,
    "preflight_verifier_sha256": preflight_verifier_path,
    "attempt_sha256": control_dir / "attempt.json",
    "start_sha256": control_dir / "start.json",
    "worker_claim_sha256": control_dir / "worker-claim.json",
    "worker_start_sha256": control_dir / "worker-start.json",
    "init_command_sha256": control_dir / "init-command.json",
    "envelope_log_sha256": control_dir / "envelope.log",
    "init_stdout_sha256": control_dir / "init.stdout.log",
    "init_stderr_sha256": control_dir / "init.stderr.log",
    "validator_command_sha256": control_dir / "validator-command.json",
    "validator_stdout_sha256": control_dir / "validator.stdout.log",
    "validator_stderr_sha256": control_dir / "validator.stderr.log",
    "suite_inventory_sha256": control_dir / "suite-inventory.txt",
    "suite_manifest_sha256": suite_dir / "suite-manifest.json",
    "single_baseline_manifest_sha256": (
        suite_dir / "single-baseline-manifest.json"
    ),
    "source_archive_sha256": suite_dir / "source.tar.gz",
    "source_archive_checksum_sha256": suite_dir / "source.tar.gz.sha256",
    "cache_manifest_sha256": suite_dir / "cache-manifest.json",
    "cache_manifest_checksum_sha256": (
        suite_dir / "cache-manifest.json.sha256"
    ),
    "nvidia_smi_sha256": suite_dir / "nvidia-smi.txt",
    "runtime_attestation_sha256": suite_dir / "runtime-attestation.json",
    "run_sh_sha256": repo_root / "run.sh",
}
for key, path in hash_paths.items():
    actual = sha256_file(real_file(path))
    if terminal.get(key) != actual:
        raise RuntimeError(
            f"terminal hash drift for {key}: "
            f"expected={terminal.get(key)!r} actual={actual!r}"
        )

if sha256_file(real_file(control_dir / "script-snapshot.sh")) != script_sha256:
    raise RuntimeError("init script snapshot hash drift")
if sha256_file(real_file(repo_root / "repro" / "path_contract.py")) != attempt.get(
    "path_contract_sha256"
):
    raise RuntimeError("path-contract hash drift")
if worker.get("attempt_sha256") != terminal.get("attempt_sha256"):
    raise RuntimeError("worker attempt-hash binding drift")
if worker.get("start_sha256") != terminal.get("start_sha256"):
    raise RuntimeError("worker start-hash binding drift")
if worker.get("worker_claim_sha256") != terminal.get("worker_claim_sha256"):
    raise RuntimeError("worker claim-hash binding drift")

expected_validator_command = [
    "./.venv/bin/python",
    "-m",
    "repro.single_baseline",
    "selected-index",
    "--suite-dir",
    str(suite_dir),
]
if type(validator.get("command")) is not list or validator.get("command") != expected_validator_command:
    raise RuntimeError("validator argv drift")
if type(attempt.get("validator_command")) is not list or attempt.get("validator_command") != expected_validator_command:
    raise RuntimeError("attempt validator argv drift")
if type(attempt.get("init_command")) is not list or attempt.get("init_command") != expected_init_command:
    raise RuntimeError("attempt init argv schema drift")
validator_stdout_path = real_file(control_dir / "validator.stdout.log")
validator_stderr_path = real_file(control_dir / "validator.stderr.log")
expected_validator = {
    "schema_version": 1,
    "run_id": run_id,
    "command": expected_validator_command,
    "exit_code": 0,
    "stdout_sha256": sha256_file(validator_stdout_path),
    "stderr_sha256": sha256_file(validator_stderr_path),
    "stdout_hex": "350a",
}
for key, expected in expected_validator.items():
    if type(validator.get(key)) is not type(expected) or validator.get(key) != expected:
        raise RuntimeError(f"validator {key} drift")
if validator.get("exit_code") != 0 or validator.get("stdout_hex") != "350a":
    raise RuntimeError("validator result drift")
if validator_stdout_path.read_bytes() != b"5\n":
    raise RuntimeError("validator stdout is not exact selected index 5")
if validator_stderr_path.read_bytes():
    raise RuntimeError("validator stderr is not empty")

supervisor_pid = int(start["envelope_supervisor_pid"])
worker_pid = int(worker["pid"])
init_pid = int(init_command["pid"])
require_exited(supervisor_pid, "envelope supervisor")
require_exited(worker_pid, "init worker")
require_exited(init_pid, "init leader")
try:
    os.killpg(init_pid, 0)
except ProcessLookupError:
    pass
except PermissionError as error:
    raise RuntimeError("init process group still exists") from error
else:
    raise RuntimeError("init process group still exists")
PY
  verify_evidence_exit=$?
  ((verify_evidence_exit == 0)) || die "durable init-baseline evidence verification failed" "$verify_evidence_exit"
  validator_output="$(PYTHONDONTWRITEBYTECODE=1 "$project_python" -m repro.single_baseline selected-index --suite-dir "$suite_dir")" \
    || die "single-baseline selected-index verifier failed"
  [[ "$validator_output" == "5" ]] || die "single-baseline selected index is not exactly 5"
  verify_formal_source || die "formal source drifted during init verification"
  [[ ! -e "$bundle_dir" && ! -L "$bundle_dir" ]] || die "controller bundle appeared during init verification"
  [[ ! -e "$formal_launch_control" && ! -L "$formal_launch_control" ]] || die "formal launch control appeared during init verification"
  verify_fresh_suite_inventory || die "single-baseline suite drifted during init verification"
  printf '{"control_dir":"%s","run_id":"%s","status":"verified","suite_dir":"%s"}\n' \
    "$control_dir" "$run_id" "$suite_dir"
  exit 0
fi

if [[ "$mode" == "start" ]]; then
  [[ -z "$bash_path" && -z "$preflight_terminal_sha256" ]] || usage
  source_script="$run_artifact/launcher/$SCRIPT_NAME"
  [[ "$0" == "$source_script" ]] || die "init-baseline script is not the canonical uploaded artifact"
  require_real_directory "$REPO_ROOT" "formal repository"
  require_real_directory "$REPO_ROOT/runs" "formal runs directory"
  require_real_directory "$run_artifact" "run artifact directory"
  require_real_directory "$preflight_control" "completed preflight control directory"
  require_real_directory "${source_script%/*}" "launcher artifact directory"
  require_real_file "$0" "init-baseline script"
  require_real_file "$REPO_ROOT/run.sh" "formal run script"
  require_real_file "$REPO_ROOT/repro/path_contract.py" "path contract"
  require_real_file "$preflight_terminal" "completed preflight terminal"
  [[ "$(sha256_file "$0")" == "$script_sha256" ]] || die "init-baseline script SHA256 differs from the frozen value"
  verify_preflight_v2 || die "canonical preflight-v2 evidence verification failed before init claim"
  [[ ! -e "$control_dir" && ! -L "$control_dir" ]] || die "init-baseline control path exists; attempt is consumed"
  verify_formal_source || die "formal source gate failed"
  verify_preinit_absence || die "fresh suite or downstream formal path gate failed"

  nohup_path="$(command -v nohup)" || die "nohup is unavailable"
  setsid_path="$(command -v setsid)" || die "setsid is unavailable"
  bash_path="$(command -v bash)" || die "bash is unavailable"
  nohup_path="$(realpath -e -- "$nohup_path")" || die "cannot resolve nohup"
  setsid_path="$(realpath -e -- "$setsid_path")" || die "cannot resolve setsid"
  bash_path="$(realpath -e -- "$bash_path")" || die "cannot resolve bash"
  [[ -f "$nohup_path" && -x "$nohup_path" ]] || die "resolved nohup is not executable"
  [[ -f "$setsid_path" && -x "$setsid_path" ]] || die "resolved setsid is not executable"
  [[ -f "$bash_path" && -x "$bash_path" ]] || die "resolved bash is not executable"
  python3_path="$(command -v python3)" || die "python3 is unavailable"
  python3_path="$(realpath -e -- "$python3_path")" || die "cannot resolve python3"
  [[ -f "$python3_path" && -x "$python3_path" ]] || die "resolved python3 is not executable"
  preflight_terminal_sha256="$(sha256_file "$preflight_terminal")" || die "cannot bind completed preflight terminal"
  PYTHONDONTWRITEBYTECODE=1 "$python3_path" - \
    "$preflight_terminal" "$run_id" "$suite_dir" "$FORMAL_SOURCE_SHA" "$FORMAL_SOURCE_TREE" <<'PY'
import json
import sys
from pathlib import Path


terminal = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected = {
    "schema_version": 2,
    "run_id": sys.argv[2],
    "suite_dir": sys.argv[3],
    "status": "completed",
    "exit_code": 0,
    "completed_steps": 4,
    "failed_step": "none",
    "reason": "none",
    "formal_source_sha": sys.argv[4],
    "formal_source_tree": sys.argv[5],
}
for key, value in expected.items():
    if type(terminal.get(key)) is not type(value) or terminal.get(key) != value:
        raise SystemExit(f"preflight terminal field drift: {key}")
PY
  preflight_validation_exit=$?
  ((preflight_validation_exit == 0)) || die "completed preflight terminal contract failed" "$preflight_validation_exit"
  [[ "$(sha256_file "$preflight_terminal")" == "$preflight_terminal_sha256" ]] || die "completed preflight terminal drifted during validation"
  PYTHONDONTWRITEBYTECODE=1 "$python3_path" "$REPO_ROOT/repro/path_contract.py" \
    --root "$REPO_ROOT" \
    --require-environments \
    --validate-source \
    >/dev/null || die "formal path contract failed before init claim"
  verify_formal_source || die "formal source drifted during path-contract gate"
  verify_preinit_absence || die "fresh suite or downstream path appeared before init claim"

  starter_handoff=0
  # No -p: this directory is the immutable claim on the only init attempt.
  mkdir -- "$control_dir" || die "init-baseline control directory already exists; attempt is consumed"
  trap on_starter_exit EXIT
  require_real_directory "$control_dir" "init-baseline control directory"
  chmod 700 -- "$control_dir" || die "cannot restrict init-baseline control directory"

  snapshot="$control_dir/script-snapshot.sh"
  (
    umask 077
    cp -- "$0" "$snapshot"
  ) || die "cannot snapshot init-baseline script"
  chmod 500 -- "$snapshot" || die "cannot make init-baseline snapshot executable"
  [[ "$(sha256_file "$snapshot")" == "$script_sha256" ]] || die "init-baseline snapshot SHA256 drifted"

  timestamp_pair="$(capture_timestamp)" || die "cannot capture canonical start timestamp"
  read -r started_utc started_unix <<< "$timestamp_pair"
  hostname_value="$(hostname)" || die "cannot read hostname"
  boot_id="$(tr '[:upper:]' '[:lower:]' < /proc/sys/kernel/random/boot_id)" || die "cannot read boot id"
  [[ "$hostname_value" =~ ^[A-Za-z0-9._-]+$ ]] || die "hostname cannot be represented safely"
  [[ "$boot_id" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || die "boot id is invalid"
  run_sh_sha256="$(sha256_file "$REPO_ROOT/run.sh")" || die "cannot hash formal run script"
  path_contract_sha256="$(sha256_file "$REPO_ROOT/repro/path_contract.py")" || die "cannot hash path contract"
  attempt_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "kind": "durable-init-baseline",\n  "formal_source_sha": "%s",\n  "formal_source_tree": "%s",\n  "suite_dir": "%s",\n  "bundle_dir": "%s",\n  "formal_launch_control": "%s",\n  "control_dir": "%s",\n  "source_script": "%s",\n  "snapshot": "%s",\n  "script_sha256": "%s",\n  "run_sh_sha256": "%s",\n  "path_contract_sha256": "%s",\n  "preflight_verifier": "%s",\n  "preflight_verifier_sha256": "%s",\n  "preflight_terminal": "%s",\n  "preflight_terminal_sha256": "%s",\n  "path_contract_command": ["%s", "%s", "--root", "%s", "--require-environments", "--validate-source"],\n  "init_command": ["%s", "./run.sh", "init-baseline", "%s"],\n  "validator_command": ["./.venv/bin/python", "-m", "repro.single_baseline", "selected-index", "--suite-dir", "%s"],\n  "starter_pid": %s,\n  "started_utc": "%s",\n  "started_unix": %s,\n  "hostname": "%s",\n  "boot_id": "%s"\n}' \
    "$run_id" "$FORMAL_SOURCE_SHA" "$FORMAL_SOURCE_TREE" "$suite_dir" "$bundle_dir" "$formal_launch_control" \
    "$control_dir" "$source_script" "$snapshot" "$script_sha256" "$run_sh_sha256" "$path_contract_sha256" \
    "$preflight_verifier" "$PREFLIGHT_V2_SHA256" "$preflight_terminal" "$preflight_terminal_sha256" \
    "$python3_path" "$REPO_ROOT/repro/path_contract.py" "$REPO_ROOT" "$bash_path" "$suite_dir" \
    "$suite_dir" "$$" "$started_utc" "$started_unix" "$hostname_value" "$boot_id")" || die "cannot build init-baseline attempt record"
  write_atomic "$control_dir/attempt.json" "$attempt_json" || die "cannot persist init-baseline attempt record"

  : > "$control_dir/envelope.log" || die "cannot create init-baseline envelope log"
  chmod 600 -- "$control_dir/envelope.log" || die "cannot restrict init-baseline envelope log"
  cd "$REPO_ROOT" || die "cannot enter formal repository"
  "$nohup_path" "$setsid_path" --fork --wait "$bash_path" "$snapshot" worker \
    --script-sha256 "$script_sha256" \
    --suite-dir "$suite_dir" \
    --control-dir "$control_dir" \
    --bash-path "$bash_path" \
    --preflight-terminal-sha256 "$preflight_terminal_sha256" \
    </dev/null >"$control_dir/envelope.log" 2>&1 &
  envelope_supervisor_pid=$!
  [[ "$envelope_supervisor_pid" =~ ^[0-9]+$ ]] || die "nohup did not return an init-baseline envelope PID"

  timestamp_pair="$(capture_timestamp)" || die "cannot capture canonical start-record timestamp"
  read -r recorded_utc recorded_unix <<< "$timestamp_pair"
  start_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "envelope_supervisor_pid": %s,\n  "nohup_path": "%s",\n  "setsid_path": "%s",\n  "bash_path": "%s",\n  "stdin": "/dev/null",\n  "envelope_log": "%s",\n  "worker_command": ["%s", "%s", "worker", "--script-sha256", "%s", "--suite-dir", "%s", "--control-dir", "%s", "--bash-path", "%s", "--preflight-terminal-sha256", "%s"],\n  "recorded_utc": "%s",\n  "recorded_unix": %s\n}' \
    "$run_id" "$envelope_supervisor_pid" "$nohup_path" "$setsid_path" "$bash_path" "$control_dir/envelope.log" \
    "$bash_path" "$snapshot" "$script_sha256" "$suite_dir" "$control_dir" "$bash_path" "$preflight_terminal_sha256" \
    "$recorded_utc" "$recorded_unix")" || die "cannot build init-baseline start record"
  write_atomic "$control_dir/start.json" "$start_json" || die "cannot persist init-baseline start record"
  worker_claim_ready=0
  for _ in $(seq 1 100); do
    if [[ -f "$control_dir/worker-claim.json" && ! -L "$control_dir/worker-claim.json" ]]; then
      worker_claim_ready=1
      break
    fi
    sleep 0.05
  done
  ((worker_claim_ready == 1)) || die "init-baseline worker did not claim terminal ownership within five seconds"
  starter_handoff=1
  trap - EXIT
  printf '{"control_dir":"%s","envelope_supervisor_pid":%s,"run_id":"%s","script_sha256":"%s","suite_dir":"%s"}\n' \
    "$control_dir" "$envelope_supervisor_pid" "$run_id" "$script_sha256" "$suite_dir"
  exit 0
fi

[[ -n "$bash_path" && "$preflight_terminal_sha256" =~ ^[0-9a-f]{64}$ ]] || usage
terminal_written=0
failure_reason="worker validation did not complete"
overall_exit=65
init_pid=""
init_exit_code=""
init_start_ticks=""
init_group_bound=0
validator_exit_code=""
worker_started_utc="unknown"
worker_started_unix=0
worker_sid=0
worker_tty="unknown"
script_actual_sha256=""
run_sh_sha256=""
attempt_sha256_bound=""
start_sha256_bound=""
worker_claim_sha256_bound=""
worker_start_sha256_bound=""
init_command_sha256_bound=""
validator_command_sha256_bound=""
suite_manifest_sha256_bound=""
single_baseline_manifest_sha256_bound=""
source_archive_sha256_bound=""
source_archive_checksum_sha256_bound=""
cache_manifest_sha256_bound=""
cache_manifest_checksum_sha256_bound=""
nvidia_smi_sha256_bound=""
runtime_attestation_sha256_bound=""
suite_inventory_sha256_bound=""
preflight_terminal_sha256_bound=""
preflight_verifier_sha256_bound=""

bound_hash_matches() {
  local path="$1"
  local expected="$2"
  [[ -z "$expected" ]] && return 0
  [[ -f "$path" && ! -L "$path" ]] || return 1
  [[ "$(sha256_file "$path")" == "$expected" ]]
}

verify_bound_hashes() {
  bound_hash_matches "$preflight_verifier" "$preflight_verifier_sha256_bound" || return 1
  bound_hash_matches "$preflight_terminal" "$preflight_terminal_sha256_bound" || return 1
  bound_hash_matches "$control_dir/attempt.json" "$attempt_sha256_bound" || return 1
  bound_hash_matches "$control_dir/start.json" "$start_sha256_bound" || return 1
  bound_hash_matches "$control_dir/worker-claim.json" "$worker_claim_sha256_bound" || return 1
  bound_hash_matches "$control_dir/worker-start.json" "$worker_start_sha256_bound" || return 1
  bound_hash_matches "$control_dir/init-command.json" "$init_command_sha256_bound" || return 1
  bound_hash_matches "$control_dir/validator-command.json" "$validator_command_sha256_bound" || return 1
  bound_hash_matches "$control_dir/suite-inventory.txt" "$suite_inventory_sha256_bound" || return 1
  bound_hash_matches "$suite_dir/suite-manifest.json" "$suite_manifest_sha256_bound" || return 1
  bound_hash_matches "$suite_dir/single-baseline-manifest.json" "$single_baseline_manifest_sha256_bound" || return 1
  bound_hash_matches "$suite_dir/source.tar.gz" "$source_archive_sha256_bound" || return 1
  bound_hash_matches "$suite_dir/source.tar.gz.sha256" "$source_archive_checksum_sha256_bound" || return 1
  bound_hash_matches "$suite_dir/cache-manifest.json" "$cache_manifest_sha256_bound" || return 1
  bound_hash_matches "$suite_dir/cache-manifest.json.sha256" "$cache_manifest_checksum_sha256_bound" || return 1
  bound_hash_matches "$suite_dir/nvidia-smi.txt" "$nvidia_smi_sha256_bound" || return 1
  bound_hash_matches "$suite_dir/runtime-attestation.json" "$runtime_attestation_sha256_bound"
}

write_terminal() {
  local status="$1"
  local exit_code="$2"
  local init_pid_json="null"
  local init_exit_json="null"
  local validator_exit_json="null"
  local ended_utc ended_unix terminal_json timestamp_pair
  ((terminal_written == 0)) || return 0
  if ! verify_bound_hashes; then
    status="failed"
    exit_code=65
    failure_reason="bound init-baseline evidence drifted before terminal"
  fi
  [[ "$init_pid" =~ ^[0-9]+$ ]] && init_pid_json="$init_pid"
  [[ "$init_exit_code" =~ ^[0-9]+$ ]] && init_exit_json="$init_exit_code"
  [[ "$validator_exit_code" =~ ^[0-9]+$ ]] && validator_exit_json="$validator_exit_code"
  timestamp_pair="$(capture_timestamp 2>/dev/null || printf 'unknown 0')"
  read -r ended_utc ended_unix <<< "$timestamp_pair"
  terminal_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "kind": "durable-init-baseline",\n  "status": "%s",\n  "exit_code": %s,\n  "reason": "%s",\n  "formal_source_sha": "%s",\n  "formal_source_tree": "%s",\n  "worker_pid": %s,\n  "worker_sid": %s,\n  "worker_tty": "%s",\n  "init_pid": %s,\n  "init_exit_code": %s,\n  "validator_exit_code": %s,\n  "script_sha256": "%s",\n  "run_sh_sha256": "%s",\n  "preflight_verifier_sha256": %s,\n  "preflight_terminal_sha256": %s,\n  "worker_started_utc": "%s",\n  "worker_started_unix": %s,\n  "ended_utc": "%s",\n  "ended_unix": %s,\n  "attempt_sha256": %s,\n  "start_sha256": %s,\n  "worker_claim_sha256": %s,\n  "worker_start_sha256": %s,\n  "init_command_sha256": %s,\n  "envelope_log_sha256": %s,\n  "init_stdout_sha256": %s,\n  "init_stderr_sha256": %s,\n  "validator_command_sha256": %s,\n  "validator_stdout_sha256": %s,\n  "validator_stderr_sha256": %s,\n  "suite_inventory_sha256": %s,\n  "suite_manifest_sha256": %s,\n  "single_baseline_manifest_sha256": %s,\n  "source_archive_sha256": %s,\n  "source_archive_checksum_sha256": %s,\n  "cache_manifest_sha256": %s,\n  "cache_manifest_checksum_sha256": %s,\n  "nvidia_smi_sha256": %s,\n  "runtime_attestation_sha256": %s\n}' \
    "$run_id" "$status" "$exit_code" "$failure_reason" "$FORMAL_SOURCE_SHA" "$FORMAL_SOURCE_TREE" \
    "$$" "$worker_sid" "$worker_tty" "$init_pid_json" "$init_exit_json" "$validator_exit_json" \
    "$script_actual_sha256" "$run_sh_sha256" "$(hash_or_null "$preflight_verifier")" "$(hash_or_null "$preflight_terminal")" \
    "$worker_started_utc" "$worker_started_unix" "$ended_utc" "$ended_unix" \
    "$(hash_or_null "$control_dir/attempt.json")" "$(hash_or_null "$control_dir/start.json")" \
    "$(hash_or_null "$control_dir/worker-claim.json")" \
    "$(hash_or_null "$control_dir/worker-start.json")" "$(hash_or_null "$control_dir/init-command.json")" \
    "$(hash_or_null "$control_dir/envelope.log")" "$(hash_or_null "$control_dir/init.stdout.log")" \
    "$(hash_or_null "$control_dir/init.stderr.log")" "$(hash_or_null "$control_dir/validator-command.json")" \
    "$(hash_or_null "$control_dir/validator.stdout.log")" "$(hash_or_null "$control_dir/validator.stderr.log")" \
    "$(hash_or_null "$control_dir/suite-inventory.txt")" \
    "$(hash_or_null "$suite_dir/suite-manifest.json")" "$(hash_or_null "$suite_dir/single-baseline-manifest.json")" \
    "$(hash_or_null "$suite_dir/source.tar.gz")" "$(hash_or_null "$suite_dir/source.tar.gz.sha256")" \
    "$(hash_or_null "$suite_dir/cache-manifest.json")" "$(hash_or_null "$suite_dir/cache-manifest.json.sha256")" \
    "$(hash_or_null "$suite_dir/nvidia-smi.txt")" "$(hash_or_null "$suite_dir/runtime-attestation.json")")" || return 1
  write_atomic "$control_dir/terminal.json" "$terminal_json" || return 1
  terminal_written=1
}

on_worker_exit() {
  local worker_exit=$?
  trap - EXIT
  if ((terminal_written == 0)); then
    ((worker_exit != 0)) || worker_exit=70
    write_terminal "failed" "$worker_exit" || true
  fi
  exit "$worker_exit"
}

on_worker_signal() {
  local signal_exit="$1"
  local signal_name="$2"
  local signal_identity=""
  local signal_ppid=""
  local signal_pgrp=""
  local signal_sid=""
  local signal_tty_nr=""
  local signal_start_ticks=""
  local group_is_bound=0
  failure_reason="worker received $signal_name"
  if [[ "$init_pid" =~ ^[0-9]+$ ]] && process_group_exists "$init_pid"; then
    signal_identity="$(proc_stat_identity "$init_pid" 2>/dev/null)" || signal_identity=""
    if [[ -n "$signal_identity" ]]; then
      read -r signal_ppid signal_pgrp signal_sid signal_tty_nr signal_start_ticks <<< "$signal_identity"
      if ((init_group_bound == 1)) \
          && [[ "$init_start_ticks" =~ ^[0-9]+$ \
            && "$signal_ppid" == "$$" \
            && "$signal_pgrp" == "$init_pid" \
            && "$signal_sid" == "$init_pid" \
            && "$signal_start_ticks" == "$init_start_ticks" ]]; then
        group_is_bound=1
        terminate_bound_process_group "$init_pid" "$init_start_ticks" || true
      else
        failure_reason="worker received $signal_name; init process-group identity mismatch"
      fi
    elif ((init_group_bound == 1)) && [[ "$init_start_ticks" =~ ^[0-9]+$ ]]; then
      # A reaped group leader can leave descendants in its already-bound PGID.
      group_is_bound=1
      terminate_remaining_process_group "$init_pid" || true
    fi
    if ((group_is_bound == 1)) && process_group_exists "$init_pid"; then
      terminate_remaining_process_group "$init_pid" || true
    fi
  fi
  exit "$signal_exit"
}

trap on_worker_exit EXIT
trap 'on_worker_signal 129 SIGHUP' HUP
trap 'on_worker_signal 130 SIGINT' INT
trap 'on_worker_signal 143 SIGTERM' TERM

snapshot="$control_dir/script-snapshot.sh"
require_real_directory "$REPO_ROOT" "formal repository"
require_real_directory "$REPO_ROOT/runs" "formal runs directory"
require_real_directory "$run_artifact" "run artifact directory"
require_real_directory "$preflight_control" "completed preflight control directory"
require_real_directory "$control_dir" "init-baseline control directory"
require_real_file "$0" "init-baseline snapshot"
[[ "$0" == "$snapshot" ]] || { failure_reason="worker is not the canonical init-baseline snapshot"; exit 65; }
script_actual_sha256="$(sha256_file "$0")" || { failure_reason="cannot hash init-baseline snapshot"; exit 65; }
[[ "$script_actual_sha256" == "$script_sha256" ]] || { failure_reason="init-baseline worker SHA256 drifted"; exit 65; }
require_real_file "$REPO_ROOT/run.sh" "formal run script"
require_real_file "$preflight_terminal" "completed preflight terminal"
[[ "$(sha256_file "$preflight_terminal")" == "$preflight_terminal_sha256" ]] || { failure_reason="completed preflight terminal SHA256 drifted before worker"; exit 65; }
preflight_terminal_sha256_bound="$preflight_terminal_sha256"
preflight_verifier_sha256_bound="$PREFLIGHT_V2_SHA256"
run_sh_sha256="$(sha256_file "$REPO_ROOT/run.sh")" || { failure_reason="cannot hash formal run script"; exit 65; }
[[ -f "$control_dir/attempt.json" && ! -L "$control_dir/attempt.json" ]] || { failure_reason="init-baseline attempt record is missing"; exit 65; }
attempt_sha256_bound="$(sha256_file "$control_dir/attempt.json")" || { failure_reason="cannot bind init-baseline attempt record"; exit 65; }
timestamp_pair="$(capture_timestamp)" || { failure_reason="cannot capture canonical worker-claim timestamp"; exit 65; }
read -r worker_claimed_utc worker_claimed_unix <<< "$timestamp_pair"
worker_claim_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "role": "durable-init-baseline-worker-claim",\n  "pid": %s,\n  "ppid": %s,\n  "script_sha256": "%s",\n  "attempt_sha256": "%s",\n  "claimed_utc": "%s",\n  "claimed_unix": %s\n}' \
  "$run_id" "$$" "$PPID" "$script_sha256" "$attempt_sha256_bound" \
  "$worker_claimed_utc" "$worker_claimed_unix")" || { failure_reason="cannot build init-baseline worker claim"; exit 65; }
write_atomic "$control_dir/worker-claim.json" "$worker_claim_json" || { failure_reason="cannot persist init-baseline worker claim"; exit 74; }
worker_claim_sha256_bound="$(sha256_file "$control_dir/worker-claim.json")" || { failure_reason="cannot bind init-baseline worker claim"; exit 74; }
verify_preflight_v2 || { failure_reason="canonical preflight-v2 evidence verification failed before init worker"; exit 65; }
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
  exit 65
fi
start_sha256_bound="$(sha256_file "$control_dir/start.json")" || { failure_reason="cannot bind init-baseline start record"; exit 65; }
resolved_bash_path="$(command -v bash)" || { failure_reason="bash is unavailable to worker"; exit 65; }
resolved_bash_path="$(realpath -e -- "$resolved_bash_path")" || { failure_reason="cannot resolve worker bash"; exit 65; }
[[ "$bash_path" == "$resolved_bash_path" && -f "$bash_path" && -x "$bash_path" ]] || { failure_reason="worker bash path drifted"; exit 65; }
[[ "$(sha256_file "$preflight_terminal")" == "$preflight_terminal_sha256_bound" ]] || { failure_reason="completed preflight terminal SHA256 drifted before init"; exit 65; }
verify_preflight_v2 || { failure_reason="canonical preflight-v2 evidence verification failed immediately before init"; exit 65; }
setsid_path="$(command -v setsid)" || { failure_reason="setsid is unavailable to worker"; exit 65; }
setsid_path="$(realpath -e -- "$setsid_path")" || { failure_reason="cannot resolve worker setsid"; exit 65; }
[[ -f "$setsid_path" && -x "$setsid_path" ]] || { failure_reason="resolved worker setsid is not executable"; exit 65; }
verify_formal_source || { failure_reason="worker formal source gate failed"; exit 65; }
verify_preinit_absence || { failure_reason="worker fresh suite or downstream formal path gate failed"; exit 65; }

timestamp_pair="$(capture_timestamp)" || { failure_reason="cannot capture canonical worker-start timestamp"; exit 65; }
read -r worker_started_utc worker_started_unix <<< "$timestamp_pair"
worker_identity="$(proc_stat_identity "$$")" || { failure_reason="cannot read worker /proc identity"; exit 65; }
read -r worker_proc_ppid worker_pgrp worker_sid worker_tty_nr worker_start_ticks <<< "$worker_identity"
worker_tty="$(ps -o tty= -p "$$" | tr -d ' ')" || { failure_reason="cannot read worker tty"; exit 65; }
worker_exe="$(readlink -e -- "/proc/$$/exe")" || { failure_reason="cannot read worker executable"; exit 65; }
worker_cwd="$(readlink -e -- "/proc/$$/cwd")" || { failure_reason="cannot read worker cwd"; exit 65; }
worker_cmdline_text="$(proc_cmdline_text "$$")" || { failure_reason="cannot read worker command line"; exit 65; }
worker_cmdline_hex="$(proc_cmdline_hex "$$")" || { failure_reason="cannot encode worker command line"; exit 65; }
worker_cmdline_sha256="$(sha256sum "/proc/$$/cmdline" | awk '{print $1}')" || { failure_reason="cannot hash worker command line"; exit 65; }
expected_worker_cmdline_hex="$(printf '%s\0' "$bash_path" "$snapshot" worker \
  --script-sha256 "$script_sha256" \
  --suite-dir "$suite_dir" \
  --control-dir "$control_dir" \
  --bash-path "$bash_path" \
  --preflight-terminal-sha256 "$preflight_terminal_sha256" | od -An -v -tx1 | tr -d ' \n')"
supervisor_pid="$(sed -n 's/^  "envelope_supervisor_pid": \([0-9][0-9]*\),$/\1/p' "$control_dir/start.json")" || { failure_reason="cannot read envelope supervisor PID"; exit 65; }
[[ "$supervisor_pid" =~ ^[0-9]+$ ]] || { failure_reason="start record envelope supervisor PID is invalid"; exit 65; }
[[ "$worker_proc_ppid" == "$PPID" && "$worker_proc_ppid" == "$supervisor_pid" ]] || { failure_reason="worker parent differs from start-record supervisor"; exit 65; }
[[ "$worker_pgrp" == "$$" && "$worker_sid" == "$$" ]] || { failure_reason="init-baseline worker is not a process-group and session leader"; exit 65; }
[[ "$worker_tty_nr" == "0" && "$worker_tty" == "?" ]] || { failure_reason="init-baseline worker retained a controlling terminal"; exit 65; }
[[ "$worker_exe" == "$bash_path" ]] || { failure_reason="worker executable differs from frozen bash"; exit 65; }
[[ "$worker_cwd" == "$REPO_ROOT" ]] || { failure_reason="init-baseline worker cwd drifted"; exit 65; }
[[ "$worker_cmdline_hex" == "$expected_worker_cmdline_hex" ]] || { failure_reason="worker command line differs from start record"; exit 65; }
[[ "$worker_cmdline_text" =~ ^[A-Za-z0-9_./:+\ =-]*$ ]] || { failure_reason="worker command line cannot be represented safely"; exit 65; }
hostname_value="$(hostname)" || { failure_reason="cannot read hostname"; exit 65; }
boot_id="$(tr '[:upper:]' '[:lower:]' < /proc/sys/kernel/random/boot_id)" || { failure_reason="cannot read boot id"; exit 65; }
[[ "$hostname_value" =~ ^[A-Za-z0-9._-]+$ ]] || { failure_reason="hostname cannot be represented safely"; exit 65; }
[[ "$boot_id" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || { failure_reason="boot id is invalid"; exit 65; }
  worker_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "role": "durable-init-baseline-worker",\n  "pid": %s,\n  "proc_ppid": %s,\n  "proc_pgrp": %s,\n  "proc_sid": %s,\n  "proc_tty_nr": %s,\n  "proc_start_ticks": %s,\n  "proc_exe": "%s",\n  "proc_cmdline_text": "%s",\n  "proc_cmdline_hex": "%s",\n  "proc_cmdline_sha256": "%s",\n  "proc_cwd": "%s",\n  "envelope_supervisor_pid": %s,\n  "tty": "%s",\n  "hostname": "%s",\n  "boot_id": "%s",\n  "started_utc": "%s",\n  "started_unix": %s,\n  "preflight_verifier_sha256": "%s",\n  "preflight_terminal_sha256": "%s",\n  "attempt_sha256": "%s",\n  "start_sha256": "%s",\n  "worker_claim_sha256": "%s"\n}' \
  "$run_id" "$$" "$worker_proc_ppid" "$worker_pgrp" "$worker_sid" "$worker_tty_nr" "$worker_start_ticks" \
  "$worker_exe" "$worker_cmdline_text" "$worker_cmdline_hex" "$worker_cmdline_sha256" "$worker_cwd" \
  "$supervisor_pid" "$worker_tty" "$hostname_value" "$boot_id" \
    "$worker_started_utc" "$worker_started_unix" "$PREFLIGHT_V2_SHA256" "$preflight_terminal_sha256_bound" \
  "$attempt_sha256_bound" "$start_sha256_bound" "$worker_claim_sha256_bound")" || { failure_reason="cannot build worker start record"; exit 65; }
write_atomic "$control_dir/worker-start.json" "$worker_json" || { failure_reason="cannot persist worker start record"; exit 65; }
worker_start_sha256_bound="$(sha256_file "$control_dir/worker-start.json")" || { failure_reason="cannot bind worker start record"; exit 65; }

export AISTATION_TARGET="GPU2"
export ZOOLOGY_EXPECTED_GIT_SHA="$FORMAL_SOURCE_SHA"
: > "$control_dir/init.stdout.log" || { failure_reason="cannot create init stdout log"; exit 74; }
: > "$control_dir/init.stderr.log" || { failure_reason="cannot create init stderr log"; exit 74; }
chmod 600 -- "$control_dir/init.stdout.log" "$control_dir/init.stderr.log" || { failure_reason="cannot restrict init logs"; exit 74; }
expected_init_cmdline_hex="$(printf '%s\0' "$bash_path" "./run.sh" "init-baseline" "$suite_dir" | od -An -v -tx1 | tr -d ' \n')"
timestamp_pair="$(capture_timestamp)" || { failure_reason="cannot capture canonical init-command timestamp"; exit 74; }
read -r init_started_utc init_started_unix <<< "$timestamp_pair"
"$setsid_path" "$bash_path" ./run.sh init-baseline "$suite_dir" \
  >"$control_dir/init.stdout.log" 2>"$control_dir/init.stderr.log" &
init_pid=$!
[[ "$init_pid" =~ ^[0-9]+$ ]] || { failure_reason="init command did not return a PID"; exit 65; }

init_identity_bound=0
for _ in $(seq 1 100); do
  candidate_identity="$(proc_stat_identity "$init_pid" 2>/dev/null)" || { sleep 0.02; continue; }
  read -r candidate_ppid candidate_pgrp candidate_sid candidate_tty_nr candidate_start_ticks <<< "$candidate_identity"
  if [[ "$candidate_ppid" == "$$" && "$candidate_pgrp" == "$init_pid" && "$candidate_sid" == "$init_pid" ]]; then
    init_start_ticks="$candidate_start_ticks"
  fi
  candidate_exe="$(readlink -e -- "/proc/$init_pid/exe" 2>/dev/null)" || { sleep 0.02; continue; }
  candidate_cwd="$(readlink -e -- "/proc/$init_pid/cwd" 2>/dev/null)" || { sleep 0.02; continue; }
  candidate_cmdline_text="$(proc_cmdline_text "$init_pid" 2>/dev/null)" || { sleep 0.02; continue; }
  candidate_cmdline_hex="$(proc_cmdline_hex "$init_pid" 2>/dev/null)" || { sleep 0.02; continue; }
  candidate_cmdline_sha256="$(sha256sum "/proc/$init_pid/cmdline" 2>/dev/null | awk '{print $1}')" || { sleep 0.02; continue; }
  sleep 0.02
  second_identity="$(proc_stat_identity "$init_pid" 2>/dev/null)" || continue
  read -r second_ppid second_pgrp second_sid second_tty_nr second_start_ticks <<< "$second_identity"
  second_exe="$(readlink -e -- "/proc/$init_pid/exe" 2>/dev/null)" || continue
  second_cwd="$(readlink -e -- "/proc/$init_pid/cwd" 2>/dev/null)" || continue
  second_cmdline_hex="$(proc_cmdline_hex "$init_pid" 2>/dev/null)" || continue
  second_cmdline_sha256="$(sha256sum "/proc/$init_pid/cmdline" 2>/dev/null | awk '{print $1}')" || continue
  if [[ "$candidate_ppid" == "$$" \
        && "$candidate_ppid" == "$second_ppid" \
        && "$candidate_pgrp" == "$init_pid" \
        && "$candidate_pgrp" == "$second_pgrp" \
        && "$candidate_sid" == "$init_pid" \
        && "$candidate_sid" == "$second_sid" \
        && "$candidate_tty_nr" == "0" \
        && "$candidate_tty_nr" == "$second_tty_nr" \
        && "$candidate_start_ticks" == "$second_start_ticks" \
        && "$candidate_exe" == "$bash_path" \
        && "$candidate_exe" == "$second_exe" \
        && "$candidate_cwd" == "$REPO_ROOT" \
        && "$candidate_cwd" == "$second_cwd" \
        && "$candidate_cmdline_hex" == "$expected_init_cmdline_hex" \
        && "$candidate_cmdline_hex" == "$second_cmdline_hex" \
        && "$candidate_cmdline_sha256" == "$second_cmdline_sha256" ]]; then
    init_ppid="$candidate_ppid"
    init_pgrp="$candidate_pgrp"
    init_sid="$candidate_sid"
    init_tty_nr="$candidate_tty_nr"
    init_start_ticks="$candidate_start_ticks"
    init_exe="$candidate_exe"
    init_cwd="$candidate_cwd"
    init_cmdline_text="$candidate_cmdline_text"
    init_cmdline_hex="$candidate_cmdline_hex"
    init_cmdline_sha256="$candidate_cmdline_sha256"
    init_identity_bound=1
    init_group_bound=1
    break
  fi
done
if ((init_identity_bound == 0)); then
  failure_reason="cannot bind exact stable init-baseline /proc identity"
  initial_identity="$(proc_stat_identity "$init_pid" 2>/dev/null)" || initial_identity=""
  if [[ -n "$initial_identity" ]]; then
    read -r initial_ppid initial_pgrp initial_sid _ init_start_ticks <<< "$initial_identity"
    if [[ "$initial_ppid" == "$$" && "$initial_pgrp" == "$init_pid" && "$initial_sid" == "$init_pid" ]]; then
      terminate_bound_process_group "$init_pid" "$init_start_ticks" || true
    else
      wait_without_signal "$init_pid"
    fi
  else
    wait_without_signal "$init_pid"
  fi
  exit 65
fi
[[ "$init_cmdline_text" =~ ^[A-Za-z0-9_./:+\ =-]*$ ]] || { failure_reason="init command line cannot be represented safely"; terminate_bound_process_group "$init_pid" "$init_start_ticks" || true; exit 65; }
init_command_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "pid": %s,\n  "proc_ppid": %s,\n  "proc_pgrp": %s,\n  "proc_sid": %s,\n  "proc_tty_nr": %s,\n  "proc_start_ticks": %s,\n  "proc_exe": "%s",\n  "proc_cwd": "%s",\n  "proc_cmdline_text": "%s",\n  "proc_cmdline_hex": "%s",\n  "proc_cmdline_sha256": "%s",\n  "spawn_command": ["%s", "%s", "./run.sh", "init-baseline", "%s"],\n  "command": ["%s", "./run.sh", "init-baseline", "%s"],\n  "started_utc": "%s",\n  "started_unix": %s\n}' \
  "$run_id" "$init_pid" "$init_ppid" "$init_pgrp" "$init_sid" "$init_tty_nr" "$init_start_ticks" "$init_exe" "$init_cwd" \
  "$init_cmdline_text" "$init_cmdline_hex" "$init_cmdline_sha256" "$setsid_path" "$bash_path" "$suite_dir" "$bash_path" "$suite_dir" \
  "$init_started_utc" "$init_started_unix")" || { failure_reason="cannot build init command record"; terminate_bound_process_group "$init_pid" "$init_start_ticks" || true; exit 65; }
write_atomic "$control_dir/init-command.json" "$init_command_json" || { failure_reason="cannot persist init command record"; terminate_bound_process_group "$init_pid" "$init_start_ticks" || true; exit 74; }
init_command_sha256_bound="$(sha256_file "$control_dir/init-command.json")" || { failure_reason="cannot bind init command record"; terminate_bound_process_group "$init_pid" "$init_start_ticks" || true; exit 74; }

failure_reason="init-baseline command returned nonzero"
wait "$init_pid"
init_exit_code=$?
if process_group_exists "$init_pid"; then
  terminate_remaining_process_group "$init_pid" || { failure_reason="init-baseline process group survived cleanup"; exit 70; }
  if ((init_exit_code == 0)); then
    failure_reason="init-baseline left descendant processes after leader exit"
    exit 70
  fi
fi
sync "$control_dir/init.stdout.log" "$control_dir/init.stderr.log" || { failure_reason="cannot sync init logs"; exit 74; }
if ((init_exit_code != 0)); then
  overall_exit="$init_exit_code"
  write_terminal "failed" "$overall_exit" || exit 74
  exit "$overall_exit"
fi

verify_formal_source || { failure_reason="formal source drifted after init-baseline"; exit 65; }
failure_reason="initialized suite structure validation failed"
require_real_directory "$suite_dir" "initialized single-baseline suite"
[[ ! -e "$bundle_dir" && ! -L "$bundle_dir" ]] || { failure_reason="controller bundle exists after init-baseline"; exit 65; }
[[ ! -e "$formal_launch_control" && ! -L "$formal_launch_control" ]] || { failure_reason="formal launch control exists after init-baseline"; exit 65; }
require_real_file "$suite_dir/suite-manifest.json" "suite manifest"
require_real_file "$suite_dir/single-baseline-manifest.json" "single-baseline manifest"
require_real_file "$suite_dir/source.tar.gz" "source archive"
require_real_file "$suite_dir/source.tar.gz.sha256" "source archive checksum"
require_real_file "$suite_dir/cache-manifest.json" "cache manifest"
require_real_file "$suite_dir/cache-manifest.json.sha256" "cache manifest checksum"
require_real_file "$suite_dir/nvidia-smi.txt" "NVIDIA inventory"
require_real_file "$suite_dir/runtime-attestation.json" "runtime attestation"
verify_fresh_suite_inventory || { failure_reason="initialized suite inventory is not exactly fresh"; exit 65; }
suite_inventory="$(fresh_suite_inventory)" || { failure_reason="cannot capture fresh suite inventory"; exit 74; }
write_atomic "$control_dir/suite-inventory.txt" "$suite_inventory" || { failure_reason="cannot persist fresh suite inventory"; exit 74; }
suite_inventory_sha256_bound="$(sha256_file "$control_dir/suite-inventory.txt")" || { failure_reason="cannot bind fresh suite inventory"; exit 74; }
suite_manifest_sha256_bound="$(sha256_file "$suite_dir/suite-manifest.json")" || { failure_reason="cannot bind suite manifest"; exit 74; }
single_baseline_manifest_sha256_bound="$(sha256_file "$suite_dir/single-baseline-manifest.json")" || { failure_reason="cannot bind single-baseline manifest"; exit 74; }
source_archive_sha256_bound="$(sha256_file "$suite_dir/source.tar.gz")" || { failure_reason="cannot bind source archive"; exit 74; }
source_archive_checksum_sha256_bound="$(sha256_file "$suite_dir/source.tar.gz.sha256")" || { failure_reason="cannot bind source archive checksum"; exit 74; }
cache_manifest_sha256_bound="$(sha256_file "$suite_dir/cache-manifest.json")" || { failure_reason="cannot bind cache manifest"; exit 74; }
cache_manifest_checksum_sha256_bound="$(sha256_file "$suite_dir/cache-manifest.json.sha256")" || { failure_reason="cannot bind cache manifest checksum"; exit 74; }
nvidia_smi_sha256_bound="$(sha256_file "$suite_dir/nvidia-smi.txt")" || { failure_reason="cannot bind NVIDIA inventory"; exit 74; }
runtime_attestation_sha256_bound="$(sha256_file "$suite_dir/runtime-attestation.json")" || { failure_reason="cannot bind runtime attestation"; exit 74; }

: > "$control_dir/validator.stdout.log" || { failure_reason="cannot create validator stdout log"; exit 74; }
: > "$control_dir/validator.stderr.log" || { failure_reason="cannot create validator stderr log"; exit 74; }
chmod 600 -- "$control_dir/validator.stdout.log" "$control_dir/validator.stderr.log" || { failure_reason="cannot restrict validator logs"; exit 74; }
timestamp_pair="$(capture_timestamp)" || { failure_reason="cannot capture canonical validator timestamp"; exit 74; }
read -r validator_started_utc validator_started_unix <<< "$timestamp_pair"
./.venv/bin/python -m repro.single_baseline selected-index --suite-dir "$suite_dir" \
  >"$control_dir/validator.stdout.log" 2>"$control_dir/validator.stderr.log"
validator_exit_code=$?
sync "$control_dir/validator.stdout.log" "$control_dir/validator.stderr.log" || { failure_reason="cannot sync validator logs"; exit 74; }
validator_stdout_sha256="$(sha256_file "$control_dir/validator.stdout.log")" || { failure_reason="cannot hash validator stdout"; exit 74; }
validator_stderr_sha256="$(sha256_file "$control_dir/validator.stderr.log")" || { failure_reason="cannot hash validator stderr"; exit 74; }
validator_stdout_hex="$(od -An -v -tx1 "$control_dir/validator.stdout.log" | tr -d ' \n')"
validator_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "command": ["./.venv/bin/python", "-m", "repro.single_baseline", "selected-index", "--suite-dir", "%s"],\n  "exit_code": %s,\n  "stdout_sha256": "%s",\n  "stderr_sha256": "%s",\n  "stdout_hex": "%s",\n  "started_utc": "%s",\n  "started_unix": %s\n}' \
  "$run_id" "$suite_dir" "$validator_exit_code" "$validator_stdout_sha256" "$validator_stderr_sha256" \
  "$validator_stdout_hex" "$validator_started_utc" "$validator_started_unix")" || { failure_reason="cannot build validator command record"; exit 74; }
write_atomic "$control_dir/validator-command.json" "$validator_json" || { failure_reason="cannot persist validator command record"; exit 74; }
validator_command_sha256_bound="$(sha256_file "$control_dir/validator-command.json")" || { failure_reason="cannot bind validator command record"; exit 74; }
if ((validator_exit_code != 0)); then
  failure_reason="single-baseline validator returned nonzero"
  overall_exit="$validator_exit_code"
  write_terminal "failed" "$overall_exit" || exit 74
  exit "$overall_exit"
fi
if [[ "$validator_stdout_hex" != "350a" || -s "$control_dir/validator.stderr.log" ]]; then
  failure_reason="single-baseline validator output was not exact selected index 5"
  exit 65
fi
if [[ "$(sha256_file "$control_dir/attempt.json")" != "$attempt_sha256_bound" \
      || "$(sha256_file "$control_dir/start.json")" != "$start_sha256_bound" \
      || "$(sha256_file "$control_dir/worker-claim.json")" != "$worker_claim_sha256_bound" \
      || "$(sha256_file "$control_dir/worker-start.json")" != "$worker_start_sha256_bound" \
      || "$(sha256_file "$control_dir/init-command.json")" != "$init_command_sha256_bound" \
      || "$(sha256_file "$control_dir/validator-command.json")" != "$validator_command_sha256_bound" \
      || "$(sha256_file "$control_dir/suite-inventory.txt")" != "$suite_inventory_sha256_bound" \
      || "$(sha256_file "$preflight_terminal")" != "$preflight_terminal_sha256_bound" \
      || "$(sha256_file "$suite_dir/suite-manifest.json")" != "$suite_manifest_sha256_bound" \
      || "$(sha256_file "$suite_dir/single-baseline-manifest.json")" != "$single_baseline_manifest_sha256_bound" \
      || "$(sha256_file "$suite_dir/source.tar.gz")" != "$source_archive_sha256_bound" \
      || "$(sha256_file "$suite_dir/source.tar.gz.sha256")" != "$source_archive_checksum_sha256_bound" \
      || "$(sha256_file "$suite_dir/cache-manifest.json")" != "$cache_manifest_sha256_bound" \
      || "$(sha256_file "$suite_dir/cache-manifest.json.sha256")" != "$cache_manifest_checksum_sha256_bound" \
      || "$(sha256_file "$suite_dir/nvidia-smi.txt")" != "$nvidia_smi_sha256_bound" \
      || "$(sha256_file "$suite_dir/runtime-attestation.json")" != "$runtime_attestation_sha256_bound" \
      || "$(sha256_file "$REPO_ROOT/run.sh")" != "$run_sh_sha256" ]]; then
  failure_reason="bound init-baseline evidence drifted"
  exit 65
fi
verify_fresh_suite_inventory || { failure_reason="fresh suite inventory drifted before completion"; exit 65; }
[[ ! -e "$bundle_dir" && ! -L "$bundle_dir" ]] || { failure_reason="controller bundle appeared before completion"; exit 65; }
[[ ! -e "$formal_launch_control" && ! -L "$formal_launch_control" ]] || { failure_reason="formal launch control appeared before completion"; exit 65; }
verify_preflight_v2 || { failure_reason="canonical preflight-v2 evidence verification failed before init completion"; exit 65; }
verify_formal_source || { failure_reason="formal source drifted before completion"; exit 65; }
failure_reason="none"
overall_exit=0
write_terminal "completed" "$overall_exit" || exit 74
exit 0
