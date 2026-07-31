from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from repro.aistation_clock_bracket import (
    CAPTURE_FILE_NAMES,
    SUITE_CLOCK_FILE_MAP,
    _module_sha256,
    build_evidence,
    capture,
    publish_and_launch,
    publish_status,
    validate_bundle,
    validate_suite_clock_evidence,
)

TEST_HELPER_SNAPSHOT = b"// exact helper snapshot\n"


@pytest.fixture(autouse=True)
def _approved_test_helper(monkeypatch):
    monkeypatch.setattr(
        "repro.aistation_clock_bracket.APPROVED_HELPER_SHA256",
        hashlib.sha256(TEST_HELPER_SNAPSHOT).hexdigest(),
    )


def _exec_payload(
    workspace: str,
    timestamp: int,
    *,
    hostname: str = "gpu2-host",
    boot_id: str = "12345678-1234-1234-1234-123456789abc",
) -> dict:
    return {
        "command": "exec",
        "ok": True,
        "targets": [
            {
                "wpName": "GPU2",
                "wpId": workspace,
                "wpStatus": "Running",
                "exec": {
                    "ok": True,
                    "exitCode": 0,
                    "stdout": (
                        f"HOST={hostname}\n"
                        f"BOOT_ID={boot_id}\n"
                        f"UNIX={timestamp}\n"
                    ),
                    "stderr": "",
                },
            }
        ],
    }


def _status_payload(
    workspace: str = "workspace-gpu2",
    status: str = "Running",
) -> dict:
    return {
        "command": "status",
        "ok": True,
        "targets": [
            {
                "wpName": "GPU2",
                "wpId": workspace,
                "wpStatus": status,
                "image": "test-image",
                "resource": "GPU:1",
                "remainTime": "14000",
            }
        ],
        "actions": [],
    }


def _build(
    before: int = 2_000_000_000,
    after: int = 2_000_000_002,
    *,
    before_workspace: str = "workspace-gpu2",
    status_workspace: str = "workspace-gpu2",
    after_workspace: str = "workspace-gpu2",
    status: str = "Running",
    after_hostname: str = "gpu2-host",
    after_boot_id: str = "12345678-1234-1234-1234-123456789abc",
) -> dict:
    before_payload = _exec_payload(before_workspace, before)
    status_payload = _status_payload(status_workspace, status)
    after_payload = _exec_payload(
        after_workspace,
        after,
        hostname=after_hostname,
        boot_id=after_boot_id,
    )
    return build_evidence(
        before_payload,
        json.dumps(before_payload).encode(),
        status_payload,
        json.dumps(status_payload).encode(),
        after_payload,
        json.dumps(after_payload).encode(),
        run_id="test-run",
        formal_source_sha="c" * 40,
        formal_source_tree="d" * 40,
        helper_sha256="a" * 64,
        module_sha256="b" * 64,
        capture_started_utc="2033-05-18T03:33:20+00:00",
        capture_ended_utc="2033-05-18T03:33:22+00:00",
        capture_elapsed_seconds=2.0,
    )


def test_selects_conservative_remote_before_timestamp():
    evidence = _build()

    assert evidence["remote_before_unix"] == 2_000_000_000
    assert evidence["remote_after_unix"] == 2_000_000_002
    assert evidence["bracket_span_seconds"] == 2
    assert evidence["selected_observed_unix"] == 2_000_000_000
    assert evidence["reported_remaining_seconds"] == 14_000
    assert evidence["minimum_controller_remaining_seconds"] == 12_060
    assert evidence["remote_hostname"] == "gpu2-host"
    assert (
        evidence["remote_boot_id"]
        == "12345678-1234-1234-1234-123456789abc"
    )


def test_rejects_wide_remote_clock_bracket():
    with pytest.raises(RuntimeError, match="remote-clock bracket"):
        _build(after=2_000_000_016)


def test_rejects_remote_clock_moving_backwards():
    with pytest.raises(RuntimeError, match="moved backwards"):
        _build(after=1_999_999_999)


def test_rejects_workspace_drift():
    with pytest.raises(RuntimeError, match="workspace changed"):
        _build(after_workspace="different-workspace")


def test_rejects_nonrunning_status():
    with pytest.raises(RuntimeError, match="not Running"):
        _build(status="Pending")


