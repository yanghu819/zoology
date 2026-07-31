import hashlib
import json
import math
import subprocess
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

import repro.aistation_clock_bracket as clock_bracket
from repro.aistation_clock_bracket import (
    REMOTE_CLOCK_COMMAND,
    SUITE_CLOCK_FILE_MAP,
    build_evidence,
)
from repro.cache_contract import (
    OFFICIAL_CONFIG_SHA256,
    frozen_cache_provenance,
    sha256_file,
    validate_manifest,
)
from repro.config_serialization import dump_full_config
from repro.configs.gdn_mqar_official import configs
from repro.numeric_contract import require_finite
from repro.single_baseline import (
    AISTATION_STATUS_NAME,
    BASELINE_RESULT_NAME,
    CONTROLLER_ADMISSION_FLOOR,
    CONTROLLER_ADMISSION_NAME,
    WORKER_ADMISSION_FLOOR,
    WORKER_ADMISSION_NAME,
    finalize_baseline,
    initialize_baseline,
    record_admission,
    validate_baseline,
    validate_result,
)
from repro.suite_contract import (
    build_suite_manifest,
    next_pending_index,
    prepare_cell,
    validate_admission,
)


ROOT = Path(__file__).resolve().parents[1]
TEST_CLOCK_HELPER_SNAPSHOT = (
    b"// immutable test AIStation helper snapshot\n"
)


@pytest.fixture(autouse=True)
def _resolve_precommit_clock_source(monkeypatch):
    current_tree = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD^{tree}"],
        text=True,
    ).strip()
    monkeypatch.setattr(
        clock_bracket,
        "_resolve_formal_source",
        lambda _formal_source_sha: current_tree,
    )
    monkeypatch.setattr(
        clock_bracket,
        "APPROVED_HELPER_SHA256",
        hashlib.sha256(TEST_CLOCK_HELPER_SNAPSHOT).hexdigest(),
    )


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


def _make_empty_suite(
    tmp_path: Path,
    suite_name: str = "suite",
) -> tuple[Path, dict]:
    suite_dir = tmp_path / suite_name
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


def _write_completed_cell(
    suite_dir: Path,
    manifest: dict,
    index: int,
    worker_mode: str = "_cell-worker",
) -> None:
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
    baseline_fields = {}
    baseline_launch_fields = {}
    requested_utc = "2026-07-30T00:00:00+00:00"
    launched_utc = "2026-07-30T00:00:01+00:00"
    if worker_mode == "_baseline-worker":
        controller_admission = json.loads(
            (suite_dir / CONTROLLER_ADMISSION_NAME).read_text(encoding="utf-8")
        )
        requested_utc = controller_admission["checked_utc"]
        launched_utc = controller_admission["checked_utc"]
        baseline_fields = {
            "baseline_manifest_sha256": sha256_file(
                suite_dir / "single-baseline-manifest.json"
            ),
            "controller_admission_sha256": sha256_file(
                suite_dir / CONTROLLER_ADMISSION_NAME
            ),
        }
        baseline_launch_fields = {
            "reported_remaining_seconds": str(
                controller_admission["reported_remaining_seconds"]
            ),
            "remaining_observed_unix": str(
                controller_admission["observed_unix"]
            ),
            "minimum_remaining_seconds": str(WORKER_ADMISSION_FLOOR),
            "controller_minimum_remaining_seconds": str(
                CONTROLLER_ADMISSION_FLOOR
            ),
        }
    command = [
        str(ROOT / "run.sh"),
        worker_mode,
        str(index),
        str(suite_dir.resolve()),
        str(launch_dir.resolve()),
    ]
    (launch_dir / "request.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "state": "requested",
                "cell_index": index,
                "requested_utc": requested_utc,
                "suite_dir": str(suite_dir.resolve()),
                "worker_mode": worker_mode,
                **baseline_fields,
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
                "launched_utc": launched_utc,
                "suite_dir": str(suite_dir.resolve()),
                "worker_mode": worker_mode,
                **baseline_fields,
                "launcher_log": str((launch_dir / "launcher.log").resolve()),
                "cell_log": str(
                    (
                        suite_dir
                        / "logs"
                        / f"run-{index:02d}.log"
                    ).resolve()
                ),
                "terminal_record": str(
                    (launch_dir / "terminal.json").resolve()
                ),
                "command": command,
                "expected_git_sha": subprocess.check_output(
                    ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                    text=True,
                ).strip(),
                "aistation_target": "GPU2",
                **baseline_launch_fields,
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
                "ended_utc": "2026-07-30T00:00:02+00:00",
            }
        ),
        encoding="utf-8",
    )


