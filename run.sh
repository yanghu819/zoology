#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:-}"
EXPECTED_SHA="${ZOOLOGY_EXPECTED_GIT_SHA:-}"
cd "${ROOT}"

PYTHONDONTWRITEBYTECODE=1 python3 "${ROOT}/repro/path_contract.py" \
  --root "${ROOT}" \
  --require-environments \
  --validate-source

export UV_CACHE_DIR="${ROOT}/.cache/uv"
export XDG_CACHE_HOME="${ROOT}/.cache/xdg"
export XDG_CONFIG_HOME="${ROOT}/.cache/xdg-config"
export XDG_DATA_HOME="${ROOT}/.cache/xdg-data"
export PIP_CACHE_DIR="${ROOT}/.cache/pip"
export TORCH_HOME="${ROOT}/.cache/torch"
export TORCH_EXTENSIONS_DIR="${ROOT}/.cache/torch-extensions"
export TRITON_CACHE_DIR="${ROOT}/.cache/triton"
export HF_HOME="${ROOT}/.cache/huggingface"
export TRANSFORMERS_CACHE="${HF_HOME}/transformers"
export WANDB_MODE="offline"
export WANDB_DIR="${ROOT}/wandb"
export WANDB_CACHE_DIR="${ROOT}/.cache/wandb"
export WANDB_CONFIG_DIR="${ROOT}/.cache/wandb-config"
export WANDB_DATA_DIR="${ROOT}/.cache/wandb-data"
export WANDB_ARTIFACT_DIR="${ROOT}/artifacts/wandb"
export CUDA_CACHE_PATH="${ROOT}/.cache/cuda"
export TMPDIR="${ROOT}/.cache/tmp"
export PYTHONPYCACHEPREFIX="${ROOT}/.cache/pycache"
export ZOOLOGY_DATA_CACHE="${ROOT}/data/mqar-cache"
export PYTHONPATH="${ROOT}/vendor/flash-linear-attention:${ROOT}"
export CUDA_VISIBLE_DEVICES="0"

mkdir -p \
  "${UV_CACHE_DIR}" \
  "${XDG_CACHE_HOME}" \
  "${XDG_CONFIG_HOME}" \
  "${XDG_DATA_HOME}" \
  "${PIP_CACHE_DIR}" \
  "${TORCH_HOME}" \
  "${TORCH_EXTENSIONS_DIR}" \
  "${TRITON_CACHE_DIR}" \
  "${HF_HOME}" \
  "${WANDB_DIR}" \
  "${WANDB_CACHE_DIR}" \
  "${WANDB_CONFIG_DIR}" \
  "${WANDB_DATA_DIR}" \
  "${WANDB_ARTIFACT_DIR}" \
  "${CUDA_CACHE_PATH}" \
  "${TMPDIR}" \
  "${ROOT}/runs"

require_source_contract() {
  local actual_sha
  if [[ "${ROOT}" != "/huyang2/zoology" ]]; then
    echo "formal execution requires ROOT=/huyang2/zoology, got ${ROOT}" >&2
    return 1
  fi
  actual_sha="$(git -C "${ROOT}" rev-parse HEAD)"
  if [[ -z "${EXPECTED_SHA}" || "${actual_sha}" != "${EXPECTED_SHA}" ]]; then
    echo "expected exact ZOOLOGY_EXPECTED_GIT_SHA, got expected=${EXPECTED_SHA:-unset} actual=${actual_sha}" >&2
    return 1
  fi
  if git -C "${ROOT}" symbolic-ref -q HEAD >/dev/null; then
    echo "formal execution requires detached HEAD" >&2
    return 1
  fi
  if [[ -n "$(git -C "${ROOT}" status --porcelain)" ]]; then
    echo "formal execution requires a clean worktree, including untracked source" >&2
    return 1
  fi
  [[ "${AISTATION_TARGET:-}" == "GPU2" ]] || {
    echo "AISTATION_TARGET must be the literal GPU2" >&2
    return 1
  }
}

resolve_suite_dir() {
  local suite_dir
  suite_dir="$(realpath -m "${1:?suite directory is required}")"
  if [[
    "${suite_dir}" == "${ROOT}/runs" ||
    "${suite_dir}" != "${ROOT}/runs/"*
  ]]; then
    echo "suite directory must be a child of ${ROOT}/runs" >&2
    return 1
  fi
  printf '%s\n' "${suite_dir}"
}

