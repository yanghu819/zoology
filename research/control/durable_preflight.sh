#!/usr/bin/env bash

# This control script records every nonzero step itself.
set -u
set -o pipefail

REPO_ROOT="/huyang2/zoology"
RUN_ID="gdn-mqar-single-baseline-nohup-20260731t093138z"
FORMAL_SOURCE_SHA="13f880b5fe61619a1006ef33610de69fbabaaec1"
FORMAL_SOURCE_TREE="ed83a7188351ca2cce8aba46d1cb3b108ce31ec2"
SCRIPT_NAME="durable_preflight.sh"
CONTROL_NAME="preflight-control"

usage() {
  printf '%s\n' "usage: $0 start|worker --script-sha256 SHA256 --control-dir PATH" >&2
  exit 64
}

die() {
  printf 'durable preflight: %s\n' "$1" >&2
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

hash_or_null() {
  local evidence="$1"
  if [[ -f "$evidence" && ! -L "$evidence" ]]; then
    printf '"%s"' "$(sha256_file "$evidence")"
  else
    printf 'null'
  fi
}

formal_suite="$REPO_ROOT/runs/$RUN_ID"
formal_controller="$REPO_ROOT/artifacts/$RUN_ID/controller"
formal_control="$REPO_ROOT/artifacts/$RUN_ID/formal-launch-control"

verify_source_and_formal_absence() {
  local head_sha head_tree forbidden
  head_sha="$(git -C "$REPO_ROOT" rev-parse HEAD)" || return 1
  head_tree="$(git -C "$REPO_ROOT" rev-parse 'HEAD^{tree}')" || return 1
  [[ "$head_sha" == "$FORMAL_SOURCE_SHA" ]] || return 1
  [[ "$head_tree" == "$FORMAL_SOURCE_TREE" ]] || return 1
  if git -C "$REPO_ROOT" symbolic-ref -q HEAD >/dev/null 2>&1; then
    return 1
  fi
  [[ -z "$(git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=all)" ]] || return 1
  for forbidden in "$formal_suite" "$formal_controller" "$formal_control"; do
    [[ ! -e "$forbidden" && ! -L "$forbidden" ]] || return 1
  done
}

mode="${1:-}"
[[ "$mode" == "start" || "$mode" == "worker" ]] || usage
shift

script_sha256=""
control_dir=""
while (($#)); do
  (($# >= 2)) || usage
  case "$1" in
    --script-sha256)
      [[ -z "$script_sha256" ]] || usage
      script_sha256="$2"
      ;;
    --control-dir)
      [[ -z "$control_dir" ]] || usage
      control_dir="$2"
      ;;
    *) usage ;;
  esac
  shift 2
done

[[ -n "$script_sha256" && -n "$control_dir" ]] || usage
[[ "$script_sha256" =~ ^[0-9a-f]{64}$ ]] || die "script SHA256 must be 64 lowercase hexadecimal characters"
expected_control="$REPO_ROOT/artifacts/$RUN_ID/$CONTROL_NAME"
[[ "$control_dir" == "$expected_control" ]] || die "control directory is not the canonical preflight path"

if [[ "$mode" == "start" ]]; then
  source_script="$REPO_ROOT/artifacts/$RUN_ID/launcher/$SCRIPT_NAME"
  [[ "$0" == "$source_script" ]] || die "preflight script is not the canonical uploaded artifact"
  require_real_directory "$REPO_ROOT" "formal repository"
  require_real_directory "${control_dir%/*}" "run artifact directory"
  require_real_directory "${source_script%/*}" "launcher artifact directory"
  [[ -f "$0" && ! -L "$0" ]] || die "preflight script is not a real regular file"
  [[ "$(realpath -e -- "$0")" == "$source_script" ]] || die "preflight script uses a symlink or path alias"
  [[ "$(sha256_file "$0")" == "$script_sha256" ]] || die "preflight script SHA256 differs from the frozen value"
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
  attempt_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "kind": "durable-preflight",\n  "formal_source_sha": "%s",\n  "formal_source_tree": "%s",\n  "control_dir": "%s",\n  "source_script": "%s",\n  "snapshot": "%s",\n  "script_sha256": "%s",\n  "starter_pid": %s,\n  "started_utc": "%s",\n  "started_unix": %s,\n  "hostname": "%s",\n  "boot_id": "%s"\n}' \
    "$RUN_ID" "$FORMAL_SOURCE_SHA" "$FORMAL_SOURCE_TREE" "$control_dir" "$source_script" "$snapshot" \
    "$script_sha256" "$$" "$started_utc" "$started_unix" "$hostname_value" "$boot_id")" || die "cannot build preflight attempt record"
  write_atomic "$control_dir/attempt.json" "$attempt_json" || die "cannot persist preflight attempt record"

  : > "$control_dir/envelope.log" || die "cannot create preflight envelope log"
  chmod 600 -- "$control_dir/envelope.log" || die "cannot restrict preflight envelope log"
  cd "$REPO_ROOT" || die "cannot enter formal repository"
  "$nohup_path" "$setsid_path" --fork --wait "$bash_path" "$snapshot" worker \
    --script-sha256 "$script_sha256" \
    --control-dir "$control_dir" \
    </dev/null >"$control_dir/envelope.log" 2>&1 &
  envelope_supervisor_pid=$!
  [[ "$envelope_supervisor_pid" =~ ^[0-9]+$ ]] || die "nohup did not return a preflight envelope PID"

  recorded_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)" || die "cannot read start-record UTC"
  recorded_unix="$(date -u +%s)" || die "cannot read start-record Unix time"
  start_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "envelope_supervisor_pid": %s,\n  "nohup_path": "%s",\n  "setsid_path": "%s",\n  "bash_path": "%s",\n  "stdin": "/dev/null",\n  "envelope_log": "%s",\n  "recorded_utc": "%s",\n  "recorded_unix": %s\n}' \
    "$RUN_ID" "$envelope_supervisor_pid" "$nohup_path" "$setsid_path" "$bash_path" \
    "$control_dir/envelope.log" "$recorded_utc" "$recorded_unix")" || die "cannot build preflight start record"
  write_atomic "$control_dir/start.json" "$start_json" || die "cannot persist preflight start record"
  printf '{"control_dir":"%s","envelope_supervisor_pid":%s,"run_id":"%s","script_sha256":"%s"}\n' \
    "$control_dir" "$envelope_supervisor_pid" "$RUN_ID" "$script_sha256"
  exit 0