def _write_active_launch(
    suite_dir: Path,
    index: int,
    worker_mode: str = "_cell-worker",
) -> None:
    launch_dir = suite_dir / "launches" / f"run-{index:02d}"
    launch_dir.mkdir()
    command = [
        str(ROOT / "run.sh"),
        worker_mode,
        str(index),
        str(suite_dir.resolve()),
        str(launch_dir.resolve()),
    ]
    request = {
        "schema_version": 1,
        "state": "requested",
        "cell_index": index,
        "suite_dir": str(suite_dir.resolve()),
        "worker_mode": worker_mode,
        "command": command,
    }
    launch = {
        "schema_version": 1,
        "state": "launched",
        "cell_index": index,
        "worker_pid": 123,
        "suite_dir": str(suite_dir.resolve()),
        "worker_mode": worker_mode,
        "command": command,
        "expected_git_sha": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            text=True,
        ).strip(),
        "aistation_target": "GPU2",
        **(
            {
                "minimum_remaining_seconds": "11460",
                "controller_minimum_remaining_seconds": "12060",
            }
            if worker_mode == "_baseline-worker"
            else {}
        ),
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
    runtime = json.loads(
        (ROOT / "repro" / "runtime_lock.json").read_text(encoding="utf-8")
    )
    assert (
        "uv-0.9.27-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
        in setup
    )
    assert (
        "79939f7e92d707fb84933509df747d1b88b00d94ebe41f3a1e30916cc33c7307"
        in setup
    )
    assert "requests-2.34.2-py3-none-any.whl" in setup
    assert (
        "2a0d60c172f83ac6ab31e4554906c0f3b3588d37b5cb939b1c061f4907e278e0"
        in setup
    )
    assert runtime["causal_conv1d_wheel"] in setup
    assert runtime["causal_conv1d_wheel_sha256"] in setup
    assert runtime["causal_conv1d_sdist"] == "causal_conv1d-1.5.3.post1.tar.gz"
    assert (
        runtime["causal_conv1d_sdist_sha256"]
        == "aba1b717484472d0b2f2e40520a1c03f35fe5155555bd753d1c324afc56ba468"
    )
    assert "--offline" in setup
    assert "--no-cache" in setup
    assert "--no-index" in setup
    assert "--only-binary :all:" in setup
    assert "--find-links" in setup
    assert "--require-hashes" in setup
    assert "--no-install-project" in setup
    assert "--inexact" in setup
    assert 'WHEELHOUSE_EXPECTED_COUNT="52"' in setup
    assert '"uv==${UV_VERSION}"' not in setup
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


def _canonical_json_bytes(payload: dict) -> bytes:
    return (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )


def _clock_exec_payload(observed_unix: int) -> dict:
    return {
        "command": "exec",
        "ok": True,
        "targets": [
            {
                "wpName": "GPU2",
                "wpId": "workspace-test-gpu2",
                "wpStatus": "Running",
                "exec": {
                    "ok": True,
                    "exitCode": 0,
                    "stdout": (
                        "HOST=baseline\n"
                        "BOOT_ID=12345678-1234-1234-1234-123456789abc\n"
                        f"UNIX={observed_unix}\n"
                    ),
                },
            }
        ],
        "actions": [],
    }


