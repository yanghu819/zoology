from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research" / "control" / "linux_exact_test_gate.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("linux_exact_test_gate", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_junit(
    path: Path,
    *,
    passed: int,
    skipped: int = 0,
    failures: int = 0,
    errors: int = 0,
) -> None:
    cases = []
    for index in range(passed):
        cases.append(f'<testcase classname="gate" name="pass-{index}" />')
    for index in range(skipped):
        cases.append(
            f'<testcase classname="gate" name="skip-{index}"><skipped /></testcase>'
        )
    for index in range(failures):
        cases.append(
            f'<testcase classname="gate" name="failure-{index}"><failure /></testcase>'
        )
    for index in range(errors):
        cases.append(
            f'<testcase classname="gate" name="error-{index}"><error /></testcase>'
        )
    total = passed + skipped + failures + errors
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>'
        '<testsuites name="pytest tests">'
        f'<testsuite name="pytest" errors="{errors}" failures="{failures}" '
        f'skipped="{skipped}" '
        f'tests="{total}" time="0.001">'
        + "".join(cases)
        + "</testsuite></testsuites>",
        encoding="utf-8",
    )


def _build_fixture(tmp_path: Path):
    gate = _load_gate()
    repo = tmp_path / "zoology"
    launcher = repo / "artifacts" / "gate-run" / "launcher"
    tests = launcher / "tests"
    tests.mkdir(parents=True)
    copied_script = launcher / gate.SCRIPT_NAME
    shutil.copyfile(SCRIPT, copied_script)
    copied_script.chmod(0o700)
    tracked_gate = launcher / "research" / "control" / gate.SCRIPT_NAME
    tracked_gate.parent.mkdir(parents=True)
    shutil.copyfile(SCRIPT, tracked_gate)
    for relative_name in gate.FIXED_SOURCE_SHA256:
        source = ROOT / relative_name
        destination = launcher / relative_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    for source_name, runtime_name in gate.RUNTIME_COPY_BY_SOURCE.items():
        runtime = launcher / runtime_name
        shutil.copyfile(ROOT / source_name, runtime)
        runtime.chmod(0o700)
    for relative_name in gate.TEST_MODULE_SHA256:
        source = ROOT / relative_name
        destination = launcher / relative_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    fake_target = repo / "fake-python"
    fake_target.write_text(
        "#!/usr/bin/env python3\n"
        "import os\n"
        "import pathlib\n"
        "import sys\n"
        "import time\n"
        "junit = next(arg.split('=', 1)[1] for arg in sys.argv if arg.startswith('--junitxml='))\n"
        "required = {\n"
        "    'CUDA_VISIBLE_DEVICES': '',\n"
        "    'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',\n"
        "    'PYTEST_ADDOPTS': '',\n"
        "    'PYTEST_PLUGINS': '',\n"
        "    'PYTHONDONTWRITEBYTECODE': '1',\n"
        "    'PYTHONNOUSERSITE': '1',\n"
        "    'PYTHONPATH': '',\n"
        "}\n"
        "if any(os.environ.get(key) != value for key, value in required.items()):\n"
        "    raise SystemExit(91)\n"
        "parent = pathlib.Path(junit).parent\n"
        "for key in ('PYTHONPYCACHEPREFIX', 'TMPDIR', 'TEMP', 'TMP'):\n"
        "    if not pathlib.Path(os.environ[key]).is_relative_to(parent):\n"
        "        raise SystemExit(92)\n"
        "mode = os.environ.get('FAKE_GATE_RESULT', 'pass')\n"
        "if mode == 'timeout':\n"
        "    time.sleep(2)\n"
        "passed, skipped = (53, 0) if mode == 'pass' else (52, 1)\n"
        "cases = [f'<testcase classname=\"gate\" name=\"pass-{i}\" />' for i in range(passed)]\n"
        "cases += [\n"
        "    f'<testcase classname=\"gate\" name=\"skip-{i}\"><skipped /></testcase>'\n"
        "    for i in range(skipped)\n"
        "]\n"
        "pathlib.Path(junit).write_text(\n"
        "    '<testsuites><testsuite name=\"pytest\" errors=\"0\" failures=\"0\" '\n"
        "    f'skipped=\"{skipped}\" tests=\"{passed + skipped}\">'\n"
        "    + ''.join(cases) + '</testsuite></testsuites>', encoding='utf-8')\n"
        "print(f'{passed} passed, {skipped} skipped')\n",
        encoding="utf-8",
    )
    fake_target.chmod(0o700)
    fake_python = repo / ".venv" / "bin" / "python"
    fake_python.parent.mkdir(parents=True)
    fake_python.symlink_to(fake_target)
    return gate, repo, copied_script