reject_single_baseline_dir() {
  local suite_dir
  suite_dir="${1:?suite directory is required}"
  if [[
    -e "${suite_dir}/single-baseline-manifest.json" ||
    -L "${suite_dir}/single-baseline-manifest.json"
  ]]; then
    echo "single baseline directory requires the baseline commands" >&2
    return 1
  fi
}

require_cell_admission() {
  local remaining_seconds observed_unix minimum_seconds
  require_cell_admission_inputs
  remaining_seconds="${ZOOLOGY_REMAINING_SECONDS}"
  observed_unix="${ZOOLOGY_REMAINING_OBSERVED_UNIX}"
  minimum_seconds="${ZOOLOGY_MIN_REMAINING_SECONDS:-11460}"
  "${ROOT}/.venv/bin/python" -m repro.suite_contract admit \
    --remaining-seconds "${remaining_seconds}" \
    --observed-unix "${observed_unix}" \
    --minimum-seconds "${minimum_seconds}"
}

require_cell_admission_inputs() {
  if [[ -z "${ZOOLOGY_REMAINING_SECONDS:-}" ]]; then
    echo "set ZOOLOGY_REMAINING_SECONDS from a fresh AIStation status response" >&2
    return 1
  fi
  if [[ -z "${ZOOLOGY_REMAINING_OBSERVED_UNIX:-}" ]]; then
    echo "set ZOOLOGY_REMAINING_OBSERVED_UNIX when remainTime is observed" >&2
    return 1
  fi
}

format_cell_index() {
  local raw_index decimal_index
  raw_index="${1:?cell index is required}"
  if [[ ! "${raw_index}" =~ ^[0-9]+$ ]]; then
    echo "cell index must be an integer in [0, 11], got ${raw_index}" >&2
    return 1
  fi
  decimal_index="$((10#${raw_index}))"
  if (( decimal_index < 0 || decimal_index > 11 )); then
    echo "cell index must be in [0, 11], got ${raw_index}" >&2
    return 1
  fi
  printf '%02d\n' "${decimal_index}"
}

finalize_cell_worker() {
  local worker_exit="$?"
  local status_exit
  local worker_admission_sha256
  local -a terminal_args
  trap - EXIT
  set +e
  terminal_args=(
    --launch-dir "${LAUNCH_DIR}"
    --index "${INDEX}"
    --worker-pid "$$"
    --exit-code "${worker_exit}"
  )
  if [[
    -n "${ZOOLOGY_WORKER_ADMISSION_PATH:-}" &&
    -f "${ZOOLOGY_WORKER_ADMISSION_PATH}" &&
    ! -L "${ZOOLOGY_WORKER_ADMISSION_PATH}"
  ]]; then
    worker_admission_sha256="$(
      sha256sum "${ZOOLOGY_WORKER_ADMISSION_PATH}" | awk '{print $1}'
    )"
    terminal_args+=(--worker-admission-sha256 "${worker_admission_sha256}")
  fi
  "${ROOT}/.venv/bin/python" -m repro.cell_launcher terminal \
    "${terminal_args[@]}"
  status_exit="$?"
  if (( status_exit != 0 && worker_exit == 0 )); then
    worker_exit=74
  fi
  exit "${worker_exit}"
}