def _write_clock_evidence(
    suite_dir: Path,
    remaining_seconds: int,
    observed_unix: int,
) -> None:
    suite_manifest = json.loads(
        (suite_dir / "suite-manifest.json").read_text(encoding="utf-8")
    )
    status_payload = {
        "command": "status",
        "ok": True,
        "targets": [
            {
                "wpName": "GPU2",
                "wpId": "workspace-test-gpu2",
                "wpStatus": "Running",
                "image": "test-image",
                "resource": "GPU:1",
                "remainTime": str(remaining_seconds),
            }
        ],
        "actions": [],
    }
    before_payload = _clock_exec_payload(observed_unix)
    after_payload = _clock_exec_payload(observed_unix + 1)
    before_raw = _canonical_json_bytes(before_payload)
    status_raw = _canonical_json_bytes(status_payload)
    after_raw = _canonical_json_bytes(after_payload)
    helper_snapshot = TEST_CLOCK_HELPER_SNAPSHOT
    helper_sha256 = hashlib.sha256(helper_snapshot).hexdigest()
    module_sha256 = sha256_file(
        ROOT / "repro" / "aistation_clock_bracket.py"
    )
    capture_started_utc = datetime.fromtimestamp(
        observed_unix,
        timezone.utc,
    ).isoformat()
    capture_ended_utc = datetime.fromtimestamp(
        observed_unix + 1,
        timezone.utc,
    ).isoformat()
    proof = build_evidence(
        before_payload,
        before_raw,
        status_payload,
        status_raw,
        after_payload,
        after_raw,
        run_id=suite_dir.name,
        formal_source_sha=suite_manifest["git_sha"],
        formal_source_tree=suite_manifest["git_tree"],
        helper_sha256=helper_sha256,
        module_sha256=module_sha256,
        capture_started_utc=capture_started_utc,
        capture_ended_utc=capture_ended_utc,
        capture_elapsed_seconds=1.0,
    )
    attempt = {
        "schema_version": 1,
        "run_id": suite_dir.name,
        "formal_source_sha": suite_manifest["git_sha"],
        "formal_source_tree": suite_manifest["git_tree"],
        "target": "GPU2",
        "helper_sha256": helper_sha256,
        "module_sha256": module_sha256,
        "capture_started_utc": capture_started_utc,
    }
    captured = {
        "capture-attempt.json": _canonical_json_bytes(attempt),
        "helper-snapshot.js": helper_snapshot,
        "remote-before.json": before_raw,
        "aistation-status.json": status_raw,
        "remote-after.json": after_raw,
        "clock-bracket.json": _canonical_json_bytes(proof),
    }
    terminal = {
        "schema_version": 1,
        "run_id": suite_dir.name,
        "formal_source_sha": suite_manifest["git_sha"],
        "formal_source_tree": suite_manifest["git_tree"],
        "status": "completed",
        "capture_ended_utc": capture_ended_utc,
        "files_sha256": {
            name: hashlib.sha256(raw).hexdigest()
            for name, raw in captured.items()
        },
        "error_type": None,
        "error": None,
    }
    captured["capture-terminal.json"] = _canonical_json_bytes(terminal)
    assert set(captured) == set(SUITE_CLOCK_FILE_MAP)
    for capture_name, suite_name in SUITE_CLOCK_FILE_MAP.items():
        (suite_dir / suite_name).write_bytes(captured[capture_name])


def _make_completed_single_baseline(tmp_path: Path) -> Path:
    suite_dir, suite_manifest = _make_empty_suite(tmp_path)
    initialize_baseline(suite_dir, 5)
    remaining_seconds = 13_000
    observed_unix = math.ceil(time.time())
    _write_clock_evidence(suite_dir, remaining_seconds, observed_unix)
    record_admission(
        suite_dir,
        "controller",
        remaining_seconds,
        observed_unix,
    )
    _write_completed_cell(
        suite_dir,
        suite_manifest,
        5,
        worker_mode="_baseline-worker",
    )
    record_admission(
        suite_dir,
        "worker",
        remaining_seconds,
        observed_unix,
    )
    terminal_path = suite_dir / "launches" / "run-05" / "terminal.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    worker_admission = json.loads(
        (
            suite_dir
            / "launches"
            / "run-05"
            / WORKER_ADMISSION_NAME
        ).read_text(encoding="utf-8")
    )
    terminal["ended_utc"] = worker_admission["checked_utc"]
    terminal["worker_admission_sha256"] = sha256_file(
        suite_dir / "launches" / "run-05" / WORKER_ADMISSION_NAME
    )
    terminal_path.write_text(json.dumps(terminal), encoding="utf-8")
    config = configs[5]
    run_dir = suite_dir / (
        f"05__d{config.model.d_model}"
        f"__lr{float(config.learning_rate):.10g}"
    )
    summary_path = run_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["best_valid_accuracy"] = 0.9861
    summary["final_metrics"] = {
        "valid/accuracy": 0.9859,
        "valid/num_kv_pairs/accuracy-256": 0.902,
    }
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    (run_dir / "metrics.jsonl").write_text(
        '{"valid/accuracy": 0.9861, '
        '"valid/num_kv_pairs/accuracy-256": 0.91}\n'
        '{"valid/accuracy": 0.9859, '
        '"valid/num_kv_pairs/accuracy-256": 0.902}\n',
        encoding="utf-8",
    )
    return suite_dir