def test_gate_contract_is_syntactically_valid_and_freezes_five_modules():
    gate = _load_gate()
    source = SCRIPT.read_text(encoding="utf-8")

    subprocess.run(["python3", "-m", "py_compile", str(SCRIPT)], check=True)
    assert gate.EXPECTED_TESTS == 53
    assert gate.PYTEST_TIMEOUT_SECONDS == 300
    assert len(gate.FIXED_SOURCE_SHA256) == 6
    assert len(gate.RUNTIME_COPY_BY_SOURCE) == 4
    for relative_name, expected_hash in gate.FIXED_SOURCE_SHA256.items():
        assert _sha256(ROOT / relative_name) == expected_hash
    assert list(gate.TEST_MODULE_SHA256) == [
        "tests/test_durable_init_baseline_control.py",
        "tests/test_durable_preflight_v2_control.py",
        "tests/test_durable_publish_launch_control.py",
        "tests/test_detached_process_smoke_control.py",
        "tests/test_durable_preflight_control.py",
    ]
    for relative_name, expected_hash in gate.TEST_MODULE_SHA256.items():
        assert _sha256(ROOT / relative_name) == expected_hash
    assert '"CUDA_VISIBLE_DEVICES": ""' in source
    assert '"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"' in source
    assert '"PYTEST_ADDOPTS": ""' in source
    assert '"PYTEST_PLUGINS": ""' in source
    assert '"PYTHONPYCACHEPREFIX": str(pycache)' in source
    assert '"TMPDIR": str(tmp)' in source
    assert '"--basetemp"' in source
    assert 'f"--junitxml={junit}"' in source
    assert '"no:cacheprovider"' in source
    assert '"--noconftest"' in source


def test_junit_validator_accepts_only_exact_53_passes(tmp_path):
    gate = _load_gate()
    exact = tmp_path / "exact.xml"
    _write_junit(exact, passed=53)
    counts = gate._read_junit_counts(exact)
    gate._require_exact_success(counts, 0)
    assert counts == {
        "tests": 53,
        "passed": 53,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
        "disabled": 0,
        "testcase_nodes": 53,
    }

    skipped = tmp_path / "skipped.xml"
    _write_junit(skipped, passed=52, skipped=1)
    with pytest.raises(gate.GateError, match="not exact 53/0"):
        gate._require_exact_success(gate._read_junit_counts(skipped), 0)
    with pytest.raises(gate.GateError, match="exited nonzero"):
        gate._require_exact_success(counts, 1)

    for name, outcome in (("failure", {"failures": 1}), ("error", {"errors": 1})):
        rejected = tmp_path / f"{name}.xml"
        _write_junit(rejected, passed=52, **outcome)
        with pytest.raises(gate.GateError, match="not exact 53/0"):
            gate._require_exact_success(gate._read_junit_counts(rejected), 0)


def test_junit_validator_rejects_summary_node_disagreement(tmp_path):
    gate = _load_gate()
    malformed = tmp_path / "disagreement.xml"
    _write_junit(malformed, passed=53)
    payload = malformed.read_text(encoding="utf-8").replace(
        'tests="53"',
        'tests="52"',
    )
    malformed.write_text(payload, encoding="utf-8")
    with pytest.raises(gate.GateError, match="disagrees with testcase nodes"):
        gate._read_junit_counts(malformed)


