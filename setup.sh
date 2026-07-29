#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${ROOT}/.venv"
UV_BOOTSTRAP="${ROOT}/.cache/uv-bootstrap"
UV_BIN="${UV_BOOTSTRAP}/bin/uv"
UV_VERSION="0.9.27"
WHEELHOUSE_EXPECTED_COUNT="52"
UV_WHEEL="${ROOT}/wheels/uv-0.9.27-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
UV_WHEEL_SHA256="79939f7e92d707fb84933509df747d1b88b00d94ebe41f3a1e30916cc33c7307"
REQUESTS_WHEEL="${ROOT}/wheels/requests-2.34.2-py3-none-any.whl"
REQUESTS_WHEEL_SHA256="2a0d60c172f83ac6ab31e4554906c0f3b3588d37b5cb939b1c061f4907e278e0"
CAUSAL_WHEEL="${ROOT}/wheels/causal_conv1d-1.5.3.post1-cp310-cp310-linux_x86_64.whl"
CAUSAL_WHEEL_SHA256="3a5ebc4f7f41ab94aee533f16fb14b4f974589cedee78061f6f55a3ec422ea8a"
LOCKED_REQUIREMENTS="${ROOT}/.cache/control/uv-lock-requirements.txt"
cd "${ROOT}"

PYTHONDONTWRITEBYTECODE=1 python3 "${ROOT}/repro/path_contract.py" \
  --root "${ROOT}" \
  --validate-source

export UV_CACHE_DIR="${ROOT}/.cache/uv"
export XDG_CACHE_HOME="${ROOT}/.cache/xdg"
export XDG_CONFIG_HOME="${ROOT}/.cache/xdg-config"
export XDG_DATA_HOME="${ROOT}/.cache/xdg-data"
export PIP_CACHE_DIR="${ROOT}/.cache/pip"
export TORCH_EXTENSIONS_DIR="${ROOT}/.cache/torch-extensions"
export CUDA_CACHE_PATH="${ROOT}/.cache/cuda"
export TMPDIR="${ROOT}/.cache/tmp"
export PYTHONPYCACHEPREFIX="${ROOT}/.cache/pycache"
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
  "${ROOT}/.cache/control" \
  "${ROOT}/artifacts" \
  "${ROOT}/checkpoints" \
  "${ROOT}/data" \
  "${ROOT}/models" \
  "${ROOT}/predictions" \
  "${ROOT}/runs" \
  "${ROOT}/wandb" \
  "${ROOT}/wheels"

WHEELHOUSE_ACTUAL_COUNT="$(
  find "${ROOT}/wheels" -maxdepth 1 -type f -name '*.whl' | wc -l | tr -d ' '
)"
if [[ "${WHEELHOUSE_ACTUAL_COUNT}" != "${WHEELHOUSE_EXPECTED_COUNT}" ]]; then
  echo "incomplete locked wheelhouse: expected=${WHEELHOUSE_EXPECTED_COUNT} actual=${WHEELHOUSE_ACTUAL_COUNT}" >&2
  exit 1
fi
for wheel in "${UV_WHEEL}" "${REQUESTS_WHEEL}" "${CAUSAL_WHEEL}"; do
  if [[ ! -f "${wheel}" ]]; then
    echo "missing locally supplied locked wheel: ${wheel}" >&2
    exit 1
  fi
done
printf '%s  %s\n' "${UV_WHEEL_SHA256}" "${UV_WHEEL}" | sha256sum --check -
printf '%s  %s\n' "${REQUESTS_WHEEL_SHA256}" "${REQUESTS_WHEEL}" | sha256sum --check -
printf '%s  %s\n' "${CAUSAL_WHEEL_SHA256}" "${CAUSAL_WHEEL}" | sha256sum --check -

if [[ ! -x "${UV_BIN}" ]]; then
  if [[ "${1:-}" == "--check" ]]; then
    echo "project-local pinned uv is missing: ${UV_BIN}" >&2
    exit 1
  else
    /opt/conda/bin/python -m venv --system-site-packages "${UV_BOOTSTRAP}"
    "${UV_BOOTSTRAP}/bin/python" -m pip install \
      --no-index \
      --no-deps \
      --no-cache-dir \
      "${UV_WHEEL}"
  fi
fi
UV_ACTUAL="$("${UV_BIN}" --version)"
if [[
  "${UV_ACTUAL}" != "uv ${UV_VERSION}" &&
  "${UV_ACTUAL}" != "uv ${UV_VERSION} "*
]]; then
  echo "uv version mismatch: expected=${UV_VERSION} actual=${UV_ACTUAL}" >&2
  exit 1
fi

if [[ "${1:-}" != "--check" ]]; then
  if [[ ! -x "${VENV}/bin/python" ]]; then
    "${UV_BIN}" venv \
      --python /opt/conda/bin/python \
      --system-site-packages \
      "${VENV}"
  fi
  LOCKED_REQUIREMENTS_TMP="$(
    mktemp "${ROOT}/.cache/control/uv-lock-requirements.XXXXXX"
  )"
  trap 'rm -f -- "${LOCKED_REQUIREMENTS_TMP}"' EXIT
  "${UV_BIN}" export \
    --frozen \
    --offline \
    --all-extras \
    --no-emit-project \
    --format requirements-txt \
    --output-file "${LOCKED_REQUIREMENTS_TMP}"
  mv -f -- "${LOCKED_REQUIREMENTS_TMP}" "${LOCKED_REQUIREMENTS}"
  trap - EXIT
  "${UV_BIN}" pip sync \
    --python "${VENV}/bin/python" \
    --require-hashes \
    --offline \
    --no-cache \
    --no-index \
    --only-binary :all: \
    --find-links "${ROOT}/wheels" \
    "${LOCKED_REQUIREMENTS}"
  "${UV_BIN}" pip install \
    --python "${VENV}/bin/python" \
    --no-build-isolation \
    --no-deps \
    --reinstall \
    "${CAUSAL_WHEEL}"
else
  if [[ ! -x "${VENV}/bin/python" ]]; then
    echo "project-local virtual environment is missing: ${VENV}" >&2
    exit 1
  fi
  "${UV_BIN}" sync \
    --frozen \
    --offline \
    --no-install-project \
    --inexact \
    --check \
    --extra build \
    --extra test
fi

PYTHONDONTWRITEBYTECODE=1 python3 "${ROOT}/repro/path_contract.py" \
  --root "${ROOT}" \
  --require-environments \
  --validate-source

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
assert torchvision.__version__ == lock["torchvision"], (
    torchvision.__version__,
    lock["torchvision"],
)
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
