import json
import os
import subprocess
from pathlib import Path

import pytest

from repro.runtime_attestation import (
    ROOT,
    _publish_exclusive_json,
    compare_attestations,
)


def _payload(hostname: str = "host-a") -> dict:
    runtime = json.loads(
        (ROOT / "repro" / "runtime_lock.json").read_text(encoding="utf-8")
    )
    return {
        "schema_version": 1,
        "captured_utc": "2026-07-29T00:00:00+00:00",
        "aistation_target": "GPU2",
        "git_sha": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            text=True,
        ).strip(),
        "git_tree": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD^{tree}"],
            text=True,
        ).strip(),
        "hostname": hostname,
        "python": "3.10.11",
        "torch": runtime["torch"],
        "torchvision": runtime["torchvision"],
        "triton": runtime["triton"],
        "causal_conv1d": runtime["causal_conv1d"],
        "torch_cxx11_abi": runtime["torch_cxx11_abi"],
        "torch_cuda_runtime": "12.6",
        "cuda_available": True,
        "cuda_device_count": 1,
        "gpu": {
            "name": "NVIDIA A800-SXM4-80GB",
            "uuid": "GPU-test",
            "driver_version": "570.00",
        },
    }


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_runtime_compare_allows_only_timestamp_and_hostname_drift(tmp_path):
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    _write(baseline, _payload("host-a"))
    changed = _payload("host-b")
    changed["captured_utc"] = "2026-07-29T01:00:00+00:00"
    _write(candidate, changed)

    compare_attestations(baseline, candidate)

    changed["gpu"]["uuid"] = "GPU-drift"
    _write(candidate, changed)
    compare_attestations(baseline, candidate)

    changed["gpu"]["driver_version"] = "571.00"
    _write(candidate, changed)
    with pytest.raises(RuntimeError, match="hardware fields drifted"):
        compare_attestations(baseline, candidate)


def test_runtime_attestation_publication_is_exclusive(tmp_path):
    path = tmp_path / "attestation.json"
    _publish_exclusive_json(path, _payload())
    assert path.stat().st_nlink == 1

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        _publish_exclusive_json(path, _payload())


def test_runtime_compare_rejects_symlink_input(tmp_path):
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    symlink = tmp_path / "candidate-link.json"
    _write(baseline, _payload())
    _write(candidate, _payload())
    os.symlink(candidate, symlink)

    with pytest.raises(RuntimeError, match="symlink"):
        compare_attestations(baseline, symlink)