def test_single_baseline_freezes_pilot_informed_cell_five(tmp_path):
    suite_dir, _ = _make_empty_suite(tmp_path)
    manifest = initialize_baseline(suite_dir, 5)

    assert manifest["selected_index"] == 5
    assert manifest["d_model"] == 128
    assert math.isclose(manifest["learning_rate"], 10**-2.5)
    assert manifest["strong_accuracy_floor"] == 0.98
    assert manifest["visual_compatibility_floor"] == 0.96
    assert manifest["full_frontier_claim_allowed"] is False
    assert "not published by upstream" in (
        manifest["strong_accuracy_floor_provenance"]
    )
    assert "confidence interval" in (
        manifest["visual_compatibility_floor_provenance"]
    )
    assert validate_baseline(suite_dir) == manifest


def test_single_baseline_rejects_any_other_official_cell(tmp_path):
    suite_dir, _ = _make_empty_suite(tmp_path)

    with pytest.raises(
        ValueError,
        match="must use local harness index 5 from the official grid",
    ):
        initialize_baseline(suite_dir, 9)


def test_single_baseline_rejects_sequential_suite_entrypoints(tmp_path):
    suite_dir, _ = _make_empty_suite(tmp_path)
    initialize_baseline(suite_dir, 5)

    with pytest.raises(RuntimeError, match="sequential suite contract"):
        next_pending_index(suite_dir)
    with pytest.raises(RuntimeError, match="sequential suite contract"):
        prepare_cell(suite_dir, 0)


def test_single_baseline_launch_reserves_controller_setup_slack():
    run_script = (ROOT / "run.sh").read_text(encoding="utf-8")

    assert CONTROLLER_ADMISSION_FLOOR == 12_060
    assert WORKER_ADMISSION_FLOOR == 11_460
    assert CONTROLLER_ADMISSION_FLOOR - WORKER_ADMISSION_FLOOR == 600
    assert "export ZOOLOGY_MIN_REMAINING_SECONDS=11460" in run_script
    assert "export ZOOLOGY_CONTROLLER_MIN_REMAINING_SECONDS=12060" in run_script
    assert "repro.single_baseline admit-controller" in run_script
    assert "repro.single_baseline admit-worker" in run_script
    assert run_script.count('reject_single_baseline_dir "${SUITE_DIR}"') >= 4


def test_single_baseline_finalizes_and_revalidates_result(tmp_path):
    suite_dir = _make_completed_single_baseline(tmp_path)

    result = finalize_baseline(suite_dir)

    assert result["decision"] == "strong_baseline_pass"
    assert result["strong_baseline_pass"] is True
    assert result["kv256_diagnostic_pass"] is True
    assert result["full_frontier_claim_allowed"] is False
    assert result["request_sha256"] == sha256_file(
        suite_dir / "launches" / "run-05" / "request.json"
    )
    assert result["launch_sha256"] == sha256_file(
        suite_dir / "launches" / "run-05" / "launch.json"
    )
    assert result["terminal_sha256"] == sha256_file(
        suite_dir / "launches" / "run-05" / "terminal.json"
    )
    assert result["evidence_sha256"]["logs/run-05.log"] == sha256_file(
        suite_dir / "logs" / "run-05.log"
    )
    assert result["evidence_sha256"][
        "05__d128__lr0.00316227766/metrics.jsonl"
    ] == sha256_file(
        suite_dir / "05__d128__lr0.00316227766" / "metrics.jsonl"
    )
    assert set(SUITE_CLOCK_FILE_MAP.values()).issubset(
        result["evidence_sha256"]
    )
    assert result["clock_bracket_sha256"] == sha256_file(
        suite_dir / "clock-bracket.json"
    )
    assert result["clock_capture_terminal_sha256"] == sha256_file(
        suite_dir / "clock-capture-terminal.json"
    )
    assert result["clock_evidence_sha256"] == {
        name: sha256_file(suite_dir / name)
        for name in SUITE_CLOCK_FILE_MAP.values()
    }
    assert validate_result(suite_dir) == result
    assert (suite_dir / BASELINE_RESULT_NAME).is_file()
    assert finalize_baseline(suite_dir) == result


