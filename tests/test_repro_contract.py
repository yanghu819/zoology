import json
import math
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from repro.cache_contract import (
    OFFICIAL_CONFIG_SHA256,
    frozen_cache_provenance,
    sha256_file,
    validate_manifest,
)
from repro.config_serialization import dump_full_config
from repro.configs.gdn_mqar_official import configs
from repro.numeric_contract import require_finite
from repro.suite_contract import (
    build_suite_manifest,
    next_pending_index,
    validate_admission,
)


ROOT = Path(__file__).resolve().parents[1]


def _runtime_attestation(hostname: str) -> dict:
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


def _write_hash_sidecar(path: Path) -> None:
    path.with_name(path.name + ".sha256").write_text(
        f"{sha256_file(path)}  {path.name}\n",
        encoding="utf-8",
    )


def _make_empty_suite(tmp_path: Path) -> tuple[Path, dict]:
    suite_dir = tmp_path / "suite"
    (suite_dir / "logs").mkdir(parents=True)
    (suite_dir / "claims").mkdir()
    (suite_dir / "launches").mkdir()
    source_path = suite_dir / "source.tar.gz"
    source_path.write_bytes(b"frozen source")
    _write_hash_sidecar(source_path)
    cache_manifest_path = suite_dir / "cache-manifest.json"
    cache_manifest_path.write_text('{"frozen": true}\n', encoding="utf-8")
    _write_hash_sidecar(cache_manifest_path)
    nvidia_path = suite_dir / "nvidia-smi.txt"
    nvidia_path.write_text("A800\n", encoding="utf-8")
    runtime_path = suite_dir / "runtime-attestation.json"
    runtime_path.write_text(
        json.dumps(_runtime_attestation("baseline")),
        encoding="utf-8",
    )
    manifest = build_suite_manifest(
        sha256_file(source_path),
        sha256_file(cache_manifest_path),
        sha256_file(nvidia_path),
        sha256_file(runtime_path),
    )
    (suite_dir / "suite-manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return suite_dir, manifest


def _write_completed_cell(suite_dir: Path, manifest: dict, index: int) -> None:
    config = configs[index]
    run_dir = suite_dir / (
        f"{index:02d}__d{config.model.d_model}"
        f"__lr{float(config.learning_rate):.10g}"
    )
    (suite_dir / "claims" / f"run-{index:02d}").mkdir()
    runtime_attestation_path = (
        suite_dir
        / "claims"
        / f"run-{index:02d}"
        / "runtime-attestation.json"
    )
    runtime_attestation_path.write_text(
        json.dumps(_runtime_attestation("candidate")),
        encoding="utf-8",
    )
    run_dir.mkdir()
    metadata = {
        "schema_version": 1,
        "index": index,
        "d_model": config.model.d_model,
        "learning_rate": float(config.learning_rate),
        "seed": config.seed,
        "upstream_result_snapshot": (
            "b386338b37ce46a9257afc0a64786b0dc5a37676"
        ),
        "vendored_fla_sha": "d30c0833f9286bd5bf43c20395db53c6bab97a2d",
        "runtime_attestation_sha256": sha256_file(runtime_attestation_path),
        **{
            key: manifest[key]
            for key in (
                "git_sha",
                "git_tree",
                "official_config_sha256",
                "cache_manifest_sha256",
                "runtime_lock_sha256",
                "uv_lock_sha256",
            )
        },
    }
    (suite_dir / f"run-{index:02d}-metadata.json").write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )
    (run_dir / "summary.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "elapsed_seconds": 1.0,
                "best_valid_accuracy": 0.5,
                "final_metrics": {"valid/accuracy": 0.5},
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "resolved-config.json").write_text(
        json.dumps(dump_full_config(config)),
        encoding="utf-8",
    )
    state_sizes = {64: 17_152, 128: 67_072, 256: 265_216}
    (run_dir / "model-metadata.json").write_text(
        json.dumps(
            {
                "num_parameters": 1,
                "state_size": state_sizes[int(config.model.d_model)],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "metrics.jsonl").write_text(
        '{"valid/accuracy": 0.5}\n',
        encoding="utf-8",
    )
    (suite_dir / "logs" / f"run-{index:02d}.log").write_text(
        "completed\n",
        encoding="utf-8",
    )
    launch_dir = suite_dir / "launches" / f"run-{index:02d}"
    launch_dir.mkdir()
    command = [str(ROOT / "run.sh"), "_cell-worker", str(index)]
    (launch_dir / "request.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "requested",
                "cell_index": index,
                "suite_dir": str(suite_dir.resolve()),
                "command": command,
            }
        ),
        encoding="utf-8",
    )
    (launch_dir / "launch.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "launched",
                "cell_index": index,
                "worker_pid": 123,
                "suite_dir": str(suite_dir.resolve()),
                "command": command,
                "expected_git_sha": subprocess.check_output(
                    ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                    text=True,
                ).strip(),
                "aistation_target": "GPU2",
            }
        ),
        encoding="utf-8",
    )
    (launch_dir / "worker.pid").write_text("123\n", encoding="utf-8")
    (launch_dir / "launcher.log").write_text("completed\n", encoding="utf-8")
    (launch_dir / "terminal.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "completed",
                "cell_index": index,
                "worker_pid": 123,
                "exit_code": 0,
            }
        ),
        encoding="utf-8",
    )


