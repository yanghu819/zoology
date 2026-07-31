#!/usr/bin/env python3
"""Run the frozen Linux durable-control tests without exposing a GPU."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


REPO_ROOT = Path("/huyang2/zoology")
SCRIPT_NAME = "linux_exact_test_gate.py"
CONTROL_NAME = "linux-exact-test-gate"
EXPECTED_TESTS = 53
PYTEST_TIMEOUT_SECONDS = 300
FIXED_SOURCE_SHA256 = {
    "research/control/durable_init_baseline.sh": (
        "26ed9ba1dd0cff7cd2c15a2ab372077b79abd33e5c69ce7dcd8a4d3a77a27541"
    ),
    "research/control/durable_preflight_v2.sh": (
        "3b1d5b682624be4149ae1ff30e9860f2904c794f047c579e00131bf7e25c93cd"
    ),
    "research/control/durable_publish_launch_start.sh": (
        "6e2eea84a1386598da5e5d48df85a9c0264f212b008ac265fd63bf2a00133b44"
    ),
    "research/control/durable_publish_launch_wrapper.sh": (
        "e326e8dd999ae7870eeeffc5429e588f53ca31ad2b896c27be691725f117e4eb"
    ),
    "research/control/detached_process_smoke.sh": (
        "59339b6977bac9c763d469a6e2dbe22de51563b27188f3b6b0b7d8acb3980d13"
    ),
    "research/control/durable_preflight.sh": (
        "3264d8d2fc52f924da801c4bb201ca2ecbc66eaf4edbf032097a6e419a28b3fc"
    ),
}
RUNTIME_COPY_BY_SOURCE = {
    "research/control/durable_init_baseline.sh": "durable_init_baseline.sh",
    "research/control/durable_preflight_v2.sh": "durable_preflight_v2.sh",
    "research/control/durable_publish_launch_start.sh": (
        "durable_publish_launch_start.sh"
    ),
    "research/control/durable_publish_launch_wrapper.sh": (
        "durable_publish_launch_wrapper.sh"
    ),
}
TEST_MODULE_SHA256 = {
    "tests/test_durable_init_baseline_control.py": (
        "b0bd42aed32f6773d86e446a8a411be79b4b70578fd3d8ef923fc49ca735cac7"
    ),
    "tests/test_durable_preflight_v2_control.py": (
        "c5786fb484434a6e32d56c86038ae071a9ef0c035cfb6491f476729d9c9ad5be"
    ),
    "tests/test_durable_publish_launch_control.py": (
        "361919534b2f8a02b8c8fa84564e0f23925cf2c9488089cd310d0493079e7355"
    ),
    "tests/test_detached_process_smoke_control.py": (
        "abbf2f330c8e9d4fa5071d17be32c9a054684c98681df57762db3e579cdf326e"
    ),
    "tests/test_durable_preflight_control.py": (
        "40a46386675158cfa656ad6b372cb1571ce5c7df2a5753c26a90ac7c746e0ce0"
    ),
}

RUN_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]*")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class GateError(RuntimeError):
    """The exact Linux test gate rejected its inputs or results."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_real_directory(path: Path, label: str) -> Path:
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise GateError(f"{label} is missing: {path}") from error
    if not stat.S_ISDIR(metadata.st_mode) or path.resolve(strict=True) != path:
        raise GateError(f"{label} is not a canonical real directory: {path}")
    return path


def _require_real_file(path: Path, label: str) -> Path:
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise GateError(f"{label} is missing: {path}") from error
    if not stat.S_ISREG(metadata.st_mode) or path.resolve(strict=True) != path:
        raise GateError(f"{label} is not a canonical real file: {path}")
    return path


