from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research" / "control" / "durable_preflight_v2.sh"
FORMAL_SHA = "13f880b5fe61619a1006ef33610de69fbabaaec1"
FORMAL_TREE = "ed83a7188351ca2cce8aba46d1cb3b108ce31ec2"
LINUX_DURABLE_AVAILABLE = (
    sys.platform.startswith("linux")
    and shutil.which("setsid") is not None
    and Path("/proc/self/stat").is_file()
)


def _run(*arguments: str | Path, cwd: Path, check: bool = True):
    return subprocess.run(
        [str(argument) for argument in arguments],
        cwd=cwd,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_fixture(
    tmp_path: Path,
    run_id: str,
    *,
    fail_cache: bool = False,
    setup_extra: str = "",
):
    repo = tmp_path / "zoology"
    repo.mkdir()
    (repo / "runs").mkdir()
    (repo / ".gitignore").write_text(
        "/artifacts/\n/runs/\n/.venv/\n",
        encoding="utf-8",
    )
    python_path = repo / ".venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.symlink_to(Path(sys.executable).resolve())
    setup = repo / "setup.sh"
    setup.write_text(
        "#!/usr/bin/env bash\n"
        f"printf 'setup\\n' >> artifacts/{run_id}/calls.txt\n"
        f"{setup_extra}",
        encoding="utf-8",
    )
    setup.chmod(0o755)
    run = repo / "run.sh"
    run.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$1\" >> artifacts/{run_id}/calls.txt\n"
        + (
            "[[ \"$1\" == cache ]] && exit 7\n"
            if fail_cache
            else "exit 0\n"
        ),
        encoding="utf-8",
    )
    run.chmod(0o755)
    _run("git", "init", cwd=repo)
    _run("git", "config", "user.name", "Fixture", cwd=repo)
    _run("git", "config", "user.email", "fixture@example.invalid", cwd=repo)
    _run("git", "add", ".gitignore", "setup.sh", "run.sh", cwd=repo)
    _run("git", "commit", "-m", "fixture", cwd=repo)
    formal_sha = _run("git", "rev-parse", "HEAD", cwd=repo).stdout.strip()
    formal_tree = _run(
        "git",
        "rev-parse",
        "HEAD^{tree}",
        cwd=repo,
    ).stdout.strip()
    _run("git", "checkout", "--detach", formal_sha, cwd=repo)

    run_artifact = repo / "artifacts" / run_id
    launcher = run_artifact / "launcher"
    launcher.mkdir(parents=True)
    suite_dir = repo / "runs" / run_id
    control = run_artifact / "preflight-control"
    uploaded = launcher / "durable_preflight_v2.sh"
    materialized = SCRIPT.read_text(encoding="utf-8")
    materialized = materialized.replace("/huyang2/zoology", str(repo))
    materialized = materialized.replace(FORMAL_SHA, formal_sha)
    materialized = materialized.replace(FORMAL_TREE, formal_tree)
    uploaded.write_text(materialized, encoding="utf-8")
    uploaded.chmod(0o700)
    script_sha256 = _sha256(uploaded)
    start_command = (
        uploaded,
        "start",
        "--script-sha256",
        script_sha256,
        "--suite-dir",
        suite_dir,
        "--control-dir",
        control,
    )
    return {
        "repo": repo,
        "run_artifact": run_artifact,
        "suite_dir": suite_dir,
        "control": control,
        "uploaded": uploaded,
        "script_sha256": script_sha256,
        "start_command": start_command,
        "formal_sha": formal_sha,
        "formal_tree": formal_tree,
    }


def _wait_for_terminal(control: Path) -> Path:
    terminal_path = control / "terminal.json"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not terminal_path.is_file():
        time.sleep(0.05)
    assert terminal_path.is_file()
    return terminal_path


def _verify_command(fixture: dict[str, object]):
    return (
        fixture["uploaded"],
        "verify",
        "--script-sha256",
        fixture["script_sha256"],
        "--suite-dir",
        fixture["suite_dir"],
        "--control-dir",
        fixture["control"],
    )


