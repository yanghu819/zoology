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
CONTROL_SOURCE = ROOT / "research" / "control"
STARTER = CONTROL_SOURCE / "durable_publish_launch_start.sh"
WRAPPER = CONTROL_SOURCE / "durable_publish_launch_wrapper.sh"
FORMAL_SHA = "13f880b5fe61619a1006ef33610de69fbabaaec1"
FORMAL_TREE = "ed83a7188351ca2cce8aba46d1cb3b108ce31ec2"


def _run(*arguments: str | Path, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(argument) for argument in arguments],
        check=True,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_shell_control_contract_is_frozen_and_syntactically_valid():
    starter = STARTER.read_text(encoding="utf-8")
    wrapper = WRAPPER.read_text(encoding="utf-8")

    _run("bash", "-n", STARTER, cwd=ROOT)
    _run("bash", "-n", WRAPPER, cwd=ROOT)

    assert 'CONTROL_NAME="formal-launch-control"' in starter
    assert 'CONTROL_NAME="formal-launch-control"' in wrapper
    assert (
        '"$nohup_path" "$setsid_path" --fork --wait '
        '"$bash_path" "$wrapper_snapshot"'
        in starter
    )
    assert '--starter-sha256 SHA256 --wrapper PATH' in starter
    assert 'mkdir -- "$control_dir"' in starter
    assert 'mkdir -p' not in starter
    assert (
        './.venv/bin/python -m repro.aistation_clock_bracket \\\n'
        '  publish-and-launch \\\n'
        in wrapper
    )
    assert './.venv/bin/python -u -m' not in wrapper
    assert wrapper.count(
        './.venv/bin/python -m repro.aistation_clock_bracket'
    ) == 1
    assert '"proc_ppid": %s' in wrapper
    assert '"proc_exe": "%s"' in wrapper
    assert 'python.stdout.log' in wrapper
    assert 'python.stderr.log' in wrapper
    assert 'envelope.log' in starter
    assert 'current_ppid" != "$$"' in wrapper
    assert 'current_start_ticks" != "$expected_start_ticks"' in wrapper
    revalidation = wrapper.index(
        'current_start_ticks" != "$expected_start_ticks"'
    )
    assert revalidation < wrapper.index('kill -TERM "$pid"')
    assert "set -e" not in {
        line.strip()
        for line in wrapper.splitlines()
        if not line.lstrip().startswith("#")
    }


