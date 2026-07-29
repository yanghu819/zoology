#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"

export UV_CACHE_DIR="${ROOT}/.cache/uv"
export XDG_CACHE_HOME="${ROOT}/.cache/xdg"
export XDG_CONFIG_HOME="${ROOT}/.cache/xdg-config"
export XDG_DATA_HOME="${ROOT}/.cache/xdg-data"
export TORCH_HOME="${ROOT}/.cache/torch"
export TORCH_EXTENSIONS_DIR="${ROOT}/.cache/torch-extensions"
export TRITON_CACHE_DIR="${ROOT}/.cache/triton"
export HF_HOME="${ROOT}/.cache/huggingface"
export TMPDIR="${ROOT}/.cache/tmp"
export ZOOLOGY_DATA_CACHE="${ROOT}/data/mqar-cache"
export PYTHONPATH="${ROOT}/vendor/flash-linear-attention:${ROOT}"

mkdir -p \
  "${UV_CACHE_DIR}" \
  "${XDG_CACHE_HOME}" \
  "${XDG_CONFIG_HOME}" \
  "${XDG_DATA_HOME}" \
  "${TORCH_HOME}" \
  "${TORCH_EXTENSIONS_DIR}" \
  "${TRITON_CACHE_DIR}" \
  "${HF_HOME}" \
  "${TMPDIR}" \
  "${ZOOLOGY_DATA_CACHE}"

"${ROOT}/.venv/bin/python" -m repro.prewarm_cache