def test_rejects_hostname_drift():
    with pytest.raises(RuntimeError, match="hostname changed"):
        _build(after_hostname="replacement-host")


def test_rejects_boot_id_drift():
    with pytest.raises(RuntimeError, match="boot id changed"):
        _build(after_boot_id="87654321-4321-4321-4321-cba987654321")


def test_rejects_invalid_capture_provenance_fields():
    with pytest.raises(RuntimeError, match="helper SHA256"):
        before_payload = _exec_payload("workspace-gpu2", 2_000_000_000)
        status_payload = _status_payload()
        after_payload = _exec_payload("workspace-gpu2", 2_000_000_002)
        build_evidence(
            before_payload,
            _canonical_json(before_payload),
            status_payload,
            _canonical_json(status_payload),
            after_payload,
            _canonical_json(after_payload),
            run_id="test-run",
            formal_source_sha="c" * 40,
            formal_source_tree="d" * 40,
            helper_sha256="arbitrary",
            module_sha256="b" * 64,
            capture_started_utc="2033-05-18T03:33:20+00:00",
            capture_ended_utc="2033-05-18T03:33:22+00:00",
            capture_elapsed_seconds=2.0,
        )


def _canonical_json(payload: dict) -> bytes:
    return (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode()


def _write_bundle(bundle_dir) -> tuple[dict, bytes]:
    before_payload = _exec_payload("workspace-gpu2", 2_000_000_000)
    status_payload = _status_payload()
    after_payload = _exec_payload("workspace-gpu2", 2_000_000_002)
    before_raw = _canonical_json(before_payload)
    status_raw = _canonical_json(status_payload)
    after_raw = _canonical_json(after_payload)
    helper_snapshot = TEST_HELPER_SNAPSHOT
    helper_sha256 = hashlib.sha256(helper_snapshot).hexdigest()
    evidence = build_evidence(
        before_payload,
        before_raw,
        status_payload,
        status_raw,
        after_payload,
        after_raw,
        run_id="test-run",
        formal_source_sha="c" * 40,
        formal_source_tree="d" * 40,
        helper_sha256=helper_sha256,
        module_sha256=_module_sha256(),
        capture_started_utc="2033-05-18T03:33:20+00:00",
        capture_ended_utc="2033-05-18T03:33:22+00:00",
        capture_elapsed_seconds=2.0,
    )
    attempt = {
        "schema_version": 1,
        "run_id": "test-run",
        "formal_source_sha": "c" * 40,
        "formal_source_tree": "d" * 40,
        "target": "GPU2",
        "helper_sha256": helper_sha256,
        "module_sha256": _module_sha256(),
        "capture_started_utc": "2033-05-18T03:33:20+00:00",
    }
    bundle_dir.mkdir(parents=True)
    files = {
        "capture-attempt.json": _canonical_json(attempt),
        "helper-snapshot.js": helper_snapshot,
        "remote-before.json": before_raw,
        "aistation-status.json": status_raw,
        "remote-after.json": after_raw,
        "clock-bracket.json": _canonical_json(evidence),
    }
    terminal = {
        "schema_version": 1,
        "run_id": "test-run",
        "formal_source_sha": "c" * 40,
        "formal_source_tree": "d" * 40,
        "status": "completed",
        "capture_ended_utc": "2033-05-18T03:33:22+00:00",
        "files_sha256": {
            name: hashlib.sha256(raw).hexdigest()
            for name, raw in files.items()
        },
        "error_type": None,
        "error": None,
    }
    files["capture-terminal.json"] = _canonical_json(terminal)
    assert set(files) == set(CAPTURE_FILE_NAMES)
    for name, raw in files.items():
        (bundle_dir / name).write_bytes(raw)
    return evidence, status_raw


def test_validates_bundle_and_publishes_unchanged_status(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "repro.aistation_clock_bracket.REPO_ROOT",
        tmp_path,
    )
    bundle_dir = tmp_path / "artifacts" / "test-run" / "controller"
    evidence, status_raw = _write_bundle(bundle_dir)
    suite_dir = tmp_path / "runs" / "test-run"
    suite_dir.mkdir(parents=True)
    (suite_dir / "single-baseline-manifest.json").write_text(
        "{}",
        encoding="utf-8",
    )
    (suite_dir / "suite-manifest.json").write_text(
        json.dumps(
            {
                "git_sha": "c" * 40,
                "git_tree": "d" * 40,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "repro.aistation_clock_bracket._resolve_formal_source",
        lambda formal_source_sha: "d" * 40,
    )
    monkeypatch.setattr(
        "repro.aistation_clock_bracket._git_output",
        lambda *arguments: "c" * 40,
    )
    monkeypatch.setattr(
        "repro.aistation_clock_bracket._current_host_identity",
        lambda: (
            "gpu2-host",
            "12345678-1234-1234-1234-123456789abc",
        ),
    )
    monkeypatch.setattr(
        "repro.aistation_clock_bracket._current_unix",
        lambda: 2_000_000_003,
    )

    validated, validated_status = validate_bundle(bundle_dir)
    result = publish_status(bundle_dir, suite_dir)

    assert validated == evidence
    assert validated_status == status_raw
    assert (suite_dir / "aistation-status.json").read_bytes() == status_raw
    for suite_name in SUITE_CLOCK_FILE_MAP.values():
        assert (suite_dir / suite_name).is_file()
        assert not (suite_dir / f".{suite_name}.tmp").exists()
    assert result["status_sha256"] == evidence["status_response_sha256"]
    with pytest.raises(FileExistsError, match="target exists"):
        publish_status(bundle_dir, suite_dir)


def test_rejects_tampered_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "repro.aistation_clock_bracket.REPO_ROOT",
        tmp_path,
    )
    bundle_dir = tmp_path / "artifacts" / "test-run" / "controller"
    _write_bundle(bundle_dir)
    (bundle_dir / "aistation-status.json").write_text(
        json.dumps(_status_payload(workspace="different-workspace")),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="workspace changed"):
        validate_bundle(bundle_dir)


def test_rejects_failed_capture_terminal(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "repro.aistation_clock_bracket.REPO_ROOT",
        tmp_path,
    )
    bundle_dir = tmp_path / "artifacts" / "test-run" / "controller"
    _write_bundle(bundle_dir)
    terminal_path = bundle_dir / "capture-terminal.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    terminal["status"] = "failed"
    terminal["error_type"] = "RuntimeError"
    terminal["error"] = "formal capture failed"
    terminal_path.write_bytes(_canonical_json(terminal))

    with pytest.raises(RuntimeError, match="terminal evidence drift"):
        validate_bundle(bundle_dir)


def test_rejects_extra_capture_file(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "repro.aistation_clock_bracket.REPO_ROOT",
        tmp_path,
    )
    bundle_dir = tmp_path / "artifacts" / "test-run" / "controller"
    _write_bundle(bundle_dir)
    (bundle_dir / "unexpected.bin").write_bytes(b"unexpected")

    with pytest.raises(RuntimeError, match="file inventory drift"):
        validate_bundle(bundle_dir)


def test_rejects_tampered_helper_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "repro.aistation_clock_bracket.REPO_ROOT",
        tmp_path,
    )
    bundle_dir = tmp_path / "artifacts" / "test-run" / "controller"
    _write_bundle(bundle_dir)
    (bundle_dir / "helper-snapshot.js").write_bytes(b"changed\n")

    with pytest.raises(RuntimeError, match="helper snapshot hash drift"):
        validate_bundle(bundle_dir)


def test_rejects_invalid_proof_run_id(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "repro.aistation_clock_bracket.REPO_ROOT",
        tmp_path,
    )
    bundle_dir = tmp_path / "artifacts" / "test-run" / "controller"
    _write_bundle(bundle_dir)
    proof_path = bundle_dir / "clock-bracket.json"
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    proof["run_id"] = "../../escape"
    proof_path.write_bytes(_canonical_json(proof))

    with pytest.raises(RuntimeError, match="run id"):
        validate_bundle(bundle_dir)


def test_rejects_symlinked_capture_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "repro.aistation_clock_bracket.REPO_ROOT",
        tmp_path,
    )
    real_bundle = tmp_path / "real-bundle"
    _write_bundle(real_bundle)
    linked_bundle = tmp_path / "artifacts" / "test-run" / "controller"
    linked_bundle.parent.mkdir(parents=True)
    linked_bundle.symlink_to(real_bundle, target_is_directory=True)

    with pytest.raises(RuntimeError, match="real directory"):
        validate_bundle(linked_bundle)