def _wait_for_verify(fixture: dict[str, object]):
    deadline = time.monotonic() + 10
    while True:
        completed = _run(
            *_verify_command(fixture),
            cwd=fixture["repo"],
            check=False,
        )
        if completed.returncode == 0:
            return completed
        process_race = (
            "PID is still present" in completed.stderr
            or "process group still exists" in completed.stderr
        )
        if not process_race or time.monotonic() >= deadline:
            raise AssertionError(completed.stderr)
        time.sleep(0.05)


def _control_snapshot(control: Path):
    return {
        path.name: (
            path.read_bytes(),
            path.stat().st_mode,
            path.stat().st_mtime_ns,
            path.stat().st_ctime_ns,
        )
        for path in sorted(control.iterdir())
    }


def _write_json(path: Path, payload: dict[str, object]):
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _assert_terminal_hashes(control: Path, terminal: dict[str, object]):
    evidence_paths = {
        "script_sha256": control / "script-snapshot.sh",
        "attempt_sha256": control / "attempt.json",
        "start_sha256": control / "start.json",
        "worker_claim_sha256": control / "worker-claim.json",
        "worker_start_sha256": control / "worker-start.json",
        "envelope_log_sha256": control / "envelope.log",
        "step_01_log_sha256": control / "01-setup.log",
        "step_01_exit_sha256": control / "01-setup.exit",
        "step_01_json_sha256": control / "01-setup.json",
        "step_02_log_sha256": control / "02-check.log",
        "step_02_exit_sha256": control / "02-check.exit",
        "step_02_json_sha256": control / "02-check.json",
        "step_03_log_sha256": control / "03-cache.log",
        "step_03_exit_sha256": control / "03-cache.exit",
        "step_03_json_sha256": control / "03-cache.json",
        "step_04_log_sha256": control / "04-smoke.log",
        "step_04_exit_sha256": control / "04-smoke.exit",
        "step_04_json_sha256": control / "04-smoke.json",
    }
    terminal_hashes = {
        field: value
        for field, value in terminal.items()
        if field.endswith("_sha256")
    }
    assert set(terminal_hashes) == set(evidence_paths)
    for field, value in terminal_hashes.items():
        path = evidence_paths[field]
        if value is None:
            assert not path.exists()
        else:
            assert value == _sha256(path)


def test_preflight_v2_derives_run_id_and_never_runs_formal_actions():
    source = SCRIPT.read_text(encoding="utf-8")
    _run("bash", "-n", SCRIPT, cwd=ROOT)

    assert "RUN_ID=" not in source
    assert '"$mode" == "verify"' in source
    assert f'FORMAL_SOURCE_SHA="{FORMAL_SHA}"' in source
    assert f'FORMAL_SOURCE_TREE="{FORMAL_TREE}"' in source
    assert 'CONTROL_NAME="preflight-control"' in source
    assert 'INIT_CONTROL_NAME="init-baseline-control"' in source
    assert 'run_id="${suite_dir#"$suite_prefix"}"' in source
    assert '[[ "$run_id" =~ ^[a-z0-9][a-z0-9-]*$ ]]' in source
    assert '[[ "$suite_dir" == "$REPO_ROOT/runs/$run_id" ]]' in source
    assert 'expected_control="$run_artifact/$CONTROL_NAME"' in source
    assert (
        'for forbidden in "$suite_dir" "$formal_controller" '
        '"$formal_launch_control" "$init_control"'
    ) in source
    assert 'mkdir -- "$control_dir"' in source
    assert "mkdir -p" not in source
    assert 'write_atomic "$control_dir/worker-claim.json"' in source
    claim_position = source.index(
        'write_atomic "$control_dir/worker-claim.json"'
    )
    trap_position = source.index("trap on_worker_exit EXIT")
    content_hash_position = source.index(
        '[[ "$(sha256_file "$0")" == "$script_sha256" ]]',
        claim_position,
    )
    assert claim_position < trap_position < content_hash_position
    verify_start = source.index('if [[ "$mode" == "verify" ]]')
    verify_end = source.index('if [[ "$mode" == "start" ]]', verify_start)
    verify_source = source[verify_start:verify_end]
    for write_primitive in (
        "write_atomic",
        "mkdir ",
        "chmod ",
        "cp ",
        "sync ",
        "touch ",
        "> \"$",
    ):
        assert write_primitive not in verify_source
    assert "verify_source_and_downstream_absence" in verify_source
    envelope = (
        '"$nohup_path" "$setsid_path" --fork --wait '
        '"$bash_path" "$snapshot" worker'
    )
    assert envelope in source
    commands = (
        '01) ./setup.sh >"$log_path" 2>&1',
        '02) ./run.sh check >"$log_path" 2>&1',
        '03) ./run.sh cache >"$log_path" 2>&1',
        '04) ./run.sh smoke >"$log_path" 2>&1',
    )
    positions = [source.index(command) for command in commands]
    assert positions == sorted(positions)
    assert all(source.count(command) == 1 for command in commands)
    for forbidden_command in (
        "./run.sh init-baseline",
        "./run.sh launch-baseline",
        "aistation_clock_bracket",
        "publish-and-launch",
        "status GPU2",
        "capture GPU2",
    ):
        assert forbidden_command not in source
    assert "GPU1" not in source
    for suffix in (".log", ".exit", ".json"):
        assert f"$index-$name{suffix}" in source