def _write_active_launch(suite_dir: Path, index: int) -> None:
    launch_dir = suite_dir / "launches" / f"run-{index:02d}"
    launch_dir.mkdir()
    command = [
        str(ROOT / "run.sh"),
        "_cell-worker",
        str(index),
        str(suite_dir.resolve()),
        str(launch_dir.resolve()),
    ]
    request = {
        "schema_version": 1,
        "state": "requested",
        "cell_index": index,
        "suite_dir": str(suite_dir.resolve()),
        "command": command,
    }
    launch = {
        "schema_version": 1,
        "state": "launched",
        "cell_index": index,
        "worker_pid": 123,
        "suite_dir": str(suite_dir.resolve()),
        "command": command,
        "expected_git_sha": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            text=True,
        ).strip(),
        "aistation_target": "GPU2",
    }
    (launch_dir / "request.json").write_text(
        json.dumps(request),
        encoding="utf-8",
    )
    (launch_dir / "launch.json").write_text(
        json.dumps(launch),
        encoding="utf-8",
    )
    (launch_dir / "worker.pid").write_text("123\n", encoding="utf-8")
    (launch_dir / "launcher.log").write_text("worker started\n", encoding="utf-8")


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


def test_setup_uses_hash_checked_local_wheels_offline():
    setup = (ROOT / "setup.sh").read_text(encoding="utf-8")
    assert "requests-2.34.2-py3-none-any.whl" in setup
    assert (
        "2a0d60c172f83ac6ab31e4554906c0f3b3588d37b5cb939b1c061f4907e278e0"
        in setup
    )
    assert "causal_conv1d-1.5.3.post1+cu12torch2.7" in setup
    assert (
        "3a60ede12aa2bcd0e0cd435956bb65a9d85260381c9d99ea4c45551e3174b894"
        in setup
    )
    assert "--offline" in setup
    assert "--find-links" in setup
    assert "--no-install-project" in setup
    assert "curl " not in setup


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
    provenance = replace(
        frozen_cache_provenance(),
        cache_dir=tmp_path.resolve(),
    )
    entries = []
    for index, name in enumerate(provenance.filenames):
        path = tmp_path / name
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
        "cache_dir": str(tmp_path.resolve()),
        "official_config_sha256": OFFICIAL_CONFIG_SHA256,
        "generation_seed": provenance.generation_seed,
        "torch_version": provenance.torch_version,
        "git_sha": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            text=True,
        ).strip(),
        "git_tree": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD^{tree}"],
            text=True,
        ).strip(),
        "files": entries,
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    validate_manifest(
        tmp_path,
        provenance=provenance,
        repo_root=ROOT,
    )

    (tmp_path / provenance.filenames[0]).write_bytes(b"drift")
    with pytest.raises(RuntimeError, match="cache size drift|cache hash drift"):
        validate_manifest(
            tmp_path,
            provenance=provenance,
            repo_root=ROOT,
        )


def test_nonfinite_metrics_fail_closed():
    require_finite({"loss": 1.0, "epoch": 0})
    for value in (math.nan, math.inf, -math.inf):
        with pytest.raises(FloatingPointError):
            require_finite({"loss": value})


def test_admission_requires_full_cell_timeout_plus_buffer():
    assert validate_admission(11_460, 1_000, now_unix=1_000) == 11_460
    with pytest.raises(RuntimeError, match="insufficient AIStation time"):
        validate_admission(11_459, 1_000, now_unix=1_000)
    with pytest.raises(ValueError, match="nonnegative"):
        validate_admission(-1, 1_000, now_unix=1_000)
    with pytest.raises(ValueError, match="cannot be lower"):
        validate_admission(11_460, 1_000, 11_459, now_unix=1_000)
    assert validate_admission(11_500, 1_000, now_unix=1_040) == 11_460
    with pytest.raises(RuntimeError, match="observation is stale"):
        validate_admission(12_500, 1_000, now_unix=1_601)


def test_resume_advances_only_past_validated_completed_cells(tmp_path):
    suite_dir, manifest = _make_empty_suite(tmp_path)
    assert next_pending_index(suite_dir) == 0

    _write_completed_cell(suite_dir, manifest, 0)
    assert next_pending_index(suite_dir) == 1


