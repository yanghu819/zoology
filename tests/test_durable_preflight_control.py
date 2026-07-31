from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research" / "control" / "durable_preflight.sh"
RUN_ID = "gdn-mqar-single-baseline-nohup-20260731t093138z"
FORMAL_SHA = "13f880b5fe61619a1006ef33610de69fbabaaec1"
FORMAL_TREE = "ed83a7188351ca2cce8aba46d1cb3b108ce31ec2"


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


def test_preflight_control_has_frozen_order_and_no_formal_launch():
    source = SCRIPT.read_text(encoding="utf-8")
    _run("bash", "-n", SCRIPT, cwd=ROOT)

    assert f'RUN_ID="{RUN_ID}"' in source
    assert 'CONTROL_NAME="preflight-control"' in source
    assert 'mkdir -- "$control_dir"' in source
    assert 'mkdir -p' not in source
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
    assert "launch-baseline" not in source
    assert "init-baseline" not in source
    assert "aistation_clock_bracket" not in source
    assert "GPU1" not in source
    for suffix in (".log", ".exit", ".json"):
        assert f'$index-$name{suffix}' in source


@pytest.mark.skipif(
    not sys.platform.startswith("linux")
    or shutil.which("setsid") is None
    or not Path("/proc/self/stat").is_file(),
    reason="the detached preflight contract requires Linux /proc",
)
@pytest.mark.parametrize("fail_cache", (False, True))
def test_start_path_orders_steps_and_refuses_second_start(tmp_path, fail_cache):
    repo = tmp_path / "zoology"
    repo.mkdir()
    (repo / ".gitignore").write_text(
        "/artifacts/\n/runs/\n",
        encoding="utf-8",
    )
    setup = repo / "setup.sh"
    setup.write_text(
        "#!/usr/bin/env bash\n"
        f"printf 'setup\\n' >> artifacts/{RUN_ID}/calls.txt\n",
        encoding="utf-8",
    )
    setup.chmod(0o755)
    run = repo / "run.sh"
    run.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$1\" >> artifacts/{RUN_ID}/calls.txt\n"
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

    run_artifact = repo / "artifacts" / RUN_ID
    launcher = run_artifact / "launcher"
    launcher.mkdir(parents=True)
    control = run_artifact / "preflight-control"
    uploaded = launcher / "durable_preflight.sh"
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
        "--control-dir",
        control,
    )
    started = time.monotonic()
    completed = _run(*start_command, cwd=repo)
    assert time.monotonic() - started < 1.5
    assert json.loads(completed.stdout)["script_sha256"] == script_sha256

    terminal_path = control / "terminal.json"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not terminal_path.is_file():
        time.sleep(0.05)
    assert terminal_path.is_file()
    terminal = json.loads(
        terminal_path.read_text(encoding="utf-8")
    )
    expected_calls = ["setup", "check", "cache"]
    if not fail_cache:
        expected_calls.append("smoke")
    calls = (repo / "artifacts" / RUN_ID / "calls.txt").read_text(
        encoding="utf-8"
    ).splitlines()
    assert calls == expected_calls
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
    assert terminal["attempt_sha256"] == _sha256(control / "attempt.json")
    assert terminal["start_sha256"] == _sha256(control / "start.json")
    assert terminal["worker_start_sha256"] == _sha256(
        control / "worker-start.json"
    )
    required_hashes = (
        "attempt_sha256",
        "start_sha256",
        "worker_start_sha256",
        "envelope_log_sha256",
        "step_01_log_sha256",
        "step_01_exit_sha256",
        "step_01_json_sha256",
        "step_02_log_sha256",
        "step_02_exit_sha256",
        "step_02_json_sha256",
        "step_03_log_sha256",
        "step_03_exit_sha256",
        "step_03_json_sha256",
    )
    if not fail_cache:
        required_hashes += (
            "step_04_log_sha256",
            "step_04_exit_sha256",
            "step_04_json_sha256",
        )
    assert all(terminal[field] is not None for field in required_hashes)

    second = _run(*start_command, cwd=repo, check=False)
    assert second.returncode != 0
    assert "attempt is consumed" in second.stderr