def test_gate_runs_with_repo_local_outputs_and_records_exact_success(tmp_path):
    gate, repo, script = _build_fixture(tmp_path)
    terminal = gate._run_gate(repo, script, "gate-run", _sha256(script))

    control = repo / "artifacts" / "gate-run" / gate.CONTROL_NAME
    assert terminal["status"] == "completed"
    assert terminal["counts"]["passed"] == 53
    for name, digest in terminal["evidence_sha256"].items():
        assert digest == _sha256(control / name)
    assert sorted(path.name for path in control.iterdir()) == [
        "attempt.json",
        "junit.xml",
        "pycache",
        "pytest.exit",
        "pytest.ini",
        "pytest.log",
        "terminal.json",
        "tmp",
    ]
    attempt = json.loads((control / "attempt.json").read_text(encoding="utf-8"))
    assert attempt["command"][0] == str(repo / ".venv" / "bin" / "python")
    assert (repo / ".venv" / "bin" / "python").is_symlink()
    assert attempt["environment_overrides"]["CUDA_VISIBLE_DEVICES"] == ""
    assert len(attempt["source_sha256"]) == 7
    assert len(attempt["runtime_copy_sha256"]) == 4
    for key in ("PYTHONPYCACHEPREFIX", "TMPDIR", "TEMP", "TMP"):
        assert Path(attempt["environment_overrides"][key]).is_relative_to(control)
    assert not (repo / ".pytest_cache").exists()
    assert not (repo / "artifacts" / "gate-run" / "launcher" / ".pytest_cache").exists()


def test_gate_fails_closed_on_skip_and_consumes_attempt(tmp_path, monkeypatch):
    gate, repo, script = _build_fixture(tmp_path)
    monkeypatch.setenv("FAKE_GATE_RESULT", "skip")
    with pytest.raises(gate.GateError, match="not exact 53/0"):
        gate._run_gate(repo, script, "gate-run", _sha256(script))

    control = repo / "artifacts" / "gate-run" / gate.CONTROL_NAME
    terminal = json.loads((control / "terminal.json").read_text(encoding="utf-8"))
    assert terminal["status"] == "failed"
    assert terminal["counts"]["skipped"] == 1
    with pytest.raises(gate.GateError, match="already consumed"):
        gate._run_gate(repo, script, "gate-run", _sha256(script))


def test_gate_fails_before_pytest_when_a_frozen_module_drifts(tmp_path):
    gate, repo, script = _build_fixture(tmp_path)
    drifted = (
        repo
        / "artifacts"
        / "gate-run"
        / "launcher"
        / "tests"
        / "test_durable_preflight_control.py"
    )
    drifted.write_text("drift\n", encoding="utf-8")

    with pytest.raises(gate.GateError, match="module SHA256 drifted"):
        gate._run_gate(repo, script, "gate-run", _sha256(script))
    control = repo / "artifacts" / "gate-run" / gate.CONTROL_NAME
    assert not (control / "pytest.log").exists()
    terminal = json.loads((control / "terminal.json").read_text(encoding="utf-8"))
    assert terminal["status"] == "failed"


@pytest.mark.parametrize("kind", ["source", "runtime"])
def test_gate_fails_before_pytest_when_control_source_or_runtime_drifts(
    tmp_path,
    kind,
):
    gate, repo, script = _build_fixture(tmp_path)
    launcher = repo / "artifacts" / "gate-run" / "launcher"
    if kind == "source":
        drifted = launcher / "research" / "control" / "durable_preflight_v2.sh"
        expected_message = "control source SHA256 drifted"
    else:
        drifted = launcher / "durable_preflight_v2.sh"
        expected_message = "runtime control copy differs"
    drifted.write_text("drift\n", encoding="utf-8")

    with pytest.raises(gate.GateError, match=expected_message):
        gate._run_gate(repo, script, "gate-run", _sha256(script))
    control = repo / "artifacts" / "gate-run" / gate.CONTROL_NAME
    assert not (control / "pytest.log").exists()


