#!/usr/bin/env bash

set -u
set -o pipefail

REPO_ROOT="/huyang2/zoology"
PYTHON="$REPO_ROOT/.venv/bin/python"
FORMAL_SOURCE_SHA="13f880b5fe61619a1006ef33610de69fbabaaec1"
FORMAL_SOURCE_TREE="ed83a7188351ca2cce8aba46d1cb3b108ce31ec2"
STARTER_NAME="durable_publish_launch_start.sh"
WRAPPER_NAME="durable_publish_launch_wrapper.sh"
CONTROL_NAME="formal-launch-control"

usage() {
  printf '%s\n' \
    "usage: $0 --starter-sha256 SHA256 --wrapper PATH --wrapper-sha256 SHA256 --bundle-dir PATH --suite-dir PATH --control-dir PATH" >&2
  exit 64
}

die() {
  printf 'durable publish-and-launch starter: %s\n' "$1" >&2
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

starter_sha256=""
wrapper=""
wrapper_sha256=""
bundle_dir=""
suite_dir=""
control_dir=""

while (($#)); do
  (($# >= 2)) || usage
  case "$1" in
    --starter-sha256)
      [[ -z "$starter_sha256" ]] || usage
      starter_sha256="$2"
      ;;
    --wrapper)
      [[ -z "$wrapper" ]] || usage
      wrapper="$2"
      ;;
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

[[ -n "$starter_sha256" && -n "$wrapper" && -n "$wrapper_sha256" && -n "$bundle_dir" && -n "$suite_dir" && -n "$control_dir" ]] || usage
[[ "$starter_sha256" =~ ^[0-9a-f]{64}$ ]] || die "starter SHA256 must be 64 lowercase hexadecimal characters"
[[ "$wrapper_sha256" =~ ^[0-9a-f]{64}$ ]] || die "wrapper SHA256 must be 64 lowercase hexadecimal characters"

suite_prefix="$REPO_ROOT/runs/"
[[ "$suite_dir" == "$suite_prefix"* ]] || die "suite directory is outside the formal repository"
run_id="${suite_dir#"$suite_prefix"}"
[[ "$run_id" =~ ^[a-z0-9][a-z0-9-]*$ ]] || die "suite directory has an invalid run id"
[[ "$suite_dir" == "$REPO_ROOT/runs/$run_id" ]] || die "suite directory is not the canonical run path"
[[ "$bundle_dir" == "$REPO_ROOT/artifacts/$run_id/controller" ]] || die "bundle directory is not the canonical controller path"
[[ "$control_dir" == "$REPO_ROOT/artifacts/$run_id/$CONTROL_NAME" ]] || die "control directory is not the canonical durable-control path"
starter="$REPO_ROOT/artifacts/$run_id/launcher/$STARTER_NAME"
[[ "$0" == "$starter" ]] || die "starter is not the canonical uploaded artifact"
[[ "$wrapper" == "$REPO_ROOT/artifacts/$run_id/launcher/$WRAPPER_NAME" ]] || die "wrapper is not the canonical uploaded artifact"

require_real_directory "$REPO_ROOT" "formal repository"
require_real_directory "$bundle_dir" "clock capture bundle"
require_real_directory "$suite_dir" "single-baseline suite"
require_real_directory "${control_dir%/*}" "run artifact directory"
require_real_directory "${wrapper%/*}" "launcher artifact directory"
[[ -f "$0" && ! -L "$0" ]] || die "starter is not a real regular file"
[[ "$(realpath -e -- "$0")" == "$starter" ]] || die "starter uses a symlink or path alias"
[[ -f "$wrapper" && ! -L "$wrapper" ]] || die "wrapper is not a real regular file"
[[ "$(realpath -e -- "$wrapper")" == "$wrapper" ]] || die "wrapper uses a symlink or path alias"
[[ -x "$PYTHON" ]] || die "formal project Python is not executable"
nohup_path="$(command -v nohup)" || die "nohup is unavailable"
setsid_path="$(command -v setsid)" || die "setsid is unavailable"
bash_path="$(command -v bash)" || die "bash is unavailable"
nohup_path="$(realpath -e -- "$nohup_path")" || die "cannot resolve nohup"
setsid_path="$(realpath -e -- "$setsid_path")" || die "cannot resolve setsid"
bash_path="$(realpath -e -- "$bash_path")" || die "cannot resolve bash"
[[ -f "$nohup_path" && -x "$nohup_path" ]] || die "resolved nohup is not executable"
[[ -f "$setsid_path" && -x "$setsid_path" ]] || die "resolved setsid is not executable"
[[ -f "$bash_path" && -x "$bash_path" ]] || die "resolved bash is not executable"

head_sha="$(git -C "$REPO_ROOT" rev-parse HEAD)" || die "cannot resolve formal repository HEAD"
head_tree="$(git -C "$REPO_ROOT" rev-parse 'HEAD^{tree}')" || die "cannot resolve formal repository tree"
[[ "$head_sha" == "$FORMAL_SOURCE_SHA" ]] || die "formal repository HEAD drifted: $head_sha"
[[ "$head_tree" == "$FORMAL_SOURCE_TREE" ]] || die "formal repository tree drifted: $head_tree"
if git -C "$REPO_ROOT" symbolic-ref -q HEAD >/dev/null 2>&1; then
  die "formal repository HEAD is not detached"
fi
[[ -z "$(git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=all)" ]] || die "formal repository is not clean"

actual_starter_sha256="$(sha256_file "$0")" || die "cannot hash starter"
[[ "$actual_starter_sha256" == "$starter_sha256" ]] || die "starter SHA256 differs from the frozen value"
actual_wrapper_sha256="$(sha256_file "$wrapper")" || die "cannot hash wrapper"
[[ "$actual_wrapper_sha256" == "$wrapper_sha256" ]] || die "wrapper SHA256 differs from the frozen value"

# This mkdir deliberately has no -p. Its existence permanently consumes the
# one allowed start attempt for this run id.
mkdir -- "$control_dir" || die "durable control directory already exists; start attempt is consumed"
require_real_directory "$control_dir" "durable control directory"
chmod 700 -- "$control_dir" || die "cannot restrict durable control directory"

wrapper_snapshot="$control_dir/wrapper-snapshot.sh"
(
  umask 077
  cp -- "$wrapper" "$wrapper_snapshot"
) || die "cannot snapshot the frozen wrapper"
chmod 500 -- "$wrapper_snapshot" || die "cannot make wrapper snapshot executable"
snapshot_sha256="$(sha256_file "$wrapper_snapshot")" || die "cannot hash wrapper snapshot"
[[ "$snapshot_sha256" == "$wrapper_sha256" ]] || die "wrapper snapshot SHA256 drifted"

starter_started_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)" || die "cannot read starter UTC time"
starter_started_unix="$(date -u +%s)" || die "cannot read starter Unix time"
hostname_value="$(hostname)" || die "cannot read hostname"
boot_id="$(tr '[:upper:]' '[:lower:]' < /proc/sys/kernel/random/boot_id)" || die "cannot read boot id"
[[ "$hostname_value" =~ ^[A-Za-z0-9._-]+$ ]] || die "hostname cannot be represented safely"
[[ "$boot_id" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || die "boot id is invalid"

attempt_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "formal_source_sha": "%s",\n  "formal_source_tree": "%s",\n  "bundle_dir": "%s",\n  "suite_dir": "%s",\n  "control_dir": "%s",\n  "starter_source": "%s",\n  "starter_sha256": "%s",\n  "wrapper_source": "%s",\n  "wrapper_snapshot": "%s",\n  "wrapper_sha256": "%s",\n  "starter_pid": %s,\n  "starter_started_utc": "%s",\n  "starter_started_unix": %s,\n  "hostname": "%s",\n  "boot_id": "%s"\n}' \
  "$run_id" "$FORMAL_SOURCE_SHA" "$FORMAL_SOURCE_TREE" "$bundle_dir" "$suite_dir" "$control_dir" \
  "$starter" "$starter_sha256" "$wrapper" "$wrapper_snapshot" "$wrapper_sha256" "$$" "$starter_started_utc" "$starter_started_unix" \
  "$hostname_value" "$boot_id")" || die "cannot build durable attempt record"
write_atomic "$control_dir/attempt.json" "$attempt_json" || die "cannot persist durable attempt record"

: > "$control_dir/envelope.log" || die "cannot create envelope log"
chmod 600 -- "$control_dir/envelope.log" || die "cannot restrict envelope log"
[[ -f "$control_dir/envelope.log" && ! -L "$control_dir/envelope.log" ]] || die "envelope log is not regular"

cd "$REPO_ROOT" || die "cannot enter formal repository"
"$nohup_path" "$setsid_path" --fork --wait "$bash_path" "$wrapper_snapshot" \
  --wrapper-sha256 "$wrapper_sha256" \
  --bundle-dir "$bundle_dir" \
  --suite-dir "$suite_dir" \
  --control-dir "$control_dir" \
  </dev/null >"$control_dir/envelope.log" 2>&1 &
envelope_supervisor_pid=$!
[[ "$envelope_supervisor_pid" =~ ^[0-9]+$ ]] || die "nohup did not return an envelope supervisor PID"

start_recorded_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)" || die "cannot read start-record UTC time"
start_recorded_unix="$(date -u +%s)" || die "cannot read start-record Unix time"
start_json="$(printf '{\n  "schema_version": 1,\n  "run_id": "%s",\n  "envelope_supervisor_pid": %s,\n  "nohup_path": "%s",\n  "setsid_path": "%s",\n  "bash_path": "%s",\n  "starter_sha256": "%s",\n  "wrapper_sha256": "%s",\n  "stdin": "/dev/null",\n  "envelope_log": "%s",\n  "start_recorded_utc": "%s",\n  "start_recorded_unix": %s\n}' \
  "$run_id" "$envelope_supervisor_pid" "$nohup_path" "$setsid_path" "$bash_path" \
  "$starter_sha256" "$wrapper_sha256" "$control_dir/envelope.log" \
  "$start_recorded_utc" "$start_recorded_unix")" || die "cannot build durable start record"
write_atomic "$control_dir/start.json" "$start_json" || die "cannot persist durable start record"

printf '{"control_dir":"%s","envelope_supervisor_pid":%s,"run_id":"%s","starter_sha256":"%s","wrapper_sha256":"%s"}\n' \
  "$control_dir" "$envelope_supervisor_pid" "$run_id" "$starter_sha256" "$wrapper_sha256"