@pytest.mark.parametrize(
    ("suite_dir", "control_dir", "message"),
    (
        (
            "/huyang2/zoology/runs/Uppercase",
            "/huyang2/zoology/artifacts/Uppercase/preflight-control",
            "invalid lowercase run id",
        ),
        (
            "/huyang2/zoology/runs/lower/nested",
            "/huyang2/zoology/artifacts/lower/nested/preflight-control",
            "invalid lowercase run id",
        ),
        (
            "/huyang2/zoology/runs/lower/",
            "/huyang2/zoology/artifacts/lower/preflight-control",
            "invalid lowercase run id",
        ),
        (
            "/huyang2/zoology/runs/one-id",
            "/huyang2/zoology/artifacts/other-id/preflight-control",
            "not the canonical preflight path",
        ),
        (
            "runs/one-id",
            "artifacts/one-id/preflight-control",
            "outside the formal repository",
        ),
    ),
)
def test_preflight_v2_rejects_noncanonical_run_paths(
    suite_dir: str,
    control_dir: str,
    message: str,
):
    completed = _run(
        SCRIPT,
        "start",
        "--script-sha256",
        "a" * 64,
        "--suite-dir",
        suite_dir,
        "--control-dir",
        control_dir,
        cwd=ROOT,
        check=False,
    )
    assert completed.returncode != 0
    assert message in completed.stderr


@pytest.mark.skipif(
    not LINUX_DURABLE_AVAILABLE,
    reason="the detached preflight contract requires Linux /proc",
)
@pytest.mark.parametrize(
    "forbidden_name",
    (
        "suite",
        "controller",
        "formal-launch-control",
        "init-baseline-control",
    ),
)
def test_preflight_v2_refuses_each_preexisting_formal_path(
    tmp_path: Path,
    forbidden_name: str,
):
    fixture = _build_fixture(tmp_path, "forbidden-path-run")
    repo = fixture["repo"]
    run_artifact = fixture["run_artifact"]
    suite_dir = fixture["suite_dir"]
    control = fixture["control"]
    forbidden = (
        suite_dir
        if forbidden_name == "suite"
        else run_artifact / forbidden_name
    )
    forbidden.mkdir()

    completed = _run(
        *fixture["start_command"],
        cwd=repo,
        check=False,
    )
    assert completed.returncode != 0
    assert "formal source or preflight path gate failed" in completed.stderr
    assert not control.exists()
    assert not (run_artifact / "calls.txt").exists()


