from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pty
import select
import shutil
import signal
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


def _run_with_controlling_pty(
    *arguments: object,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: float = 30.0,
):
    command = [str(argument) for argument in arguments]
    child_pid, master_fd = pty.fork()
    if child_pid == 0:
        try:
            os.chdir(cwd)
            os.execve(command[0], command, os.environ.copy() if env is None else env)
        except BaseException as error:
            os.write(2, f"pty child setup failed: {error}\n".encode("utf-8", errors="replace"))
            os._exit(127)

    output = bytearray()
    status = None
    deadline = time.monotonic() + timeout
    timed_out = False
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master_fd], [], [], 0.05)
            if ready:
                try:
                    chunk = os.read(master_fd, 65536)
                except OSError:
                    chunk = b""
                if chunk:
                    output.extend(chunk)
            waited_pid, waited_status = os.waitpid(child_pid, os.WNOHANG)
            if waited_pid == child_pid:
                status = waited_status
                break
        if status is None:
            timed_out = True
        else:
            drain_deadline = time.monotonic() + 0.2
            while time.monotonic() < drain_deadline:
                ready, _, _ = select.select([master_fd], [], [], 0.02)
                if not ready:
                    break
                try:
                    chunk = os.read(master_fd, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                output.extend(chunk)
    finally:
        if status is None:
            try:
                os.killpg(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                _, status = os.waitpid(child_pid, 0)
            except ChildProcessError:
                pass
        os.close(master_fd)
    if timed_out:
        raise subprocess.TimeoutExpired(command, timeout, output=bytes(output))
    return subprocess.CompletedProcess(
        command,
        os.waitstatus_to_exitcode(status),
        bytes(output).decode("utf-8", errors="replace"),
        "",
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
    processes = {
        pid: ticks
        for pid, ticks in (
            (start.get("transport_pid"), start.get("transport_start_ticks")),
            (start.get("supervisor_pid"), start.get("supervisor_start_ticks")),
            (terminal.get("worker_pid"), terminal.get("worker_start_ticks")),
            (terminal.get("gate_pid"), terminal.get("gate_start_ticks")),
        )
        if isinstance(pid, int) and pid > 0 and isinstance(ticks, int) and ticks > 0
    }
    while time.monotonic() < deadline:
        if all(_proc_start_ticks(pid) != ticks for pid, ticks in processes.items()):
            return terminal
        time.sleep(0.05)
    pytest.fail(f"detached processes remained after terminal: {sorted(processes)}")


def _proc_start_ticks(pid: int) -> int | None:
    try:
        stat_text = (Path("/proc") / str(pid) / "stat").read_text(encoding="ascii")
        fields = stat_text.rsplit(") ", 1)[1].split()
        return int(fields[19])
    except (FileNotFoundError, IndexError, UnicodeDecodeError, ValueError):
        return None


def _terminate_recorded_processes(control: Path):
    targets: dict[int, tuple[int, int | None]] = {}
    for name, fields in (
        (
            "start.json",
            (
                ("transport_pid", "transport_start_ticks", None),
                ("supervisor_pid", "supervisor_start_ticks", "supervisor_pgid"),
            ),
        ),
        ("worker-start.json", (("pid", "proc_start_ticks", "pgid"),)),
        ("gate-process.json", (("pid", "proc_start_ticks", "pgid"),)),
    ):
        path = control / name
        if not path.is_file():
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        for pid_key, ticks_key, pgid_key in fields:
            pid = record.get(pid_key)
            ticks = record.get(ticks_key)
            pgid = record.get(pgid_key) if pgid_key is not None else None
            if isinstance(pid, int) and isinstance(ticks, int) and pid > 0 and ticks > 0:
                targets[pid] = (ticks, pgid if isinstance(pgid, int) and pgid > 0 else None)
    for pid, (ticks, pgid) in targets.items():
        if _proc_start_ticks(pid) != ticks:
            continue
        try:
            if pgid is not None:
                os.killpg(pgid, signal.SIGKILL)
            else:
                os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def test_envelope_contract_is_syntactically_valid_and_durable():
    source = ENVELOPE.read_text(encoding="utf-8")
    completed = _run("bash", "-n", ENVELOPE, cwd=ROOT)
    assert completed.returncode == 0, completed.stderr
    assert ENVELOPE.stat().st_mode & 0o111
    assert "start|verify" in source
    assert '"$nohup_path" "$setsid_path" --fork --wait' in source
    assert 'transport_tty="inherited"' in source
    assert 'claim_identity="$(' in source
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


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="requires Linux /proc and pty")
def test_controlling_pty_transport_binds_the_detached_supervisor(tmp_path, request):
    repo, run_id, script, script_hash, gate_hash, control, command = _materialize(
        tmp_path,
        outcome="success",
    )
    request.addfinalizer(lambda: _terminate_recorded_processes(control))
    environment = os.environ.copy()
    environment["TEST_ENVELOPE_GATE_DELAY"] = "2.0"
    started = time.monotonic()
    launched = _run_with_controlling_pty(*command, cwd=repo, env=environment)
    elapsed = time.monotonic() - started
    assert launched.returncode == 0, launched.stdout
    assert elapsed < 10

    start = json.loads((control / "start.json").read_text(encoding="utf-8"))
    claim = json.loads((control / "worker-claim.json").read_text(encoding="utf-8"))
    assert start["schema_version"] == 2
    assert start["transport_tty"] == "inherited"
    assert start["transport_tty_nr"] != 0
    assert start["supervisor_pid"] == claim["worker_pid"]
    assert start["supervisor_ppid"] == start["transport_pid"]
    assert start["supervisor_pid"] == start["supervisor_pgid"] == start["supervisor_sid"]
    assert start["supervisor_tty"] == "none"
    assert start["supervisor_tty_nr"] == 0
    assert start["stdin"] == "/dev/null"
    assert not (control / "terminal.json").exists()

    terminal = _wait_for_terminal_and_exit(control)
    assert terminal["status"] == "completed"
    verified = _run(
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
    assert verified.returncode == 0, verified.stderr
    assert json.loads(verified.stdout)["tests"] == 53
    for forbidden in (
        repo / "runs" / run_id,
        repo / "artifacts" / run_id / "controller",
        repo / "artifacts" / run_id / "formal-launch-control",
    ):
        assert not forbidden.exists()


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