fi

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
  terminal_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "status": "%s",\n  "exit_code": %s,\n  "completed_steps": %s,\n  "failed_step": "%s",\n  "reason": "%s",\n  "worker_pid": %s,\n  "worker_sid": %s,\n  "worker_tty": "%s",\n  "started_utc": "%s",\n  "started_unix": %s,\n  "ended_utc": "%s",\n  "ended_unix": %s,\n  "script_sha256": "%s",\n  "attempt_sha256": %s,\n  "start_sha256": %s,\n  "worker_start_sha256": %s,\n  "envelope_log_sha256": %s,\n  "step_01_log_sha256": %s,\n  "step_01_exit_sha256": %s,\n  "step_01_json_sha256": %s,\n  "step_02_log_sha256": %s,\n  "step_02_exit_sha256": %s,\n  "step_02_json_sha256": %s,\n  "step_03_log_sha256": %s,\n  "step_03_exit_sha256": %s,\n  "step_03_json_sha256": %s,\n  "step_04_log_sha256": %s,\n  "step_04_exit_sha256": %s,\n  "step_04_json_sha256": %s\n}' \
    "$RUN_ID" "$terminal_status" "$terminal_exit" "$completed_steps" "$failed_step" "$failure_reason" \
    "$$" "$worker_sid" "$worker_tty" "$worker_started_utc" "$worker_started_unix" "$ended_utc" "$ended_unix" \
    "$script_sha256" "$(hash_or_null "$control_dir/attempt.json")" "$(hash_or_null "$control_dir/start.json")" \
    "$(hash_or_null "$control_dir/worker-start.json")" "$(hash_or_null "$control_dir/envelope.log")" \
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

snapshot="$control_dir/script-snapshot.sh"
require_real_directory "$REPO_ROOT" "formal repository"
require_real_directory "$control_dir" "preflight control directory"
[[ "$0" == "$snapshot" ]] || die "worker is not the canonical preflight snapshot"
[[ -f "$0" && ! -L "$0" ]] || die "preflight snapshot is not a real regular file"
[[ "$(realpath -e -- "$0")" == "$snapshot" ]] || die "preflight snapshot uses a symlink or path alias"
[[ "$(sha256_file "$0")" == "$script_sha256" ]] || die "preflight worker SHA256 drifted"
[[ -f "$control_dir/attempt.json" && ! -L "$control_dir/attempt.json" ]] || die "preflight attempt record is missing"
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
worker_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "role": "durable-preflight-worker",\n  "pid": %s,\n  "ppid": %s,\n  "sid": %s,\n  "tty": "%s",\n  "cwd": "%s",\n  "started_utc": "%s",\n  "started_unix": %s\n}' \
  "$RUN_ID" "$$" "$PPID" "$worker_sid" "$worker_tty" "$worker_cwd" "$worker_started_utc" "$worker_started_unix")" || die "cannot build preflight worker record"
write_atomic "$control_dir/worker-start.json" "$worker_json" || die "cannot persist preflight worker record"

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
  step_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "index": "%s",\n  "name": "%s",\n  "command": %s,\n  "command_exit_code": %s,\n  "step_exit_code": %s,\n  "started_utc": "%s",\n  "started_unix": %s,\n  "ended_utc": "%s",\n  "ended_unix": %s,\n  "log_sha256": "%s",\n  "exit_sha256": "%s"\n}' \
    "$RUN_ID" "$index" "$name" "$command_json" "$command_exit" "$step_exit" "$started_utc" "$started_unix" \
    "$ended_utc" "$ended_unix" "$(sha256_file "$log_path")" "$(sha256_file "$exit_path")")" || return 74
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
terminal_status="completed"
((overall_exit == 0 && completed_steps == 4)) || terminal_status="failed"
if [[ "$terminal_status" == "completed" ]]; then
  failure_reason="none"
elif [[ "$failure_reason" == "none" ]]; then
  failure_reason="preflight step or postflight gate failed"
fi
write_worker_terminal "$terminal_status" "$overall_exit" || die "cannot persist preflight terminal record"
exit "$overall_exit"
