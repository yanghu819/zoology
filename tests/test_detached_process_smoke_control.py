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
SCRIPT = ROOT / "research" / "control" / "detached_process_smoke.sh"
RUN_ID = "gdn-mqar-single-baseline-nohup-20260731t093138z"


def _run(*command: object, cwd: Path, check: bool = True):
    return subprocess.run(
        [str(part) for part in command],
        check=check,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_detached_smoke_contract_is_frozen_and_syntactically_valid():
    text = SCRIPT.read_text(encoding="utf-8")

    _run("bash", "-n", SCRIPT, cwd=ROOT)
    assert 'RUN_ID="gdn-mqar-single-baseline-nohup-20260731t093138z"' in text
    assert 'CONTROL_NAME="detach-smoke-control"' in text
    assert "DURATION_SECONDS=45" in text
    assert 'mkdir -- "$control_dir"' in text
    assert "mkdir -p" not in text
    assert (
        '"$nohup_path" "$setsid_path" --fork --wait '
        '"$bash_path" "$snapshot" worker'
        in text
    )
    assert "formal-launch-control" in text
    assert '"status": "completed"' in text
    assert '[[ "$worker_sid" == "$$" ]]' in text
    assert '[[ "$worker_tty" == "?" ]]' in text


@pytest.mark.skipif(
    not sys.platform.startswith("linux")
    or shutil.which("setsid") is None
    or not Path("/proc/self/stat").is_file(),
    reason="the detached smoke integration requires Linux /proc and setsid",
)
def test_detached_smoke_is_one_shot_and_records_detached_terminal(tmp_path):
    root = tmp_path / "zoology"
    launcher = root / "artifacts" / RUN_ID / "launcher"
    launcher.mkdir(parents=True)
    script = launcher / SCRIPT.name
    source = SCRIPT.read_text(encoding="utf-8")
    source = source.replace("/huyang2/zoology", str(root))
    source = source.replace("DURATION_SECONDS=45", "DURATION_SECONDS=1")
    script.write_text(source, encoding="utf-8")
    script.chmod(0o700)

    digest = hashlib.sha256(script.read_bytes()).hexdigest()
    control = root / "artifacts" / RUN_ID / "detach-smoke-control"
    command = [
        script,
        "start",
        "--script-sha256",
        digest,
        "--control-dir",
        control,
    ]

    started = time.monotonic()
    first = _run(*command, cwd=root)
    assert time.monotonic() - started < 1
    assert json.loads(first.stdout)["script_sha256"] == digest

    terminal_path = control / "terminal.json"
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not terminal_path.is_file():
        time.sleep(0.05)
    assert terminal_path.is_file()

    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    worker = json.loads(
        (control / "worker-start.json").read_text(encoding="utf-8")
    )
    assert terminal["status"] == "completed"
    assert terminal["elapsed_seconds"] >= 1
    assert terminal["worker_sid"] == terminal["worker_pid"]
    assert terminal["worker_tty"] == "?"
    assert worker["sid"] == worker["pid"]
    assert worker["tty"] == "?"
    assert not (root / "runs" / RUN_ID).exists()
    assert not (root / "artifacts" / RUN_ID / "controller").exists()
    assert not (root / "artifacts" / RUN_ID / "formal-launch-control").exists()

    second = _run(*command, cwd=root, check=False)
    assert second.returncode != 0
    assert "smoke attempt is consumed" in second.stderr