case "${MODE}" in
  check)
    "${ROOT}/setup.sh" --check
    ;;
  cache)
    "${ROOT}/down.sh"
    ;;
  smoke)
    SMOKE_ID="smoke-$(date -u +%Y%m%dT%H%M%SZ)"
    export ZOOLOGY_SMOKE_DIR="${ROOT}/runs/${SMOKE_ID}"
    "${ROOT}/.venv/bin/python" -m repro.smoke
    ;;
  run-one)
    require_source_contract
    INDEX="${2:?run-one requires an index 0..11}"
    INDEX="$((10#$(format_cell_index "${INDEX}")))"
    SUITE_DIR="$(resolve_suite_dir "${3:?run-one requires a suite directory}")"
    reject_single_baseline_dir "${SUITE_DIR}"
    "${ROOT}/setup.sh" --check
    "${ROOT}/.venv/bin/python" -m repro.suite_contract prepare-cell \
      --index "${INDEX}" \
      --suite-dir "${SUITE_DIR}"
    require_cell_admission
    CELL_ID="$(format_cell_index "${INDEX}")"
    CLAIM_PATH="${SUITE_DIR}/claims/run-${CELL_ID}"
    mkdir "${CLAIM_PATH}"
    export ZOOLOGY_RUNTIME_ATTESTATION_PATH="${CLAIM_PATH}/runtime-attestation.json"
    "${ROOT}/.venv/bin/python" -m repro.runtime_attestation capture \
      --output "${ZOOLOGY_RUNTIME_ATTESTATION_PATH}"
    "${ROOT}/.venv/bin/python" -m repro.runtime_attestation compare \
      --baseline "${SUITE_DIR}/runtime-attestation.json" \
      --candidate "${ZOOLOGY_RUNTIME_ATTESTATION_PATH}"
    LOG_PATH="${SUITE_DIR}/logs/run-${CELL_ID}.log"
    printf 'cell=%s log=%s\n' "${INDEX}" "${LOG_PATH}"
    /usr/bin/timeout --signal=TERM --kill-after=60s 10800s \
      "${ROOT}/.venv/bin/python" -m repro.run_one \
      --index "${INDEX}" \
      --suite-dir "${SUITE_DIR}" \
      > "${LOG_PATH}" 2>&1
    ;;
  run-one-baseline)
    require_source_contract
    INDEX="${2:?run-one-baseline requires the selected index}"
    INDEX="$((10#$(format_cell_index "${INDEX}")))"
    SUITE_DIR="$(resolve_suite_dir "${3:?run-one-baseline requires a suite directory}")"
    "${ROOT}/setup.sh" --check
    "${ROOT}/.venv/bin/python" -m repro.single_baseline prepare \
      --index "${INDEX}" \
      --suite-dir "${SUITE_DIR}"
    "${ROOT}/.venv/bin/python" -m repro.single_baseline admit-worker \
      --suite-dir "${SUITE_DIR}" \
      --remaining-seconds "${ZOOLOGY_REMAINING_SECONDS}" \
      --observed-unix "${ZOOLOGY_REMAINING_OBSERVED_UNIX}"
    CELL_ID="$(format_cell_index "${INDEX}")"
    CLAIM_PATH="${SUITE_DIR}/claims/run-${CELL_ID}"
    mkdir "${CLAIM_PATH}"
    export ZOOLOGY_RUNTIME_ATTESTATION_PATH="${CLAIM_PATH}/runtime-attestation.json"
    "${ROOT}/.venv/bin/python" -m repro.runtime_attestation capture \
      --output "${ZOOLOGY_RUNTIME_ATTESTATION_PATH}"
    "${ROOT}/.venv/bin/python" -m repro.runtime_attestation compare \
      --baseline "${SUITE_DIR}/runtime-attestation.json" \
      --candidate "${ZOOLOGY_RUNTIME_ATTESTATION_PATH}"
    LOG_PATH="${SUITE_DIR}/logs/run-${CELL_ID}.log"
    printf 'baseline_cell=%s log=%s\n' "${INDEX}" "${LOG_PATH}"
    /usr/bin/timeout --signal=TERM --kill-after=60s 10800s \
      "${ROOT}/.venv/bin/python" -m repro.run_one \
      --index "${INDEX}" \
      --suite-dir "${SUITE_DIR}" \
      > "${LOG_PATH}" 2>&1
    ;;
  init-suite)
    require_source_contract
    "${ROOT}/setup.sh" --check
    "${ROOT}/down.sh"
    if [[ -n "${2:-}" ]]; then
      SUITE_DIR="$(resolve_suite_dir "${2}")"
    else
      SUITE_ID="gdn-mqar-official-$(date -u +%Y%m%dT%H%M%SZ)-${EXPECTED_SHA:0:12}"
      SUITE_DIR="${ROOT}/runs/${SUITE_ID}"
    fi
    mkdir "${SUITE_DIR}"
    mkdir "${SUITE_DIR}/logs"
    mkdir "${SUITE_DIR}/claims"
    mkdir "${SUITE_DIR}/launches"
    git -C "${ROOT}" archive HEAD | gzip -n > "${SUITE_DIR}/source.tar.gz"
    sha256sum "${SUITE_DIR}/source.tar.gz" > "${SUITE_DIR}/source.tar.gz.sha256"
    cp "${ZOOLOGY_DATA_CACHE}/manifest.json" "${SUITE_DIR}/cache-manifest.json"
    sha256sum "${SUITE_DIR}/cache-manifest.json" \
      > "${SUITE_DIR}/cache-manifest.json.sha256"
    nvidia-smi -q > "${SUITE_DIR}/nvidia-smi.txt"
    "${ROOT}/.venv/bin/python" -m repro.runtime_attestation capture \
      --output "${SUITE_DIR}/runtime-attestation.json"
    "${ROOT}/.venv/bin/python" -m repro.suite_contract initialize \
      --suite-dir "${SUITE_DIR}"
    printf 'suite_dir=%s\n' "${SUITE_DIR}"
    ;;
  init-baseline)
    require_source_contract
    INDEX=5
    if [[ -n "${3:-}" ]]; then
      echo "init-baseline accepts at most one suite-directory argument" >&2
      exit 2
    fi
    if [[ -n "${2:-}" ]]; then
      SUITE_DIR="$(resolve_suite_dir "${2}")"
    else
      BASELINE_ID="gdn-mqar-single-baseline-$(date -u +%Y%m%dT%H%M%SZ)-${EXPECTED_SHA:0:12}"
      SUITE_DIR="${ROOT}/runs/${BASELINE_ID}"
    fi
    "${ROOT}/run.sh" init-suite "${SUITE_DIR}"
    "${ROOT}/.venv/bin/python" -m repro.single_baseline initialize \
      --suite-dir "${SUITE_DIR}"
    printf 'baseline_dir=%s selected_index=%s\n' "${SUITE_DIR}" "${INDEX}"
    ;;
  resume)
    require_source_contract
    SUITE_DIR="$(resolve_suite_dir "${2:?resume requires a suite directory}")"
    reject_single_baseline_dir "${SUITE_DIR}"
    INDEX="$(
      "${ROOT}/.venv/bin/python" -m repro.suite_contract next-index \
        --suite-dir "${SUITE_DIR}"
    )"
    if [[ "${INDEX}" == "complete" ]]; then
      printf 'suite_complete=%s\n' "${SUITE_DIR}"
      exit 0
    fi
    require_cell_admission
    "${ROOT}/.venv/bin/python" -m repro.cell_launcher launch \
      --root "${ROOT}" \
      --index "${INDEX}" \
      --suite-dir "${SUITE_DIR}"
    ;;
  launch-baseline)
    require_source_contract
    SUITE_DIR="$(resolve_suite_dir "${2:?launch-baseline requires a suite directory}")"
    INDEX="$(
      "${ROOT}/.venv/bin/python" -m repro.single_baseline selected-index \
        --suite-dir "${SUITE_DIR}"
    )"
    require_cell_admission_inputs
    "${ROOT}/.venv/bin/python" -m repro.single_baseline admit-controller \
      --suite-dir "${SUITE_DIR}" \
      --remaining-seconds "${ZOOLOGY_REMAINING_SECONDS}" \
      --observed-unix "${ZOOLOGY_REMAINING_OBSERVED_UNIX}"
    export ZOOLOGY_BASELINE_MANIFEST_SHA256="$(
      sha256sum "${SUITE_DIR}/single-baseline-manifest.json" | awk '{print $1}'
    )"
    export ZOOLOGY_CONTROLLER_ADMISSION_SHA256="$(
      sha256sum "${SUITE_DIR}/controller-admission.json" | awk '{print $1}'
    )"
    export ZOOLOGY_CONTROLLER_MIN_REMAINING_SECONDS=12060
    export ZOOLOGY_MIN_REMAINING_SECONDS=11460
    "${ROOT}/.venv/bin/python" -m repro.cell_launcher launch \
      --root "${ROOT}" \
      --index "${INDEX}" \
      --suite-dir "${SUITE_DIR}" \
      --worker-mode "_baseline-worker"
    ;;
  _cell-worker)
    INDEX="${2:?internal cell worker requires an index}"
    INDEX="$((10#$(format_cell_index "${INDEX}")))"
    CELL_ID="$(format_cell_index "${INDEX}")"
    SUITE_DIR="$(resolve_suite_dir "${3:?internal cell worker requires a suite directory}")"
    reject_single_baseline_dir "${SUITE_DIR}"
    LAUNCH_DIR="$(realpath -m "${4:?internal cell worker requires a launch directory}")"
    if [[ "${LAUNCH_DIR}" != "${SUITE_DIR}/launches/run-${CELL_ID}" ]]; then
      echo "worker launch directory does not match suite/index" >&2
      exit 1
    fi
    trap finalize_cell_worker EXIT
    for _ in $(seq 1 100); do
      if [[ -f "${LAUNCH_DIR}/launch.json" && -f "${LAUNCH_DIR}/worker.pid" ]]; then
        break
      fi
      sleep 0.1
    done
    if [[ ! -f "${LAUNCH_DIR}/launch.json" || ! -f "${LAUNCH_DIR}/worker.pid" ]]; then
      echo "launcher handshake did not complete" >&2
      exit 70
    fi
    "${ROOT}/.venv/bin/python" -m repro.cell_launcher verify-worker \
      --launch-dir "${LAUNCH_DIR}" \
      --suite-dir "${SUITE_DIR}" \
      --index "${INDEX}" \
      --worker-pid "$$"
    require_source_contract
    "${ROOT}/run.sh" run-one "${INDEX}" "${SUITE_DIR}"
    "${ROOT}/.venv/bin/python" -m repro.suite_contract validate-artifacts \
      --index "${INDEX}" \
      --suite-dir "${SUITE_DIR}"
    ;;
  _baseline-worker)
    INDEX="${2:?internal baseline worker requires an index}"
    INDEX="$((10#$(format_cell_index "${INDEX}")))"
    CELL_ID="$(format_cell_index "${INDEX}")"
    SUITE_DIR="$(resolve_suite_dir "${3:?internal baseline worker requires a suite directory}")"
    LAUNCH_DIR="$(realpath -m "${4:?internal baseline worker requires a launch directory}")"
    export ZOOLOGY_WORKER_ADMISSION_PATH="${LAUNCH_DIR}/worker-admission.json"
    if [[ "${LAUNCH_DIR}" != "${SUITE_DIR}/launches/run-${CELL_ID}" ]]; then
      echo "baseline worker launch directory does not match suite/index" >&2
      exit 1
    fi
    trap finalize_cell_worker EXIT
    for _ in $(seq 1 100); do
      if [[ -f "${LAUNCH_DIR}/launch.json" && -f "${LAUNCH_DIR}/worker.pid" ]]; then
        break
      fi
      sleep 0.1
    done
    if [[ ! -f "${LAUNCH_DIR}/launch.json" || ! -f "${LAUNCH_DIR}/worker.pid" ]]; then
      echo "baseline launcher handshake did not complete" >&2
      exit 70
    fi
    "${ROOT}/.venv/bin/python" -m repro.cell_launcher verify-worker \
      --launch-dir "${LAUNCH_DIR}" \
      --suite-dir "${SUITE_DIR}" \
      --index "${INDEX}" \
      --worker-pid "$$"
    require_source_contract
    "${ROOT}/run.sh" run-one-baseline "${INDEX}" "${SUITE_DIR}"
    "${ROOT}/.venv/bin/python" -m repro.suite_contract validate-artifacts \
      --index "${INDEX}" \
      --suite-dir "${SUITE_DIR}"
    ;;
  aggregate)
    require_source_contract
    SUITE_DIR="$(resolve_suite_dir "${2:?aggregate requires a suite directory}")"
    reject_single_baseline_dir "${SUITE_DIR}"
    "${ROOT}/.venv/bin/python" -m repro.suite_contract assert-complete \
      --suite-dir "${SUITE_DIR}"
    "${ROOT}/.venv/bin/python" -m repro.aggregate --suite-dir "${SUITE_DIR}"
    printf 'suite_dir=%s\n' "${SUITE_DIR}"
    ;;
  finalize-baseline)
    require_source_contract
    SUITE_DIR="$(resolve_suite_dir "${2:?finalize-baseline requires a suite directory}")"
    "${ROOT}/.venv/bin/python" -m repro.single_baseline finalize \
      --suite-dir "${SUITE_DIR}"
    ;;
  validate-baseline)
    require_source_contract
    SUITE_DIR="$(resolve_suite_dir "${2:?validate-baseline requires a suite directory}")"
    "${ROOT}/.venv/bin/python" -m repro.single_baseline validate-result \
      --suite-dir "${SUITE_DIR}"
    ;;
  full)
    echo "full is disabled on expiring AIStation sessions" >&2
    echo "use init-suite, then refresh remainTime and call resume once per cell" >&2
    echo "after all 12 validated cells, call aggregate" >&2
    exit 2
    ;;
  *)
    echo "usage: $0 {check|cache|smoke|init-suite [SUITE_DIR]|resume SUITE_DIR|" >&2
    echo "          run-one INDEX SUITE_DIR|aggregate SUITE_DIR|" >&2
    echo "          init-baseline [SUITE_DIR]|launch-baseline SUITE_DIR|" >&2
    echo "          finalize-baseline SUITE_DIR|validate-baseline SUITE_DIR}" >&2
    exit 2
    ;;
esac