@pytest.mark.skipif(
    not sys.platform.startswith("linux")
    or shutil.which("setsid") is None
    or not Path("/proc/self/stat").is_file(),
    reason="the durable process attestation contract requires Linux /proc",
)
@pytest.mark.parametrize(
    ("run_id", "python_exit_code", "terminal_status"),
    (
        ("durable-test-run", 0, "completed"),
        ("durable-nonzero-run", 7, "failed"),
    ),
)
def test_durable_start_is_one_shot_and_records_terminal_evidence(
    tmp_path,
    run_id,
    python_exit_code,
    terminal_status,
):
    root = tmp_path / "zoology"
    root.mkdir()
    (root / ".gitignore").write_text(
        "/.venv/\n/artifacts/\n/runs/\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text("fixture\n", encoding="utf-8")
    module = root / "repro" / "aistation_clock_bracket.py"
    module.parent.mkdir()
    (module.parent / "__init__.py").write_text("", encoding="utf-8")
    module.write_text(
        "import pathlib\n"
        "import sys\n"
        "import time\n"
        "suite = pathlib.Path(sys.argv[sys.argv.index('--suite-dir') + 1])\n"
        "path = pathlib.Path('artifacts') / suite.name / 'invocation.txt'\n"
        "with path.open('a', encoding='utf-8') as stream:\n"
        "    stream.write('\\n'.join(sys.argv[1:]) + '\\n')\n"
        "time.sleep(2)\n"
        "print('{\"ok\": true}')\n"
        f"raise SystemExit({python_exit_code})\n",
        encoding="utf-8",
    )
    _run("git", "init", cwd=root)
    _run("git", "config", "user.name", "Fixture", cwd=root)
    _run("git", "config", "user.email", "fixture@example.invalid", cwd=root)
    _run("git", "add", ".gitignore", "README.md", "repro", cwd=root)
    _run("git", "commit", "-m", "fixture", cwd=root)
    formal_sha = _run("git", "rev-parse", "HEAD", cwd=root).stdout.strip()
    formal_tree = _run(
        "git",
        "rev-parse",
        "HEAD^{tree}",
        cwd=root,
    ).stdout.strip()
    _run("git", "checkout", "--detach", formal_sha, cwd=root)

    bundle_dir = root / "artifacts" / run_id / "controller"
    launcher_dir = root / "artifacts" / run_id / "launcher"
    suite_dir = root / "runs" / run_id
    control_dir = root / "artifacts" / run_id / "formal-launch-control"
    bundle_dir.mkdir(parents=True)
    launcher_dir.mkdir()
    suite_dir.mkdir(parents=True)

    invocation_path = root / "artifacts" / run_id / "invocation.txt"
    python = root / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.symlink_to(Path(sys.executable).resolve())

    replacements = {
        "/huyang2/zoology": str(root),
        FORMAL_SHA: formal_sha,
        FORMAL_TREE: formal_tree,
    }

    def materialize(source: Path, destination: Path) -> None:
        text = source.read_text(encoding="utf-8")
        for old, new in replacements.items():
            text = text.replace(old, new)
        destination.write_text(text, encoding="utf-8")
        destination.chmod(0o700)

    starter = launcher_dir / STARTER.name
    wrapper = launcher_dir / WRAPPER.name
    materialize(STARTER, starter)
    materialize(WRAPPER, wrapper)
    starter_sha256 = _sha256(starter)
    wrapper_sha256 = _sha256(wrapper)
    command = [
        str(starter),
        "--starter-sha256",
        starter_sha256,
        "--wrapper",
        str(wrapper),
        "--wrapper-sha256",
        wrapper_sha256,
        "--bundle-dir",
        str(bundle_dir),
        "--suite-dir",
        str(suite_dir),
        "--control-dir",
        str(control_dir),
    ]

    started = time.monotonic()
    first = subprocess.run(
        command,
        check=True,
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert time.monotonic() - started < 1.5
    start_result = json.loads(first.stdout)
    assert start_result["starter_sha256"] == starter_sha256
    assert start_result["wrapper_sha256"] == wrapper_sha256

    deadline = time.monotonic() + 10
    terminal_path = control_dir / "terminal.json"
    while time.monotonic() < deadline and not terminal_path.is_file():
        time.sleep(0.05)
    assert terminal_path.is_file()

    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    attempt = json.loads(
        (control_dir / "attempt.json").read_text(encoding="utf-8")
    )
    python_start = json.loads(
        (control_dir / "python-start.json").read_text(encoding="utf-8")
    )
    wrapper_start = json.loads(
        (control_dir / "wrapper-start.json").read_text(encoding="utf-8")
    )
    assert terminal["status"] == terminal_status
    assert terminal["python_exit_code"] == python_exit_code
    assert attempt["starter_sha256"] == starter_sha256
    assert attempt["wrapper_sha256"] == wrapper_sha256
    assert wrapper_start["proc_sid"] == wrapper_start["pid"]
    assert wrapper_start["proc_tty_nr"] == 0
    assert python_start["proc_ppid"] == terminal["wrapper_pid"]
    assert python_start["proc_sid"] == wrapper_start["proc_sid"]
    assert python_start["proc_tty_nr"] == 0
    assert python_start["command"] == [
        "./.venv/bin/python",
        "-m",
        "repro.aistation_clock_bracket",
        "publish-and-launch",
        "--bundle-dir",
        str(bundle_dir),
        "--suite-dir",
        str(suite_dir),
    ]
    assert invocation_path.read_text(encoding="utf-8").splitlines() == [
        "publish-and-launch",
        "--bundle-dir",
        str(bundle_dir),
        "--suite-dir",
        str(suite_dir),
    ]
    expected_hashes = {
        "attempt_sha256": control_dir / "attempt.json",
        "starter_start_sha256": control_dir / "start.json",
        "wrapper_start_sha256": control_dir / "wrapper-start.json",
        "python_start_sha256": control_dir / "python-start.json",
        "envelope_log_sha256": control_dir / "envelope.log",
        "python_stdout_sha256": control_dir / "python.stdout.log",
        "python_stderr_sha256": control_dir / "python.stderr.log",
    }
    for field, evidence_path in expected_hashes.items():
        assert terminal[field] == _sha256(evidence_path)

    second = subprocess.run(
        command,
        check=False,
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert second.returncode != 0
    assert "start attempt is consumed" in second.stderr
    assert invocation_path.read_text(encoding="utf-8").splitlines().count(
        "publish-and-launch"
    ) == 1
