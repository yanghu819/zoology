from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research" / "control" / "durable_init_baseline.sh"
PREFLIGHT_SCRIPT = ROOT / "research" / "control" / "durable_preflight_v2.sh"
FORMAL_SHA = "13f880b5fe61619a1006ef33610de69fbabaaec1"
FORMAL_TREE = "ed83a7188351ca2cce8aba46d1cb3b108ce31ec2"
PREFLIGHT_V2_SHA256 = (
    "3b1d5b682624be4149ae1ff30e9860f2904c794f047c579e00131bf7e25c93cd"
)


def _run(
    *arguments: str | Path,
    cwd: Path,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(argument) for argument in arguments],
        cwd=cwd,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wait_for(path: Path, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not path.is_file():
        time.sleep(0.05)
    assert path.is_file(), f"timed out waiting for {path}"


def _make_rollover_date(tmp_path: Path) -> Path:
    real_date = shutil.which("date")
    assert real_date is not None
    fake_bin = tmp_path / "rollover-bin"
    fake_bin.mkdir()
    state = tmp_path / "rollover-date-state"
    state.write_text("0\n", encoding="utf-8")
    fake_date = fake_bin / "date"
    fake_date.write_text(
        "#!/usr/bin/env bash\n"
        "set -u\n"
        f'state="{state}"\n'
        f'real_date="{Path(real_date).resolve()}"\n'
        "if [[ \"$#\" == 2 && \"$1\" == -u && \"$2\" == +%s ]]; then\n"
        "  while ! mkdir \"$state.lock\" 2>/dev/null; do sleep 0.01; done\n"
        "  count=$(<\"$state\")\n"
        "  printf '%s\\n' \"$((count + 1))\" > \"$state\"\n"
        "  rmdir \"$state.lock\"\n"
        "  printf '%s\\n' \"$((2000000000 + count))\"\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$#\" == 2 && \"$1\" == -u && "
        "\"$2\" == +%Y-%m-%dT%H:%M:%SZ ]]; then\n"
        "  printf '2033-05-18T03:33:19Z\\n'\n"
        "  exit 0\n"
        "fi\n"
        "exec \"$real_date\" \"$@\"\n",
        encoding="utf-8",
    )
    fake_date.chmod(0o755)
    return fake_bin


def _read_only_snapshot(*roots: Path) -> dict[str, tuple[int, int, int, str]]:
    snapshot: dict[str, tuple[int, int, int, str]] = {}
    for root in roots:
        paths = [root]
        if root.is_dir():
            paths.extend(sorted(root.rglob("*")))
        for path in paths:
            metadata = path.lstat()
            digest = _sha256(path) if path.is_file() and not path.is_symlink() else ""
            snapshot[str(path)] = (
                metadata.st_mode,
                metadata.st_mtime_ns,
                metadata.st_ctime_ns,
                digest,
            )
    return snapshot


def _make_fixture(
    tmp_path: Path,
    *,
    run_id: str,
    init_exit_code: int = 0,
    start_record_delay: float = 0,
    hang: bool = False,
    orphan_after_leader: bool = False,
    post_wait_delay: float = 0,
    starter_snapshot_failure: bool = False,
    signal_identity_mismatch: bool = False,
    supervisor_spawn_failure: bool = False,
    extra_suite_evidence: bool = False,
    preflight_status: str = "completed",
) -> dict[str, object]:
    repo = tmp_path / "zoology"
    repo.mkdir()
    (repo / ".gitignore").write_text(
        "/.venv/\n/artifacts/\n/runs/\n/data/\n",
        encoding="utf-8",
    )
    (repo / "runs").mkdir()
    path_contract = repo / "repro" / "path_contract.py"
    path_contract.parent.mkdir()
    path_contract.write_text(
        "import argparse\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--root', required=True)\n"
        "parser.add_argument('--require-environments', action='store_true')\n"
        "parser.add_argument('--validate-source', action='store_true')\n"
        "args = parser.parse_args()\n"
        "if not args.require_environments or not args.validate_source:\n"
        "    raise SystemExit(65)\n",
        encoding="utf-8",
    )
    module = repo / "repro" / "single_baseline.py"
    (module.parent / "__init__.py").write_text("", encoding="utf-8")
    module.write_text(
        "import argparse\n"
        "import json\n"
        "from pathlib import Path\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('command')\n"
        "parser.add_argument('--suite-dir', type=Path, required=True)\n"
        "args = parser.parse_args()\n"
        "if args.command != 'selected-index':\n"
        "    raise SystemExit(64)\n"
        "payload = json.loads((args.suite_dir / "
        "'single-baseline-manifest.json').read_text())\n"
        "if payload != {'selected_index': 5}:\n"
        "    raise SystemExit(65)\n"
        "print(5)\n",
        encoding="utf-8",
    )
    run_script = repo / "run.sh"
    if hang:
        body = (
            "sleep 30 &\n"
            "descendant=$!\n"
            f"printf '%s\\n' \"$descendant\" > artifacts/{run_id}/descendant.pid\n"
            "wait \"$descendant\"\n"
        )
    elif orphan_after_leader:
        body = (
            "sleep 30 &\n"
            "descendant=$!\n"
            f"printf '%s\\n' \"$descendant\" > "
            f"artifacts/{run_id}/descendant.pid\n"
            "exit 0\n"
        )
    elif init_exit_code:
        body = f"sleep 0.4\nexit {init_exit_code}\n"
    else:
        body = (
            "sleep 0.4\n"
            "mkdir \"$2\"\n"
            "mkdir \"$2/logs\" \"$2/claims\" \"$2/launches\"\n"
            "printf 'source\\n' > \"$2/source.tar.gz\"\n"
            "printf 'source-checksum\\n' > \"$2/source.tar.gz.sha256\"\n"
            "printf '{\"cache\": true}\\n' > \"$2/cache-manifest.json\"\n"
            "printf 'cache-checksum\\n' > \"$2/cache-manifest.json.sha256\"\n"
            "printf 'gpu inventory\\n' > \"$2/nvidia-smi.txt\"\n"
            "printf '{\"runtime\": true}\\n' > \"$2/runtime-attestation.json\"\n"
            "printf '{\"suite\": true}\\n' > \"$2/suite-manifest.json\"\n"
            "printf '{\"selected_index\": 5}\\n' > "
            "\"$2/single-baseline-manifest.json\"\n"
            + (
                "printf '{\"too_late\": true}\\n' > "
                "\"$2/clock-bracket.json\"\n"
                if extra_suite_evidence
                else ""
            )
        )
    preflight_failure = (
        '[[ "$1" == cache ]] && exit 7\n'
        if preflight_status != "completed"
        else ""
    )
    run_script.write_text(
        "#!/usr/bin/env bash\n"
        "set -u\n"
        f"printf '%s\\n' \"$1\" >> artifacts/{run_id}/calls.txt\n"
        "if [[ \"$1\" == check || \"$1\" == cache || "
        "\"$1\" == smoke ]]; then\n"
        f"  {preflight_failure}"
        "  exit 0\n"
        "fi\n"
        "[[ \"${AISTATION_TARGET:-}\" == GPU2 ]] || exit 66\n"
        "[[ -n \"${ZOOLOGY_EXPECTED_GIT_SHA:-}\" ]] || exit 67\n"
        f"printf '%s\\n' \"$@\" > artifacts/{run_id}/init-invocation.txt\n"
        "[[ \"$1\" == init-baseline ]] || exit 64\n"
        + body,
        encoding="utf-8",
    )
    run_script.chmod(0o755)
    setup_script = repo / "setup.sh"
    setup_script.write_text(
        "#!/usr/bin/env bash\n"
        "set -u\n"
        f"printf 'setup\\n' >> artifacts/{run_id}/calls.txt\n",
        encoding="utf-8",
    )
    setup_script.chmod(0o755)
    _run("git", "init", cwd=repo)
    _run("git", "config", "user.name", "Fixture", cwd=repo)
    _run("git", "config", "user.email", "fixture@example.invalid", cwd=repo)
    _run(
        "git",
        "add",
        ".gitignore",
        "repro",
        "run.sh",
        "setup.sh",
        cwd=repo,
    )
    _run("git", "commit", "-m", "fixture", cwd=repo)
    formal_sha = _run("git", "rev-parse", "HEAD", cwd=repo).stdout.strip()
    formal_tree = _run(
        "git",
        "rev-parse",
        "HEAD^{tree}",
        cwd=repo,
    ).stdout.strip()
    _run("git", "checkout", "--detach", formal_sha, cwd=repo)

    python = repo / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.symlink_to(Path(sys.executable).resolve())
    run_artifact = repo / "artifacts" / run_id
    launcher = run_artifact / "launcher"
    launcher.mkdir(parents=True)
    suite = repo / "runs" / run_id
    control = run_artifact / "init-baseline-control"
    preflight_control = run_artifact / "preflight-control"
    preflight_uploaded = launcher / PREFLIGHT_SCRIPT.name
    assert _sha256(PREFLIGHT_SCRIPT) == PREFLIGHT_V2_SHA256
    preflight_materialized = PREFLIGHT_SCRIPT.read_text(encoding="utf-8")
    preflight_materialized = preflight_materialized.replace(
        "/huyang2/zoology", str(repo)
    )
    preflight_materialized = preflight_materialized.replace(
        FORMAL_SHA, formal_sha
    )
    preflight_materialized = preflight_materialized.replace(
        FORMAL_TREE, formal_tree
    )
    preflight_uploaded.write_text(preflight_materialized, encoding="utf-8")
    preflight_uploaded.chmod(0o700)
    preflight_script_sha256 = _sha256(preflight_uploaded)
    preflight_command = [
        str(preflight_uploaded),
        "start",
        "--script-sha256",
        preflight_script_sha256,
        "--suite-dir",
        str(suite),
        "--control-dir",
        str(preflight_control),
    ]
    preflight_started = _run(*preflight_command, cwd=repo)
    assert json.loads(preflight_started.stdout)["run_id"] == run_id
    preflight_terminal = preflight_control / "terminal.json"
    _wait_for(preflight_terminal)
    preflight_payload = json.loads(
        preflight_terminal.read_text(encoding="utf-8")
    )
    assert preflight_payload["status"] == preflight_status
    if preflight_status == "completed":
        preflight_verify_command = list(preflight_command)
        preflight_verify_command[1] = "verify"
        deadline = time.monotonic() + 10
        while True:
            verified = _run(
                *preflight_verify_command,
                cwd=repo,
                check=False,
            )
            if verified.returncode == 0:
                break
            if time.monotonic() >= deadline:
                raise AssertionError(verified.stderr)
            time.sleep(0.05)
    uploaded = launcher / SCRIPT.name
    materialized = SCRIPT.read_text(encoding="utf-8")
    materialized = materialized.replace("/huyang2/zoology", str(repo))
    materialized = materialized.replace(FORMAL_SHA, formal_sha)
    materialized = materialized.replace(FORMAL_TREE, formal_tree)
    materialized = materialized.replace(
        PREFLIGHT_V2_SHA256, preflight_script_sha256
    )
    if start_record_delay:
        needle = (
            '  write_atomic "$control_dir/start.json" "$start_json" || '
            'die "cannot persist init-baseline start record"\n'
        )
        replacement = (
            f"  sleep {start_record_delay}\n"
            + needle
        )
        assert materialized.count(needle) == 1
        materialized = materialized.replace(needle, replacement)
    if post_wait_delay:
        needle = (
            "init_exit_code=$?\n"
            'if process_group_exists "$init_pid"; then\n'
        )
        replacement = (
            "init_exit_code=$?\n"
            f"printf 'ready\\n' > "
            f'"$run_artifact/post-wait.marker"\n'
            f"post_wait_deadline=$((SECONDS + {post_wait_delay}))\n"
            "while ((SECONDS < post_wait_deadline)); do :; done\n"
            'if process_group_exists "$init_pid"; then\n'
        )
        assert materialized.count(needle) == 1
        materialized = materialized.replace(needle, replacement)
    if starter_snapshot_failure:
        needle = '    cp -- "$0" "$snapshot"\n'
        replacement = "    false\n"
        assert materialized.count(needle) == 1
        materialized = materialized.replace(needle, replacement)
    if signal_identity_mismatch:
        needle = '  failure_reason="worker received $signal_name"\n'
        replacement = (
            needle
            + "  init_start_ticks=$((init_start_ticks + 1))\n"
        )
        assert materialized.count(needle) == 1
        materialized = materialized.replace(needle, replacement)
    if supervisor_spawn_failure:
        needle = (
            '  "$nohup_path" "$setsid_path" --fork --wait '
            '"$bash_path" "$snapshot" worker \\\n'
        )
        replacement = "  false \\\n"
        assert materialized.count(needle) == 1
        materialized = materialized.replace(needle, replacement)
    uploaded.write_text(materialized, encoding="utf-8")
    uploaded.chmod(0o700)
    script_sha256 = _sha256(uploaded)
    command = [
        str(uploaded),
        "start",
        "--script-sha256",
        script_sha256,
        "--suite-dir",
        str(suite),
        "--control-dir",
        str(control),
    ]
    return {
        "repo": repo,
        "run_id": run_id,
        "run_artifact": run_artifact,
        "suite": suite,
        "control": control,
        "preflight_terminal": preflight_terminal,
        "preflight_verifier": preflight_uploaded,
        "preflight_verifier_sha256": preflight_script_sha256,
        "uploaded": uploaded,
        "script_sha256": script_sha256,
        "command": command,
    }


def test_control_is_frozen_to_init_only_and_is_syntactically_valid():
    source = SCRIPT.read_text(encoding="utf-8")
    _run("bash", "-n", SCRIPT, cwd=ROOT)

    assert f'FORMAL_SOURCE_SHA="{FORMAL_SHA}"' in source
    assert f'FORMAL_SOURCE_TREE="{FORMAL_TREE}"' in source
    assert f'PREFLIGHT_V2_SHA256="{PREFLIGHT_V2_SHA256}"' in source
    assert 'CONTROL_NAME="init-baseline-control"' in source
    assert 'FORMAL_LAUNCH_CONTROL_NAME="formal-launch-control"' in source
    assert 'mkdir -- "$control_dir"' in source
    assert 'mkdir -p' not in source
    assert (
        '"$nohup_path" "$setsid_path" --fork --wait '
        '"$bash_path" "$snapshot" worker'
    ) in source
    assert source.count(
        '"$setsid_path" "$bash_path" ./run.sh init-baseline "$suite_dir"'
    ) == 1
    assert source.count(
        "./.venv/bin/python -m repro.single_baseline selected-index"
    ) == 1
    assert "launch-baseline" not in source
    assert "aistation_clock_bracket" not in source
    assert "publish-status" not in source
    assert "verify_fresh_suite_inventory" in source
    assert "suite-inventory.txt" in source
    assert "--require-environments" in source
    assert "--validate-source" in source
    assert 'preflight_control="$run_artifact/preflight-control"' in source
    assert (
        'preflight_verifier="$run_artifact/launcher/$PREFLIGHT_V2_NAME"'
        in source
    )
    assert source.count("verify_preflight_v2 ||") == 5
    assert '"$preflight_verifier" verify' in source
    assert '--script-sha256 "$PREFLIGHT_V2_SHA256"' in source
    assert 'project_python="$(realpath -e -- ' in source
    assert "capture_timestamp()" in source
    assert source.count("date -u +%Y-%m-%dT%H:%M:%SZ") == 0
    assert 'date -u -d "@$captured_unix"' in source
    assert "GIT_OPTIONAL_LOCKS=0 git" in source
    assert '"preflight_terminal_sha256": "%s"' in source
    assert '"preflight_verifier_sha256": "%s"' in source
    assert "completed preflight terminal contract failed" in source
    assert "durable init-baseline evidence verification failed" in source
    assert '"proc_start_ticks": %s' in source
    assert '"proc_cmdline_hex": "%s"' in source
    assert '"proc_cmdline_sha256": "%s"' in source
    assert 'export AISTATION_TARGET="GPU2"' in source
    assert "GPU1" not in source
    assert 'mode" == "verify"' in source
    assert '"status": "completed"' in source
    assert "expected_control_names" in source
    assert 'write_atomic "$control_dir/worker-claim.json"' in source
    assert '"worker_claim_sha256": %s' in source
    assert 'require_exact_fields(attempt, attempt_fields, "attempt")' in source
    assert 'require_exact_fields(start, start_fields, "start")' in source
    assert 'require_exact_fields(worker, worker_fields, "worker start")' in source
    assert 'require_exact_fields(init_command, init_command_fields, "init command")' in source
    assert 'require_exact_fields(validator, validator_fields, "validator command")' in source
    assert 'require_exact_fields(terminal, terminal_fields, "terminal")' in source
    assert "require_exited(supervisor_pid" in source
    assert "require_exited(worker_pid" in source
    assert 'candidate_cmdline_hex" == "$expected_init_cmdline_hex"' in source
    assert 'candidate_pgrp" == "$init_pid"' in source
    assert 'candidate_sid" == "$init_pid"' in source
    assert 'kill -TERM -- "-$pid"' in source
    assert 'kill -KILL -- "-$pid"' in source
    assert "trap on_starter_exit EXIT" in source
    assert 'write_atomic "$control_dir/starter-terminal.json"' in source
    assert source.index(
        'write_atomic "$control_dir/start.json"'
    ) < source.index(
        '((worker_claim_ready == 1))'
    ) < source.index(
        "starter_handoff=1"
    )
    signal_start = source.index("on_worker_signal()")
    signal_end = source.index("trap on_worker_exit EXIT", signal_start)
    assert "init_exit_code" not in source[signal_start:signal_end]


@pytest.mark.skipif(
    not sys.platform.startswith("linux")
    or shutil.which("setsid") is None
    or not Path("/proc/self/stat").is_file(),
    reason="the durable init-baseline contract requires Linux /proc",
)
@pytest.mark.parametrize(
    ("run_id", "init_exit_code", "terminal_status"),
    (
        ("durable-init-success", 0, "completed"),
        ("durable-init-failure", 7, "failed"),
    ),
)
def test_start_is_detached_one_shot_and_records_terminal_evidence(
    tmp_path: Path,
    run_id: str,
    init_exit_code: int,
    terminal_status: str,
):
    fixture = _make_fixture(
        tmp_path,
        run_id=run_id,
        init_exit_code=init_exit_code,
    )
    repo = fixture["repo"]
    control = fixture["control"]
    suite = fixture["suite"]
    command = fixture["command"]
    assert isinstance(repo, Path)
    assert isinstance(control, Path)
    assert isinstance(suite, Path)
    assert isinstance(command, list)

    started = time.monotonic()
    first = _run(*command, cwd=repo)
    assert time.monotonic() - started < 1.5
    start_result = json.loads(first.stdout)
    assert start_result["script_sha256"] == fixture["script_sha256"]
    assert start_result["suite_dir"] == str(suite)

    terminal_path = control / "terminal.json"
    _wait_for(terminal_path)
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    worker_start = json.loads(
        (control / "worker-start.json").read_text(encoding="utf-8")
    )
    worker_claim = json.loads(
        (control / "worker-claim.json").read_text(encoding="utf-8")
    )
    init_command = json.loads(
        (control / "init-command.json").read_text(encoding="utf-8")
    )
    assert terminal["status"] == terminal_status
    assert terminal["exit_code"] == init_exit_code
    assert terminal["init_exit_code"] == init_exit_code
    assert worker_start["proc_pgrp"] == worker_start["pid"]
    assert worker_start["proc_sid"] == worker_start["pid"]
    assert worker_start["proc_tty_nr"] == 0
    assert worker_start["tty"] == "?"
    start = json.loads((control / "start.json").read_text(encoding="utf-8"))
    assert worker_start["proc_ppid"] == start["envelope_supervisor_pid"]
    assert worker_claim["pid"] == worker_start["pid"]
    assert worker_claim["ppid"] == start["envelope_supervisor_pid"]
    assert terminal["worker_claim_sha256"] == _sha256(
        control / "worker-claim.json"
    )
    assert worker_start["proc_cmdline_hex"]
    assert worker_start["proc_cmdline_sha256"]
    assert init_command["proc_ppid"] == worker_start["pid"]
    assert init_command["proc_pgrp"] == init_command["pid"]
    assert init_command["proc_sid"] == init_command["pid"]
    assert init_command["proc_tty_nr"] == 0
    assert init_command["proc_cwd"] == str(repo)
    assert init_command["command"] == [
        init_command["proc_exe"],
        "./run.sh",
        "init-baseline",
        str(suite),
    ]
    assert terminal["attempt_sha256"] == _sha256(control / "attempt.json")
    assert terminal["preflight_terminal_sha256"] == _sha256(
        fixture["preflight_terminal"]
    )
    assert terminal["preflight_verifier_sha256"] == _sha256(
        fixture["preflight_verifier"]
    )
    attempt = json.loads(
        (control / "attempt.json").read_text(encoding="utf-8")
    )
    assert attempt["preflight_verifier"] == str(
        fixture["preflight_verifier"]
    )
    assert attempt["preflight_verifier_sha256"] == fixture[
        "preflight_verifier_sha256"
    ]
    assert terminal["start_sha256"] == _sha256(control / "start.json")
    assert terminal["worker_start_sha256"] == _sha256(
        control / "worker-start.json"
    )
    assert terminal["init_command_sha256"] == _sha256(
        control / "init-command.json"
    )
    assert (fixture["run_artifact"] / "init-invocation.txt").read_text(
        encoding="utf-8"
    ).splitlines() == ["init-baseline", str(suite)]

    if init_exit_code == 0:
        validator = json.loads(
            (control / "validator-command.json").read_text(encoding="utf-8")
        )
        assert validator["command"] == [
            "./.venv/bin/python",
            "-m",
            "repro.single_baseline",
            "selected-index",
            "--suite-dir",
            str(suite),
        ]
        assert validator["stdout_hex"] == "350a"
        assert terminal["validator_command_sha256"] == _sha256(
            control / "validator-command.json"
        )
        expected_suite_hashes = {
            "suite_inventory_sha256": None,
            "suite_manifest_sha256": "suite-manifest.json",
            "single_baseline_manifest_sha256": (
                "single-baseline-manifest.json"
            ),
            "source_archive_sha256": "source.tar.gz",
            "source_archive_checksum_sha256": "source.tar.gz.sha256",
            "cache_manifest_sha256": "cache-manifest.json",
            "cache_manifest_checksum_sha256": "cache-manifest.json.sha256",
            "nvidia_smi_sha256": "nvidia-smi.txt",
            "runtime_attestation_sha256": "runtime-attestation.json",
        }
        for field, filename in expected_suite_hashes.items():
            evidence = (
                control / "suite-inventory.txt"
                if filename is None
                else suite / filename
            )
            assert terminal[field] == _sha256(evidence)
        assert (control / "suite-inventory.txt").read_text(
            encoding="utf-8"
        ).splitlines() == sorted(
            [
                "cache-manifest.json",
                "cache-manifest.json.sha256",
                "claims",
                "launches",
                "logs",
                "nvidia-smi.txt",
                "runtime-attestation.json",
                "single-baseline-manifest.json",
                "source.tar.gz",
                "source.tar.gz.sha256",
                "suite-manifest.json",
            ]
        )
        assert not (fixture["run_artifact"] / "controller").exists()
        assert not (
            fixture["run_artifact"] / "formal-launch-control"
        ).exists()
        verify_command = list(command)
        verify_command[1] = "verify"
        deadline = time.monotonic() + 10
        verified = None
        while time.monotonic() < deadline:
            verified = _run(*verify_command, cwd=repo, check=False)
            if verified.returncode == 0:
                break
            time.sleep(0.05)
        assert verified is not None
        assert verified.returncode == 0, verified.stderr
        assert json.loads(verified.stdout) == {
            "control_dir": str(control),
            "run_id": run_id,
            "status": "verified",
            "suite_dir": str(suite),
        }
        read_only_roots = (
            fixture["run_artifact"],
            suite,
            repo / ".git" / "index",
        )
        before_verify = _read_only_snapshot(*read_only_roots)
        verified_again = _run(
            *verify_command,
            cwd=repo,
            check=False,
        )
        assert verified_again.returncode == 0, verified_again.stderr
        assert _read_only_snapshot(*read_only_roots) == before_verify
    else:
        assert terminal["validator_exit_code"] is None
        assert terminal["validator_command_sha256"] is None
        assert not suite.exists()
        verify_command = list(command)
        verify_command[1] = "verify"
        verified = _run(*verify_command, cwd=repo, check=False)
        assert verified.returncode != 0

    second = _run(*command, cwd=repo, check=False)
    assert second.returncode != 0
    assert "attempt is consumed" in second.stderr
    assert (fixture["run_artifact"] / "init-invocation.txt").read_text(
        encoding="utf-8"
    ).splitlines().count("init-baseline") == 1
    if init_exit_code == 0:
        preflight = json.loads(
            fixture["preflight_terminal"].read_text(encoding="utf-8")
        )
        preflight["ended_unix"] = 1
        fixture["preflight_terminal"].write_text(
            json.dumps(preflight, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        tampered = _run(*verify_command, cwd=repo, check=False)
        assert tampered.returncode != 0


@pytest.mark.skipif(
    not sys.platform.startswith("linux")
    or shutil.which("setsid") is None
    or not Path("/proc/self/stat").is_file(),
    reason="the durable init-baseline contract requires Linux /proc",
)
def test_worker_waits_for_start_record(tmp_path: Path):
    fixture = _make_fixture(
        tmp_path,
        run_id="durable-init-start-race",
        start_record_delay=0.4,
    )
    completed = _run(*fixture["command"], cwd=fixture["repo"])
    assert json.loads(completed.stdout)["run_id"] == fixture["run_id"]
    terminal_path = fixture["control"] / "terminal.json"
    _wait_for(terminal_path)
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    assert terminal["status"] == "completed"
    assert terminal["start_sha256"] == _sha256(
        fixture["control"] / "start.json"
    )


@pytest.mark.skipif(
    not sys.platform.startswith("linux")
    or shutil.which("setsid") is None
    or not Path("/proc/self/stat").is_file(),
    reason="the durable init-baseline contract requires Linux /proc",
)
def test_timestamp_pairs_remain_atomic_across_forced_rollovers(
    tmp_path: Path,
):
    fixture = _make_fixture(
        tmp_path,
        run_id="durable-init-timestamp-rollover",
    )
    fake_bin = _make_rollover_date(tmp_path)
    environment = dict(os.environ)
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
    started = _run(
        *fixture["command"],
        cwd=fixture["repo"],
        env=environment,
    )
    assert json.loads(started.stdout)["run_id"] == fixture["run_id"]
    terminal_path = fixture["control"] / "terminal.json"
    _wait_for(terminal_path)
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    assert terminal["status"] == "completed"

    evidence_pairs = (
        (
            json.loads(
                (fixture["control"] / "attempt.json").read_text(
                    encoding="utf-8"
                )
            ),
            "started",
        ),
        (
            json.loads(
                (fixture["control"] / "start.json").read_text(
                    encoding="utf-8"
                )
            ),
            "recorded",
        ),
        (
            json.loads(
                (fixture["control"] / "worker-start.json").read_text(
                    encoding="utf-8"
                )
            ),
            "started",
        ),
        (
            json.loads(
                (fixture["control"] / "worker-claim.json").read_text(
                    encoding="utf-8"
                )
            ),
            "claimed",
        ),
        (
            json.loads(
                (fixture["control"] / "init-command.json").read_text(
                    encoding="utf-8"
                )
            ),
            "started",
        ),
        (
            json.loads(
                (fixture["control"] / "validator-command.json").read_text(
                    encoding="utf-8"
                )
            ),
            "started",
        ),
        (terminal, "worker_started"),
        (terminal, "ended"),
    )
    for payload, prefix in evidence_pairs:
        parsed = datetime.strptime(
            payload[f"{prefix}_utc"],
            "%Y-%m-%dT%H:%M:%SZ",
        ).replace(tzinfo=timezone.utc)
        assert int(parsed.timestamp()) == payload[f"{prefix}_unix"]

    verify_command = list(fixture["command"])
    verify_command[1] = "verify"
    verified = _run(*verify_command, cwd=fixture["repo"], check=False)
    assert verified.returncode == 0, verified.stderr


@pytest.mark.skipif(
    not sys.platform.startswith("linux")
    or shutil.which("setsid") is None
    or not Path("/proc/self/stat").is_file(),
    reason="the durable init-baseline contract requires Linux /proc",
)
def test_completed_rejects_nonfresh_suite_inventory(tmp_path: Path):
    fixture = _make_fixture(
        tmp_path,
        run_id="durable-init-nonfresh-inventory",
        extra_suite_evidence=True,
    )
    completed = _run(*fixture["command"], cwd=fixture["repo"])
    assert json.loads(completed.stdout)["run_id"] == fixture["run_id"]
    terminal_path = fixture["control"] / "terminal.json"
    _wait_for(terminal_path)
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    assert terminal["status"] == "failed"
    assert terminal["reason"] == "initialized suite inventory is not exactly fresh"
    assert terminal["validator_command_sha256"] is None


@pytest.mark.skipif(
    not sys.platform.startswith("linux")
    or shutil.which("setsid") is None
    or not Path("/proc/self/stat").is_file(),
    reason="the durable init-baseline contract requires Linux /proc",
)
def test_downstream_path_race_gets_early_terminal(tmp_path: Path):
    fixture = _make_fixture(
        tmp_path,
        run_id="durable-init-path-race",
        start_record_delay=0.5,
    )
    process = subprocess.Popen(
        fixture["command"],
        cwd=fixture["repo"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _wait_for(fixture["control"] / "attempt.json")
    (fixture["run_artifact"] / "controller").mkdir()
    stdout, stderr = process.communicate(timeout=5)
    assert process.returncode == 0, stderr
    assert json.loads(stdout)["run_id"] == fixture["run_id"]
    terminal_path = fixture["control"] / "terminal.json"
    _wait_for(terminal_path)
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    assert terminal["status"] == "failed"
    assert "downstream formal path gate failed" in terminal["reason"]
    assert not (fixture["run_artifact"] / "init-invocation.txt").exists()


@pytest.mark.skipif(
    not sys.platform.startswith("linux")
    or shutil.which("setsid") is None
    or not Path("/proc/self/stat").is_file(),
    reason="the durable init-baseline contract requires Linux /proc",
)
def test_failed_preflight_is_rejected_before_init_claim(tmp_path: Path):
    fixture = _make_fixture(
        tmp_path,
        run_id="durable-init-failed-preflight",
        preflight_status="failed",
    )
    completed = _run(
        *fixture["command"],
        cwd=fixture["repo"],
        check=False,
    )
    assert completed.returncode != 0
    assert not fixture["control"].exists()
    assert not (fixture["run_artifact"] / "init-invocation.txt").exists()


@pytest.mark.skipif(
    not sys.platform.startswith("linux")
    or shutil.which("setsid") is None
    or not Path("/proc/self/stat").is_file(),
    reason="the durable init-baseline contract requires Linux /proc",
)
def test_preflight_terminal_drift_is_rejected_by_worker(tmp_path: Path):
    fixture = _make_fixture(
        tmp_path,
        run_id="durable-init-preflight-drift",
        start_record_delay=0.5,
    )
    process = subprocess.Popen(
        fixture["command"],
        cwd=fixture["repo"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _wait_for(fixture["control"] / "attempt.json")
    preflight = json.loads(
        fixture["preflight_terminal"].read_text(encoding="utf-8")
    )
    preflight["ended_unix"] = 1
    fixture["preflight_terminal"].write_text(
        json.dumps(preflight, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    stdout, stderr = process.communicate(timeout=5)
    assert process.returncode == 0, stderr
    assert json.loads(stdout)["run_id"] == fixture["run_id"]
    terminal_path = fixture["control"] / "terminal.json"
    _wait_for(terminal_path)
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    assert terminal["status"] == "failed"
    assert "preflight" in terminal["reason"]
    assert not (fixture["run_artifact"] / "init-invocation.txt").exists()


@pytest.mark.skipif(
    not sys.platform.startswith("linux")
    or shutil.which("setsid") is None
    or not Path("/proc/self/stat").is_file(),
    reason="the durable init-baseline contract requires Linux /proc",
)
def test_preflight_step_chain_tamper_is_rejected_before_init_claim(
    tmp_path: Path,
):
    fixture = _make_fixture(
        tmp_path,
        run_id="durable-init-preflight-step-tamper",
    )
    step_log = fixture["run_artifact"] / "preflight-control" / "02-check.log"
    step_log.write_text("tampered\n", encoding="utf-8")
    completed = _run(
        *fixture["command"],
        cwd=fixture["repo"],
        check=False,
    )
    assert completed.returncode != 0
    assert "preflight-v2 evidence verification failed" in completed.stderr
    assert not fixture["control"].exists()
    assert not fixture["suite"].exists()
    assert not (fixture["run_artifact"] / "init-invocation.txt").exists()


@pytest.mark.skipif(
    not sys.platform.startswith("linux")
    or shutil.which("setsid") is None
    or not Path("/proc/self/stat").is_file(),
    reason="the durable init-baseline contract requires Linux /proc",
)
@pytest.mark.parametrize(
    "forbidden_name",
    ("suite", "controller", "formal-launch-control"),
)
def test_symlinked_fresh_paths_are_rejected(
    tmp_path: Path,
    forbidden_name: str,
):
    fixture = _make_fixture(
        tmp_path,
        run_id=f"durable-init-symlink-{forbidden_name}",
    )
    target = tmp_path / f"{forbidden_name}-target"
    target.mkdir()
    if forbidden_name == "suite":
        forbidden = fixture["suite"]
    else:
        forbidden = fixture["run_artifact"] / forbidden_name
    forbidden.symlink_to(target, target_is_directory=True)
    completed = _run(
        *fixture["command"],
        cwd=fixture["repo"],
        check=False,
    )
    assert completed.returncode != 0
    assert "fresh suite or downstream formal path gate failed" in completed.stderr
    assert not fixture["control"].exists()


@pytest.mark.skipif(
    not sys.platform.startswith("linux")
    or shutil.which("setsid") is None
    or not Path("/proc/self/stat").is_file(),
    reason="the durable init-baseline contract requires Linux /proc",
)
def test_concurrent_reentry_runs_init_once(tmp_path: Path):
    fixture = _make_fixture(
        tmp_path,
        run_id="durable-init-concurrent-reentry",
    )
    processes = [
        subprocess.Popen(
            fixture["command"],
            cwd=fixture["repo"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(2)
    ]
    results = [process.communicate(timeout=5) for process in processes]
    assert sorted(process.returncode for process in processes) == [0, 1]
    assert any("attempt is consumed" in stderr for _, stderr in results)
    _wait_for(fixture["control"] / "terminal.json")
    assert (fixture["run_artifact"] / "init-invocation.txt").read_text(
        encoding="utf-8"
    ).splitlines().count("init-baseline") == 1


@pytest.mark.skipif(
    not sys.platform.startswith("linux")
    or shutil.which("setsid") is None
    or not Path("/proc/self/stat").is_file(),
    reason="the durable init-baseline contract requires Linux /proc",
)
def test_signal_terminates_init_process_group_before_terminal(tmp_path: Path):
    fixture = _make_fixture(
        tmp_path,
        run_id="durable-init-signal",
        hang=True,
    )
    completed = _run(*fixture["command"], cwd=fixture["repo"])
    assert json.loads(completed.stdout)["run_id"] == fixture["run_id"]
    init_command_path = fixture["control"] / "init-command.json"
    _wait_for(init_command_path)
    worker_start = json.loads(
        (fixture["control"] / "worker-start.json").read_text(
            encoding="utf-8"
        )
    )
    init_command = json.loads(init_command_path.read_text(encoding="utf-8"))
    os.kill(worker_start["pid"], signal.SIGTERM)
    terminal_path = fixture["control"] / "terminal.json"
    _wait_for(terminal_path)
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    assert terminal["status"] == "failed"
    assert terminal["reason"] == "worker received SIGTERM"
    with pytest.raises(ProcessLookupError):
        os.killpg(init_command["proc_pgrp"], 0)


@pytest.mark.skipif(
    not sys.platform.startswith("linux")
    or shutil.which("setsid") is None
    or not Path("/proc/self/stat").is_file(),
    reason="the durable init-baseline contract requires Linux /proc",
)
def test_signal_after_leader_wait_cleans_surviving_process_group(
    tmp_path: Path,
):
    fixture = _make_fixture(
        tmp_path,
        run_id="durable-init-post-wait-signal",
        orphan_after_leader=True,
        post_wait_delay=5,
    )
    completed = _run(*fixture["command"], cwd=fixture["repo"])
    assert json.loads(completed.stdout)["run_id"] == fixture["run_id"]
    marker = fixture["run_artifact"] / "post-wait.marker"
    _wait_for(marker)
    worker_start = json.loads(
        (fixture["control"] / "worker-start.json").read_text(
            encoding="utf-8"
        )
    )
    init_command = json.loads(
        (fixture["control"] / "init-command.json").read_text(
            encoding="utf-8"
        )
    )
    os.kill(worker_start["pid"], signal.SIGTERM)
    terminal_path = fixture["control"] / "terminal.json"
    _wait_for(terminal_path, timeout=15)
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    assert terminal["status"] == "failed"
    assert terminal["reason"] == "worker received SIGTERM"
    assert terminal["init_exit_code"] == 0
    with pytest.raises(ProcessLookupError):
        os.killpg(init_command["proc_pgrp"], 0)


@pytest.mark.skipif(
    not sys.platform.startswith("linux")
    or shutil.which("setsid") is None
    or not Path("/proc/self/stat").is_file(),
    reason="the durable init-baseline contract requires Linux /proc",
)
def test_signal_identity_mismatch_fails_closed_without_killing_group(
    tmp_path: Path,
):
    fixture = _make_fixture(
        tmp_path,
        run_id="durable-init-signal-identity-mismatch",
        hang=True,
        signal_identity_mismatch=True,
    )
    _run(*fixture["command"], cwd=fixture["repo"])
    init_command_path = fixture["control"] / "init-command.json"
    _wait_for(init_command_path)
    worker = json.loads(
        (fixture["control"] / "worker-start.json").read_text(
            encoding="utf-8"
        )
    )
    init_command = json.loads(init_command_path.read_text(encoding="utf-8"))
    process_group = init_command["proc_pgrp"]
    os.kill(worker["pid"], signal.SIGTERM)
    terminal_path = fixture["control"] / "terminal.json"
    _wait_for(terminal_path)
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    assert terminal["reason"] == (
        "worker received SIGTERM; init process-group identity mismatch"
    )
    os.killpg(process_group, 0)
    os.killpg(process_group, signal.SIGKILL)
    deadline = time.monotonic() + 5
    while True:
        try:
            os.killpg(process_group, 0)
        except ProcessLookupError:
            break
        if time.monotonic() >= deadline:
            raise AssertionError("fixture process group survived cleanup")
        time.sleep(0.05)


@pytest.mark.skipif(
    not sys.platform.startswith("linux")
    or shutil.which("setsid") is None
    or not Path("/proc/self/stat").is_file(),
    reason="the durable init-baseline contract requires Linux /proc",
)
def test_starter_failure_after_claim_writes_failure_terminal(tmp_path: Path):
    fixture = _make_fixture(
        tmp_path,
        run_id="durable-init-starter-failure",
        starter_snapshot_failure=True,
    )
    completed = _run(
        *fixture["command"],
        cwd=fixture["repo"],
        check=False,
    )
    assert completed.returncode != 0
    starter_terminal_path = fixture["control"] / "starter-terminal.json"
    assert starter_terminal_path.is_file()
    starter_terminal = json.loads(
        starter_terminal_path.read_text(encoding="utf-8")
    )
    assert starter_terminal == {
        "schema_version": 1,
        "run_id": fixture["run_id"],
        "kind": "durable-init-baseline-starter",
        "status": "failed",
        "exit_code": completed.returncode,
        "reason": "starter failed after init-baseline control claim",
        "formal_source_sha": _run(
            "git", "rev-parse", "HEAD", cwd=fixture["repo"]
        ).stdout.strip(),
        "formal_source_tree": _run(
            "git", "rev-parse", "HEAD^{tree}", cwd=fixture["repo"]
        ).stdout.strip(),
        "suite_dir": str(fixture["suite"]),
        "control_dir": str(fixture["control"]),
        "script_sha256": fixture["script_sha256"],
        "ended_utc": starter_terminal["ended_utc"],
        "ended_unix": starter_terminal["ended_unix"],
    }
    assert not (fixture["control"] / "start.json").exists()
    assert not (fixture["control"] / "terminal.json").exists()
    assert not fixture["suite"].exists()


@pytest.mark.skipif(
    not sys.platform.startswith("linux")
    or shutil.which("setsid") is None
    or not Path("/proc/self/stat").is_file(),
    reason="the durable init-baseline contract requires Linux /proc",
)
def test_starter_keeps_terminal_ownership_until_worker_claim(tmp_path: Path):
    fixture = _make_fixture(
        tmp_path,
        run_id="durable-init-missing-worker-claim",
        supervisor_spawn_failure=True,
    )
    completed = _run(
        *fixture["command"],
        cwd=fixture["repo"],
        check=False,
    )
    assert completed.returncode != 0
    assert "did not claim terminal ownership" in completed.stderr
    starter_terminal_path = fixture["control"] / "starter-terminal.json"
    assert starter_terminal_path.is_file()
    starter_terminal = json.loads(
        starter_terminal_path.read_text(encoding="utf-8")
    )
    assert starter_terminal["status"] == "failed"
    assert (fixture["control"] / "start.json").is_file()
    assert not (fixture["control"] / "worker-claim.json").exists()
    assert not (fixture["control"] / "terminal.json").exists()
    assert not fixture["suite"].exists()


@pytest.mark.skipif(
    not sys.platform.startswith("linux")
    or shutil.which("setsid") is None
    or not Path("/proc/self/stat").is_file(),
    reason="the durable init-baseline contract requires Linux /proc",
)
def test_verify_rejects_terminal_schema_time_identity_and_field_tamper(
    tmp_path: Path,
):
    fixture = _make_fixture(
        tmp_path,
        run_id="durable-init-terminal-tamper",
    )
    _run(*fixture["command"], cwd=fixture["repo"])
    terminal_path = fixture["control"] / "terminal.json"
    _wait_for(terminal_path)
    original = json.loads(terminal_path.read_text(encoding="utf-8"))
    verify_command = list(fixture["command"])
    verify_command[1] = "verify"

    tampered_payloads = []
    payload = dict(original)
    payload["schema_version"] = 99
    tampered_payloads.append(payload)
    payload = dict(original)
    payload["ended_unix"] = original["ended_unix"] + 1
    tampered_payloads.append(payload)
    payload = dict(original)
    payload["worker_sid"] = original["worker_sid"] + 1
    tampered_payloads.append(payload)
    payload = dict(original)
    del payload["ended_utc"]
    tampered_payloads.append(payload)
    payload = dict(original)
    payload["unexpected"] = True
    tampered_payloads.append(payload)

    for payload in tampered_payloads:
        terminal_path.write_text(
            json.dumps(payload, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        verified = _run(
            *verify_command,
            cwd=fixture["repo"],
            check=False,
        )
        assert verified.returncode != 0

    terminal_path.write_text(
        json.dumps(original, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    verified = _run(*verify_command, cwd=fixture["repo"], check=False)
    assert verified.returncode == 0, verified.stderr


@pytest.mark.skipif(
    not sys.platform.startswith("linux")
    or shutil.which("setsid") is None
    or not Path("/proc/self/stat").is_file(),
    reason="the durable init-baseline contract requires Linux /proc",
)
def test_verify_rejects_coherent_extra_field_tamper_in_every_json_record(
    tmp_path: Path,
):
    fixture = _make_fixture(
        tmp_path,
        run_id="durable-init-coherent-schema-tamper",
    )
    _run(*fixture["command"], cwd=fixture["repo"])
    control = fixture["control"]
    terminal_path = control / "terminal.json"
    _wait_for(terminal_path)
    record_paths = {
        "attempt": control / "attempt.json",
        "start": control / "start.json",
        "claim": control / "worker-claim.json",
        "worker": control / "worker-start.json",
        "init": control / "init-command.json",
        "validator": control / "validator-command.json",
        "terminal": terminal_path,
    }
    originals = {
        name: path.read_bytes() for name, path in record_paths.items()
    }
    verify_command = list(fixture["command"])
    verify_command[1] = "verify"

    for target in (
        "attempt",
        "start",
        "claim",
        "worker",
        "init",
        "validator",
    ):
        for name, path in record_paths.items():
            path.write_bytes(originals[name])
        target_path = record_paths[target]
        target_payload = json.loads(target_path.read_text(encoding="utf-8"))
        target_payload["unexpected"] = True
        target_path.write_text(
            json.dumps(target_payload, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        terminal = json.loads(originals["terminal"])
        terminal_field = {
            "attempt": "attempt_sha256",
            "start": "start_sha256",
            "claim": "worker_claim_sha256",
            "worker": "worker_start_sha256",
            "init": "init_command_sha256",
            "validator": "validator_command_sha256",
        }[target]
        terminal[terminal_field] = _sha256(target_path)

        if target == "attempt":
            claim_path = record_paths["claim"]
            claim = json.loads(claim_path.read_text(encoding="utf-8"))
            claim["attempt_sha256"] = _sha256(target_path)
            claim_path.write_text(
                json.dumps(claim, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            terminal["worker_claim_sha256"] = _sha256(claim_path)
        if target in {"attempt", "start", "claim"}:
            worker_path = record_paths["worker"]
            worker = json.loads(worker_path.read_text(encoding="utf-8"))
            worker_field = (
                "worker_claim_sha256"
                if target == "claim"
                else f"{target}_sha256"
            )
            worker[worker_field] = _sha256(target_path)
            if target == "attempt":
                worker["worker_claim_sha256"] = terminal[
                    "worker_claim_sha256"
                ]
            worker_path.write_text(
                json.dumps(worker, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            terminal["worker_start_sha256"] = _sha256(worker_path)
        terminal_path.write_text(
            json.dumps(terminal, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        verified = _run(
            *verify_command,
            cwd=fixture["repo"],
            check=False,
        )
        assert verified.returncode != 0, target

    for name, path in record_paths.items():
        path.write_bytes(originals[name])
    verified = _run(*verify_command, cwd=fixture["repo"], check=False)
    assert verified.returncode == 0, verified.stderr
