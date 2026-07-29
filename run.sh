#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:-}"
EXPECTED_SHA="${ZOOLOGY_EXPECTED_GIT_SHA:-}"
cd "${ROOT}"

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
  if [[ -n "$(git -C "${ROOT}" status --porcelain --untracked-files=no)" ]]; then
    echo "formal execution requires a clean tracked worktree" >&2
    return 1
  fi
  [[ "${AISTATION_TARGET:-}" == "GPU2" ]] || {
    echo "AISTATION_TARGET must be the literal GPU2" >&2
    return 1
  }
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
    SUITE_DIR="$(realpath -m "${3:?run-one requires a suite directory}")"
    if [[ "${SUITE_DIR}" == "${ROOT}/runs" || "${SUITE_DIR}" != "${ROOT}/runs/"* ]]; then
      echo "suite directory must be a child of ${ROOT}/runs" >&2
      exit 1
    fi
    /usr/bin/timeout --signal=TERM --kill-after=60s 10800s \
      "${ROOT}/.venv/bin/python" -m repro.run_one \
      --index "${INDEX}" \
      --suite-dir "${SUITE_DIR}"
    ;;
  full)
    require_source_contract
    "${ROOT}/down.sh"
    SUITE_ID="gdn-mqar-official-$(date -u +%Y%m%dT%H%M%SZ)-${EXPECTED_SHA:0:12}"
    SUITE_DIR="${ROOT}/runs/${SUITE_ID}"
    mkdir -p "${SUITE_DIR}/logs"
    git -C "${ROOT}" archive HEAD | gzip -n > "${SUITE_DIR}/source.tar.gz"
    sha256sum "${SUITE_DIR}/source.tar.gz" > "${SUITE_DIR}/source.tar.gz.sha256"
    cp "${ZOOLOGY_DATA_CACHE}/manifest.json" "${SUITE_DIR}/cache-manifest.json"
    sha256sum "${SUITE_DIR}/cache-manifest.json" \
      > "${SUITE_DIR}/cache-manifest.json.sha256"
    nvidia-smi -q > "${SUITE_DIR}/nvidia-smi.txt"
    for index in $(seq 0 11); do
      "${ROOT}/run.sh" run-one "${index}" "${SUITE_DIR}" \
        > "${SUITE_DIR}/logs/run-$(printf '%02d' "${index}").log" 2>&1
    done
    "${ROOT}/.venv/bin/python" -m repro.aggregate --suite-dir "${SUITE_DIR}"
    printf 'suite_dir=%s\n' "${SUITE_DIR}"
    ;;
  *)
    echo "usage: $0 {check|cache|smoke|run-one INDEX SUITE_DIR|full}" >&2
    exit 2
    ;;
esac