def test_gate_times_out_fail_closed(tmp_path, monkeypatch):
    gate, repo, script = _build_fixture(tmp_path)
    monkeypatch.setenv("FAKE_GATE_RESULT", "timeout")
    monkeypatch.setattr(gate, "PYTEST_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(gate.GateError, match="exceeded frozen"):
        gate._run_gate(repo, script, "gate-run", _sha256(script))

    control = repo / "artifacts" / "gate-run" / gate.CONTROL_NAME
    terminal = json.loads((control / "terminal.json").read_text(encoding="utf-8"))
    assert terminal["status"] == "failed"
    assert terminal["pytest_exit_code"] == 124
    assert terminal["pytest_timeout_seconds"] == 0.01


def test_real_pytest_ignores_parent_config_conftest_and_inherited_options(
    tmp_path,
    monkeypatch,
):
    gate = _load_gate()
    repo = tmp_path / "zoology"
    launcher = repo / "artifacts" / "isolated-run" / "launcher"
    test_path = launcher / "tests" / "test_one.py"
    test_path.parent.mkdir(parents=True)
    test_path.write_text("def test_one():\n    assert True\n", encoding="utf-8")
    script = launcher / gate.SCRIPT_NAME
    shutil.copyfile(SCRIPT, script)
    script.chmod(0o700)
    python_entry = repo / ".venv" / "bin" / "python"
    python_entry.parent.mkdir(parents=True)
    python_delegate = repo / "pytest-python"
    python_delegate.write_text(
        "#!/usr/bin/env python3\n"
        "import os\n"
        "import sys\n"
        "environment = os.environ.copy()\n"
        "environment.pop('PYTHONNOUSERSITE', None)\n"
        "os.execve(sys.executable, [sys.executable, *sys.argv[1:]], environment)\n",
        encoding="utf-8",
    )
    python_delegate.chmod(0o700)
    python_entry.symlink_to(python_delegate)

    run_artifact = launcher.parent
    sentinel = run_artifact / "conftest-loaded"
    (run_artifact / "conftest.py").write_text(
        f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('loaded')\n",
        encoding="utf-8",
    )
    (run_artifact / "pytest.ini").write_text(
        "[pytest]\naddopts = -k definitely_missing\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k definitely_missing")
    monkeypatch.setenv("PYTEST_PLUGINS", "plugin_that_must_not_load")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "outside-pythonpath"))
    monkeypatch.setattr(gate, "EXPECTED_TESTS", 1)
    monkeypatch.setattr(
        gate,
        "TEST_MODULE_SHA256",
        {"tests/test_one.py": _sha256(test_path)},
    )
    monkeypatch.setattr(gate, "FIXED_SOURCE_SHA256", {})
    monkeypatch.setattr(gate, "RUNTIME_COPY_BY_SOURCE", {})
    gate_source = launcher / "research" / "control" / gate.SCRIPT_NAME
    gate_source.parent.mkdir(parents=True)
    shutil.copyfile(SCRIPT, gate_source)

    terminal = gate._run_gate(repo, script, "isolated-run", _sha256(script))
    assert terminal["status"] == "completed"
    assert terminal["counts"]["passed"] == 1
    assert not sentinel.exists()


def test_gate_rejects_symlinked_junit(tmp_path):
    gate = _load_gate()
    real = tmp_path / "real.xml"
    _write_junit(real, passed=53)
    linked = tmp_path / "linked.xml"
    linked.symlink_to(real)
    assert stat.S_ISLNK(linked.lstat().st_mode)
    with pytest.raises(gate.GateError, match="canonical real file"):
        gate._read_junit_counts(linked)
