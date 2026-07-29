#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${ROOT}/.venv"
CAUSAL_WHEEL="${ROOT}/wheels/causal_conv1d-1.5.3.post1+cu12torch2.7cxx11abiTRUE-cp310-cp310-linux_x86_64.whl"
CAUSAL_WHEEL_URL="https://github.com/Dao-AILab/causal-conv1d/releases/download/v1.5.3.post1/causal_conv1d-1.5.3.post1%2Bcu12torch2.7cxx11abiTRUE-cp310-cp310-linux_x86_64.whl"
CAUSAL_WHEEL_SHA256="3a60ede12aa2bcd0e0cd435956bb65a9d85260381c9d99ea4c45551e3174b894"
cd "${ROOT}"

export UV_CACHE_DIR="${ROOT}/.cache/uv"
export XDG_CACHE_HOME="${ROOT}/.cache/xdg"
export XDG_CONFIG_HOME="${ROOT}/.cache/xdg-config"
export XDG_DATA_HOME="${ROOT}/.cache/xdg-data"
export PIP_CACHE_DIR="${ROOT}/.cache/pip"
export TORCH_EXTENSIONS_DIR="${ROOT}/.cache/torch-extensions"
export CUDA_CACHE_PATH="${ROOT}/.cache/cuda"
export TMPDIR="${ROOT}/.cache/tmp"
export PYTHONPATH="${ROOT}/vendor/flash-linear-attention:${ROOT}"

mkdir -p \
  "${UV_CACHE_DIR}" \
  "${XDG_CACHE_HOME}" \
  "${XDG_CONFIG_HOME}" \
  "${XDG_DATA_HOME}" \
  "${PIP_CACHE_DIR}" \
  "${TORCH_EXTENSIONS_DIR}" \
  "${CUDA_CACHE_PATH}" \
  "${TMPDIR}" \
  "${ROOT}/artifacts" \
  "${ROOT}/data" \
  "${ROOT}/models" \
  "${ROOT}/predictions" \
  "${ROOT}/runs" \
  "${ROOT}/wandb" \
  "${ROOT}/wheels"

if [[ "${1:-}" != "--check" ]]; then
  uv venv --python /opt/conda/bin/python --system-site-packages "${VENV}"
  uv sync --frozen --extra build --extra test

  if [[ ! -f "${CAUSAL_WHEEL}" ]]; then
    echo "downloading pinned causal-conv1d wheel into project-local wheels/" >&2
    curl --fail --location --retry 3 \
      --output "${CAUSAL_WHEEL}.partial" \
      "${CAUSAL_WHEEL_URL}"
    mv "${CAUSAL_WHEEL}.partial" "${CAUSAL_WHEEL}"
  fi
  printf '%s  %s\n' "${CAUSAL_WHEEL_SHA256}" "${CAUSAL_WHEEL}" | sha256sum --check -
  uv pip install \
    --python "${VENV}/bin/python" \
    --no-build-isolation \
    --no-deps \
    --reinstall \
    "${CAUSAL_WHEEL}"
fi

"${VENV}/bin/python" - <<'PY'
import importlib.metadata
import json
from pathlib import Path
import sys

import causal_conv1d
import torch
import torchvision
import triton

root = Path.cwd()
lock = json.loads((root / "repro" / "runtime_lock.json").read_text())
assert sys.version.startswith(lock["python_prefix"]), (
    sys.version,
    lock["python_prefix"],
)
assert torch.__version__ == lock["torch"], (torch.__version__, lock["torch"])
assert triton.__version__ == lock["triton"], (triton.__version__, lock["triton"])
assert bool(torch._C._GLIBCXX_USE_CXX11_ABI) == lock["torch_cxx11_abi"]
assert importlib.metadata.version("causal-conv1d") == lock["causal_conv1d"]
assert torch.cuda.is_available()
assert torch.cuda.device_count() == 1, torch.cuda.device_count()
print(
    "runtime_check=pass",
    f"python={__import__('sys').version.split()[0]}",
    f"torch={torch.__version__}",
    f"torchvision={torchvision.__version__}",
    f"triton={triton.__version__}",
    f"causal_conv1d={getattr(causal_conv1d, '__version__', 'unknown')}",
    f"gpu={torch.cuda.get_device_name(0)}",
)
PY

"${VENV}/bin/python" -m repro.validate_contract
