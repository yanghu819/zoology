#!/usr/bin/env bash

set -u
set -o pipefail

REPO_ROOT="/huyang2/zoology"
RUN_ID="gdn-mqar-single-baseline-nohup-20260731t093138z"
CONTROL_NAME="detach-smoke-control"
SCRIPT_NAME="detached_process_smoke.sh"
DURATION_SECONDS=45

usage() {
  printf '%s\n' "usage: $0 start|worker --script-sha256 SHA256 --control-dir PATH" >&2
  exit 64
}

die() {
  printf 'detached-process smoke: %s\n' "$1" >&2
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

proc_start_ticks() {
  local pid="$1"
  local line tail
  local -a fields
  IFS= read -r line < "/proc/$pid/stat" || return 1
  tail="${line##*) }"
  read -r -a fields <<< "$tail"
  ((${#fields[@]} >= 20)) || return 1
  printf '%s' "${fields[19]}"
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
[[ "$control_dir" == "$expected_control" ]] || die "control directory is not the canonical smoke path"

if [[ "$mode" == "start" ]]; then
  source_script="$REPO_ROOT/artifacts/$RUN_ID/launcher/$SCRIPT_NAME"
  formal_suite="$REPO_ROOT/runs/$RUN_ID"
  formal_controller="$REPO_ROOT/artifacts/$RUN_ID/controller"
  formal_control="$REPO_ROOT/artifacts/$RUN_ID/formal-launch-control"
  [[ "$0" == "$source_script" ]] || die "smoke script is not the canonical uploaded artifact"
  require_real_directory "$REPO_ROOT" "formal repository"
  require_real_directory "${control_dir%/*}" "run artifact directory"
  require_real_directory "${source_script%/*}" "launcher artifact directory"
  [[ -f "$0" && ! -L "$0" ]] || die "smoke script is not a real regular file"
  [[ "$(realpath -e -- "$0")" == "$source_script" ]] || die "smoke script uses a symlink or path alias"
  [[ "$(sha256_file "$0")" == "$script_sha256" ]] || die "smoke script SHA256 differs from the frozen value"
  for forbidden in "$formal_suite" "$formal_controller" "$formal_control"; do
    [[ ! -e "$forbidden" && ! -L "$forbidden" ]] || die "formal path exists before detached smoke: $forbidden"
  done

  nohup_path="$(command -v nohup)" || die "nohup is unavailable"
  setsid_path="$(command -v setsid)" || die "setsid is unavailable"
  bash_path="$(command -v bash)" || die "bash is unavailable"
  nohup_path="$(realpath -e -- "$nohup_path")" || die "cannot resolve nohup"
  setsid_path="$(realpath -e -- "$setsid_path")" || die "cannot resolve setsid"
  bash_path="$(realpath -e -- "$bash_path")" || die "cannot resolve bash"

  # This exact directory is a one-shot diagnostic claim; it is never re-entered.
  mkdir -- "$control_dir" || die "smoke control directory already exists; smoke attempt is consumed"
  require_real_directory "$control_dir" "smoke control directory"
  chmod 700 -- "$control_dir" || die "cannot restrict smoke control directory"

  snapshot="$control_dir/script-snapshot.sh"
  (
    umask 077
    cp -- "$0" "$snapshot"
  ) || die "cannot snapshot smoke script"
  chmod 500 -- "$snapshot" || die "cannot make smoke snapshot executable"
  [[ "$(sha256_file "$snapshot")" == "$script_sha256" ]] || die "smoke snapshot SHA256 drifted"

  started_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)" || die "cannot read start UTC"
  started_unix="$(date -u +%s)" || die "cannot read start Unix time"
  hostname_value="$(hostname)" || die "cannot read hostname"
  boot_id="$(tr '[:upper:]' '[:lower:]' < /proc/sys/kernel/random/boot_id)" || die "cannot read boot id"
  [[ "$hostname_value" =~ ^[A-Za-z0-9._-]+$ ]] || die "hostname cannot be represented safely"
  [[ "$boot_id" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || die "boot id is invalid"
  attempt_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "kind": "detached-process-smoke",\n  "duration_seconds": %s,\n  "control_dir": "%s",\n  "source_script": "%s",\n  "snapshot": "%s",\n  "script_sha256": "%s",\n  "starter_pid": %s,\n  "started_utc": "%s",\n  "started_unix": %s,\n  "hostname": "%s",\n  "boot_id": "%s"\n}' \
    "$RUN_ID" "$DURATION_SECONDS" "$control_dir" "$source_script" "$snapshot" "$script_sha256" \
    "$$" "$started_utc" "$started_unix" "$hostname_value" "$boot_id")" || die "cannot build smoke attempt record"
  write_atomic "$control_dir/attempt.json" "$attempt_json" || die "cannot persist smoke attempt record"

  : > "$control_dir/envelope.log" || die "cannot create smoke envelope log"
  chmod 600 -- "$control_dir/envelope.log" || die "cannot restrict smoke envelope log"
  cd "$REPO_ROOT" || die "cannot enter formal repository"
  "$nohup_path" "$setsid_path" --fork --wait "$bash_path" "$snapshot" worker \
    --script-sha256 "$script_sha256" \
    --control-dir "$control_dir" \
    </dev/null >"$control_dir/envelope.log" 2>&1 &
  envelope_supervisor_pid=$!
  [[ "$envelope_supervisor_pid" =~ ^[0-9]+$ ]] || die "nohup did not return a smoke envelope PID"

  recorded_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)" || die "cannot read start-record UTC"
  recorded_unix="$(date -u +%s)" || die "cannot read start-record Unix time"
  start_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "envelope_supervisor_pid": %s,\n  "nohup_path": "%s",\n  "setsid_path": "%s",\n  "bash_path": "%s",\n  "stdin": "/dev/null",\n  "envelope_log": "%s",\n  "recorded_utc": "%s",\n  "recorded_unix": %s\n}' \
    "$RUN_ID" "$envelope_supervisor_pid" "$nohup_path" "$setsid_path" "$bash_path" \
    "$control_dir/envelope.log" "$recorded_utc" "$recorded_unix")" || die "cannot build smoke start record"
  write_atomic "$control_dir/start.json" "$start_json" || die "cannot persist smoke start record"
  printf '{"control_dir":"%s","envelope_supervisor_pid":%s,"run_id":"%s","script_sha256":"%s"}\n' \
    "$control_dir" "$envelope_supervisor_pid" "$RUN_ID" "$script_sha256"
  exit 0
fi

snapshot="$control_dir/script-snapshot.sh"
formal_suite="$REPO_ROOT/runs/$RUN_ID"
formal_controller="$REPO_ROOT/artifacts/$RUN_ID/controller"
formal_control="$REPO_ROOT/artifacts/$RUN_ID/formal-launch-control"
require_real_directory "$control_dir" "smoke control directory"
[[ "$0" == "$snapshot" ]] || die "worker is not the canonical smoke snapshot"
[[ -f "$0" && ! -L "$0" ]] || die "smoke snapshot is not a real regular file"
[[ "$(realpath -e -- "$0")" == "$snapshot" ]] || die "smoke snapshot uses a symlink or path alias"
[[ "$(sha256_file "$0")" == "$script_sha256" ]] || die "smoke worker SHA256 drifted"
[[ -f "$control_dir/attempt.json" && ! -L "$control_dir/attempt.json" ]] || die "smoke attempt record is missing"

worker_started_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)" || die "cannot read worker UTC"
worker_started_unix="$(date -u +%s)" || die "cannot read worker Unix time"
worker_start_ticks="$(proc_start_ticks "$$")" || die "cannot read smoke worker start ticks"
worker_sid="$(ps -o sid= -p "$$" | tr -d ' ')" || die "cannot read smoke worker session"
worker_tty="$(ps -o tty= -p "$$" | tr -d ' ')" || die "cannot read smoke worker tty"
worker_cwd="$(readlink -e -- "/proc/$$/cwd")" || die "cannot read smoke worker cwd"
worker_cmdline_sha256="$(sha256_file "/proc/$$/cmdline")" || die "cannot hash smoke worker cmdline"
worker_hostname="$(hostname)" || die "cannot read smoke worker hostname"
worker_boot_id="$(tr '[:upper:]' '[:lower:]' < /proc/sys/kernel/random/boot_id)" || die "cannot read smoke worker boot id"
[[ "$worker_start_ticks" =~ ^[0-9]+$ ]] || die "smoke worker start ticks are invalid"
[[ "$worker_sid" == "$$" ]] || die "smoke worker did not become a session leader"
[[ "$worker_tty" == "?" ]] || die "smoke worker retained a controlling terminal"
[[ "$worker_cwd" == "$REPO_ROOT" ]] || die "smoke worker cwd drifted"
[[ "$worker_hostname" =~ ^[A-Za-z0-9._-]+$ ]] || die "smoke worker hostname cannot be represented safely"
[[ "$worker_boot_id" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || die "smoke worker boot id is invalid"
for forbidden in "$formal_suite" "$formal_controller" "$formal_control"; do
  [[ ! -e "$forbidden" && ! -L "$forbidden" ]] || die "formal path exists during detached smoke: $forbidden"
done

worker_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "role": "detached-smoke-worker",\n  "pid": %s,\n  "ppid": %s,\n  "sid": %s,\n  "tty": "%s",\n  "proc_start_ticks": %s,\n  "proc_cmdline_sha256": "%s",\n  "proc_cwd": "%s",\n  "hostname": "%s",\n  "boot_id": "%s",\n  "started_utc": "%s",\n  "started_unix": %s\n}' \
  "$RUN_ID" "$$" "$PPID" "$worker_sid" "$worker_tty" "$worker_start_ticks" \
  "$worker_cmdline_sha256" "$worker_cwd" "$worker_hostname" "$worker_boot_id" \
  "$worker_started_utc" "$worker_started_unix")" || die "cannot build smoke worker record"
write_atomic "$control_dir/worker-start.json" "$worker_json" || die "cannot persist smoke worker record"

sleep "$DURATION_SECONDS" || die "smoke sleep failed"
ended_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)" || die "cannot read smoke end UTC"
ended_unix="$(date -u +%s)" || die "cannot read smoke end Unix time"
elapsed_seconds=$((ended_unix - worker_started_unix))
((elapsed_seconds >= DURATION_SECONDS)) || die "smoke elapsed time is shorter than required"
for required in attempt.json start.json worker-start.json envelope.log; do
  [[ -f "$control_dir/$required" && ! -L "$control_dir/$required" ]] || die "required smoke evidence is missing: $required"
done
for forbidden in "$formal_suite" "$formal_controller" "$formal_control"; do
  [[ ! -e "$forbidden" && ! -L "$forbidden" ]] || die "formal path exists after detached smoke: $forbidden"
done

terminal_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "status": "completed",\n  "duration_seconds": %s,\n  "elapsed_seconds": %s,\n  "worker_pid": %s,\n  "worker_start_ticks": %s,\n  "worker_sid": %s,\n  "worker_tty": "%s",\n  "hostname": "%s",\n  "boot_id": "%s",\n  "started_utc": "%s",\n  "started_unix": %s,\n  "ended_utc": "%s",\n  "ended_unix": %s,\n  "script_sha256": "%s",\n  "attempt_sha256": "%s",\n  "start_sha256": "%s",\n  "worker_start_sha256": "%s"\n}' \
  "$RUN_ID" "$DURATION_SECONDS" "$elapsed_seconds" "$$" "$worker_start_ticks" "$worker_sid" "$worker_tty" \
  "$worker_hostname" "$worker_boot_id" "$worker_started_utc" "$worker_started_unix" \
  "$ended_utc" "$ended_unix" "$script_sha256" \
  "$(sha256_file "$control_dir/attempt.json")" "$(sha256_file "$control_dir/start.json")" \
  "$(sha256_file "$control_dir/worker-start.json")")" || die "cannot build smoke terminal record"
write_atomic "$control_dir/terminal.json" "$terminal_json" || die "cannot persist smoke terminal record"