def _write_initialized_suite(suite_dir: Path) -> None:
    suite_dir.mkdir(parents=True)
    (suite_dir / "single-baseline-manifest.json").write_text(
        "{}",
        encoding="utf-8",
    )
    (suite_dir / "suite-manifest.json").write_text(
        json.dumps(
            {
                "git_sha": "c" * 40,
                "git_tree": "d" * 40,
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("host_identity", "publish_unix", "expected"),
    (
        (
            (
                "wrong-host",
                "12345678-1234-1234-1234-123456789abc",
            ),
            2_000_000_003,
            "hostname",
        ),
        (
            (
                "gpu2-host",
                "87654321-4321-4321-4321-cba987654321",
            ),
            2_000_000_003,
            "boot id",
        ),
        (
            (
                "gpu2-host",
                "12345678-1234-1234-1234-123456789abc",
            ),
            2_000_000_061,
            "too old",
        ),
    ),
)
def test_publish_rejects_host_restart_or_stale_capture(
    tmp_path,
    monkeypatch,
    host_identity,
    publish_unix,
    expected,
):
    monkeypatch.setattr(
        "repro.aistation_clock_bracket.REPO_ROOT",
        tmp_path,
    )
    bundle_dir = tmp_path / "artifacts" / "test-run" / "controller"
    _write_bundle(bundle_dir)
    suite_dir = tmp_path / "runs" / "test-run"
    _write_initialized_suite(suite_dir)
    monkeypatch.setattr(
        "repro.aistation_clock_bracket._resolve_formal_source",
        lambda formal_source_sha: "d" * 40,
    )
    monkeypatch.setattr(
        "repro.aistation_clock_bracket._git_output",
        lambda *arguments: "c" * 40,
    )
    monkeypatch.setattr(
        "repro.aistation_clock_bracket._current_host_identity",
        lambda: host_identity,
    )
    monkeypatch.setattr(
        "repro.aistation_clock_bracket._current_unix",
        lambda: publish_unix,
    )

    with pytest.raises(RuntimeError, match=expected):
        publish_status(bundle_dir, suite_dir)
    for suite_name in SUITE_CLOCK_FILE_MAP.values():
        assert not (suite_dir / suite_name).exists()


def test_suite_clock_evidence_binds_run_directory_name(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "repro.aistation_clock_bracket.REPO_ROOT",
        tmp_path,
    )
    bundle_dir = tmp_path / "artifacts" / "test-run" / "controller"
    _write_bundle(bundle_dir)
    suite_dir = tmp_path / "other-run"
    _write_initialized_suite(suite_dir)
    for source_name, suite_name in SUITE_CLOCK_FILE_MAP.items():
        (suite_dir / suite_name).write_bytes(
            (bundle_dir / source_name).read_bytes()
        )
    monkeypatch.setattr(
        "repro.aistation_clock_bracket._resolve_formal_source",
        lambda formal_source_sha: "d" * 40,
    )

    with pytest.raises(RuntimeError, match="suite path disagrees"):
        validate_suite_clock_evidence(suite_dir)


def test_publish_and_launch_uses_bound_suite_values(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "repro.aistation_clock_bracket.REPO_ROOT",
        tmp_path,
    )
    bundle_dir = tmp_path / "artifacts" / "test-run" / "controller"
    _write_bundle(bundle_dir)
    suite_dir = tmp_path / "runs" / "test-run"
    _write_initialized_suite(suite_dir)
    monkeypatch.setattr(
        "repro.aistation_clock_bracket._resolve_formal_source",
        lambda formal_source_sha: "d" * 40,
    )
    monkeypatch.setattr(
        "repro.aistation_clock_bracket._git_output",
        lambda *arguments: "c" * 40,
    )
    monkeypatch.setattr(
        "repro.aistation_clock_bracket._current_host_identity",
        lambda: (
            "gpu2-host",
            "12345678-1234-1234-1234-123456789abc",
        ),
    )
    context_checks = {"count": 0}

    def current_unix():
        context_checks["count"] += 1
        return 2_000_000_003

    monkeypatch.setattr(
        "repro.aistation_clock_bracket._current_unix",
        current_unix,
    )
    captured = {}

    def fake_run(arguments, **kwargs):
        captured["arguments"] = arguments
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setattr(
        "repro.aistation_clock_bracket.subprocess.run",
        fake_run,
    )

    result = publish_and_launch(bundle_dir, suite_dir)

    assert captured["arguments"] == [
        str(tmp_path / "run.sh"),
        "launch-baseline",
        str(suite_dir),
    ]
    environment = captured["kwargs"]["env"]
    assert environment["AISTATION_TARGET"] == "GPU2"
    assert environment["ZOOLOGY_EXPECTED_GIT_SHA"] == "c" * 40
    assert environment["ZOOLOGY_REMAINING_SECONDS"] == "14000"
    assert (
        environment["ZOOLOGY_REMAINING_OBSERVED_UNIX"]
        == "2000000000"
    )
    assert result["launch_exit_code"] == 0
    assert result["launch_hostname"] == "gpu2-host"
    assert context_checks["count"] == 2


def test_publish_and_launch_rechecks_age_before_worker_start(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "repro.aistation_clock_bracket.REPO_ROOT",
        tmp_path,
    )
    bundle_dir = tmp_path / "artifacts" / "test-run" / "controller"
    _write_bundle(bundle_dir)
    suite_dir = tmp_path / "runs" / "test-run"
    _write_initialized_suite(suite_dir)
    monkeypatch.setattr(
        "repro.aistation_clock_bracket._resolve_formal_source",
        lambda formal_source_sha: "d" * 40,
    )
    monkeypatch.setattr(
        "repro.aistation_clock_bracket._git_output",
        lambda *arguments: "c" * 40,
    )
    monkeypatch.setattr(
        "repro.aistation_clock_bracket._current_host_identity",
        lambda: (
            "gpu2-host",
            "12345678-1234-1234-1234-123456789abc",
        ),
    )
    publish_times = iter((2_000_000_003, 2_000_000_061))
    monkeypatch.setattr(
        "repro.aistation_clock_bracket._current_unix",
        lambda: next(publish_times),
    )
    launch_called = {"value": False}

    def fake_run(*arguments, **kwargs):
        launch_called["value"] = True
        return subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setattr(
        "repro.aistation_clock_bracket.subprocess.run",
        fake_run,
    )

    with pytest.raises(RuntimeError, match="too old"):
        publish_and_launch(bundle_dir, suite_dir)

    assert launch_called["value"] is False


def test_failed_capture_is_durable_and_cannot_be_retried(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "repro.aistation_clock_bracket.REPO_ROOT",
        tmp_path,
    )
    monkeypatch.setattr(
        "repro.aistation_clock_bracket._resolve_formal_source",
        lambda formal_source_sha: "d" * 40,
    )
    monkeypatch.setattr(
        "repro.aistation_clock_bracket._run_helper",
        lambda *arguments: (_ for _ in ()).throw(
            RuntimeError("simulated helper failure")
        ),
    )
    helper = tmp_path / "aistation_api.js"
    helper.write_text("// frozen helper\n", encoding="utf-8")
    monkeypatch.setattr(
        "repro.aistation_clock_bracket.APPROVED_HELPER_PATH",
        helper,
    )
    monkeypatch.setattr(
        "repro.aistation_clock_bracket.APPROVED_HELPER_SHA256",
        hashlib.sha256(helper.read_bytes()).hexdigest(),
    )
    output_dir = (
        tmp_path / "artifacts" / "failed-run" / "controller"
    )

    with pytest.raises(RuntimeError, match="simulated helper failure"):
        capture(helper, output_dir, "failed-run", "c" * 40)

    attempt = json.loads(
        (output_dir / "capture-attempt.json").read_text(encoding="utf-8")
    )
    terminal = json.loads(
        (output_dir / "capture-terminal.json").read_text(encoding="utf-8")
    )
    assert attempt["run_id"] == "failed-run"
    assert terminal["status"] == "failed"
    assert terminal["error_type"] == "RuntimeError"
    assert set(terminal["files_sha256"]) == {
        "capture-attempt.json",
        "helper-snapshot.js",
    }

    with pytest.raises(FileExistsError):
        capture(helper, output_dir, "failed-run", "c" * 40)