def test_single_baseline_rejects_generic_worker_mode(tmp_path):
    suite_dir, suite_manifest = _make_empty_suite(tmp_path)
    initialize_baseline(suite_dir, 5)
    remaining_seconds = 13_000
    observed_unix = math.ceil(time.time())
    _write_clock_evidence(suite_dir, remaining_seconds, observed_unix)
    record_admission(
        suite_dir,
        "controller",
        remaining_seconds,
        observed_unix,
    )
    _write_completed_cell(suite_dir, suite_manifest, 5)

    with pytest.raises(RuntimeError, match="baseline worker mode"):
        finalize_baseline(suite_dir)


@pytest.mark.parametrize(
    ("remaining_delta", "observed_delta", "expected_message"),
    (
        (1, 0, "remaining seconds disagree with"),
        (0, 1, "observed Unix time disagrees with"),
    ),
)
def test_single_baseline_admission_arguments_must_match_clock_proof(
    tmp_path,
    remaining_delta,
    observed_delta,
    expected_message,
):
    suite_dir, _ = _make_empty_suite(tmp_path)
    initialize_baseline(suite_dir, 5)
    remaining_seconds = 13_000
    observed_unix = math.ceil(time.time())
    _write_clock_evidence(suite_dir, remaining_seconds, observed_unix)

    with pytest.raises(RuntimeError, match=expected_message):
        record_admission(
            suite_dir,
            "controller",
            remaining_seconds + remaining_delta,
            observed_unix + observed_delta,
        )


def test_single_baseline_rejects_controller_without_launch_slack(tmp_path):
    suite_dir = _make_completed_single_baseline(tmp_path)
    launch_path = suite_dir / "launches" / "run-05" / "launch.json"
    launch = json.loads(launch_path.read_text(encoding="utf-8"))
    launch["controller_minimum_remaining_seconds"] = "11460"
    launch_path.write_text(json.dumps(launch), encoding="utf-8")

    with pytest.raises(RuntimeError, match="controller admission floor"):
        finalize_baseline(suite_dir)


