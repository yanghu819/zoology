import json
import math
from pathlib import Path

import pytest

from repro.cache_contract import (
    OFFICIAL_CONFIG_SHA256,
    sha256_file,
    validate_manifest,
)
from repro.configs.gdn_mqar_official import configs
from repro.numeric_contract import require_finite


ROOT = Path(__file__).resolve().parents[1]


def test_exact_official_grid():
    assert len(configs) == 12
    assert {config.model.d_model for config in configs} == {64, 128, 256}
    assert {
        round(float(config.learning_rate), 12) for config in configs
    } == {
        round(value, 12)
        for value in (1e-3, 10**-2.5, 1e-2, 10**-1.5)
    }


def test_all_persistent_paths_are_project_local():
    assert all(
        Path(config.data.cache_dir).is_relative_to(ROOT)
        for config in configs
    )
    runtime = json.loads(
        (ROOT / "repro" / "runtime_lock.json").read_text(encoding="utf-8")
    )
    assert runtime["remote_root"] == "/huyang2/zoology"


def test_official_baseline_does_not_invent_exact_scores():
    baseline = json.loads(
        (ROOT / "repro" / "official_baseline.json").read_text(encoding="utf-8")
    )
    assert baseline["official_exact_accuracy_available"] is False
    assert all(
        point["official_accuracy_exact"] is None
        for point in baseline["plot_points"]
    )
    assert baseline["uncommitted_plot_point"]["included_in_reproduction"] is False


def test_cache_manifest_rejects_content_drift(tmp_path):
    entries = []
    for index in range(12):
        path = tmp_path / f"data_{index:02d}.pt"
        path.write_bytes(f"frozen-{index}".encode())
        entries.append(
            {
                "name": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    manifest = {
        "schema_version": 1,
        "origin": "generated_by_frozen_prewarm",
        "official_config_sha256": OFFICIAL_CONFIG_SHA256,
        "files": entries,
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    validate_manifest(tmp_path)

    (tmp_path / "data_00.pt").write_bytes(b"drift")
    with pytest.raises(RuntimeError, match="cache size drift|cache hash drift"):
        validate_manifest(tmp_path)


def test_nonfinite_metrics_fail_closed():
    require_finite({"loss": 1.0, "epoch": 0})
    for value in (math.nan, math.inf, -math.inf):
        with pytest.raises(FloatingPointError):
            require_finite({"loss": value})
