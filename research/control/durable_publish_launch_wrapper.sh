#!/usr/bin/env bash

# Do not enable `set -e`: the wrapper must observe and durably record a nonzero
# publish-and-launch exit instead of exiting at `wait`.
set -u
set -o pipefail

REPO_ROOT="/huyang2/zoology"
PYTHON="$REPO_ROOT/.venv/bin/python"
FORMAL_SOURCE_SHA="13f880b5fe61619a1006ef33610de69fbabaaec1"
FORMAL_SOURCE_TREE="ed83a7188351ca2cce8aba46d1cb3b108ce31ec2"
CONTROL_NAME="formal-launch-control"

usage() {
  printf '%s\n' \
    "usage: $0 --wrapper-sha256 SHA256 --bundle-dir PATH --suite-dir PATH --control-dir PATH" >&2
  exit 64
}

sha256_file() {
  sha256sum -- "$1" | awk '{print $1}'
}

require_real_directory() {
  local path="$1"
  [[ -d "$path" && ! -L "$path" ]] || return 1
  [[ "$(realpath -e -- "$path")" == "$path" ]]
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

proc_stat_identity() {
  local pid="$1"
  local line tail
  local -a fields
  IFS= read -r line < "/proc/$pid/stat" || return 1
  tail="${line##*) }"
  read -r -a fields <<< "$tail"
  ((${#fields[@]} >= 20)) || return 1
  printf '%s %s %s %s' \
    "${fields[1]}" "${fields[3]}" "${fields[4]}" "${fields[19]}"
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

wait_without_signal() {
  local pid="$1"
  wait "$pid" 2>/dev/null
  python_exit_code=$?
}

terminate_bound_direct_child() {
  local pid="$1"
  local expected_start_ticks="$2"
  local current_identity=""
  local current_ppid=""
  local current_sid=""
  local current_tty_nr=""
  local current_start_ticks=""
  local state=""
  local _

  current_identity="$(proc_stat_identity "$pid" 2>/dev/null)" || {
    wait_without_signal "$pid"
    return 1
  }
  read -r current_ppid current_sid current_tty_nr current_start_ticks <<< "$current_identity"
  if [[ "$current_ppid" != "$$" || "$current_start_ticks" != "$expected_start_ticks" ]]; then
    wait_without_signal "$pid"
    return 1
  fi
  kill -TERM "$pid" 2>/dev/null || true
  for _ in $(seq 1 50); do
    current_identity="$(proc_stat_identity "$pid" 2>/dev/null)" || break
    read -r current_ppid current_sid current_tty_nr current_start_ticks <<< "$current_identity"
    if [[ "$current_ppid" != "$$" || "$current_start_ticks" != "$expected_start_ticks" ]]; then
      wait_without_signal "$pid"
      return 1
    fi
    state="$(proc_state "$pid" 2>/dev/null)" || break
    [[ "$state" == "Z" ]] && break
    sleep 0.1
  done
  current_identity="$(proc_stat_identity "$pid" 2>/dev/null)" || current_identity=""
  if [[ -n "$current_identity" ]]; then
    read -r current_ppid current_sid current_tty_nr current_start_ticks <<< "$current_identity"
    state="$(proc_state "$pid" 2>/dev/null)" || state="gone"
    if [[ "$current_ppid" == "$$" \
          && "$current_start_ticks" == "$expected_start_ticks" \
          && "$state" != "gone" \
          && "$state" != "Z" ]]; then
      kill -KILL "$pid" 2>/dev/null || true
    fi
  fi
  wait_without_signal "$pid"
}

wrapper_sha256=""
bundle_dir=""
suite_dir=""
control_dir=""

while (($#)); do
  (($# >= 2)) || usage
  case "$1" in
    --wrapper-sha256)
      [[ -z "$wrapper_sha256" ]] || usage
      wrapper_sha256="$2"
      ;;
    --bundle-dir)
      [[ -z "$bundle_dir" ]] || usage
      bundle_dir="$2"
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

[[ -n "$wrapper_sha256" && -n "$bundle_dir" && -n "$suite_dir" && -n "$control_dir" ]] || usage

run_id="unknown"
python_pid=""
python_exit_code=""
python_initial_start_ticks=""
python_start_ticks=""
failure_reason="wrapper validation did not complete"
terminal_written=0
wrapper_actual_sha256=""
wrapper_started_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || printf unknown)"
wrapper_started_unix="$(date -u +%s 2>/dev/null || printf 0)"

hash_or_null() {
  local path="$1"
  if [[ -f "$path" && ! -L "$path" ]]; then
    printf '"%s"' "$(sha256_file "$path")"
  else
    printf 'null'
  fi
}

write_terminal() {
  local status="$1"
  local reason="$2"
  local exit_json="null"
  local pid_json="null"
  local ended_utc ended_unix terminal_json
  ((terminal_written == 0)) || return 0
  [[ "$python_exit_code" =~ ^[0-9]+$ ]] && exit_json="$python_exit_code"
  [[ "$python_pid" =~ ^[0-9]+$ ]] && pid_json="$python_pid"
  ended_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || printf unknown)"
  ended_unix="$(date -u +%s 2>/dev/null || printf 0)"
  terminal_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "status": "%s",\n  "reason": "%s",\n  "formal_source_sha": "%s",\n  "formal_source_tree": "%s",\n  "wrapper_pid": %s,\n  "python_pid": %s,\n  "python_exit_code": %s,\n  "wrapper_sha256": "%s",\n  "wrapper_started_utc": "%s",\n  "wrapper_started_unix": %s,\n  "ended_utc": "%s",\n  "ended_unix": %s,\n  "attempt_sha256": %s,\n  "starter_start_sha256": %s,\n  "wrapper_start_sha256": %s,\n  "python_start_sha256": %s,\n  "envelope_log_sha256": %s,\n  "python_stdout_sha256": %s,\n  "python_stderr_sha256": %s\n}' \
    "$run_id" "$status" "$reason" "$FORMAL_SOURCE_SHA" "$FORMAL_SOURCE_TREE" "$$" "$pid_json" "$exit_json" \
    "$wrapper_actual_sha256" "$wrapper_started_utc" "$wrapper_started_unix" "$ended_utc" "$ended_unix" \
    "$(hash_or_null "$control_dir/attempt.json")" "$(hash_or_null "$control_dir/start.json")" \
    "$(hash_or_null "$control_dir/wrapper-start.json")" "$(hash_or_null "$control_dir/python-start.json")" \
    "$(hash_or_null "$control_dir/envelope.log")" "$(hash_or_null "$control_dir/python.stdout.log")" \
    "$(hash_or_null "$control_dir/python.stderr.log")")" || return 1
  write_atomic "$control_dir/terminal.json" "$terminal_json" || return 1
  terminal_written=1
}

on_exit() {
  local shell_exit=$?
  if ((terminal_written == 0)); then
    write_terminal "failed" "$failure_reason" || true
  fi
  return "$shell_exit"
}

on_signal() {
  local exit_code="$1"
  local signal_name="$2"
  failure_reason="wrapper received $signal_name"
  if [[ "$python_pid" =~ ^[0-9]+$ && ! "$python_exit_code" =~ ^[0-9]+$ ]]; then
    cleanup_start_ticks="$python_start_ticks"
    [[ "$cleanup_start_ticks" =~ ^[0-9]+$ ]] || cleanup_start_ticks="$python_initial_start_ticks"
    if [[ "$cleanup_start_ticks" =~ ^[0-9]+$ ]]; then
      terminate_bound_direct_child "$python_pid" "$cleanup_start_ticks" || true
    else
      wait_without_signal "$python_pid"
    fi
  fi
  exit "$exit_code"
}
trap on_exit EXIT
trap 'on_signal 129 SIGHUP' HUP
trap 'on_signal 130 SIGINT' INT
trap 'on_signal 143 SIGTERM' TERM

[[ "$wrapper_sha256" =~ ^[0-9a-f]{64}$ ]] || { failure_reason="wrapper SHA256 is invalid"; exit 65; }
suite_prefix="$REPO_ROOT/runs/"
[[ "$suite_dir" == "$suite_prefix"* ]] || { failure_reason="suite directory is outside the formal repository"; exit 65; }
run_id="${suite_dir#"$suite_prefix"}"
[[ "$run_id" =~ ^[a-z0-9][a-z0-9-]*$ ]] || { failure_reason="suite directory has an invalid run id"; exit 65; }
[[ "$suite_dir" == "$REPO_ROOT/runs/$run_id" ]] || { failure_reason="suite directory is not canonical"; exit 65; }
[[ "$bundle_dir" == "$REPO_ROOT/artifacts/$run_id/controller" ]] || { failure_reason="bundle directory is not canonical"; exit 65; }
[[ "$control_dir" == "$REPO_ROOT/artifacts/$run_id/$CONTROL_NAME" ]] || { failure_reason="control directory is not canonical"; exit 65; }

require_real_directory "$REPO_ROOT" || { failure_reason="formal repository is not a real directory"; exit 65; }
require_real_directory "$bundle_dir" || { failure_reason="clock capture bundle is not a real directory"; exit 65; }
require_real_directory "$suite_dir" || { failure_reason="single-baseline suite is not a real directory"; exit 65; }
require_real_directory "$control_dir" || { failure_reason="durable control directory is not a real directory"; exit 65; }
[[ -f "$0" && ! -L "$0" ]] || { failure_reason="wrapper snapshot is not a real regular file"; exit 65; }
[[ "$(realpath -e -- "$0")" == "$control_dir/wrapper-snapshot.sh" ]] || { failure_reason="wrapper snapshot path is not canonical"; exit 65; }
wrapper_actual_sha256="$(sha256_file "$0")" || { failure_reason="cannot hash wrapper snapshot"; exit 65; }
[[ "$wrapper_actual_sha256" == "$wrapper_sha256" ]] || { failure_reason="wrapper snapshot SHA256 drifted"; exit 65; }
[[ -x "$PYTHON" ]] || { failure_reason="formal project Python is not executable"; exit 65; }
python_real="$(realpath -e -- "$PYTHON")" || { failure_reason="cannot resolve formal project Python"; exit 65; }
[[ -f "$python_real" && -x "$python_real" ]] || { failure_reason="resolved formal project Python is not executable"; exit 65; }

head_sha="$(git -C "$REPO_ROOT" rev-parse HEAD)" || { failure_reason="cannot resolve formal repository HEAD"; exit 65; }
head_tree="$(git -C "$REPO_ROOT" rev-parse 'HEAD^{tree}')" || { failure_reason="cannot resolve formal repository tree"; exit 65; }
[[ "$head_sha" == "$FORMAL_SOURCE_SHA" ]] || { failure_reason="formal repository HEAD drifted"; exit 65; }
[[ "$head_tree" == "$FORMAL_SOURCE_TREE" ]] || { failure_reason="formal repository tree drifted"; exit 65; }
if git -C "$REPO_ROOT" symbolic-ref -q HEAD >/dev/null 2>&1; then
  failure_reason="formal repository HEAD is not detached"
  exit 65
fi
[[ -z "$(git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=all)" ]] || { failure_reason="formal repository is not clean"; exit 65; }

cd "$REPO_ROOT" || { failure_reason="cannot enter formal repository"; exit 65; }
hostname_value="$(hostname)" || { failure_reason="cannot read hostname"; exit 65; }
boot_id="$(tr '[:upper:]' '[:lower:]' < /proc/sys/kernel/random/boot_id)" || { failure_reason="cannot read boot id"; exit 65; }
[[ "$hostname_value" =~ ^[A-Za-z0-9._-]+$ ]] || { failure_reason="hostname cannot be represented safely"; exit 65; }
[[ "$boot_id" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || { failure_reason="boot id is invalid"; exit 65; }

read -r wrapper_ppid wrapper_sid wrapper_tty_nr wrapper_start_ticks <<< "$(proc_stat_identity "$$")" || { failure_reason="cannot read wrapper /proc identity"; exit 65; }
wrapper_exe="$(readlink -e -- "/proc/$$/exe")" || { failure_reason="cannot read wrapper /proc executable"; exit 65; }
wrapper_cmdline_text="$(proc_cmdline_text "$$")" || { failure_reason="cannot read wrapper /proc cmdline"; exit 65; }
wrapper_cmdline_hex="$(proc_cmdline_hex "$$")" || { failure_reason="cannot encode wrapper /proc cmdline"; exit 65; }
wrapper_cmdline_sha256="$(sha256_file "/proc/$$/cmdline")" || { failure_reason="cannot hash wrapper /proc cmdline"; exit 65; }
wrapper_cwd="$(readlink -e -- "/proc/$$/cwd")" || { failure_reason="cannot read wrapper /proc cwd"; exit 65; }
[[ "$wrapper_start_ticks" =~ ^[0-9]+$ ]] || { failure_reason="wrapper /proc start ticks are invalid"; exit 65; }
[[ "$wrapper_ppid" =~ ^[0-9]+$ && "$wrapper_sid" =~ ^[0-9]+$ && "$wrapper_tty_nr" =~ ^-?[0-9]+$ ]] || { failure_reason="wrapper /proc identity is invalid"; exit 65; }
[[ "$wrapper_sid" == "$$" ]] || { failure_reason="wrapper is not the detached session leader"; exit 65; }
[[ "$wrapper_tty_nr" == "0" ]] || { failure_reason="wrapper still has a controlling TTY"; exit 65; }
[[ "$wrapper_exe" =~ ^[A-Za-z0-9_./:+\ =-]+$ ]] || { failure_reason="wrapper /proc executable cannot be represented safely"; exit 65; }
[[ "$wrapper_cmdline_text" =~ ^[A-Za-z0-9_./:+\ =-]*$ ]] || { failure_reason="wrapper /proc cmdline cannot be represented safely"; exit 65; }
[[ "$wrapper_cmdline_hex" =~ ^[0-9a-f]+$ ]] || { failure_reason="wrapper /proc cmdline encoding is invalid"; exit 65; }
[[ "$wrapper_cwd" == "$REPO_ROOT" ]] || { failure_reason="wrapper cwd drifted"; exit 65; }

wrapper_start_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "role": "wrapper",\n  "pid": %s,\n  "proc_ppid": %s,\n  "proc_sid": %s,\n  "proc_tty_nr": %s,\n  "proc_start_ticks": %s,\n  "proc_exe": "%s",\n  "proc_cmdline_text": "%s",\n  "proc_cmdline_hex": "%s",\n  "proc_cmdline_sha256": "%s",\n  "proc_cwd": "%s",\n  "hostname": "%s",\n  "boot_id": "%s",\n  "observed_utc": "%s",\n  "observed_unix": %s\n}' \
  "$run_id" "$$" "$wrapper_ppid" "$wrapper_sid" "$wrapper_tty_nr" "$wrapper_start_ticks" "$wrapper_exe" \
  "$wrapper_cmdline_text" "$wrapper_cmdline_hex" "$wrapper_cmdline_sha256" \
  "$wrapper_cwd" "$hostname_value" "$boot_id" "$wrapper_started_utc" "$wrapper_started_unix")" || { failure_reason="cannot build wrapper start record"; exit 65; }
write_atomic "$control_dir/wrapper-start.json" "$wrapper_start_json" || { failure_reason="cannot persist wrapper start record"; exit 65; }

# These regular files are intentionally separate from the outer envelope log.
# No tee or pipe can keep an SSH-owned descriptor attached to the child.
: > "$control_dir/python.stdout.log" || { failure_reason="cannot create Python stdout log"; exit 65; }
: > "$control_dir/python.stderr.log" || { failure_reason="cannot create Python stderr log"; exit 65; }
chmod 600 -- "$control_dir/python.stdout.log" "$control_dir/python.stderr.log" || { failure_reason="cannot restrict Python logs"; exit 65; }
[[ -f "$control_dir/python.stdout.log" && ! -L "$control_dir/python.stdout.log" ]] || { failure_reason="Python stdout log is not regular"; exit 65; }
[[ -f "$control_dir/python.stderr.log" && ! -L "$control_dir/python.stderr.log" ]] || { failure_reason="Python stderr log is not regular"; exit 65; }

# This is the only publish/launch process in this wrapper. Publication is not
# split from launch, and this command is never invoked a second time.
expected_python_cmdline_hex="$(printf '%s\0' \
  "./.venv/bin/python" \
  "-m" \
  "repro.aistation_clock_bracket" \
  "publish-and-launch" \
  "--bundle-dir" \
  "$bundle_dir" \
  "--suite-dir" \
  "$suite_dir" | od -An -v -tx1 | tr -d ' \n')" || { failure_reason="cannot build expected Python argv"; exit 65; }
./.venv/bin/python -m repro.aistation_clock_bracket \
  publish-and-launch \
  --bundle-dir "$bundle_dir" \
  --suite-dir "$suite_dir" \
  >"$control_dir/python.stdout.log" 2>"$control_dir/python.stderr.log" &
python_pid=$!

python_initial_identity_bound=0
for _ in $(seq 1 20); do
  initial_identity="$(proc_stat_identity "$python_pid" 2>/dev/null)" || { sleep 0.01; continue; }
  read -r initial_ppid initial_sid initial_tty_nr initial_start_ticks <<< "$initial_identity"
  if [[ "$initial_ppid" == "$$" && "$initial_start_ticks" =~ ^[0-9]+$ ]]; then
    python_initial_start_ticks="$initial_start_ticks"
    python_initial_identity_bound=1
    break
  fi
  sleep 0.01
done
if ((python_initial_identity_bound == 0)); then
  failure_reason="cannot bind initial direct-child /proc identity"
  wait_without_signal "$python_pid"
  exit 65
fi

python_identity_bound=0
for _ in $(seq 1 50); do
  first_identity="$(proc_stat_identity "$python_pid" 2>/dev/null)" || { sleep 0.02; continue; }
  read -r candidate_ppid candidate_sid candidate_tty_nr candidate_start_ticks <<< "$first_identity"
  candidate_exe="$(readlink -e -- "/proc/$python_pid/exe" 2>/dev/null)" || { sleep 0.02; continue; }
  candidate_cwd="$(readlink -e -- "/proc/$python_pid/cwd" 2>/dev/null)" || { sleep 0.02; continue; }
  candidate_cmdline_text="$(proc_cmdline_text "$python_pid" 2>/dev/null)" || { sleep 0.02; continue; }
  candidate_cmdline_hex="$(proc_cmdline_hex "$python_pid" 2>/dev/null)" || { sleep 0.02; continue; }
  candidate_cmdline_sha256="$(sha256_file "/proc/$python_pid/cmdline" 2>/dev/null)" || { sleep 0.02; continue; }
  sleep 0.01
  second_identity="$(proc_stat_identity "$python_pid" 2>/dev/null)" || { sleep 0.02; continue; }
  read -r second_ppid second_sid second_tty_nr second_start_ticks <<< "$second_identity"
  second_cmdline_hex="$(proc_cmdline_hex "$python_pid" 2>/dev/null)" || { sleep 0.02; continue; }
  if [[ "$candidate_start_ticks" =~ ^[0-9]+$ \
        && "$candidate_start_ticks" == "$second_start_ticks" \
        && "$candidate_start_ticks" == "$python_initial_start_ticks" \
        && "$candidate_ppid" == "$$" \
        && "$candidate_ppid" == "$second_ppid" \
        && "$candidate_sid" == "$second_sid" \
        && "$candidate_tty_nr" == "$second_tty_nr" \
        && "$candidate_exe" == "$python_real" \
        && "$candidate_cwd" == "$REPO_ROOT" \
        && "$candidate_cmdline_hex" == "$expected_python_cmdline_hex" \
        && "$candidate_cmdline_hex" == "$second_cmdline_hex" ]]; then
    python_ppid="$candidate_ppid"
    python_sid="$candidate_sid"
    python_tty_nr="$candidate_tty_nr"
    python_start_ticks="$candidate_start_ticks"
    python_exe="$candidate_exe"
    python_cwd="$candidate_cwd"
    python_cmdline_text="$candidate_cmdline_text"
    python_cmdline_hex="$candidate_cmdline_hex"
    python_cmdline_sha256="$candidate_cmdline_sha256"
    python_identity_bound=1
    break
  fi
  sleep 0.02
done
if ((python_identity_bound == 0)); then
  failure_reason="cannot bind exact stable Python /proc identity"
  terminate_bound_direct_child "$python_pid" "$python_initial_start_ticks" || true
  exit 65
fi

python_observed_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)" || { failure_reason="cannot read Python observation UTC time"; terminate_bound_direct_child "$python_pid" "$python_start_ticks" || true; exit 65; }
python_observed_unix="$(date -u +%s)" || { failure_reason="cannot read Python observation Unix time"; terminate_bound_direct_child "$python_pid" "$python_start_ticks" || true; exit 65; }
[[ "$python_start_ticks" =~ ^[0-9]+$ ]] || { failure_reason="Python /proc start ticks are invalid"; wait_without_signal "$python_pid"; exit 65; }
[[ "$python_ppid" == "$$" ]] || { failure_reason="Python parent PID differs from wrapper PID"; terminate_bound_direct_child "$python_pid" "$python_start_ticks" || true; exit 65; }
[[ "$python_sid" == "$wrapper_sid" && "$python_tty_nr" == "$wrapper_tty_nr" ]] || { failure_reason="Python session or TTY differs from wrapper"; terminate_bound_direct_child "$python_pid" "$python_start_ticks" || true; exit 65; }
[[ "$python_exe" =~ ^[A-Za-z0-9_./:+\ =-]+$ ]] || { failure_reason="Python /proc executable cannot be represented safely"; terminate_bound_direct_child "$python_pid" "$python_start_ticks" || true; exit 65; }
[[ "$python_cmdline_text" =~ ^[A-Za-z0-9_./:+\ =-]*$ ]] || { failure_reason="Python /proc cmdline cannot be represented safely"; terminate_bound_direct_child "$python_pid" "$python_start_ticks" || true; exit 65; }
[[ "$python_cmdline_hex" =~ ^[0-9a-f]+$ ]] || { failure_reason="Python /proc cmdline encoding is invalid"; terminate_bound_direct_child "$python_pid" "$python_start_ticks" || true; exit 65; }
[[ "$python_cwd" == "$REPO_ROOT" ]] || { failure_reason="Python cwd drifted"; terminate_bound_direct_child "$python_pid" "$python_start_ticks" || true; exit 65; }

python_start_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "role": "publish-and-launch",\n  "pid": %s,\n  "proc_ppid": %s,\n  "proc_sid": %s,\n  "proc_tty_nr": %s,\n  "proc_start_ticks": %s,\n  "proc_exe": "%s",\n  "proc_cmdline_text": "%s",\n  "proc_cmdline_hex": "%s",\n  "proc_cmdline_sha256": "%s",\n  "proc_cwd": "%s",\n  "hostname": "%s",\n  "boot_id": "%s",\n  "observed_utc": "%s",\n  "observed_unix": %s,\n  "command": ["./.venv/bin/python", "-m", "repro.aistation_clock_bracket", "publish-and-launch", "--bundle-dir", "%s", "--suite-dir", "%s"]\n}' \
  "$run_id" "$python_pid" "$python_ppid" "$python_sid" "$python_tty_nr" "$python_start_ticks" "$python_exe" \
  "$python_cmdline_text" "$python_cmdline_hex" "$python_cmdline_sha256" "$python_cwd" "$hostname_value" "$boot_id" \
  "$python_observed_utc" "$python_observed_unix" "$bundle_dir" "$suite_dir")" || { failure_reason="cannot build Python start record"; terminate_bound_direct_child "$python_pid" "$python_start_ticks" || true; exit 65; }
write_atomic "$control_dir/python-start.json" "$python_start_json" || { failure_reason="cannot persist Python start record"; terminate_bound_direct_child "$python_pid" "$python_start_ticks" || true; exit 65; }

failure_reason="publish-and-launch process returned nonzero"
wait "$python_pid"
python_exit_code=$?
if ((python_exit_code == 0)); then
  failure_reason="none"
  write_terminal "completed" "$failure_reason" || exit 74
else
  write_terminal "failed" "$failure_reason" || exit 74
fi
exit "$python_exit_code"