def test_resume_rejects_base_type_truncated_config_archive(tmp_path):
    suite_dir, manifest = _make_empty_suite(tmp_path)
    _write_completed_cell(suite_dir, manifest, 0)
    config = configs[0]
    run_dir = suite_dir / (
        f"00__d{config.model.d_model}"
        f"__lr{float(config.learning_rate):.10g}"
    )
    (run_dir / "resolved-config.json").write_text(
        json.dumps(config.model_dump(mode="json")),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="resolved config drift"):
        next_pending_index(suite_dir)


def test_suite_manifest_must_be_self_contained_regular_file(tmp_path):
    suite_dir, _ = _make_empty_suite(tmp_path)
    manifest_path = suite_dir / "suite-manifest.json"
    outside = tmp_path / "outside-suite-manifest.json"
    manifest_path.rename(outside)
    manifest_path.symlink_to(outside)

    with pytest.raises(RuntimeError, match="not a regular file"):
        next_pending_index(suite_dir)


def test_resume_fails_closed_on_partial_cell(tmp_path):
    suite_dir, manifest = _make_empty_suite(tmp_path)
    _write_completed_cell(suite_dir, manifest, 0)
    (suite_dir / "run-01-metadata.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match=r"cell 1 is partial, failed, or invalid"):
        next_pending_index(suite_dir)


def test_worker_accepts_only_its_pristine_active_launch(tmp_path):
    suite_dir, _ = _make_empty_suite(tmp_path)
    _write_active_launch(suite_dir, 0)

    with pytest.raises(RuntimeError, match=r"cell 0 is partial, failed, or invalid"):
        next_pending_index(suite_dir)
    assert next_pending_index(suite_dir, active_launch_index=0) == 0


def test_worker_rejects_broken_cell_log_symlink(tmp_path):
    suite_dir, _ = _make_empty_suite(tmp_path)
    _write_active_launch(suite_dir, 0)
    (suite_dir / "logs" / "run-00.log").symlink_to(
        tmp_path / "outside-missing.log"
    )

    with pytest.raises(RuntimeError, match="already has cell evidence"):
        next_pending_index(suite_dir, active_launch_index=0)


def test_resume_fails_closed_on_recorded_failure(tmp_path):
    suite_dir, manifest = _make_empty_suite(tmp_path)
    _write_completed_cell(suite_dir, manifest, 0)
    config = configs[1]
    run_dir = suite_dir / (
        f"01__d{config.model.d_model}"
        f"__lr{float(config.learning_rate):.10g}"
    )
    run_dir.mkdir()
    (run_dir / "failure.json").write_text(
        '{"status": "failed"}\n',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match=r"cell 1.*failure record"):
        next_pending_index(suite_dir)


def test_resume_rejects_model_metadata_missing_num_parameters(tmp_path):
    suite_dir, manifest = _make_empty_suite(tmp_path)
    _write_completed_cell(suite_dir, manifest, 0)
    config = configs[0]
    run_dir = suite_dir / (
        f"00__d{config.model.d_model}"
        f"__lr{float(config.learning_rate):.10g}"
    )
    (run_dir / "model-metadata.json").write_text(
        json.dumps({"state_size": 17_152}),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="model metadata is incomplete"):
        next_pending_index(suite_dir)


def test_resume_rejects_unexpected_cell_metadata(tmp_path):
    suite_dir, _ = _make_empty_suite(tmp_path)
    (suite_dir / "run-99-metadata.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="unexpected cell metadata"):
        next_pending_index(suite_dir)


def test_resume_rejects_missing_terminal_record(tmp_path):
    suite_dir, manifest = _make_empty_suite(tmp_path)
    _write_completed_cell(suite_dir, manifest, 0)
    (suite_dir / "launches" / "run-00" / "terminal.json").unlink()

    with pytest.raises(RuntimeError, match="terminal.json"):
        next_pending_index(suite_dir)


def test_resume_rejects_failed_terminal_record(tmp_path):
    suite_dir, manifest = _make_empty_suite(tmp_path)
    _write_completed_cell(suite_dir, manifest, 0)
    terminal_path = suite_dir / "launches" / "run-00" / "terminal.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    terminal["state"] = "failed"
    terminal["exit_code"] = 1
    terminal_path.write_text(json.dumps(terminal), encoding="utf-8")

    with pytest.raises(RuntimeError, match="launch/terminal contract mismatch"):
        next_pending_index(suite_dir)


def test_resume_rejects_run_directory_symlink(tmp_path):
    suite_dir, manifest = _make_empty_suite(tmp_path)
    _write_completed_cell(suite_dir, manifest, 0)
    config = configs[0]
    run_dir = suite_dir / (
        f"00__d{config.model.d_model}"
        f"__lr{float(config.learning_rate):.10g}"
    )
    outside = tmp_path / "outside-run"
    run_dir.rename(outside)
    run_dir.symlink_to(outside, target_is_directory=True)

    with pytest.raises(RuntimeError, match="not a real directory"):
        next_pending_index(suite_dir)
