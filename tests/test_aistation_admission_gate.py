from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

import repro.aistation_admission_gate as gate


RUN_ID = "gdn-mqar-p006"
WORKSPACE_ID = "workspace-gpu2"
HOSTNAME = "gpu2-host"
BOOT_ID = "12345678-1234-1234-1234-123456789abc"


def _raw(payload: dict) -> bytes:
    return (json.dumps(payload, indent=3) + "\n").encode("utf-8")


def _status(
    *,
    status: str = "Running",
    resource: str = gate.EXPECTED_RESOURCE,
    remaining: str = "14000",
    workspace_id: str = WORKSPACE_ID,
) -> bytes:
    return _raw(
        {
            "command": "status",
            "ok": True,
            "targets": [
                {
                    "wpName": "GPU2",
                    "wpId": workspace_id,
                    "wpStatus": status,
                    "image": "fixture",
                    "resource": resource,
                    "remainTime": remaining,
                }
            ],
            "actions": [],
        }
    )


def _probe(
    *,
    workspace_id: str = WORKSPACE_ID,
    hostname: str = HOSTNAME,
    gpu_name: str = gate.EXPECTED_GPU_NAME,
    stderr: str = "",
) -> bytes:
    return _raw(
        {
            "command": "probe",
            "ok": True,
            "targets": [
                {
                    "wpName": "GPU2",
                    "wpId": workspace_id,
                    "wpStatus": "Running",
                    "probe": {
                        "ok": True,
                        "exitCode": 0,
                        "stdout": (
                            f"{hostname}\n"
                            f"{gpu_name}, 0 MiB, "
                            "81920 MiB, 0 %\n"
                        ),
                        "stderr": stderr,
                    },
                }
            ],
        }
    )


def _identity(
    *,
    workspace_id: str = WORKSPACE_ID,
    hostname: str = HOSTNAME,
    boot_id: str = BOOT_ID,
    remote_unix: int = 2_000_000_001,
    stderr: str = "",
) -> bytes:
    return _raw(
        {
            "command": "exec",
            "ok": True,
            "targets": [
                {
                    "wpName": "GPU2",
                    "wpId": workspace_id,
                    "wpStatus": "Running",
                    "exec": {
                        "ok": True,
                        "exitCode": 0,
                        "stdout": (
                            f"HOST={hostname}\n\n"
                            f"BOOT_ID={boot_id}\n\n"
                            f"UNIX={remote_unix}\n"
                        ),
                        "stderr": stderr,
                    },
                }
            ],
        }
    )


class FakeRunner:
    def __init__(self, responses: list[bytes]):
        self.responses = list(responses)
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, node, helper, arguments):
        self.calls.append(arguments)
        if not self.responses:
            raise AssertionError("unexpected helper call")
        return subprocess.CompletedProcess(
            [str(node), str(helper), *arguments],
            0,
            stdout=self.responses.pop(0),
            stderr=b"",
        )


class FakeClock:
    def __init__(self):
        self.samples = iter(
            (
                (2_000_000_000_000_000_000, 10_000),
                (2_000_000_002_000_000_000, 20_000),
            )
        )

    def __call__(self):
        return next(self.samples)


class TimeoutRunner:
    def __init__(self, stdout: bytes):
        self.stdout = stdout
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, node, helper, arguments):
        self.calls.append(arguments)
        raise subprocess.TimeoutExpired(
            [str(node), str(helper), *arguments],
            gate.HELPER_TIMEOUT_SECONDS,
            output=self.stdout,
        )


@pytest.fixture
def context(tmp_path: Path, monkeypatch):
    repo = tmp_path / "zoology"
    output = repo / "artifacts" / f"admission-{RUN_ID}"
    output.mkdir(parents=True)
    helper = tmp_path / "aistation_api.js"
    helper_bytes = b"// fixture helper\n"
    helper.write_bytes(helper_bytes)
    node = tmp_path / "node"
    node.write_bytes(b"#!/bin/sh\nexit 1\n")
    node.chmod(0o700)
    monkeypatch.setattr(gate, "REPO_ROOT", repo)
    monkeypatch.setattr(gate, "APPROVED_HELPER_PATH", helper)
    monkeypatch.setattr(
        gate,
        "APPROVED_HELPER_SHA256",
        hashlib.sha256(helper_bytes).hexdigest(),
    )
    return output, helper, node


def _capture(context, phase: str, responses: list[bytes]):
    output, helper, node = context
    runner = FakeRunner(responses)
    observation = gate.capture_observation(
        helper,
        output,
        RUN_ID,
        phase,
        gate._module_sha256(),
        runner=runner,
        clock=FakeClock(),
        node=node,
    )
    return observation, runner


