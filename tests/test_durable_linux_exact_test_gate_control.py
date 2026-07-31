from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
ENVELOPE = ROOT / "research" / "control" / "durable_linux_exact_test_gate.sh"
PYTHON_GATE = ROOT / "research" / "control" / "linux_exact_test_gate.py"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_gate():
    spec = importlib.util.spec_from_file_location("durable_envelope_gate", PYTHON_GATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(*arguments: object, cwd: Path, env: dict[str, str] | None = None):
    return subprocess.run(
        [str(argument) for argument in arguments],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


def _materialize(tmp_path: Path, *, outcome: str = "success"):
    gate = _load_gate()
    repo = tmp_path / "zoology"
    run_id = f"envelope-{outcome}"
    launcher = repo / "artifacts" / run_id / "launcher"
    launcher.mkdir(parents=True)

    envelope_source = ENVELOPE.read_text(encoding="utf-8").replace(
        'REPO_ROOT="/huyang2/zoology"',
        f'REPO_ROOT="{repo}"',
        1,
    )
    envelope_runtime = launcher / ENVELOPE.name
    envelope_runtime.write_text(envelope_source, encoding="utf-8")
    envelope_runtime.chmod(0o700)
    envelope_hash = _sha256(envelope_runtime)

    test_payloads: dict[str, str] = {}
    for relative_name in gate.TEST_MODULE_SHA256:
        source = ROOT / relative_name
        test_payloads[relative_name] = source.read_text(encoding="utf-8")
    if outcome == "failure":
        selected = next(iter(test_payloads))
        test_payloads[selected] += "\n\ndef test_envelope_forced_failure():\n    assert False\n"

    gate_source = PYTHON_GATE.read_text(encoding="utf-8")
    gate_source = gate_source.replace(
        'REPO_ROOT = Path("/huyang2/zoology")',
        f"REPO_ROOT = Path({str(repo)!r})",
        1,
    )
    gate_source = gate_source.replace(_sha256(ENVELOPE), envelope_hash, 1)
    gate_source = gate_source.replace("import subprocess\n", "import subprocess\nimport time\n", 1)
    gate_source = gate_source.replace(
        "        _run_gate(\n",
        "        time.sleep(float(os.environ.get('TEST_ENVELOPE_GATE_DELAY', '0')))\n"
        "        _run_gate(\n",
        1,
    )
    if outcome == "timeout":
        gate_source = gate_source.replace(
            "PYTEST_TIMEOUT_SECONDS = 300",
            "PYTEST_TIMEOUT_SECONDS = 0.01",
            1,
        )
    for relative_name, payload in test_payloads.items():
        original_hash = gate.TEST_MODULE_SHA256[relative_name]
        payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        gate_source = gate_source.replace(original_hash, payload_hash, 1)

    gate_runtime = launcher / PYTHON_GATE.name
    gate_runtime.write_text(gate_source, encoding="utf-8")
    gate_runtime.chmod(0o700)
    gate_hash = _sha256(gate_runtime)
    tracked_gate = launcher / "research" / "control" / PYTHON_GATE.name
    tracked_gate.parent.mkdir(parents=True)
    shutil.copyfile(gate_runtime, tracked_gate)

    for relative_name in gate.FIXED_SOURCE_SHA256:
        destination = launcher / relative_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if relative_name == "research/control/durable_linux_exact_test_gate.sh":
            shutil.copyfile(envelope_runtime, destination)
        else:
            shutil.copyfile(ROOT / relative_name, destination)
    for source_name, runtime_name in gate.RUNTIME_COPY_BY_SOURCE.items():
        runtime = launcher / runtime_name
        if source_name == "research/control/durable_linux_exact_test_gate.sh":
            shutil.copyfile(envelope_runtime, runtime)
        else:
            shutil.copyfile(ROOT / source_name, runtime)
        runtime.chmod(0o700)
    for relative_name, payload in test_payloads.items():
        destination = launcher / relative_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(payload, encoding="utf-8")

    python_entry = repo / ".venv" / "bin" / "python"
    python_entry.parent.mkdir(parents=True)
    python_entry.symlink_to(Path(sys.executable).resolve())
    control = repo / "artifacts" / run_id / "linux-exact-test-envelope"
    command = [
        envelope_runtime,
        "start",
        "--run-id",
        run_id,
        "--script-sha256",
        envelope_hash,
        "--gate-sha256",
        gate_hash,
        "--control-dir",
        control,
    ]
    return repo, run_id, envelope_runtime, envelope_hash, gate_hash, control, command


def _wait_for_terminal_and_exit(control: Path, timeout: float = 30.0):
    deadline = time.monotonic() + timeout
    terminal_path = control / "terminal.json"
    while time.monotonic() < deadline and not terminal_path.is_file():
        time.sleep(0.05)
    assert terminal_path.is_file(), "detached envelope did not publish terminal.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    start = json.loads((control / "start.json").read_text(encoding="utf-8"))
    pids = {
        value
        for value in (
            start.get("supervisor_pid"),
            terminal.get("worker_pid"),
            terminal.get("gate_pid"),
        )
        if isinstance(value, int) and value > 0
    }
    while time.monotonic() < deadline:
        if all(not (Path("/proc") / str(pid)).exists() for pid in pids):
            return terminal
        time.sleep(0.05)
    pytest.fail(f"detached processes remained after terminal: {sorted(pids)}")


def test_envelope_contract_is_syntactically_valid_and_durable():
    source = ENVELOPE.read_text(encoding="utf-8")
    completed = _run("bash", "-n", ENVELOPE, cwd=ROOT)
    assert completed.returncode == 0, completed.stderr
    assert ENVELOPE.stat().st_mode & 0o111
    assert "start|verify" in source
    assert '"$nohup_path" "$setsid_path" --fork --wait' in source
    assert '</dev/null >"$control_dir/envelope.log" 2>&1 &' in source
    assert '"$setsid_path" "$python_entry" "$gate_script"' in source
    assert 'kill -TERM -- "-$gate_pid"' in source
    assert 'require_process_absent(worker["pid"], worker["pgid"], "worker")' in source
    assert 'require_process_absent(gate["pid"], gate["pgid"], "gate")' in source
    assert 'gate_terminal.get("counts") != expected_counts' in source
    assert 'launcher_actual != launcher_expected' in source
    assert '"CUDA_VISIBLE_DEVICES": ""' in source
    assert 'preflight_control="$run_artifact/preflight-control"' in source
    assert 'init_control="$run_artifact/init-baseline-control"' in source


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="requires Linux /proc and setsid")
def test_transport_parent_exits_then_verify_rejects_early_and_accepts_once_complete(
    tmp_path,
):
    repo, run_id, script, script_hash, gate_hash, control, command = _materialize(
        tmp_path,
        outcome="success",
    )
    environment = os.environ.copy()
    environment["TEST_ENVELOPE_GATE_DELAY"] = "1.0"
    started = time.monotonic()
    launched = _run(*command, cwd=repo, env=environment)
    elapsed = time.monotonic() - started
    assert launched.returncode == 0, launched.stderr
    assert elapsed < 10
    assert not (control / "terminal.json").exists()

    verify = [
        script,
        "verify",
        "--run-id",
        run_id,
        "--script-sha256",
        script_hash,
        "--gate-sha256",
        gate_hash,
        "--control-dir",
        control,
    ]
    early = _run(*verify, cwd=repo, env=environment)
    assert early.returncode != 0
    assert "terminal" in early.stderr.lower()

    reentry = _run(*command, cwd=repo, env=environment)
    assert reentry.returncode != 0
    assert "one-shot path already exists" in reentry.stderr

    terminal = _wait_for_terminal_and_exit(control)
    assert terminal["status"] == "completed"
    verified = _run(*verify, cwd=repo, env=environment)
    assert verified.returncode == 0, verified.stderr
    assert json.loads(verified.stdout)["tests"] == 53


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="requires Linux /proc and setsid")
@pytest.mark.parametrize("outcome", ["failure", "timeout"])
def test_failure_and_timeout_are_terminal_one_shot_and_never_verify(tmp_path, outcome):
    repo, run_id, script, script_hash, gate_hash, control, command = _materialize(
        tmp_path,
        outcome=outcome,
    )
    environment = os.environ.copy()
    environment["TEST_ENVELOPE_GATE_DELAY"] = "0.3"
    launched = _run(*command, cwd=repo, env=environment)
    assert launched.returncode == 0, launched.stderr
    terminal = _wait_for_terminal_and_exit(control)
    assert terminal["status"] == "failed"
    gate_terminal = json.loads(
        (repo / "artifacts" / run_id / "linux-exact-test-gate" / "terminal.json").read_text(
            encoding="utf-8"
        )
    )
    assert gate_terminal["status"] == "failed"
    if outcome == "timeout":
        assert gate_terminal["pytest_exit_code"] == 124

    verify = _run(
        script,
        "verify",
        "--run-id",
        run_id,
        "--script-sha256",
        script_hash,
        "--gate-sha256",
        gate_hash,
        "--control-dir",
        control,
        cwd=repo,
        env=environment,
    )
    assert verify.returncode != 0
    assert "did not complete exactly" in verify.stderr
    retry = _run(*command, cwd=repo, env=environment)
    assert retry.returncode != 0
    assert "one-shot path already exists" in retry.stderr


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="requires Linux /proc and setsid")
def test_hash_drift_is_rejected_before_attempt_claim(tmp_path):
    repo, run_id, script, script_hash, gate_hash, control, command = _materialize(
        tmp_path,
        outcome="success",
    )
    bad_script = list(command)
    bad_script[bad_script.index(script_hash)] = "0" * 64
    rejected_script = _run(*bad_script, cwd=repo)
    assert rejected_script.returncode != 0
    assert "envelope SHA256 differs" in rejected_script.stderr
    assert not control.exists()

    bad_gate = list(command)
    bad_gate[bad_gate.index(gate_hash)] = "f" * 64
    rejected_gate = _run(*bad_gate, cwd=repo)
    assert rejected_gate.returncode != 0
    assert "Python gate SHA256 differs" in rejected_gate.stderr
    assert not control.exists()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="requires Linux /proc and setsid")
@pytest.mark.parametrize("forbidden_name", ["preflight-control", "init-baseline-control"])
def test_prior_phase_control_including_dangling_symlink_is_rejected_before_claim(
    tmp_path,
    forbidden_name,
):
    repo, run_id, _, _, _, control, command = _materialize(
        tmp_path,
        outcome="success",
    )
    forbidden = repo / "artifacts" / run_id / forbidden_name
    forbidden.symlink_to(repo / "missing-prior-phase-evidence")
    rejected = _run(*command, cwd=repo)
    assert rejected.returncode != 0
    assert f"one-shot path already exists: {forbidden}" in rejected.stderr
    assert not control.exists()
