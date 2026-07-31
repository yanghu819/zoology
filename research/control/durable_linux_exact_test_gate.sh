#!/usr/bin/env bash

set -u
set -o pipefail

REPO_ROOT="/huyang2/zoology"
SCRIPT_NAME="durable_linux_exact_test_gate.sh"
GATE_NAME="linux_exact_test_gate.py"
CONTROL_NAME="linux-exact-test-envelope"
GATE_CONTROL_NAME="linux-exact-test-gate"
EXPECTED_TESTS=53
WORKER_CLAIM_WAIT_TENTHS=50

usage() {
  printf '%s\n' \
    "usage: $0 start|verify --run-id RUN_ID --script-sha256 SHA256 --gate-sha256 SHA256 --control-dir PATH" >&2
  exit 64
}

die() {
  printf 'durable linux exact test gate: %s\n' "$1" >&2
  exit "${2:-1}"
}

sha256_file() {
  sha256sum -- "$1" | awk '{print $1}'
}

require_real_directory() {
  local path="$1"
  local label="$2"
  [[ -d "$path" && ! -L "$path" ]] || die "$label is not a real directory: $path"
  [[ "$(realpath -e -- "$path")" == "$path" ]] || die "$label uses a symlink or path alias: $path"
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

proc_identity() {
  local pid="$1"
  local line tail cmdline_file
  local -a fields
  [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
  IFS= read -r line < "/proc/$pid/stat" || return 1
  tail="${line##*) }"
  read -r -a fields <<< "$tail"
  ((${#fields[@]} >= 20)) || return 1
  PROC_PPID="${fields[1]}"
  PROC_PGID="${fields[2]}"
  PROC_SID="${fields[3]}"
  PROC_TTY_NR="${fields[4]}"
  PROC_START_TICKS="${fields[19]}"
  for value in "$PROC_PPID" "$PROC_PGID" "$PROC_SID" "$PROC_TTY_NR" "$PROC_START_TICKS"; do
    [[ "$value" =~ ^-?[0-9]+$ ]] || return 1
  done
  PROC_EXE="$(readlink -e -- "/proc/$pid/exe")" || return 1
  PROC_CWD="$(readlink -e -- "/proc/$pid/cwd")" || return 1
  cmdline_file="/proc/$pid/cmdline"
  PROC_CMDLINE_SHA256="$(sha256_file "$cmdline_file")" || return 1
  PROC_CMDLINE_HEX="$(od -An -v -tx1 -- "$cmdline_file" | tr -d ' \n')" || return 1
  PROC_CMDLINE_TEXT="$(tr '\000' ' ' < "$cmdline_file" | sed 's/ $//')" || return 1
  [[ "$PROC_CMDLINE_HEX" =~ ^([0-9a-f][0-9a-f])+$ ]] || return 1
  [[ "$PROC_CMDLINE_TEXT" != *'"'* && "$PROC_CMDLINE_TEXT" != *'\\'* ]] || return 1
}

utc_now() {
  date -u +%Y-%m-%dT%H:%M:%SZ
}

unix_now() {
  date -u +%s
}

boot_id_now() {
  tr '[:upper:]' '[:lower:]' < /proc/sys/kernel/random/boot_id
}

mode="${1:-}"
[[ "$mode" == "start" || "$mode" == "verify" || "$mode" == "worker" ]] || usage
shift

run_id=""
script_sha256=""
gate_sha256=""
control_dir=""
while (($#)); do
  (($# >= 2)) || usage
  case "$1" in
    --run-id)
      [[ -z "$run_id" ]] || usage
      run_id="$2"
      ;;
    --script-sha256)
      [[ -z "$script_sha256" ]] || usage
      script_sha256="$2"
      ;;
    --gate-sha256)
      [[ -z "$gate_sha256" ]] || usage
      gate_sha256="$2"
      ;;
    --control-dir)
      [[ -z "$control_dir" ]] || usage
      control_dir="$2"
      ;;
    *) usage ;;
  esac
  shift 2
done

[[ "$run_id" =~ ^[a-z0-9][a-z0-9-]*$ ]] || die "run id must contain lowercase letters, digits, and hyphens"
[[ "$script_sha256" =~ ^[0-9a-f]{64}$ ]] || die "script SHA256 must be 64 lowercase hexadecimal characters"
[[ "$gate_sha256" =~ ^[0-9a-f]{64}$ ]] || die "gate SHA256 must be 64 lowercase hexadecimal characters"
[[ -f /proc/self/stat ]] || die "Linux /proc is required"

run_artifact="$REPO_ROOT/artifacts/$run_id"
launcher="$run_artifact/launcher"
source_script="$launcher/$SCRIPT_NAME"
gate_script="$launcher/$GATE_NAME"
expected_control="$run_artifact/$CONTROL_NAME"
gate_control="$run_artifact/$GATE_CONTROL_NAME"
snapshot="$expected_control/script-snapshot.sh"
python_entry="$REPO_ROOT/.venv/bin/python"
formal_suite="$REPO_ROOT/runs/$run_id"
formal_controller="$run_artifact/controller"
formal_control="$run_artifact/formal-launch-control"
preflight_control="$run_artifact/preflight-control"
init_control="$run_artifact/init-baseline-control"

[[ "$control_dir" == "$expected_control" ]] || die "control directory is not the canonical envelope path"

if [[ "$mode" == "start" ]]; then
  [[ "$0" == "$source_script" ]] || die "envelope is not the canonical launcher runtime"
  require_real_directory "$REPO_ROOT" "repository root"
  require_real_directory "$run_artifact" "run artifact"
  require_real_directory "$launcher" "launcher"
  require_real_file "$source_script" "envelope runtime"
  require_real_file "$gate_script" "Python gate runtime"
  [[ -x "$source_script" ]] || die "envelope runtime is not executable"
  [[ "$(sha256_file "$source_script")" == "$script_sha256" ]] || die "envelope SHA256 differs from the frozen value"
  [[ "$(sha256_file "$gate_script")" == "$gate_sha256" ]] || die "Python gate SHA256 differs from the frozen value"
  for forbidden in "$formal_suite" "$formal_controller" "$formal_control" \
    "$preflight_control" "$init_control" "$gate_control" "$control_dir"; do
    [[ ! -e "$forbidden" && ! -L "$forbidden" ]] || die "one-shot path already exists: $forbidden"
  done

  try_python_target="$(realpath -e -- "$python_entry")" || die "project Python is missing"
  [[ -f "$try_python_target" && -x "$try_python_target" ]] || die "project Python target is not executable"
  nohup_path="$(command -v nohup)" || die "nohup is unavailable"
  setsid_path="$(command -v setsid)" || die "setsid is unavailable"
  bash_path="$(command -v bash)" || die "bash is unavailable"
  nohup_path="$(realpath -e -- "$nohup_path")" || die "cannot resolve nohup"
  setsid_path="$(realpath -e -- "$setsid_path")" || die "cannot resolve setsid"
  bash_path="$(realpath -e -- "$bash_path")" || die "cannot resolve bash"

  mkdir -- "$control_dir" || die "envelope attempt is already consumed"
  chmod 700 -- "$control_dir" || die "cannot restrict envelope control directory"
  require_real_directory "$control_dir" "envelope control directory"
  (
    umask 077
    cp -- "$source_script" "$snapshot"
  ) || die "cannot snapshot envelope"
  chmod 500 -- "$snapshot" || die "cannot make envelope snapshot executable"
  [[ "$(sha256_file "$snapshot")" == "$script_sha256" ]] || die "envelope snapshot SHA256 drifted"

  started_utc="$(utc_now)" || die "cannot read start UTC"
  started_unix="$(unix_now)" || die "cannot read start Unix time"
  hostname_value="$(hostname)" || die "cannot read hostname"
  boot_id="$(boot_id_now)" || die "cannot read boot id"
  [[ "$hostname_value" =~ ^[A-Za-z0-9._-]+$ ]] || die "hostname cannot be represented safely"
  [[ "$boot_id" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || die "boot id is invalid"
  attempt_json="$(printf '{\n  "schema_version": 1,\n  "kind": "durable-linux-exact-test-gate",\n  "run_id": "%s",\n  "control_dir": "%s",\n  "gate_control_dir": "%s",\n  "source_script": "%s",\n  "gate_script": "%s",\n  "snapshot": "%s",\n  "script_sha256": "%s",\n  "gate_sha256": "%s",\n  "starter_pid": %s,\n  "started_utc": "%s",\n  "started_unix": %s,\n  "hostname": "%s",\n  "boot_id": "%s"\n}' \
    "$run_id" "$control_dir" "$gate_control" "$source_script" "$gate_script" "$snapshot" \
    "$script_sha256" "$gate_sha256" "$$" "$started_utc" "$started_unix" "$hostname_value" "$boot_id")" || die "cannot build attempt record"
  write_atomic "$control_dir/attempt.json" "$attempt_json" || die "cannot persist attempt record"
  : > "$control_dir/envelope.log" || die "cannot create envelope log"
  chmod 600 -- "$control_dir/envelope.log" || die "cannot restrict envelope log"

  cd "$REPO_ROOT" || die "cannot enter repository root"
  "$nohup_path" "$setsid_path" --fork --wait "$bash_path" "$snapshot" worker \
    --run-id "$run_id" \
    --script-sha256 "$script_sha256" \
    --gate-sha256 "$gate_sha256" \
    --control-dir "$control_dir" \
    </dev/null >"$control_dir/envelope.log" 2>&1 &
  supervisor_pid=$!
  [[ "$supervisor_pid" =~ ^[1-9][0-9]*$ ]] || die "nohup did not return a supervisor PID"

  claim_ready=0
  for ((index = 0; index < WORKER_CLAIM_WAIT_TENTHS; index++)); do
    if [[ -f "$control_dir/worker-claim.json" && ! -L "$control_dir/worker-claim.json" ]]; then
      claim_ready=1
      break
    fi
    kill -0 "$supervisor_pid" 2>/dev/null || break
    sleep 0.1
  done
  [[ "$claim_ready" == 1 ]] || die "detached worker did not claim the attempt within five seconds"
  proc_identity "$supervisor_pid" || die "cannot bind detached supervisor identity"
  supervisor_ppid="$PROC_PPID"
  supervisor_pgid="$PROC_PGID"
  supervisor_sid="$PROC_SID"
  supervisor_tty_nr="$PROC_TTY_NR"
  supervisor_start_ticks="$PROC_START_TICKS"
  supervisor_exe="$PROC_EXE"
  supervisor_cwd="$PROC_CWD"
  supervisor_cmdline_sha256="$PROC_CMDLINE_SHA256"
  supervisor_cmdline_hex="$PROC_CMDLINE_HEX"
  supervisor_cmdline_text="$PROC_CMDLINE_TEXT"
  [[ "$supervisor_tty_nr" == 0 ]] || die "detached supervisor retained a controlling terminal"

  recorded_utc="$(utc_now)" || die "cannot read start-record UTC"
  recorded_unix="$(unix_now)" || die "cannot read start-record Unix time"
  start_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "script_sha256": "%s",\n  "gate_sha256": "%s",\n  "supervisor_pid": %s,\n  "supervisor_ppid": %s,\n  "supervisor_pgid": %s,\n  "supervisor_sid": %s,\n  "supervisor_tty": "none",\n  "supervisor_tty_nr": %s,\n  "supervisor_start_ticks": %s,\n  "supervisor_exe": "%s",\n  "supervisor_cwd": "%s",\n  "supervisor_cmdline_text": "%s",\n  "supervisor_cmdline_hex": "%s",\n  "supervisor_cmdline_sha256": "%s",\n  "nohup_path": "%s",\n  "setsid_path": "%s",\n  "bash_path": "%s",\n  "python_entry": "%s",\n  "python_target": "%s",\n  "stdin": "/dev/null",\n  "envelope_log": "%s",\n  "attempt_sha256": "%s",\n  "worker_claim_sha256": "%s",\n  "recorded_utc": "%s",\n  "recorded_unix": %s\n}' \
    "$run_id" "$script_sha256" "$gate_sha256" "$supervisor_pid" "$supervisor_ppid" \
    "$supervisor_pgid" "$supervisor_sid" "$supervisor_tty_nr" "$supervisor_start_ticks" \
    "$supervisor_exe" "$supervisor_cwd" "$supervisor_cmdline_text" "$supervisor_cmdline_hex" \
    "$supervisor_cmdline_sha256" "$nohup_path" "$setsid_path" "$bash_path" "$python_entry" \
    "$try_python_target" "$control_dir/envelope.log" "$(sha256_file "$control_dir/attempt.json")" \
    "$(sha256_file "$control_dir/worker-claim.json")" "$recorded_utc" "$recorded_unix")" || die "cannot build start record"
  write_atomic "$control_dir/start.json" "$start_json" || die "cannot persist start record"
  printf '{"control_dir":"%s","run_id":"%s","supervisor_pid":%s,"script_sha256":"%s","gate_sha256":"%s"}\n' \
    "$control_dir" "$run_id" "$supervisor_pid" "$script_sha256" "$gate_sha256"
  exit 0
fi

if [[ "$mode" == "worker" ]]; then
  gate_pid=""
  gate_active=0
  worker_cleanup() {
    local exit_code=$?
    local index failure_utc failure_unix failure_json
    trap - EXIT HUP INT TERM
    if [[ "$gate_active" == 1 && -n "$gate_pid" && "$gate_pid" =~ ^[1-9][0-9]*$ ]]; then
      kill -TERM -- "-$gate_pid" 2>/dev/null || true
      for ((index = 0; index < 50; index++)); do
        kill -0 -- "-$gate_pid" 2>/dev/null || break
        sleep 0.02
      done
      kill -KILL -- "-$gate_pid" 2>/dev/null || true
      wait "$gate_pid" 2>/dev/null || true
    fi
    if [[ ! -e "$control_dir/gate.stdout" && ! -L "$control_dir/gate.stdout" ]]; then
      : > "$control_dir/gate.stdout" 2>/dev/null || true
    fi
    if [[ ! -e "$control_dir/gate.stderr" && ! -L "$control_dir/gate.stderr" ]]; then
      : > "$control_dir/gate.stderr" 2>/dev/null || true
    fi
    if [[ ! -e "$control_dir/gate.exit" && ! -L "$control_dir/gate.exit" ]]; then
      write_atomic "$control_dir/gate.exit" "125" 2>/dev/null || true
    fi
    if [[ ! -e "$control_dir/terminal.json" && ! -L "$control_dir/terminal.json" ]]; then
      failure_utc="$(utc_now 2>/dev/null || printf '1970-01-01T00:00:00Z')"
      failure_unix="$(unix_now 2>/dev/null || printf '0')"
      failure_json="$(printf '{\n  "schema_version": 1,\n  "kind": "durable-linux-exact-test-gate",\n  "run_id": "%s",\n  "status": "failed",\n  "reason": "detached-worker-aborted-before-complete",\n  "worker_pid": %s,\n  "gate_pid": %s,\n  "script_sha256": "%s",\n  "gate_sha256": "%s",\n  "ended_utc": "%s",\n  "ended_unix": %s\n}' \
        "$run_id" "$$" "${gate_pid:-0}" "$script_sha256" "$gate_sha256" "$failure_utc" "$failure_unix")"
      write_atomic "$control_dir/terminal.json" "$failure_json" 2>/dev/null || true
    fi
    exit "$exit_code"
  }
  trap worker_cleanup EXIT
  trap 'exit 129' HUP
  trap 'exit 130' INT
  trap 'exit 143' TERM

  require_real_directory "$REPO_ROOT" "repository root"
  require_real_directory "$control_dir" "envelope control directory"
  [[ "$0" == "$snapshot" ]] || die "worker is not the canonical envelope snapshot"
  require_real_file "$snapshot" "envelope snapshot"
  require_real_file "$gate_script" "Python gate runtime"
  [[ "$(sha256_file "$snapshot")" == "$script_sha256" ]] || die "worker envelope SHA256 drifted"
  [[ "$(sha256_file "$gate_script")" == "$gate_sha256" ]] || die "worker Python gate SHA256 drifted"
  for forbidden in "$formal_suite" "$formal_controller" "$formal_control" \
    "$preflight_control" "$init_control" "$gate_control"; do
    [[ ! -e "$forbidden" && ! -L "$forbidden" ]] || die "forbidden path exists before gate worker: $forbidden"
  done

  worker_claimed_utc="$(utc_now)" || die "cannot read worker claim UTC"
  worker_claimed_unix="$(unix_now)" || die "cannot read worker claim Unix time"
  worker_claim_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "worker_pid": %s,\n  "worker_ppid": %s,\n  "script_sha256": "%s",\n  "gate_sha256": "%s",\n  "claimed_utc": "%s",\n  "claimed_unix": %s\n}' \
    "$run_id" "$$" "$PPID" "$script_sha256" "$gate_sha256" "$worker_claimed_utc" "$worker_claimed_unix")" || die "cannot build worker claim"
  write_atomic "$control_dir/worker-claim.json" "$worker_claim_json" || die "worker claim already exists"

  start_ready=0
  for ((index = 0; index < WORKER_CLAIM_WAIT_TENTHS; index++)); do
    if [[ -f "$control_dir/start.json" && ! -L "$control_dir/start.json" ]]; then
      start_ready=1
      break
    fi
    sleep 0.1
  done
  [[ "$start_ready" == 1 ]] || die "starter did not publish start.json within five seconds"

  worker_hostname="$(hostname)" || die "cannot read worker hostname"
  worker_boot_id="$(boot_id_now)" || die "cannot read worker boot id"
  worker_started_utc="$(utc_now)" || die "cannot read worker UTC"
  worker_started_unix="$(unix_now)" || die "cannot read worker Unix time"
  proc_identity "$$" || die "cannot bind worker identity"
  [[ "$PROC_SID" == "$$" && "$PROC_PGID" == "$$" ]] || die "worker is not a session and process-group leader"
  [[ "$PROC_TTY_NR" == 0 ]] || die "worker retained a controlling terminal"
  [[ "$PROC_CWD" == "$REPO_ROOT" ]] || die "worker cwd drifted"
  worker_start_ticks="$PROC_START_TICKS"
  worker_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "role": "detached-linux-exact-test-worker",\n  "pid": %s,\n  "ppid": %s,\n  "pgid": %s,\n  "sid": %s,\n  "tty": "none",\n  "tty_nr": %s,\n  "proc_start_ticks": %s,\n  "proc_exe": "%s",\n  "proc_cwd": "%s",\n  "proc_cmdline_text": "%s",\n  "proc_cmdline_hex": "%s",\n  "proc_cmdline_sha256": "%s",\n  "hostname": "%s",\n  "boot_id": "%s",\n  "script_sha256": "%s",\n  "gate_sha256": "%s",\n  "attempt_sha256": "%s",\n  "start_sha256": "%s",\n  "worker_claim_sha256": "%s",\n  "started_utc": "%s",\n  "started_unix": %s\n}' \
    "$run_id" "$$" "$PROC_PPID" "$PROC_PGID" "$PROC_SID" "$PROC_TTY_NR" "$PROC_START_TICKS" \
    "$PROC_EXE" "$PROC_CWD" "$PROC_CMDLINE_TEXT" "$PROC_CMDLINE_HEX" "$PROC_CMDLINE_SHA256" \
    "$worker_hostname" "$worker_boot_id" "$script_sha256" "$gate_sha256" \
    "$(sha256_file "$control_dir/attempt.json")" "$(sha256_file "$control_dir/start.json")" \
    "$(sha256_file "$control_dir/worker-claim.json")" "$worker_started_utc" "$worker_started_unix")" || die "cannot build worker record"
  write_atomic "$control_dir/worker-start.json" "$worker_json" || die "cannot persist worker record"

  python_target="$(realpath -e -- "$python_entry")" || die "project Python is missing"
  [[ -f "$python_target" && -x "$python_target" ]] || die "project Python target is not executable"
  setsid_path="$(command -v setsid)" || die "setsid is unavailable"
  setsid_path="$(realpath -e -- "$setsid_path")" || die "cannot resolve setsid"
  : > "$control_dir/gate.stdout" || die "cannot create gate stdout"
  : > "$control_dir/gate.stderr" || die "cannot create gate stderr"
  chmod 600 -- "$control_dir/gate.stdout" "$control_dir/gate.stderr" || die "cannot restrict gate streams"
  "$setsid_path" "$python_entry" "$gate_script" \
    --run-id "$run_id" --script-sha256 "$gate_sha256" \
    </dev/null >"$control_dir/gate.stdout" 2>"$control_dir/gate.stderr" &
  gate_pid=$!
  gate_active=1
  [[ "$gate_pid" =~ ^[1-9][0-9]*$ ]] || die "gate launcher did not return a PID"

  gate_bound=0
  for ((index = 0; index < 50; index++)); do
    if proc_identity "$gate_pid"; then
      if [[ "$PROC_SID" == "$gate_pid" && "$PROC_PGID" == "$gate_pid" && \
        "$PROC_TTY_NR" == 0 && "$PROC_EXE" == "$python_target" && \
        "$PROC_CMDLINE_TEXT" == *"$gate_script"* && "$PROC_CMDLINE_TEXT" == *"$gate_sha256"* ]]; then
        gate_bound=1
        break
      fi
    fi
    kill -0 "$gate_pid" 2>/dev/null || break
    sleep 0.02
  done
  [[ "$gate_bound" == 1 ]] || die "cannot bind detached Python gate identity"
  gate_start_ticks="$PROC_START_TICKS"
  gate_launched_utc="$(utc_now)" || die "cannot read gate launch UTC"
  gate_launched_unix="$(unix_now)" || die "cannot read gate launch Unix time"
  gate_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "role": "detached-python-exact-test-gate",\n  "pid": %s,\n  "ppid": %s,\n  "pgid": %s,\n  "sid": %s,\n  "tty": "none",\n  "tty_nr": %s,\n  "proc_start_ticks": %s,\n  "proc_exe": "%s",\n  "proc_cwd": "%s",\n  "proc_cmdline_text": "%s",\n  "proc_cmdline_hex": "%s",\n  "proc_cmdline_sha256": "%s",\n  "python_entry": "%s",\n  "python_target": "%s",\n  "gate_script": "%s",\n  "script_sha256": "%s",\n  "gate_sha256": "%s",\n  "worker_pid": %s,\n  "worker_start_sha256": "%s",\n  "launched_utc": "%s",\n  "launched_unix": %s\n}' \
    "$run_id" "$gate_pid" "$PROC_PPID" "$PROC_PGID" "$PROC_SID" "$PROC_TTY_NR" \
    "$PROC_START_TICKS" "$PROC_EXE" "$PROC_CWD" "$PROC_CMDLINE_TEXT" "$PROC_CMDLINE_HEX" \
    "$PROC_CMDLINE_SHA256" "$python_entry" "$python_target" "$gate_script" "$script_sha256" \
    "$gate_sha256" "$$" "$(sha256_file "$control_dir/worker-start.json")" \
    "$gate_launched_utc" "$gate_launched_unix")" || die "cannot build gate process record"
  write_atomic "$control_dir/gate-process.json" "$gate_json" || die "cannot persist gate process record"

  wait "$gate_pid"
  gate_exit_code=$?
  gate_process_group_residual=false
  if kill -0 -- "-$gate_pid" 2>/dev/null; then
    gate_process_group_residual=true
    kill -TERM -- "-$gate_pid" 2>/dev/null || true
    for ((index = 0; index < 50; index++)); do
      kill -0 -- "-$gate_pid" 2>/dev/null || break
      sleep 0.02
    done
    kill -KILL -- "-$gate_pid" 2>/dev/null || true
  fi
  gate_active=0
  write_atomic "$control_dir/gate.exit" "$gate_exit_code" || die "cannot persist gate exit code"
  ended_utc="$(utc_now)" || die "cannot read terminal UTC"
  ended_unix="$(unix_now)" || die "cannot read terminal Unix time"

  terminal_status="failed"
  terminal_reason="python-gate-nonzero-or-incomplete"
  gate_terminal_sha256=""
  if [[ -f "$gate_control/terminal.json" && ! -L "$gate_control/terminal.json" ]]; then
    gate_terminal_sha256="$(sha256_file "$gate_control/terminal.json")" || gate_terminal_sha256=""
  fi
  if [[ "$gate_exit_code" == 0 && "$gate_process_group_residual" == false && -n "$gate_terminal_sha256" ]]; then
    if "$python_entry" - "$gate_control/terminal.json" "$run_id" "$gate_sha256" "$EXPECTED_TESTS" <<'PY'
import json
import sys
from pathlib import Path

terminal = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected_counts = {
    "tests": int(sys.argv[4]),
    "passed": int(sys.argv[4]),
    "failures": 0,
    "errors": 0,
    "skipped": 0,
    "disabled": 0,
    "testcase_nodes": int(sys.argv[4]),
}
if terminal.get("status") != "completed":
    raise SystemExit(1)
if terminal.get("run_id") != sys.argv[2] or terminal.get("script_sha256") != sys.argv[3]:
    raise SystemExit(1)
if terminal.get("pytest_exit_code") != 0 or terminal.get("counts") != expected_counts:
    raise SystemExit(1)
PY
    then
      terminal_status="completed"
      terminal_reason="exactly-53-tests-passed-with-zero-nonpasses"
    fi
  fi

  evidence_json="$(printf '{\n    "attempt.json": "%s",\n    "envelope.log": "%s",\n    "gate-process.json": "%s",\n    "gate.exit": "%s",\n    "gate.stderr": "%s",\n    "gate.stdout": "%s",\n    "script-snapshot.sh": "%s",\n    "start.json": "%s",\n    "worker-claim.json": "%s",\n    "worker-start.json": "%s"\n  }' \
    "$(sha256_file "$control_dir/attempt.json")" "$(sha256_file "$control_dir/envelope.log")" \
    "$(sha256_file "$control_dir/gate-process.json")" "$(sha256_file "$control_dir/gate.exit")" \
    "$(sha256_file "$control_dir/gate.stderr")" "$(sha256_file "$control_dir/gate.stdout")" \
    "$(sha256_file "$snapshot")" "$(sha256_file "$control_dir/start.json")" \
    "$(sha256_file "$control_dir/worker-claim.json")" "$(sha256_file "$control_dir/worker-start.json")")" || die "cannot build evidence map"
  terminal_json="$(printf '{\n  "schema_version": 1,\n  "kind": "durable-linux-exact-test-gate",\n  "run_id": "%s",\n  "status": "%s",\n  "reason": "%s",\n  "expected_tests": %s,\n  "gate_exit_code": %s,\n  "gate_process_group_residual": %s,\n  "worker_pid": %s,\n  "worker_pgid": %s,\n  "worker_sid": %s,\n  "worker_start_ticks": %s,\n  "gate_pid": %s,\n  "gate_pgid": %s,\n  "gate_sid": %s,\n  "gate_start_ticks": %s,\n  "hostname": "%s",\n  "boot_id": "%s",\n  "script_sha256": "%s",\n  "gate_sha256": "%s",\n  "gate_terminal_sha256": "%s",\n  "started_utc": "%s",\n  "started_unix": %s,\n  "ended_utc": "%s",\n  "ended_unix": %s,\n  "evidence_sha256": %s\n}' \
    "$run_id" "$terminal_status" "$terminal_reason" "$EXPECTED_TESTS" "$gate_exit_code" \
    "$gate_process_group_residual" \
    "$$" "$$" "$$" "$worker_start_ticks" \
    "$gate_pid" "$gate_pid" "$gate_pid" "$gate_start_ticks" \
    "$worker_hostname" "$worker_boot_id" "$script_sha256" "$gate_sha256" "$gate_terminal_sha256" \
    "$worker_started_utc" "$worker_started_unix" "$ended_utc" "$ended_unix" "$evidence_json")" || die "cannot build terminal record"
  write_atomic "$control_dir/terminal.json" "$terminal_json" || die "cannot persist terminal record"
  if [[ "$terminal_status" != "completed" ]]; then
    trap - EXIT HUP INT TERM
    exit 1
  fi
  trap - EXIT HUP INT TERM
  exit 0
fi

require_real_directory "$REPO_ROOT" "repository root"
require_real_directory "$control_dir" "envelope control directory"
[[ "$0" == "$source_script" ]] || die "verifier is not the canonical launcher runtime"
require_real_file "$source_script" "envelope runtime"
require_real_file "$gate_script" "Python gate runtime"
[[ "$(sha256_file "$source_script")" == "$script_sha256" ]] || die "verifier envelope SHA256 drifted"
[[ "$(sha256_file "$gate_script")" == "$gate_sha256" ]] || die "verifier Python gate SHA256 drifted"
require_real_file "$control_dir/terminal.json" "envelope terminal"
python_target="$(realpath -e -- "$python_entry")" || die "project Python is missing"
[[ -f "$python_target" && -x "$python_target" ]] || die "project Python target is not executable"

"$python_entry" - "$REPO_ROOT" "$run_id" "$script_sha256" "$gate_sha256" <<'PY'
import hashlib
import json
import os
import re
import signal
import stat
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

repo = Path(sys.argv[1])
run_id, script_sha, gate_sha = sys.argv[2:]
run_artifact = repo / "artifacts" / run_id
launcher = run_artifact / "launcher"
control = run_artifact / "linux-exact-test-envelope"
gate_control = run_artifact / "linux-exact-test-gate"

def fail(message):
    raise SystemExit(f"durable linux exact test gate verify: {message}")

def real_file(path, label):
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        fail(f"{label} is missing: {path}")
    if not stat.S_ISREG(metadata.st_mode) or path.resolve(strict=True) != path:
        fail(f"{label} is not a canonical real file: {path}")
    return path

def real_dir(path, label):
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        fail(f"{label} is missing: {path}")
    if not stat.S_ISDIR(metadata.st_mode) or path.resolve(strict=True) != path:
        fail(f"{label} is not a canonical real directory: {path}")
    return path

def digest(path):
    return hashlib.sha256(real_file(path, "evidence").read_bytes()).hexdigest()

def load(name, keys):
    path = real_file(control / name, name)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        fail(f"{name} is invalid JSON: {error}")
    if not isinstance(value, dict) or set(value) != set(keys):
        fail(f"{name} schema drifted")
    return value

expected_inventory = {
    "attempt.json", "envelope.log", "gate-process.json", "gate.exit",
    "gate.stderr", "gate.stdout", "script-snapshot.sh", "start.json",
    "terminal.json", "worker-claim.json", "worker-start.json",
}
real_dir(control, "envelope control")
actual_inventory = {path.name for path in control.iterdir()}
if actual_inventory != expected_inventory:
    fail(f"envelope inventory drifted: {sorted(actual_inventory)}")
for name in expected_inventory:
    real_file(control / name, name)

attempt = load("attempt.json", {
    "schema_version", "kind", "run_id", "control_dir", "gate_control_dir",
    "source_script", "gate_script", "snapshot", "script_sha256", "gate_sha256",
    "starter_pid", "started_utc", "started_unix", "hostname", "boot_id",
})
start = load("start.json", {
    "schema_version", "run_id", "script_sha256", "gate_sha256", "supervisor_pid",
    "supervisor_ppid", "supervisor_pgid", "supervisor_sid", "supervisor_tty",
    "supervisor_tty_nr", "supervisor_start_ticks", "supervisor_exe", "supervisor_cwd",
    "supervisor_cmdline_text", "supervisor_cmdline_hex", "supervisor_cmdline_sha256",
    "nohup_path", "setsid_path", "bash_path", "python_entry", "python_target",
    "stdin", "envelope_log", "attempt_sha256", "worker_claim_sha256",
    "recorded_utc", "recorded_unix",
})
claim = load("worker-claim.json", {
    "schema_version", "run_id", "worker_pid", "worker_ppid", "script_sha256",
    "gate_sha256", "claimed_utc", "claimed_unix",
})
worker = load("worker-start.json", {
    "schema_version", "run_id", "role", "pid", "ppid", "pgid", "sid", "tty",
    "tty_nr", "proc_start_ticks", "proc_exe", "proc_cwd", "proc_cmdline_text",
    "proc_cmdline_hex", "proc_cmdline_sha256", "hostname", "boot_id",
    "script_sha256", "gate_sha256", "attempt_sha256", "start_sha256",
    "worker_claim_sha256", "started_utc", "started_unix",
})
gate = load("gate-process.json", {
    "schema_version", "run_id", "role", "pid", "ppid", "pgid", "sid", "tty",
    "tty_nr", "proc_start_ticks", "proc_exe", "proc_cwd", "proc_cmdline_text",
    "proc_cmdline_hex", "proc_cmdline_sha256", "python_entry", "python_target",
    "gate_script", "script_sha256", "gate_sha256", "worker_pid",
    "worker_start_sha256", "launched_utc", "launched_unix",
})
terminal = load("terminal.json", {
    "schema_version", "kind", "run_id", "status", "reason", "expected_tests",
    "gate_exit_code", "gate_process_group_residual", "worker_pid", "worker_pgid", "worker_sid",
    "worker_start_ticks", "gate_pid", "gate_pgid", "gate_sid", "gate_start_ticks",
    "hostname", "boot_id", "script_sha256", "gate_sha256", "gate_terminal_sha256",
    "started_utc", "started_unix", "ended_utc", "ended_unix", "evidence_sha256",
})

records = (attempt, start, claim, worker, gate, terminal)
if any(record.get("schema_version") != 1 or record.get("run_id") != run_id for record in records):
    fail("schema version or run id binding drifted")
if any(record.get("script_sha256") != script_sha or record.get("gate_sha256") != gate_sha for record in records):
    fail("script hash binding drifted")
if attempt["kind"] != "durable-linux-exact-test-gate" or terminal["kind"] != attempt["kind"]:
    fail("envelope kind drifted")
if terminal["status"] != "completed" or terminal["reason"] != "exactly-53-tests-passed-with-zero-nonpasses":
    fail("envelope did not complete exactly")
if terminal["expected_tests"] != 53 or terminal["gate_exit_code"] != 0:
    fail("envelope terminal count or exit contract drifted")
if terminal["gate_process_group_residual"] is not False:
    fail("gate left a residual process group")

canonical = {
    "control_dir": str(control),
    "gate_control_dir": str(gate_control),
    "source_script": str(launcher / "durable_linux_exact_test_gate.sh"),
    "gate_script": str(launcher / "linux_exact_test_gate.py"),
    "snapshot": str(control / "script-snapshot.sh"),
}
if any(attempt[key] != value for key, value in canonical.items()):
    fail("canonical path binding drifted")
if start["python_entry"] != str(repo / ".venv/bin/python") or gate["python_entry"] != start["python_entry"]:
    fail("project Python entry binding drifted")
current_python_target = Path(start["python_entry"]).resolve(strict=True)
if current_python_target != Path(start["python_target"]).resolve(strict=True):
    fail("current project Python target drifted")
if current_python_target != Path(gate["python_target"]).resolve(strict=True):
    fail("project Python target binding drifted")
if start["stdin"] != "/dev/null" or start["envelope_log"] != str(control / "envelope.log"):
    fail("detached stream binding drifted")
if digest(launcher / "durable_linux_exact_test_gate.sh") != script_sha:
    fail("envelope runtime drifted")
if digest(launcher / "linux_exact_test_gate.py") != gate_sha:
    fail("Python gate runtime drifted")
if digest(control / "script-snapshot.sh") != script_sha:
    fail("envelope snapshot drifted")

expected_evidence = expected_inventory - {"terminal.json"}
if not isinstance(terminal["evidence_sha256"], dict) or set(terminal["evidence_sha256"]) != expected_evidence:
    fail("envelope evidence map drifted")
for name, expected in terminal["evidence_sha256"].items():
    if digest(control / name) != expected:
        fail(f"envelope evidence hash drifted: {name}")
if start["attempt_sha256"] != digest(control / "attempt.json"):
    fail("start attempt hash binding drifted")
if start["worker_claim_sha256"] != digest(control / "worker-claim.json"):
    fail("start claim hash binding drifted")
if worker["attempt_sha256"] != start["attempt_sha256"] or worker["start_sha256"] != digest(control / "start.json"):
    fail("worker start hash binding drifted")
if worker["worker_claim_sha256"] != start["worker_claim_sha256"]:
    fail("worker claim hash binding drifted")
if gate["worker_start_sha256"] != digest(control / "worker-start.json"):
    fail("gate worker hash binding drifted")

def verify_cmdline(record, prefix):
    try:
        raw = bytes.fromhex(record[f"{prefix}cmdline_hex"])
    except (ValueError, TypeError):
        fail(f"{prefix}cmdline hex is invalid")
    if hashlib.sha256(raw).hexdigest() != record[f"{prefix}cmdline_sha256"]:
        fail(f"{prefix}cmdline hash drifted")
    text = b" ".join(part for part in raw.split(b"\0") if part).decode("utf-8")
    if text != record[f"{prefix}cmdline_text"]:
        fail(f"{prefix}cmdline text drifted")
    return text

supervisor_cmd = verify_cmdline(start, "supervisor_")
worker_cmd = verify_cmdline(worker, "proc_")
gate_cmd = verify_cmdline(gate, "proc_")
for required in (start["setsid_path"], "--fork", "--wait", str(control / "script-snapshot.sh"), "worker", run_id, script_sha, gate_sha):
    if required not in supervisor_cmd:
        fail(f"supervisor command binding is missing: {required}")
for required in (start["bash_path"], str(control / "script-snapshot.sh"), "worker", run_id, script_sha, gate_sha):
    if required not in worker_cmd:
        fail(f"worker command binding is missing: {required}")
for required in (str(launcher / "linux_exact_test_gate.py"), "--run-id", run_id, "--script-sha256", gate_sha):
    if required not in gate_cmd:
        fail(f"gate command binding is missing: {required}")

if worker["pid"] != claim["worker_pid"] or worker["ppid"] != claim["worker_ppid"]:
    fail("worker PID binding drifted")
if start["supervisor_ppid"] != attempt["starter_pid"] or worker["ppid"] != start["supervisor_pid"]:
    fail("supervisor and worker parent binding drifted")
if start["supervisor_tty"] != "none" or start["supervisor_tty_nr"] != 0:
    fail("supervisor retained a controlling terminal")
if start["supervisor_cwd"] != str(repo) or Path(start["supervisor_exe"]).resolve(strict=True) != Path(start["setsid_path"]).resolve(strict=True):
    fail("supervisor cwd or executable binding drifted")
if worker["pid"] != worker["pgid"] or worker["pid"] != worker["sid"] or worker["tty"] != "none" or worker["tty_nr"] != 0:
    fail("worker was not detached into its own session")
if Path(worker["proc_exe"]).resolve(strict=True) != Path(start["bash_path"]).resolve(strict=True):
    fail("worker executable binding drifted")
if gate["pid"] != gate["pgid"] or gate["pid"] != gate["sid"] or gate["tty"] != "none" or gate["tty_nr"] != 0:
    fail("gate was not detached into its own session")
if gate["ppid"] != worker["pid"] or gate["worker_pid"] != worker["pid"]:
    fail("gate parent binding drifted")
if Path(gate["proc_exe"]).resolve(strict=True) != current_python_target or gate["gate_script"] != str(launcher / "linux_exact_test_gate.py"):
    fail("gate executable or script binding drifted")
if terminal["worker_pid"] != worker["pid"] or terminal["worker_pgid"] != worker["pgid"] or terminal["worker_sid"] != worker["sid"]:
    fail("terminal worker identity drifted")
if terminal["gate_pid"] != gate["pid"] or terminal["gate_pgid"] != gate["pgid"] or terminal["gate_sid"] != gate["sid"]:
    fail("terminal gate identity drifted")
if terminal["worker_start_ticks"] != worker["proc_start_ticks"] or terminal["gate_start_ticks"] != gate["proc_start_ticks"]:
    fail("terminal process start-tick binding drifted")
if worker["proc_cwd"] != str(repo) or gate["proc_cwd"] != str(repo):
    fail("detached cwd binding drifted")
if worker["hostname"] != attempt["hostname"] or terminal["hostname"] != attempt["hostname"]:
    fail("hostname binding drifted")
if worker["boot_id"] != attempt["boot_id"] or terminal["boot_id"] != attempt["boot_id"]:
    fail("boot id binding drifted")
if terminal["started_utc"] != worker["started_utc"] or terminal["started_unix"] != worker["started_unix"]:
    fail("terminal worker start-time binding drifted")
if not (attempt["started_unix"] <= claim["claimed_unix"] <= start["recorded_unix"] <= worker["started_unix"] <= gate["launched_unix"] <= terminal["ended_unix"]):
    fail("evidence timestamps are not monotonic")

try:
    gate_exit_text = (control / "gate.exit").read_text(encoding="ascii")
except UnicodeDecodeError:
    fail("gate exit is not ASCII")
if gate_exit_text != "0\n":
    fail("gate exit evidence is not exact zero")

gate_terminal_path = real_file(gate_control / "terminal.json", "Python gate terminal")
if digest(gate_terminal_path) != terminal["gate_terminal_sha256"]:
    fail("Python gate terminal hash drifted")
gate_terminal = json.loads(gate_terminal_path.read_text(encoding="utf-8"))
expected_gate_terminal_keys = {
    "command", "counts", "evidence_sha256", "expected_tests",
    "pytest_timeout_seconds", "pytest_exit_code", "reason", "run_id",
    "schema_version", "script_sha256", "source_sha256", "status",
    "test_module_sha256", "runtime_copy_sha256",
}
if not isinstance(gate_terminal, dict) or set(gate_terminal) != expected_gate_terminal_keys:
    fail("Python gate terminal schema drifted")
expected_counts = {
    "tests": 53, "passed": 53, "failures": 0, "errors": 0,
    "skipped": 0, "disabled": 0, "testcase_nodes": 53,
}
if gate_terminal.get("schema_version") != 1 or gate_terminal.get("run_id") != run_id:
    fail("Python gate terminal identity drifted")
if gate_terminal.get("status") != "completed" or gate_terminal.get("pytest_exit_code") != 0:
    fail("Python gate terminal is not completed")
if gate_terminal.get("expected_tests") != 53 or gate_terminal.get("counts") != expected_counts:
    fail("Python gate terminal is not exact 53/0")
if gate_terminal.get("pytest_timeout_seconds") != 300:
    fail("Python gate terminal timeout drifted")
if gate_terminal.get("reason") != "exactly 53 tests passed with zero skips, failures, or errors":
    fail("Python gate terminal reason drifted")
if gate_terminal.get("script_sha256") != gate_sha:
    fail("Python gate terminal script hash drifted")
gate_evidence = gate_terminal.get("evidence_sha256")
if not isinstance(gate_evidence, dict) or set(gate_evidence) != {"attempt.json", "junit.xml", "pytest.exit", "pytest.ini", "pytest.log"}:
    fail("Python gate evidence map drifted")
for name, expected in gate_evidence.items():
    if not isinstance(expected, str) or digest(gate_control / name) != expected:
        fail(f"Python gate evidence hash drifted: {name}")
if (gate_control / "pytest.exit").read_text(encoding="ascii") != "0\n":
    fail("Python gate pytest exit evidence is not exact zero")
if (gate_control / "pytest.ini").read_text(encoding="ascii") != "[pytest]\n":
    fail("Python gate pytest config drifted")

try:
    junit_root = ET.parse(gate_control / "junit.xml").getroot()
except ET.ParseError as error:
    fail(f"Python gate JUnit is malformed: {error}")
if junit_root.tag == "testsuite":
    junit_suites = [junit_root]
elif junit_root.tag == "testsuites":
    junit_suites = list(junit_root)
    if not junit_suites or any(suite.tag != "testsuite" for suite in junit_suites):
        fail("Python gate JUnit suite inventory drifted")
else:
    fail("Python gate JUnit root tag drifted")
junit_counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0, "disabled": 0}
junit_cases = []
for suite in junit_suites:
    for field in ("tests", "failures", "errors", "skipped"):
        value = suite.get(field)
        if value is None or re.fullmatch(r"[0-9]+", value) is None:
            fail(f"Python gate JUnit {field} is invalid")
        junit_counts[field] += int(value)
    disabled = suite.get("disabled", "0")
    if re.fullmatch(r"[0-9]+", disabled) is None:
        fail("Python gate JUnit disabled is invalid")
    junit_counts["disabled"] += int(disabled)
    junit_cases.extend(child for child in suite if child.tag == "testcase")
if junit_counts != {"tests": 53, "failures": 0, "errors": 0, "skipped": 0, "disabled": 0}:
    fail(f"Python gate JUnit summary is not exact 53/0: {junit_counts}")
if len(junit_cases) != 53:
    fail("Python gate JUnit testcase count is not exact 53")
if any(any(child.tag in {"failure", "error", "skipped"} for child in case) for case in junit_cases):
    fail("Python gate JUnit contains a non-pass outcome")
gate_names = {path.name for path in gate_control.iterdir()}
required_gate_names = set(gate_evidence) | {"terminal.json", "tmp", "pycache"}
if not required_gate_names.issubset(gate_names) or gate_names - required_gate_names - {"basetemp"}:
    fail(f"Python gate inventory drifted: {sorted(gate_names)}")
for name in ("tmp", "pycache"):
    real_dir(gate_control / name, f"Python gate {name}")
if "basetemp" in gate_names:
    real_dir(gate_control / "basetemp", "Python gate basetemp")

gate_attempt = json.loads(real_file(gate_control / "attempt.json", "Python gate attempt").read_text(encoding="utf-8"))
expected_gate_attempt_keys = {
    "command", "control_dir", "environment_overrides", "expected_tests",
    "pytest_timeout_seconds", "run_id", "schema_version", "script_sha256",
    "source_sha256", "test_module_sha256", "runtime_copy_sha256",
}
if not isinstance(gate_attempt, dict) or set(gate_attempt) != expected_gate_attempt_keys:
    fail("Python gate attempt schema drifted")
if gate_attempt["schema_version"] != 1 or gate_attempt["run_id"] != run_id:
    fail("Python gate attempt identity drifted")
if gate_attempt["control_dir"] != str(gate_control) or gate_attempt["script_sha256"] != gate_sha:
    fail("Python gate attempt path or hash binding drifted")
if gate_attempt["expected_tests"] != 53 or gate_attempt["pytest_timeout_seconds"] != 300:
    fail("Python gate attempt count or timeout drifted")
required_environment = {
    "CUDA_VISIBLE_DEVICES": "",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    "PYTEST_ADDOPTS": "",
    "PYTEST_PLUGINS": "",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONNOUSERSITE": "1",
    "PYTHONPATH": "",
}
environment = gate_attempt["environment_overrides"]
expected_environment_keys = set(required_environment) | {"PYTHONPYCACHEPREFIX", "TMPDIR", "TEMP", "TMP"}
if not isinstance(environment, dict) or set(environment) != expected_environment_keys:
    fail("Python gate isolation environment schema drifted")
if any(environment.get(key) != value for key, value in required_environment.items()):
    fail("Python gate isolation environment drifted")
for key, relative in (("PYTHONPYCACHEPREFIX", "pycache"), ("TMPDIR", "tmp"), ("TEMP", "tmp"), ("TMP", "tmp")):
    if environment.get(key) != str(gate_control / relative):
        fail(f"Python gate repo-local environment drifted: {key}")
for map_name in ("source_sha256", "runtime_copy_sha256", "test_module_sha256"):
    mapping = gate_terminal.get(map_name)
    if not isinstance(mapping, dict) or mapping != gate_attempt.get(map_name):
        fail(f"Python gate {map_name} binding drifted")
    for relative, expected in mapping.items():
        if digest(launcher / relative) != expected:
            fail(f"Python gate frozen file drifted: {relative}")
if gate_terminal.get("command") != gate_attempt.get("command"):
    fail("Python gate command binding drifted")
launcher_expected = (
    set(gate_terminal["source_sha256"])
    | set(gate_terminal["runtime_copy_sha256"])
    | set(gate_terminal["test_module_sha256"])
    | {"linux_exact_test_gate.py"}
)
launcher_actual = {
    path.relative_to(launcher).as_posix()
    for path in launcher.rglob("*")
    if path.is_file() or path.is_symlink()
}
if launcher_actual != launcher_expected:
    fail("Python gate launcher inventory drifted")
if gate_terminal["source_sha256"].get("research/control/durable_linux_exact_test_gate.sh") != script_sha:
    fail("Python gate did not freeze the envelope source")
if gate_terminal["runtime_copy_sha256"].get("durable_linux_exact_test_gate.sh") != script_sha:
    fail("Python gate did not freeze the envelope runtime")
if gate_terminal["source_sha256"].get("research/control/linux_exact_test_gate.py") != gate_sha:
    fail("Python gate source self-binding drifted")

for forbidden in (
    repo / "runs" / run_id,
    run_artifact / "controller",
    run_artifact / "formal-launch-control",
    run_artifact / "preflight-control",
    run_artifact / "init-baseline-control",
):
    if forbidden.exists() or forbidden.is_symlink():
        fail(f"formal path exists after exact test gate: {forbidden}")

def require_process_absent(pid, pgid, label):
    if (Path("/proc") / str(pid)).exists():
        fail(f"{label} PID is still present: {pid}")
    try:
        os.kill(-int(pgid), 0)
    except ProcessLookupError:
        return
    except PermissionError:
        fail(f"cannot prove {label} process group is absent: {pgid}")
    fail(f"{label} process group is still present: {pgid}")

require_process_absent(worker["pid"], worker["pgid"], "worker")
require_process_absent(gate["pid"], gate["pgid"], "gate")
if (Path("/proc") / str(start["supervisor_pid"])).exists():
    fail(f"supervisor PID is still present: {start['supervisor_pid']}")

print(json.dumps({
    "status": "verified",
    "run_id": run_id,
    "tests": 53,
    "nonpasses": 0,
    "script_sha256": script_sha,
    "gate_sha256": gate_sha,
}, sort_keys=True))
PY