def test_initial_and_pre_capture_success_bind_raw_bytes_and_identity(context):
    initial_raw = [
        _status(),
        _probe(stderr="Warning: known host was added\n"),
        _identity(stderr="Warning: known host was added\n"),
    ]
    initial, initial_runner = _capture(context, "initial", initial_raw)

    assert initial_runner.calls == [
        ("status", "GPU2"),
        ("probe", "GPU2"),
        ("exec", "GPU2", "--", gate.REMOTE_IDENTITY_COMMAND),
    ]
    assert initial["workspace_id"] == WORKSPACE_ID
    assert initial["remote_hostname"] == HOSTNAME
    assert initial["remote_boot_id"] == BOOT_ID
    assert initial["minimum_remaining_seconds"] == 13_200
    for name, raw in zip(
        ("status-running.json", "probe-running.json", "identity-running.json"),
        initial_raw,
    ):
        assert (context[0] / name).read_bytes() == raw
        assert initial["raw_files_sha256"][name] == hashlib.sha256(raw).hexdigest()

    pre, _ = _capture(
        context,
        "pre-capture",
        [_status(remaining="13000"), _probe(), _identity(remote_unix=2_000_000_003)],
    )
    initial_observation = context[0] / "observation-initial.json"
    assert pre["initial_observation_sha256"] == hashlib.sha256(
        initial_observation.read_bytes()
    ).hexdigest()
    assert pre["minimum_remaining_seconds"] == 12_120
    assert gate.verify_observation(
        context[0], RUN_ID, "pre-capture", gate._module_sha256()
    ) == pre


@pytest.mark.parametrize(
    ("status_raw", "message"),
    (
        (_status(status="Pending"), "not Running"),
        (_status(remaining="13199"), "below the admission floor"),
    ),
)
def test_status_gate_rejects_before_probe(context, status_raw, message):
    runner = FakeRunner([status_raw])
    with pytest.raises(gate.AdmissionGateError, match=message):
        gate.capture_observation(
            context[1],
            context[0],
            RUN_ID,
            "initial",
            gate._module_sha256(),
            runner=runner,
            clock=FakeClock(),
            node=context[2],
        )

    assert runner.calls == [("status", "GPU2")]
    assert (context[0] / "status-running.json").read_bytes() == status_raw
    assert not (context[0] / "probe-running.json").exists()


def test_status_parse_failure_is_persisted_and_stops_before_probe(context):
    malformed = b"{not-json\n"
    runner = FakeRunner([malformed])
    with pytest.raises(gate.AdmissionGateError, match="not valid JSON"):
        gate.capture_observation(
            context[1],
            context[0],
            RUN_ID,
            "initial",
            gate._module_sha256(),
            runner=runner,
            clock=FakeClock(),
            node=context[2],
        )

    assert runner.calls == [("status", "GPU2")]
    assert (context[0] / "status-running.json").read_bytes() == malformed


def test_resource_mismatch_stops_before_probe(context):
    runner = FakeRunner([_status(resource="NVIDIA-H100:1")])
    with pytest.raises(gate.AdmissionGateError, match="resource differs"):
        gate.capture_observation(
            context[1],
            context[0],
            RUN_ID,
            "initial",
            gate._module_sha256(),
            runner=runner,
            clock=FakeClock(),
            node=context[2],
        )

    assert runner.calls == [("status", "GPU2")]


def test_probe_gpu_mismatch_stops_before_identity(context):
    runner = FakeRunner([_status(), _probe(gpu_name="NVIDIA H100 80GB HBM3")])
    with pytest.raises(gate.AdmissionGateError, match="did not report the A100"):
        gate.capture_observation(
            context[1],
            context[0],
            RUN_ID,
            "initial",
            gate._module_sha256(),
            runner=runner,
            clock=FakeClock(),
            node=context[2],
        )

    assert runner.calls == [("status", "GPU2"), ("probe", "GPU2")]
    assert not (context[0] / "identity-running.json").exists()


@pytest.mark.parametrize(
    ("responses", "message", "call_count"),
    (
        (
            [_status(), _probe(workspace_id="different-workspace")],
            "workspace changed before probe",
            2,
        ),
        (
            [_status(), _probe(), _identity(workspace_id="different-workspace")],
            "workspace changed before identity",
            3,
        ),
    ),
)
def test_helper_workspace_drift_is_rejected(
    context, responses, message, call_count
):
    runner = FakeRunner(responses)
    with pytest.raises(gate.AdmissionGateError, match=message):
        gate.capture_observation(
            context[1],
            context[0],
            RUN_ID,
            "initial",
            gate._module_sha256(),
            runner=runner,
            clock=FakeClock(),
            node=context[2],
        )

    assert len(runner.calls) == call_count
    assert not (context[0] / "observation-initial.json").exists()