def _write_exclusive(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _write_json_exclusive(path: Path, payload: dict[str, object]) -> None:
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    _write_exclusive(path, serialized.encode("utf-8"))


def _hash_if_real_file(path: Path) -> str | None:
    try:
        return _sha256(_require_real_file(path, "gate evidence"))
    except GateError:
        return None


def _launcher_file_inventory(launcher: Path) -> set[str]:
    inventory = set()
    for path in launcher.rglob("*"):
        if path.is_symlink() or path.is_file():
            inventory.add(path.relative_to(launcher).as_posix())
    return inventory


def _decimal_attribute(element: ET.Element, name: str, label: str) -> int:
    value = element.get(name)
    if value is None or re.fullmatch(r"[0-9]+", value) is None:
        raise GateError(f"{label} {name} is not a nonnegative decimal integer")
    return int(value)


def _read_junit_counts(path: Path) -> dict[str, int]:
    _require_real_file(path, "JUnit XML")
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as error:
        raise GateError(f"JUnit XML is malformed: {error}") from error

    if root.tag == "testsuite":
        suites = [root]
    elif root.tag == "testsuites":
        suites = [child for child in root if child.tag == "testsuite"]
        if len(suites) != len(list(root)):
            raise GateError("JUnit XML contains a non-testsuite root child")
    else:
        raise GateError(f"JUnit XML has an unexpected root tag: {root.tag}")
    if not suites:
        raise GateError("JUnit XML contains no test suites")

    aggregate = {
        "tests": 0,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
        "disabled": 0,
    }
    testcase_count = 0
    testcase_outcomes = {
        "failures": 0,
        "errors": 0,
        "skipped": 0,
    }
    for suite_index, suite in enumerate(suites):
        label = f"JUnit suite {suite_index}"
        for field in ("tests", "failures", "errors", "skipped"):
            aggregate[field] += _decimal_attribute(suite, field, label)
        if suite.get("disabled") is not None:
            aggregate["disabled"] += _decimal_attribute(suite, "disabled", label)

        cases = [child for child in suite if child.tag == "testcase"]
        testcase_count += len(cases)
        for case in cases:
            outcomes = [
                child.tag
                for child in case
                if child.tag in {"failure", "error", "skipped"}
            ]
            if len(outcomes) > 1:
                raise GateError("JUnit testcase has multiple terminal outcomes")
            if outcomes:
                field = f"{outcomes[0]}s" if outcomes[0] != "skipped" else "skipped"
                testcase_outcomes[field] += 1

    if aggregate["tests"] != testcase_count:
        raise GateError(
            "JUnit test count disagrees with testcase nodes: "
            f"summary={aggregate['tests']} nodes={testcase_count}"
        )
    for field in ("failures", "errors", "skipped"):
        if aggregate[field] != testcase_outcomes[field]:
            raise GateError(
                f"JUnit {field} count disagrees with testcase nodes: "
                f"summary={aggregate[field]} nodes={testcase_outcomes[field]}"
            )
    terminal_outcomes = sum(aggregate[field] for field in ("failures", "errors", "skipped"))
    if terminal_outcomes > aggregate["tests"]:
        raise GateError("JUnit terminal outcomes exceed its test count")

    aggregate["passed"] = aggregate["tests"] - terminal_outcomes
    aggregate["testcase_nodes"] = testcase_count
    return aggregate


def _require_exact_success(counts: dict[str, int], exit_code: int) -> None:
    expected = {
        "tests": EXPECTED_TESTS,
        "passed": EXPECTED_TESTS,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
        "disabled": 0,
        "testcase_nodes": EXPECTED_TESTS,
    }
    if exit_code != 0:
        raise GateError(f"pytest exited nonzero: {exit_code}")
    if counts != expected:
        raise GateError(f"pytest result is not exact {EXPECTED_TESTS}/0: {counts}")


def _run_gate(
    repo_root: Path,
    script_path: Path,
    run_id: str,
    expected_script_sha256: str,
) -> dict[str, object]:
    if RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise GateError("run id must contain lowercase letters, digits, and hyphens")
    if SHA256_PATTERN.fullmatch(expected_script_sha256) is None:
        raise GateError("script SHA256 must be 64 lowercase hexadecimal characters")

    repo_root = _require_real_directory(repo_root, "repository root")
    artifacts = _require_real_directory(repo_root / "artifacts", "artifact root")
    run_artifact = _require_real_directory(artifacts / run_id, "run artifact")
    launcher = _require_real_directory(run_artifact / "launcher", "launcher")
    canonical_script = launcher / SCRIPT_NAME
    script_path = _require_real_file(script_path, "gate script")
    if script_path != canonical_script:
        raise GateError(f"gate script is not the canonical launcher copy: {script_path}")
    actual_script_sha256 = _sha256(script_path)
    if actual_script_sha256 != expected_script_sha256:
        raise GateError("gate script SHA256 differs from the frozen value")

    control = run_artifact / CONTROL_NAME
    try:
        control.mkdir(mode=0o700)
    except FileExistsError as error:
        raise GateError(f"test gate attempt is already consumed: {control}") from error

    counts: dict[str, int] | None = None
    exit_code: int | None = None
    reason = ""
    status = "failed"
    command: list[str] = []
    module_hashes: dict[str, str] = {}
    source_hashes: dict[str, str] = {}
    runtime_hashes: dict[str, str] = {}
    try:
        gate_source_name = f"research/control/{SCRIPT_NAME}"
        gate_source = _require_real_file(
            launcher / gate_source_name,
            "tracked gate source copy",
        )
        if _sha256(gate_source) != actual_script_sha256:
            raise GateError("tracked gate source and runtime copy differ")
        source_hashes[gate_source_name] = actual_script_sha256

        for relative_name, expected_hash in FIXED_SOURCE_SHA256.items():
            source_path = _require_real_file(
                launcher / relative_name,
                f"frozen control source {relative_name}",
            )
            actual_hash = _sha256(source_path)
            if actual_hash != expected_hash:
                raise GateError(f"frozen control source SHA256 drifted: {relative_name}")
            source_hashes[relative_name] = actual_hash

        for source_name, runtime_name in RUNTIME_COPY_BY_SOURCE.items():
            runtime_path = _require_real_file(
                launcher / runtime_name,
                f"runtime control copy {runtime_name}",
            )
            if not os.access(runtime_path, os.X_OK):
                raise GateError(f"runtime control copy is not executable: {runtime_name}")
            actual_hash = _sha256(runtime_path)
            if actual_hash != source_hashes[source_name]:
                raise GateError(f"runtime control copy differs from source: {runtime_name}")
            runtime_hashes[runtime_name] = actual_hash

        test_paths = []
        for relative_name, expected_hash in TEST_MODULE_SHA256.items():
            test_path = _require_real_file(
                launcher / relative_name,
                f"frozen test module {relative_name}",
            )
            actual_hash = _sha256(test_path)
            if actual_hash != expected_hash:
                raise GateError(f"frozen test module SHA256 drifted: {relative_name}")
            module_hashes[relative_name] = actual_hash
            test_paths.append(test_path)

        expected_inventory = (
            set(source_hashes)
            | set(runtime_hashes)
            | set(module_hashes)
            | {SCRIPT_NAME}
        )
        actual_inventory = _launcher_file_inventory(launcher)
        if actual_inventory != expected_inventory:
            raise GateError(
                "launcher file inventory drifted: "
                f"expected={sorted(expected_inventory)} actual={sorted(actual_inventory)}"
            )

        python_entry = repo_root / ".venv" / "bin" / "python"
        try:
            python_target = python_entry.resolve(strict=True)
        except FileNotFoundError as error:
            raise GateError("project Python is missing") from error
        if not python_target.is_file() or not os.access(python_target, os.X_OK):
            raise GateError("resolved project Python is not an executable regular file")

        tmp = control / "tmp"
        pycache = control / "pycache"
        tmp.mkdir(mode=0o700)
        pycache.mkdir(mode=0o700)
        basetemp = control / "basetemp"
        junit = control / "junit.xml"
        log = control / "pytest.log"
        pytest_config = control / "pytest.ini"
        _write_exclusive(pytest_config, b"[pytest]\n")
        command = [
            str(python_entry),
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--noconftest",
            "-c",
            str(pytest_config),
            "--basetemp",
            str(basetemp),
            f"--junitxml={junit}",
            *(str(path) for path in test_paths),
        ]
        environment_overrides = {
            "CUDA_VISIBLE_DEVICES": "",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTEST_ADDOPTS": "",
            "PYTEST_PLUGINS": "",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": "",
            "PYTHONPYCACHEPREFIX": str(pycache),
            "TMPDIR": str(tmp),
            "TEMP": str(tmp),
            "TMP": str(tmp),
        }
        _write_json_exclusive(
            control / "attempt.json",
            {
                "command": command,
                "control_dir": str(control),
                "environment_overrides": environment_overrides,
                "expected_tests": EXPECTED_TESTS,
                "pytest_timeout_seconds": PYTEST_TIMEOUT_SECONDS,
                "run_id": run_id,
                "schema_version": 1,
                "script_sha256": actual_script_sha256,
                "source_sha256": source_hashes,
                "test_module_sha256": module_hashes,
                "runtime_copy_sha256": runtime_hashes,
            },
        )

        environment = os.environ.copy()
        environment.update(environment_overrides)
        descriptor = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as log_stream:
            try:
                completed = subprocess.run(
                    command,
                    cwd=launcher,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=log_stream,
                    stderr=subprocess.STDOUT,
                    check=False,
                    timeout=PYTEST_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired as error:
                exit_code = 124
                log_stream.flush()
                os.fsync(log_stream.fileno())
                _write_exclusive(
                    control / "pytest.exit",
                    f"{exit_code}\n".encode("ascii"),
                )
                raise GateError(
                    f"pytest exceeded frozen {PYTEST_TIMEOUT_SECONDS}-second timeout"
                ) from error
            log_stream.flush()
            os.fsync(log_stream.fileno())
        if exit_code is None:
            exit_code = completed.returncode
        _write_exclusive(control / "pytest.exit", f"{exit_code}\n".encode("ascii"))
        counts = _read_junit_counts(junit)
        _require_exact_success(counts, exit_code)
        if _sha256(script_path) != actual_script_sha256:
            raise GateError("gate script drifted while pytest was running")
        for relative_name, expected_hash in TEST_MODULE_SHA256.items():
            if _sha256(launcher / relative_name) != expected_hash:
                raise GateError(
                    f"frozen test module drifted while pytest was running: {relative_name}"
                )
        for relative_name, expected_hash in source_hashes.items():
            if _sha256(launcher / relative_name) != expected_hash:
                raise GateError(
                    f"control source drifted while pytest was running: {relative_name}"
                )
        for relative_name, expected_hash in runtime_hashes.items():
            if _sha256(launcher / relative_name) != expected_hash:
                raise GateError(
                    f"runtime copy drifted while pytest was running: {relative_name}"
                )
        if _launcher_file_inventory(launcher) != expected_inventory:
            raise GateError("launcher file inventory drifted while pytest was running")
        status = "completed"
        reason = "exactly 53 tests passed with zero skips, failures, or errors"
    except Exception as error:
        reason = str(error)

    terminal = {
        "command": command,
        "counts": counts,
        "evidence_sha256": {
            "attempt.json": _hash_if_real_file(control / "attempt.json"),
            "junit.xml": _hash_if_real_file(control / "junit.xml"),
            "pytest.exit": _hash_if_real_file(control / "pytest.exit"),
            "pytest.ini": _hash_if_real_file(control / "pytest.ini"),
            "pytest.log": _hash_if_real_file(control / "pytest.log"),
        },
        "expected_tests": EXPECTED_TESTS,
        "pytest_timeout_seconds": PYTEST_TIMEOUT_SECONDS,
        "pytest_exit_code": exit_code,
        "reason": reason,
        "run_id": run_id,
        "schema_version": 1,
        "script_sha256": actual_script_sha256,
        "source_sha256": source_hashes,
        "status": status,
        "test_module_sha256": module_hashes,
        "runtime_copy_sha256": runtime_hashes,
    }
    _write_json_exclusive(control / "terminal.json", terminal)
    if status != "completed":
        raise GateError(reason)
    return terminal


def _parse_args(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--script-sha256", required=True)
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    options = _parse_args(sys.argv[1:] if arguments is None else arguments)
    try:
        if not sys.platform.startswith("linux") or not Path("/proc/self/stat").is_file():
            raise GateError("the exact test gate requires Linux /proc")
        _run_gate(
            REPO_ROOT,
            Path(__file__).resolve(strict=True),
            options.run_id,
            options.script_sha256,
        )
    except (GateError, OSError) as error:
        print(f"linux exact test gate: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