@pytest.mark.skipif(
    not LINUX_DURABLE_AVAILABLE,
    reason="the detached preflight contract requires Linux /proc",
)
def test_preflight_v2_early_worker_failure_is_terminal_and_consumed(
    tmp_path: Path,
):
    fixture = _build_fixture(tmp_path, "early-worker-failure")
    repo = fixture["repo"]
    suite_dir = fixture["suite_dir"]
    control = fixture["control"]
    control.mkdir()
    snapshot = control / "script-snapshot.sh"
    shutil.copyfile(fixture["uploaded"], snapshot)
    snapshot.chmod(0o500)
    attempt = control / "attempt.json"
    attempt.write_text('{"fixture":"attempt"}\n', encoding="utf-8")
    wrong_sha256 = "b" * 64
    worker_command = (
        shutil.which("setsid"),
        "--fork",
        "--wait",
        shutil.which("bash"),
        snapshot,
        "worker",
        "--script-sha256",
        wrong_sha256,
        "--suite-dir",
        suite_dir,
        "--control-dir",
        control,
    )

    first = _run(*worker_command, cwd=repo, check=False)
    assert first.returncode != 0
    assert "worker SHA256 drifted" in first.stderr
    claim = json.loads(
        (control / "worker-claim.json").read_text(encoding="utf-8")
    )
    assert claim["attempt_sha256"] == _sha256(attempt)
    terminal_path = _wait_for_terminal(control)
    terminal_bytes = terminal_path.read_bytes()
    terminal = json.loads(terminal_bytes)
    assert terminal["status"] == "failed"
    assert terminal["failed_step"] == "worker-initialization"
    assert terminal["completed_steps"] == 0
    _assert_terminal_hashes(control, terminal)

    second = _run(*worker_command, cwd=repo, check=False)
    assert second.returncode != 0
    assert "worker attempt is consumed" in second.stderr
    assert terminal_path.read_bytes() == terminal_bytes
    assert not list(control.glob(".*.tmp.*"))


@pytest.mark.skipif(
    not LINUX_DURABLE_AVAILABLE,
    reason="the detached preflight contract requires Linux /proc",
)
def test_preflight_v2_stops_when_a_step_creates_a_formal_path(
    tmp_path: Path,
):
    run_id = "step-gate-run"
    fixture = _build_fixture(
        tmp_path,
        run_id,
        setup_extra=f"mkdir -- artifacts/{run_id}/controller\n",
    )
    repo = fixture["repo"]
    run_artifact = fixture["run_artifact"]
    control = fixture["control"]

    _run(*fixture["start_command"], cwd=repo)
    terminal_path = _wait_for_terminal(control)
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    assert (run_artifact / "calls.txt").read_text(
        encoding="utf-8"
    ).splitlines() == ["setup"]
    assert terminal["status"] == "failed"
    assert terminal["exit_code"] == 65
    assert terminal["failed_step"] == "01-setup"
    setup_evidence = json.loads(
        (control / "01-setup.json").read_text(encoding="utf-8")
    )
    assert setup_evidence["command_exit_code"] == 0
    assert setup_evidence["step_exit_code"] == 65
    assert not (control / "02-check.log").exists()
    assert not (control / "03-cache.log").exists()
    assert not (control / "04-smoke.log").exists()
    _assert_terminal_hashes(control, terminal)


@pytest.mark.skipif(
    not LINUX_DURABLE_AVAILABLE,
    reason="the detached preflight contract requires Linux /proc",
)
def test_preflight_v2_verify_allows_suite_and_init_control(
    tmp_path: Path,
):
    fixture = _build_fixture(tmp_path, "verify-after-init-claim")
    repo = fixture["repo"]
    run_artifact = fixture["run_artifact"]
    control = fixture["control"]
    _run(*fixture["start_command"], cwd=repo)
    _wait_for_terminal(control)
    _wait_for_verify(fixture)

    fixture["suite_dir"].mkdir()
    (run_artifact / "init-baseline-control").mkdir()
    before_verify = _control_snapshot(control)
    verified = _run(*_verify_command(fixture), cwd=repo)
    assert json.loads(verified.stdout)["status"] == "verified"
    assert _control_snapshot(control) == before_verify