def test_identity_mismatch_rejects_without_observation(context):
    runner = FakeRunner([_status(), _probe(), _identity(hostname="other-host")])
    with pytest.raises(gate.AdmissionGateError, match="hostname changed"):
        gate.capture_observation(
            context[1],
            context[0],
            RUN_ID,
            "initial",
            gate._module_sha256(),
            runner=runner,
            clock=FakeClock(),
            node=context[2],
        )

    assert len(runner.calls) == 3
    assert not (context[0] / "observation-initial.json").exists()


def test_pre_capture_rejects_initial_raw_drift_before_status(context):
    _capture(context, "initial", [_status(), _probe(), _identity()])
    (context[0] / "status-running.json").write_bytes(_status(remaining="13999"))
    runner = FakeRunner([])
    with pytest.raises(gate.AdmissionGateError, match="raw-file hash drift"):
        gate.capture_observation(
            context[1],
            context[0],
            RUN_ID,
            "pre-capture",
            gate._module_sha256(),
            runner=runner,
            clock=FakeClock(),
            node=context[2],
        )

    assert runner.calls == []


def test_pre_capture_rejects_initial_observation_tamper_before_status(context):
    _capture(context, "initial", [_status(), _probe(), _identity()])
    observation_path = context[0] / "observation-initial.json"
    observation = json.loads(observation_path.read_bytes())
    observation["workspace_id"] = "tampered-workspace"
    observation_path.write_bytes(gate._canonical_json(observation))
    runner = FakeRunner([])

    with pytest.raises(gate.AdmissionGateError, match="observation/raw drift"):
        gate.capture_observation(
            context[1],
            context[0],
            RUN_ID,
            "pre-capture",
            gate._module_sha256(),
            runner=runner,
            clock=FakeClock(),
            node=context[2],
        )

    assert runner.calls == []


@pytest.mark.parametrize(
    ("pre_status", "message"),
    (
        (_status(remaining="12119"), "below the admission floor"),
        (
            _status(remaining="13000", workspace_id="replacement-workspace"),
            "workspace differs from initial",
        ),
    ),
)
def test_pre_capture_status_drift_stops_before_probe(
    context, pre_status, message
):
    _capture(context, "initial", [_status(), _probe(), _identity()])
    runner = FakeRunner([pre_status])

    with pytest.raises(gate.AdmissionGateError, match=message):
        gate.capture_observation(
            context[1],
            context[0],
            RUN_ID,
            "pre-capture",
            gate._module_sha256(),
            runner=runner,
            clock=FakeClock(),
            node=context[2],
        )

    assert runner.calls == [("status", "GPU2")]
    assert not (context[0] / "probe-pre-capture.json").exists()


@pytest.mark.parametrize(
    ("identity", "message"),
    (
        (
            _identity(boot_id="abcdef01-2345-6789-abcd-ef0123456789"),
            "boot id differs from initial",
        ),
        (
            _identity(remote_unix=2_000_000_000),
            "remote Unix time moved backwards",
        ),
    ),
)
def test_pre_capture_identity_drift_is_rejected(context, identity, message):
    _capture(context, "initial", [_status(), _probe(), _identity()])
    runner = FakeRunner([_status(remaining="13000"), _probe(), identity])

    with pytest.raises(gate.AdmissionGateError, match=message):
        gate.capture_observation(
            context[1],
            context[0],
            RUN_ID,
            "pre-capture",
            gate._module_sha256(),
            runner=runner,
            clock=FakeClock(),
            node=context[2],
        )

    assert len(runner.calls) == 3
    assert not (context[0] / "observation-pre-capture.json").exists()


def test_verify_rejects_self_consistent_pre_capture_clock_rollback(context):
    _capture(context, "initial", [_status(), _probe(), _identity()])
    _capture(
        context,
        "pre-capture",
        [_status(remaining="13000"), _probe(), _identity(remote_unix=2_000_000_003)],
    )
    identity_path = context[0] / "identity-pre-capture.json"
    rolled_back_identity = _identity(remote_unix=2_000_000_000)
    identity_path.write_bytes(rolled_back_identity)
    observation_path = context[0] / "observation-pre-capture.json"
    observation = json.loads(observation_path.read_bytes())
    observation["remote_unix"] = 2_000_000_000
    observation["raw_files_sha256"][identity_path.name] = hashlib.sha256(
        rolled_back_identity
    ).hexdigest()
    observation_path.write_bytes(gate._canonical_json(observation))

    with pytest.raises(
        gate.AdmissionGateError,
        match="remote Unix time moved backwards",
    ):
        gate.verify_observation(
            context[0], RUN_ID, "pre-capture", gate._module_sha256()
        )