def test_single_baseline_marks_kv256_diagnostic_anomaly(tmp_path):
    suite_dir = _make_completed_single_baseline(tmp_path)
    config = configs[5]
    summary_path = suite_dir / (
        f"05__d{config.model.d_model}"
        f"__lr{float(config.learning_rate):.10g}"
        "/summary.json"
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["final_metrics"]["valid/num_kv_pairs/accuracy-256"] = 0.8
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    metrics_path = suite_dir / (
        f"05__d{config.model.d_model}"
        f"__lr{float(config.learning_rate):.10g}"
        "/metrics.jsonl"
    )
    metrics_path.write_text(
        '{"valid/accuracy": 0.9861, '
        '"valid/num_kv_pairs/accuracy-256": 0.81}\n'
        '{"valid/accuracy": 0.9859, '
        '"valid/num_kv_pairs/accuracy-256": 0.8}\n',
        encoding="utf-8",
    )

    result = finalize_baseline(suite_dir)

    assert result["strong_baseline_pass"] is True
    assert result["kv256_diagnostic_pass"] is False
    assert result["diagnostic_anomaly"] is True
    assert result["decision"] == "strong_baseline_pass_with_kv256_anomaly"


def test_single_baseline_result_rejects_nonselected_cell_evidence(tmp_path):
    suite_dir = _make_completed_single_baseline(tmp_path)
    finalize_baseline(suite_dir)
    (suite_dir / "run-00-metadata.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="unexpected root evidence"):
        validate_result(suite_dir)


def test_single_baseline_result_rejects_metric_tampering(tmp_path):
    suite_dir = _make_completed_single_baseline(tmp_path)
    finalize_baseline(suite_dir)
    result_path = suite_dir / BASELINE_RESULT_NAME
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["final_valid_accuracy"] = 1.0
    result_path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(RuntimeError, match="single baseline result drift"):
        validate_result(suite_dir)


def test_single_baseline_rejects_manifest_timestamp_tampering_after_launch(
    tmp_path,
):
    suite_dir = _make_completed_single_baseline(tmp_path)
    manifest_path = suite_dir / "single-baseline-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["created_utc"] = "2000-01-01T00:00:00+00:00"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(
        RuntimeError,
        match=(
            "baseline manifest hash drift|admission evidence drift|"
            "baseline manifest predates suite initialization"
        ),
    ):
        finalize_baseline(suite_dir)


def test_single_baseline_rejects_result_timestamp_tampering(tmp_path):
    suite_dir = _make_completed_single_baseline(tmp_path)
    finalize_baseline(suite_dir)
    result_path = suite_dir / BASELINE_RESULT_NAME
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["recorded_utc"] = "2000-01-01T00:00:00+00:00"
    result_path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(RuntimeError, match="single baseline result drift"):
        validate_result(suite_dir)


@pytest.mark.parametrize(
    "kv256_accuracy",
    (2.0, -0.1),
)
def test_single_baseline_rejects_invalid_kv256_accuracy(
    tmp_path,
    kv256_accuracy,
):
    suite_dir = _make_completed_single_baseline(tmp_path)
    summary_path = (
        suite_dir / "05__d128__lr0.00316227766" / "summary.json"
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["final_metrics"][
        "valid/num_kv_pairs/accuracy-256"
    ] = kv256_accuracy
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(RuntimeError, match="outside \\[0, 1\\]"):
        finalize_baseline(suite_dir)


def test_single_baseline_rejects_kv256_summary_log_disagreement(tmp_path):
    suite_dir = _make_completed_single_baseline(tmp_path)
    summary_path = (
        suite_dir / "05__d128__lr0.00316227766" / "summary.json"
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["final_metrics"]["valid/num_kv_pairs/accuracy-256"] = 0.9
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(RuntimeError, match="KV256 accuracy disagrees"):
        finalize_baseline(suite_dir)


@pytest.mark.parametrize(
    ("relative_path", "timestamp_field"),
    (
        (Path("launches/run-05/request.json"), "requested_utc"),
        (Path("launches/run-05/terminal.json"), "ended_utc"),
    ),
)
def test_single_baseline_rejects_impossible_evidence_timeline(
    tmp_path,
    relative_path,
    timestamp_field,
):
    suite_dir = _make_completed_single_baseline(tmp_path)
    evidence_path = suite_dir / relative_path
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence[timestamp_field] = "2000-01-01T00:00:00+00:00"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(
        RuntimeError,
        match=(
            "request predates controller admission|"
            "terminal predates worker admission"
        ),
    ):
        finalize_baseline(suite_dir)


@pytest.mark.parametrize(
    ("relative_path", "mutation"),
    (
        (
            Path("launches/run-05/launch.json"),
            lambda payload: payload.update(
                {"launched_utc": "2000-01-01T00:00:00+00:00"}
            ),
        ),
        (
            Path("launches/run-05/terminal.json"),
            lambda payload: payload.update({"unexpected": True}),
        ),
    ),
)
def test_single_baseline_rejects_launch_terminal_evidence_tampering(
    tmp_path,
    relative_path,
    mutation,
):
    suite_dir = _make_completed_single_baseline(tmp_path)
    finalize_baseline(suite_dir)
    evidence_path = suite_dir / relative_path
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    mutation(evidence)
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(
        RuntimeError,
        match=(
            "baseline launch predates its request|baseline terminal fields drifted|"
            "single baseline result drift"
        ),
    ):
        validate_result(suite_dir)


@pytest.mark.parametrize(
    "relative_path",
    (
        Path("05__d128__lr0.00316227766/metrics.jsonl"),
        Path("logs/run-05.log"),
    ),
)
def test_single_baseline_result_binds_metrics_and_log(
    tmp_path,
    relative_path,
):
    suite_dir = _make_completed_single_baseline(tmp_path)
    finalize_baseline(suite_dir)
    evidence_path = suite_dir / relative_path
    if evidence_path.name == "metrics.jsonl":
        with evidence_path.open("a", encoding="utf-8") as handle:
            handle.write(
                '{"valid/num_kv_pairs/accuracy-256": 0.1}\n'
            )
    else:
        evidence_path.write_text("replaced log\n", encoding="utf-8")

    with pytest.raises(
        RuntimeError,
        match=(
            "KV256 accuracy disagrees with metrics|"
            "single baseline result drift"
        ),
    ):
        validate_result(suite_dir)


@pytest.mark.parametrize(
    "unexpected_name",
    (
        "run-99-metadata.json",
        "aggregate.json",
        "frontier.csv",
        "09__d256__lr0.00316227766",
    ),
)
def test_single_baseline_rejects_unexpected_root_artifacts(
    tmp_path,
    unexpected_name,
):
    suite_dir = _make_completed_single_baseline(tmp_path)
    unexpected = suite_dir / unexpected_name
    if "." in unexpected_name:
        unexpected.write_text("{}\n", encoding="utf-8")
    else:
        unexpected.mkdir()

    with pytest.raises(RuntimeError, match="unexpected root evidence"):
        finalize_baseline(suite_dir)


def test_single_baseline_rejects_admission_tampering(tmp_path):
    suite_dir = _make_completed_single_baseline(tmp_path)
    admission_path = suite_dir / CONTROLLER_ADMISSION_NAME
    admission = json.loads(admission_path.read_text(encoding="utf-8"))
    admission["reported_remaining_seconds"] = 1
    admission_path.write_text(json.dumps(admission), encoding="utf-8")

    with pytest.raises(
        RuntimeError,
        match=(
            "controller admission hash drift|admission evidence drift|"
            "insufficient AIStation time|drift from clock proof"
        ),
    ):
        finalize_baseline(suite_dir)


def test_single_baseline_rejects_wrong_logical_aistation_row(tmp_path):
    suite_dir = _make_completed_single_baseline(tmp_path)
    status_path = suite_dir / AISTATION_STATUS_NAME
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status["targets"][0]["wpName"] = "GPU1"
    status_path.write_text(json.dumps(status), encoding="utf-8")

    with pytest.raises(
        RuntimeError,
        match="not a running GPU2 row|target must be literal GPU2",
    ):
        finalize_baseline(suite_dir)


def test_single_baseline_rejects_missing_clock_evidence(tmp_path):
    suite_dir = _make_completed_single_baseline(tmp_path)
    (suite_dir / "clock-remote-before.json").unlink()

    with pytest.raises(RuntimeError, match="clock|missing|regular file"):
        finalize_baseline(suite_dir)


def test_single_baseline_rejects_tampered_clock_proof(tmp_path):
    suite_dir = _make_completed_single_baseline(tmp_path)
    proof_path = suite_dir / "clock-bracket.json"
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    proof["selected_observed_unix"] += 1
    proof_path.write_text(json.dumps(proof), encoding="utf-8")

    with pytest.raises(RuntimeError, match="clock-bracket|clock capture|drift"):
        finalize_baseline(suite_dir)


@pytest.mark.parametrize(
    "evidence_name",
    (
        "clock-helper-snapshot.js",
        "clock-capture-terminal.json",
    ),
)
def test_single_baseline_rejects_tampered_clock_lifecycle_evidence(
    tmp_path,
    evidence_name,
):
    suite_dir = _make_completed_single_baseline(tmp_path)
    evidence_path = suite_dir / evidence_name
    evidence_path.write_bytes(evidence_path.read_bytes() + b"\ntampered\n")

    with pytest.raises(RuntimeError, match="clock|helper|terminal|hash|JSON"):
        finalize_baseline(suite_dir)


def test_single_baseline_rejects_clock_evidence_replayed_to_another_run(
    tmp_path,
):
    source_dir, _ = _make_empty_suite(tmp_path / "source", "source-run")
    initialize_baseline(source_dir, 5)
    remaining_seconds = 13_000
    observed_unix = math.ceil(time.time())
    _write_clock_evidence(source_dir, remaining_seconds, observed_unix)

    target_dir, _ = _make_empty_suite(tmp_path / "target", "target-run")
    initialize_baseline(target_dir, 5)
    for suite_name in SUITE_CLOCK_FILE_MAP.values():
        (target_dir / suite_name).write_bytes(
            (source_dir / suite_name).read_bytes()
        )

    with pytest.raises(RuntimeError, match="run id|suite path|suite"):
        record_admission(
            target_dir,
            "controller",
            remaining_seconds,
            observed_unix,
        )