@pytest.mark.skipif(
    not LINUX_DURABLE_AVAILABLE,
    reason="the detached preflight contract requires Linux /proc",
)
@pytest.mark.parametrize(
    "tamper_kind",
    ("inventory", "terminal", "step-command", "worker-binding", "snapshot"),
)
def test_preflight_v2_verify_rejects_tampered_evidence(
    tmp_path: Path,
    tamper_kind: str,
):
    fixture = _build_fixture(tmp_path, f"verify-tamper-{tamper_kind}")
    repo = fixture["repo"]
    control = fixture["control"]
    _run(*fixture["start_command"], cwd=repo)
    _wait_for_terminal(control)
    _wait_for_verify(fixture)
    terminal_path = control / "terminal.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))

    if tamper_kind == "inventory":
        (control / "unexpected.txt").write_text("extra\n", encoding="utf-8")
    elif tamper_kind == "terminal":
        terminal["completed_steps"] = 3
        _write_json(terminal_path, terminal)
    elif tamper_kind == "step-command":
        step_path = control / "02-check.json"
        step = json.loads(step_path.read_text(encoding="utf-8"))
        step["command"] = ["./run.sh", "smoke"]
        _write_json(step_path, step)
        terminal["step_02_json_sha256"] = _sha256(step_path)
        _write_json(terminal_path, terminal)
    elif tamper_kind == "worker-binding":
        worker_path = control / "worker-start.json"
        worker = json.loads(worker_path.read_text(encoding="utf-8"))
        worker["attempt_sha256"] = "0" * 64
        _write_json(worker_path, worker)
        terminal["worker_start_sha256"] = _sha256(worker_path)
        _write_json(terminal_path, terminal)
    else:
        snapshot = control / "script-snapshot.sh"
        snapshot.write_bytes(snapshot.read_bytes() + b"\n")

    rejected = _run(
        *_verify_command(fixture),
        cwd=repo,
        check=False,
    )
    assert rejected.returncode != 0
    assert "durable preflight evidence verification failed" in rejected.stderr


@pytest.mark.skipif(
    not LINUX_DURABLE_AVAILABLE,
    reason="the detached preflight contract requires Linux /proc",
)
@pytest.mark.parametrize("active_process", ("envelope", "worker"))
def test_preflight_v2_verify_rejects_bound_live_process(
    tmp_path: Path,
    active_process: str,
):
    fixture = _build_fixture(tmp_path, f"verify-live-{active_process}")
    repo = fixture["repo"]
    control = fixture["control"]
    _run(*fixture["start_command"], cwd=repo)
    _wait_for_terminal(control)
    _wait_for_verify(fixture)

    start_path = control / "start.json"
    claim_path = control / "worker-claim.json"
    worker_path = control / "worker-start.json"
    terminal_path = control / "terminal.json"
    start = json.loads(start_path.read_text(encoding="utf-8"))
    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    worker = json.loads(worker_path.read_text(encoding="utf-8"))
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    live_pid = os.getpid()

    if active_process == "envelope":
        start["envelope_supervisor_pid"] = live_pid
        _write_json(start_path, start)
        worker["ppid"] = live_pid
        worker["start_sha256"] = _sha256(start_path)
    else:
        claim["worker_pid"] = live_pid
        _write_json(claim_path, claim)
        worker["pid"] = live_pid
        worker["sid"] = live_pid
        worker["worker_claim_sha256"] = _sha256(claim_path)
        terminal["worker_pid"] = live_pid
        terminal["worker_sid"] = live_pid
        terminal["worker_claim_sha256"] = _sha256(claim_path)

    _write_json(worker_path, worker)
    terminal["start_sha256"] = _sha256(start_path)
    terminal["worker_start_sha256"] = _sha256(worker_path)
    _write_json(terminal_path, terminal)

    rejected = _run(
        *_verify_command(fixture),
        cwd=repo,
        check=False,
    )
    assert rejected.returncode != 0
    assert f"preflight {active_process}" in rejected.stderr
    assert "PID is still present" in rejected.stderr