def test_module_hash_drift_rejects_before_helper(context):
    runner = FakeRunner([])
    with pytest.raises(gate.AdmissionGateError, match="module differs"):
        gate.capture_observation(
            context[1],
            context[0],
            RUN_ID,
            "initial",
            "0" * 64,
            runner=runner,
            clock=FakeClock(),
            node=context[2],
        )

    assert runner.calls == []
    assert list(context[0].iterdir()) == []


def test_status_timeout_is_bounded_persisted_and_fail_closed(context):
    partial_stdout = b'{"command":"status"'
    runner = TimeoutRunner(partial_stdout)

    with pytest.raises(gate.AdmissionGateError, match="status helper process timed out"):
        gate.capture_observation(
            context[1],
            context[0],
            RUN_ID,
            "initial",
            gate._module_sha256(),
            runner=runner,
            clock=FakeClock(),
            node=context[2],
        )

    assert gate.HELPER_TIMEOUT_SECONDS == 30
    assert runner.calls == [("status", "GPU2")]
    assert (context[0] / "status-running.json").read_bytes() == partial_stdout
    assert not (context[0] / "probe-running.json").exists()


def test_run_helper_uses_frozen_timeout(context, monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, stdout=b"{}", stderr=b"")

    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    gate._run_helper(context[2], context[1], ("status", "GPU2"))

    assert captured["timeout"] == 30
    assert captured["stdout"] is subprocess.PIPE
    assert captured["stderr"] is subprocess.PIPE


def test_outer_helper_stderr_is_persisted_then_rejected(context):
    status_raw = _status()

    class StderrRunner:
        calls = []

        def __call__(self, node, helper, arguments):
            self.calls.append(arguments)
            return subprocess.CompletedProcess(
                [str(node), str(helper), *arguments],
                0,
                stdout=status_raw,
                stderr=b"unexpected wrapper warning\n",
            )

    runner = StderrRunner()
    with pytest.raises(gate.AdmissionGateError, match="process stderr is not empty"):
        gate.capture_observation(
            context[1],
            context[0],
            RUN_ID,
            "initial",
            gate._module_sha256(),
            runner=runner,
            clock=FakeClock(),
            node=context[2],
        )

    assert runner.calls == [("status", "GPU2")]
    assert (context[0] / "status-running.json").read_bytes() == status_raw


def test_helper_hash_drift_after_status_stops_before_probe(context):
    status_raw = _status()

    class MutatingRunner:
        calls = []

        def __call__(self, node, helper, arguments):
            self.calls.append(arguments)
            helper.write_bytes(b"// modified during helper call\n")
            return subprocess.CompletedProcess(
                [str(node), str(helper), *arguments],
                0,
                stdout=status_raw,
                stderr=b"",
            )

    runner = MutatingRunner()
    with pytest.raises(gate.AdmissionGateError, match="helper differs"):
        gate.capture_observation(
            context[1],
            context[0],
            RUN_ID,
            "initial",
            gate._module_sha256(),
            runner=runner,
            clock=FakeClock(),
            node=context[2],
        )

    assert runner.calls == [("status", "GPU2")]
    assert (context[0] / "status-running.json").read_bytes() == status_raw
    assert not (context[0] / "probe-running.json").exists()


def test_verify_remains_read_only_after_reserved_capture_path_exists(context):
    initial, _ = _capture(context, "initial", [_status(), _probe(), _identity()])
    (context[0].parent / RUN_ID).mkdir()

    assert gate.verify_observation(
        context[0], RUN_ID, "initial", gate._module_sha256()
    ) == initial


def test_phase_outputs_are_exclusive_and_block_reentry(context):
    _capture(context, "initial", [_status(), _probe(), _identity()])
    runner = FakeRunner([])
    with pytest.raises(FileExistsError, match="output already exists"):
        gate.capture_observation(
            context[1],
            context[0],
            RUN_ID,
            "initial",
            gate._module_sha256(),
            runner=runner,
            clock=FakeClock(),
            node=context[2],
        )

    assert runner.calls == []