@pytest.mark.skipif(
    not LINUX_DURABLE_AVAILABLE,
    reason="the detached preflight contract requires Linux /proc",
)
@pytest.mark.parametrize("run_id", ("gdn-mqar-p006", "reusable-run-7"))
@pytest.mark.parametrize("fail_cache", (False, True))
def test_preflight_v2_is_durable_ordered_and_one_shot(
    tmp_path: Path,
    run_id: str,
    fail_cache: bool,
):
    fixture = _build_fixture(
        tmp_path,
        run_id,
        fail_cache=fail_cache,
    )
    repo = fixture["repo"]
    run_artifact = fixture["run_artifact"]
    suite_dir = fixture["suite_dir"]
    control = fixture["control"]
    script_sha256 = fixture["script_sha256"]
    start_command = fixture["start_command"]
    formal_sha = fixture["formal_sha"]
    formal_tree = fixture["formal_tree"]
    started = time.monotonic()
    completed = _run(*start_command, cwd=repo)
    assert time.monotonic() - started < 1.5
    start_output = json.loads(completed.stdout)
    assert start_output["run_id"] == run_id
    assert start_output["suite_dir"] == str(suite_dir)
    assert start_output["script_sha256"] == script_sha256

    terminal_path = _wait_for_terminal(control)
    terminal_bytes = terminal_path.read_bytes()
    terminal = json.loads(terminal_bytes)
    expected_calls = ["setup", "check", "cache"]
    if not fail_cache:
        expected_calls.append("smoke")
    calls_path = repo / "artifacts" / run_id / "calls.txt"
    assert calls_path.read_text(encoding="utf-8").splitlines() == expected_calls
    assert terminal["run_id"] == run_id
    assert terminal["suite_dir"] == str(suite_dir)
    assert terminal["formal_source_sha"] == formal_sha
    assert terminal["formal_source_tree"] == formal_tree
    assert terminal["status"] == ("failed" if fail_cache else "completed")
    assert terminal["exit_code"] == (7 if fail_cache else 0)
    assert terminal["worker_sid"] == terminal["worker_pid"]
    assert terminal["worker_tty"] == "?"
    for index, name in (("01", "setup"), ("02", "check"), ("03", "cache")):
        for suffix in ("log", "exit", "json"):
            assert (control / f"{index}-{name}.{suffix}").is_file()
    if fail_cache:
        assert not (control / "04-smoke.log").exists()
    else:
        assert (control / "04-smoke.json").is_file()
    _assert_terminal_hashes(control, terminal)
    attempt_sha256 = _sha256(control / "attempt.json")
    start_sha256 = _sha256(control / "start.json")
    worker_claim_sha256 = _sha256(control / "worker-claim.json")
    claim = json.loads(
        (control / "worker-claim.json").read_text(encoding="utf-8")
    )
    worker_start = json.loads(
        (control / "worker-start.json").read_text(encoding="utf-8")
    )
    assert claim["attempt_sha256"] == attempt_sha256
    assert worker_start["attempt_sha256"] == attempt_sha256
    assert worker_start["start_sha256"] == start_sha256
    assert worker_start["worker_claim_sha256"] == worker_claim_sha256

    if fail_cache:
        rejected_verify = _run(
            *_verify_command(fixture),
            cwd=repo,
            check=False,
        )
        assert rejected_verify.returncode != 0
        assert "durable preflight evidence verification failed" in (
            rejected_verify.stderr
        )
    else:
        verified = _wait_for_verify(fixture)
        verify_output = json.loads(verified.stdout)
        assert verify_output == {
            "control_dir": str(control),
            "run_id": run_id,
            "status": "verified",
            "suite_dir": str(suite_dir),
        }
        before_verify = _control_snapshot(control)
        verified_again = _run(*_verify_command(fixture), cwd=repo)
        assert json.loads(verified_again.stdout) == verify_output
        assert _control_snapshot(control) == before_verify

    assert not suite_dir.exists()
    assert not (run_artifact / "controller").exists()
    assert not (run_artifact / "formal-launch-control").exists()
    assert not (run_artifact / "init-baseline-control").exists()

    second_start = _run(*start_command, cwd=repo, check=False)
    assert second_start.returncode != 0
    assert "attempt is consumed" in second_start.stderr

    snapshot = control / "script-snapshot.sh"
    second_worker = _run(
        snapshot,
        "worker",
        "--script-sha256",
        script_sha256,
        "--suite-dir",
        suite_dir,
        "--control-dir",
        control,
        cwd=repo,
        check=False,
    )
    assert second_worker.returncode != 0
    assert "worker attempt is consumed" in second_worker.stderr
    assert calls_path.read_text(encoding="utf-8").splitlines() == expected_calls
    assert terminal_path.read_bytes() == terminal_bytes
