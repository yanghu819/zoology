from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

import repro.aistation_admission_gate as gate
import repro.aistation_clock_bracket as clock_gate


RUN_ID = "gdn-mqar-p006"
WORKSPACE_ID = "workspace-gpu2"
HOSTNAME = "gpu2-host"
BOOT_ID = "12345678-1234-1234-1234-123456789abc"
FORMAL_SOURCE_SHA = "c" * 40
FORMAL_SOURCE_TREE = "d" * 40


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
    monkeypatch.setattr(clock_gate, "REPO_ROOT", repo)
    monkeypatch.setattr(clock_gate, "APPROVED_HELPER_PATH", helper)
    monkeypatch.setattr(
        clock_gate,
        "APPROVED_HELPER_SHA256",
        hashlib.sha256(helper_bytes).hexdigest(),
    )
    def resolve_formal_source(source_sha):
        if source_sha != FORMAL_SOURCE_SHA:
            raise RuntimeError("unexpected source SHA")
        return FORMAL_SOURCE_TREE

    monkeypatch.setattr(
        clock_gate, "_resolve_formal_source", resolve_formal_source
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


def _complete_admission(context):
    initial, _ = _capture(
        context, "initial", [_status(), _probe(), _identity()]
    )
    pre_capture, _ = _capture(
        context,
        "pre-capture",
        [
            _status(remaining="13000"),
            _probe(),
            _identity(remote_unix=2_000_000_003),
        ],
    )
    return initial, pre_capture


def _write_clock_bundle(
    context,
    *,
    workspace_id: str = WORKSPACE_ID,
    hostname: str = HOSTNAME,
    boot_id: str = BOOT_ID,
    before_unix: int = 2_000_000_004,
):
    output, helper, _ = context
    bundle = output.parent / RUN_ID / "controller"
    bundle.mkdir(parents=True)
    before_raw = _identity(
        workspace_id=workspace_id,
        hostname=hostname,
        boot_id=boot_id,
        remote_unix=before_unix,
    )
    status_raw = _status(
        workspace_id=workspace_id,
        remaining="13000",
    )
    after_raw = _identity(
        workspace_id=workspace_id,
        hostname=hostname,
        boot_id=boot_id,
        remote_unix=before_unix + 2,
    )
    helper_raw = helper.read_bytes()
    proof = clock_gate.build_evidence(
        json.loads(before_raw),
        before_raw,
        json.loads(status_raw),
        status_raw,
        json.loads(after_raw),
        after_raw,
        run_id=RUN_ID,
        formal_source_sha=FORMAL_SOURCE_SHA,
        formal_source_tree=FORMAL_SOURCE_TREE,
        helper_sha256=hashlib.sha256(helper_raw).hexdigest(),
        module_sha256=clock_gate._module_sha256(),
        capture_started_utc="2033-05-18T03:33:20+00:00",
        capture_ended_utc="2033-05-18T03:33:22+00:00",
        capture_elapsed_seconds=2.0,
    )
    attempt = {
        "schema_version": 1,
        "run_id": RUN_ID,
        "formal_source_sha": FORMAL_SOURCE_SHA,
        "formal_source_tree": FORMAL_SOURCE_TREE,
        "target": "GPU2",
        "helper_sha256": hashlib.sha256(helper_raw).hexdigest(),
        "module_sha256": clock_gate._module_sha256(),
        "capture_started_utc": "2033-05-18T03:33:20+00:00",
    }
    files = {
        "capture-attempt.json": clock_gate._canonical_json(attempt),
        "helper-snapshot.js": helper_raw,
        "remote-before.json": before_raw,
        "aistation-status.json": status_raw,
        "remote-after.json": after_raw,
        "clock-bracket.json": clock_gate._canonical_json(proof),
    }
    terminal = {
        "schema_version": 1,
        "run_id": RUN_ID,
        "formal_source_sha": FORMAL_SOURCE_SHA,
        "formal_source_tree": FORMAL_SOURCE_TREE,
        "status": "completed",
        "capture_ended_utc": "2033-05-18T03:33:22+00:00",
        "files_sha256": {
            name: hashlib.sha256(raw).hexdigest()
            for name, raw in files.items()
        },
        "error_type": None,
        "error": None,
    }
    files["capture-terminal.json"] = clock_gate._canonical_json(terminal)
    assert set(files) == set(clock_gate.CAPTURE_FILE_NAMES)
    for name, raw in files.items():
        (bundle / name).write_bytes(raw)
    return bundle, proof, files


def _operation_response(
    command: str,
    *,
    workspace_id: str = WORKSPACE_ID,
    target: str = "GPU2",
    status: str = "Running",
    outer_ok: bool = True,
    inner_ok: bool = True,
    exit_code: int = 0,
    local_path: str | None = None,
    remote_path: str | None = None,
    duplicate_target: bool = False,
) -> bytes:
    operation = {
        "ok": inner_ok,
        "exitCode": exit_code,
        "stdout": "operation output",
        "stderr": "",
    }
    if command == "push":
        operation["localPath"] = local_path
        operation["remotePath"] = remote_path
    target_payload = {
        "wpName": target,
        "wpId": workspace_id,
        "wpStatus": status,
        command: operation,
    }
    targets = [target_payload]
    if duplicate_target:
        targets.append(dict(target_payload))
    return _raw({"command": command, "ok": outer_ok, "targets": targets})


class OperationFakeRunner:
    def __init__(
        self,
        response: bytes,
        *,
        returncode: int = 0,
        stderr: bytes = b"",
    ):
        self.response = response
        self.returncode = returncode
        self.stderr = stderr
        self.calls = []

    def __call__(self, node, helper, arguments, timeout_seconds):
        self.calls.append((arguments, timeout_seconds))
        return subprocess.CompletedProcess(
            [str(node), str(helper), *arguments],
            self.returncode,
            stdout=self.response,
            stderr=self.stderr,
        )


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
    assert initial["python_executable"] == gate.EXPECTED_PYTHON_EXECUTABLE
    assert initial["python_version"] == gate.EXPECTED_PYTHON_VERSION
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


def test_bind_clock_success_binds_both_observations_and_all_bundle_files(context):
    _, pre_capture = _complete_admission(context)
    bundle, proof, files = _write_clock_bundle(context)

    binding = gate.bind_clock(
        context[0],
        bundle,
        RUN_ID,
        FORMAL_SOURCE_SHA,
        FORMAL_SOURCE_TREE,
        gate._module_sha256(),
    )

    assert binding["workspace_id"] == WORKSPACE_ID
    assert binding["remote_hostname"] == HOSTNAME
    assert binding["remote_boot_id"] == BOOT_ID
    assert binding["pre_capture_remote_unix"] == pre_capture["remote_unix"]
    assert (
        binding["clock_selected_observed_unix"]
        == proof["selected_observed_unix"]
    )
    assert binding["formal_source_sha"] == FORMAL_SOURCE_SHA
    assert binding["formal_source_tree"] == FORMAL_SOURCE_TREE
    assert binding["admission_module_sha256"] == gate._module_sha256()
    assert binding["python_executable"] == gate.EXPECTED_PYTHON_EXECUTABLE
    assert binding["python_version"] == gate.EXPECTED_PYTHON_VERSION
    assert binding["bundle_files_sha256"] == {
        name: hashlib.sha256(raw).hexdigest()
        for name, raw in files.items()
    }
    assert binding["clock_bracket_sha256"] == hashlib.sha256(
        files["clock-bracket.json"]
    ).hexdigest()
    assert binding["capture_terminal_sha256"] == hashlib.sha256(
        files["capture-terminal.json"]
    ).hexdigest()
    assert gate.verify_clock_binding(
        context[0],
        bundle,
        RUN_ID,
        FORMAL_SOURCE_SHA,
        FORMAL_SOURCE_TREE,
        gate._module_sha256(),
    ) == binding


@pytest.mark.parametrize(
    ("bundle_kwargs", "message"),
    (
        ({"workspace_id": "replacement-workspace"}, "workspace_id"),
        ({"hostname": "replacement-host"}, "remote_hostname"),
        (
            {"boot_id": "abcdef01-2345-6789-abcd-ef0123456789"},
            "remote_boot_id",
        ),
        ({"before_unix": 2_000_000_002}, "precedes the pre-capture"),
    ),
)
def test_bind_clock_identity_or_time_drift_consumes_attempt_without_binding(
    context, bundle_kwargs, message
):
    _complete_admission(context)
    bundle, _, _ = _write_clock_bundle(context, **bundle_kwargs)

    with pytest.raises(gate.AdmissionGateError, match=message):
        gate.bind_clock(
            context[0],
            bundle,
            RUN_ID,
            FORMAL_SOURCE_SHA,
            FORMAL_SOURCE_TREE,
            gate._module_sha256(),
        )

    assert (context[0] / gate.CLOCK_BINDING_ATTEMPT_NAME).is_file()
    assert not (context[0] / gate.CLOCK_BINDING_NAME).exists()
    with pytest.raises(FileExistsError, match="output already exists"):
        gate.bind_clock(
            context[0],
            bundle,
            RUN_ID,
            FORMAL_SOURCE_SHA,
            FORMAL_SOURCE_TREE,
            gate._module_sha256(),
        )


def test_bind_clock_rejects_observation_tamper_without_success_binding(context):
    _complete_admission(context)
    bundle, _, _ = _write_clock_bundle(context)
    status_path = context[0] / "status-pre-capture.json"
    status_path.write_bytes(_status(remaining="12999"))

    with pytest.raises(gate.AdmissionGateError, match="raw-file hash drift"):
        gate.bind_clock(
            context[0],
            bundle,
            RUN_ID,
            FORMAL_SOURCE_SHA,
            FORMAL_SOURCE_TREE,
            gate._module_sha256(),
        )

    assert (context[0] / gate.CLOCK_BINDING_ATTEMPT_NAME).is_file()
    assert not (context[0] / gate.CLOCK_BINDING_NAME).exists()


@pytest.mark.parametrize(
    "tampered_name",
    ("aistation-status.json", "capture-terminal.json"),
)
def test_bind_clock_rejects_bundle_tamper_without_success_binding(
    context, tampered_name
):
    _complete_admission(context)
    bundle, _, _ = _write_clock_bundle(context)
    tampered_path = bundle / tampered_name
    tampered_path.write_bytes(tampered_path.read_bytes() + b" ")

    with pytest.raises(
        gate.AdmissionGateError,
        match="formal clock bundle",
    ):
        gate.bind_clock(
            context[0],
            bundle,
            RUN_ID,
            FORMAL_SOURCE_SHA,
            FORMAL_SOURCE_TREE,
            gate._module_sha256(),
        )

    assert (context[0] / gate.CLOCK_BINDING_ATTEMPT_NAME).is_file()
    assert not (context[0] / gate.CLOCK_BINDING_NAME).exists()


def test_bind_clock_rejects_formal_source_drift(context):
    _complete_admission(context)
    bundle, _, _ = _write_clock_bundle(context)

    with pytest.raises(gate.AdmissionGateError, match="formal_source_sha"):
        gate.bind_clock(
            context[0],
            bundle,
            RUN_ID,
            "e" * 40,
            FORMAL_SOURCE_TREE,
            gate._module_sha256(),
        )

    assert not (context[0] / gate.CLOCK_BINDING_NAME).exists()


def test_bind_clock_exclusive_reentry_is_rejected(context):
    _complete_admission(context)
    bundle, _, _ = _write_clock_bundle(context)
    gate.bind_clock(
        context[0],
        bundle,
        RUN_ID,
        FORMAL_SOURCE_SHA,
        FORMAL_SOURCE_TREE,
        gate._module_sha256(),
    )

    with pytest.raises(FileExistsError, match="output already exists"):
        gate.bind_clock(
            context[0],
            bundle,
            RUN_ID,
            FORMAL_SOURCE_SHA,
            FORMAL_SOURCE_TREE,
            gate._module_sha256(),
        )


@pytest.mark.parametrize(
    "tamper_kind",
    (
        "binding",
        "attempt",
        "pre-capture",
        "controller-status",
        "controller-terminal",
    ),
)
def test_verify_binding_rejects_post_success_evidence_tamper(
    context, tamper_kind
):
    _complete_admission(context)
    bundle, _, _ = _write_clock_bundle(context)
    gate.bind_clock(
        context[0],
        bundle,
        RUN_ID,
        FORMAL_SOURCE_SHA,
        FORMAL_SOURCE_TREE,
        gate._module_sha256(),
    )
    if tamper_kind == "binding":
        path = context[0] / gate.CLOCK_BINDING_NAME
        payload = json.loads(path.read_bytes())
        payload["workspace_id"] = "tampered-workspace"
        path.write_bytes(gate._canonical_json(payload))
    elif tamper_kind == "attempt":
        path = context[0] / gate.CLOCK_BINDING_ATTEMPT_NAME
        payload = json.loads(path.read_bytes())
        payload["target"] = "GPU1"
        path.write_bytes(gate._canonical_json(payload))
    elif tamper_kind == "pre-capture":
        path = context[0] / "status-pre-capture.json"
        path.write_bytes(_status(remaining="12999"))
    elif tamper_kind == "controller-status":
        path = bundle / "aistation-status.json"
        path.write_bytes(_status(remaining="12999"))
    else:
        path = bundle / "capture-terminal.json"
        path.write_bytes(path.read_bytes() + b" ")

    with pytest.raises(gate.AdmissionGateError):
        gate.verify_clock_binding(
            context[0],
            bundle,
            RUN_ID,
            FORMAL_SOURCE_SHA,
            FORMAL_SOURCE_TREE,
            gate._module_sha256(),
        )


def test_run_operation_exec_success_binds_exact_command_and_initial_parent(context):
    initial, _ = _capture(context, "initial", [_status(), _probe(), _identity()])
    remote_command = "cd /huyang2/zoology && git rev-parse HEAD"
    response = _operation_response("exec")
    runner = OperationFakeRunner(response)

    receipt = gate.run_operation(
        context[1],
        context[0],
        RUN_ID,
        "source-check",
        "exec",
        "initial",
        gate._module_sha256(),
        remote_command=remote_command,
        runner=runner,
        node=context[2],
    )

    assert runner.calls == [
        (("exec", "GPU2", "--", remote_command), 30)
    ]
    assert receipt["remote_command"] == remote_command
    assert receipt["identity_parent"] == "initial"
    assert receipt["identity_parent_sha256"] == hashlib.sha256(
        (context[0] / "observation-initial.json").read_bytes()
    ).hexdigest()
    assert receipt["workspace_id"] == initial["workspace_id"]
    assert receipt["python_executable"] == gate.EXPECTED_PYTHON_EXECUTABLE
    assert receipt["python_version"] == gate.EXPECTED_PYTHON_VERSION
    assert receipt["raw_response_sha256"] == hashlib.sha256(
        response
    ).hexdigest()
    assert (
        context[0] / "operation-source-check-raw.json"
    ).read_bytes() == response


def test_run_operation_push_success_uses_620_second_timeout_and_exact_paths(context):
    _capture(context, "initial", [_status(), _probe(), _identity()])
    local_path = context[0].parent / "launcher-payload"
    local_path.mkdir()
    remote_path = f"/huyang2/zoology/artifacts/{RUN_ID}/launcher"
    response = _operation_response(
        "push",
        local_path=str(local_path),
        remote_path=remote_path,
    )
    runner = OperationFakeRunner(response)

    receipt = gate.run_operation(
        context[1],
        context[0],
        RUN_ID,
        "launcher-push",
        "push",
        "initial",
        gate._module_sha256(),
        local_path=str(local_path),
        remote_path=remote_path,
        runner=runner,
        node=context[2],
    )

    assert runner.calls == [
        (("push", "GPU2", "--", str(local_path), remote_path), 620)
    ]
    assert receipt["local_path"] == str(local_path)
    assert receipt["remote_path"] == remote_path
    assert receipt["timeout_seconds"] == 620


def test_run_operation_binding_parent_is_revalidated_and_hashed(context):
    _complete_admission(context)
    bundle, _, _ = _write_clock_bundle(context)
    gate.bind_clock(
        context[0],
        bundle,
        RUN_ID,
        FORMAL_SOURCE_SHA,
        FORMAL_SOURCE_TREE,
        gate._module_sha256(),
    )
    runner = OperationFakeRunner(_operation_response("exec"))

    receipt = gate.run_operation(
        context[1],
        context[0],
        RUN_ID,
        "formal-start",
        "exec",
        "binding",
        gate._module_sha256(),
        remote_command="/huyang2/zoology/formal-start",
        bundle_dir=bundle,
        formal_source_sha=FORMAL_SOURCE_SHA,
        formal_source_tree=FORMAL_SOURCE_TREE,
        runner=runner,
        node=context[2],
    )

    assert receipt["identity_parent"] == "binding"
    assert receipt["identity_parent_sha256"] == hashlib.sha256(
        (context[0] / gate.CLOCK_BINDING_NAME).read_bytes()
    ).hexdigest()


@pytest.mark.parametrize(
    ("response", "message"),
    (
        (b"{malformed", "not valid JSON"),
        (_operation_response("exec", outer_ok=False), "helper call failed"),
        (_operation_response("exec", inner_ok=False), "operation failed"),
        (_operation_response("exec", exit_code=9), "operation failed"),
        (_operation_response("exec", target="GPU1"), "literal GPU2"),
        (_operation_response("exec", status="Halt"), "not Running"),
        (
            _operation_response("exec", workspace_id="replacement-workspace"),
            "workspace differs",
        ),
        (
            _operation_response("exec", duplicate_target=True),
            "exactly one target",
        ),
        (_operation_response("push"), "helper call failed"),
    ),
)
def test_run_operation_rejects_invalid_helper_json_and_consumes_stage(
    context, response, message
):
    _capture(context, "initial", [_status(), _probe(), _identity()])
    runner = OperationFakeRunner(response)

    with pytest.raises(gate.AdmissionGateError, match=message):
        gate.run_operation(
            context[1],
            context[0],
            RUN_ID,
            "invalid-response",
            "exec",
            "initial",
            gate._module_sha256(),
            remote_command="true",
            runner=runner,
            node=context[2],
        )

    assert len(runner.calls) == 1
    assert (
        context[0] / "operation-invalid-response-attempt.json"
    ).is_file()
    assert (
        context[0] / "operation-invalid-response-raw.json"
    ).read_bytes() == response
    assert not (
        context[0] / "operation-invalid-response-receipt.json"
    ).exists()
    with pytest.raises(FileExistsError, match="stage output already exists"):
        gate.run_operation(
            context[1],
            context[0],
            RUN_ID,
            "invalid-response",
            "exec",
            "initial",
            gate._module_sha256(),
            remote_command="true",
            runner=OperationFakeRunner(_operation_response("exec")),
            node=context[2],
        )


@pytest.mark.parametrize(
    ("returncode", "process_stderr", "message"),
    (
        (7, b"", "helper process failed"),
        (0, b"wrapper warning", "process stderr is not empty"),
    ),
)
def test_run_operation_rejects_helper_process_failure(
    context, returncode, process_stderr, message
):
    _capture(context, "initial", [_status(), _probe(), _identity()])
    runner = OperationFakeRunner(
        _operation_response("exec"),
        returncode=returncode,
        stderr=process_stderr,
    )

    with pytest.raises(gate.AdmissionGateError, match=message):
        gate.run_operation(
            context[1],
            context[0],
            RUN_ID,
            "helper-failure",
            "exec",
            "initial",
            gate._module_sha256(),
            remote_command="true",
            runner=runner,
            node=context[2],
        )

    assert not (
        context[0] / "operation-helper-failure-receipt.json"
    ).exists()


def test_run_operation_rejects_helper_hash_mutation_after_call(context):
    _capture(context, "initial", [_status(), _probe(), _identity()])
    response = _operation_response("exec")

    class MutatingOperationRunner:
        calls = []

        def __call__(self, node, helper, arguments, timeout_seconds):
            self.calls.append((arguments, timeout_seconds))
            helper.write_bytes(b"// mutated during operation\n")
            return subprocess.CompletedProcess(
                [str(node), str(helper), *arguments],
                0,
                stdout=response,
                stderr=b"",
            )

    runner = MutatingOperationRunner()
    with pytest.raises(gate.AdmissionGateError, match="helper differs"):
        gate.run_operation(
            context[1],
            context[0],
            RUN_ID,
            "helper-mutation",
            "exec",
            "initial",
            gate._module_sha256(),
            remote_command="true",
            runner=runner,
            node=context[2],
        )

    assert runner.calls == [(("exec", "GPU2", "--", "true"), 30)]
    assert (
        context[0] / "operation-helper-mutation-raw.json"
    ).read_bytes() == response
    assert not (
        context[0] / "operation-helper-mutation-receipt.json"
    ).exists()


def test_run_operation_rejects_parent_tamper_before_stage_consumption(context):
    _capture(context, "initial", [_status(), _probe(), _identity()])
    (context[0] / "status-running.json").write_bytes(
        _status(remaining="13999")
    )
    runner = OperationFakeRunner(_operation_response("exec"))

    with pytest.raises(gate.AdmissionGateError, match="raw-file hash drift"):
        gate.run_operation(
            context[1],
            context[0],
            RUN_ID,
            "parent-tamper",
            "exec",
            "initial",
            gate._module_sha256(),
            remote_command="true",
            runner=runner,
            node=context[2],
        )

    assert runner.calls == []
    assert not (
        context[0] / "operation-parent-tamper-attempt.json"
    ).exists()


def test_binding_parent_controller_drift_after_call_blocks_receipt(context):
    _complete_admission(context)
    bundle, _, _ = _write_clock_bundle(context)
    gate.bind_clock(
        context[0],
        bundle,
        RUN_ID,
        FORMAL_SOURCE_SHA,
        FORMAL_SOURCE_TREE,
        gate._module_sha256(),
    )
    response = _operation_response("exec")

    class ControllerMutatingRunner:
        calls = []

        def __call__(self, node, helper, arguments, timeout_seconds):
            self.calls.append((arguments, timeout_seconds))
            terminal = bundle / "capture-terminal.json"
            terminal.write_bytes(terminal.read_bytes() + b" ")
            return subprocess.CompletedProcess(
                [str(node), str(helper), *arguments],
                0,
                stdout=response,
                stderr=b"",
            )

    runner = ControllerMutatingRunner()
    with pytest.raises(gate.AdmissionGateError, match="formal clock bundle"):
        gate.run_operation(
            context[1],
            context[0],
            RUN_ID,
            "binding-drift",
            "exec",
            "binding",
            gate._module_sha256(),
            remote_command="true",
            bundle_dir=bundle,
            formal_source_sha=FORMAL_SOURCE_SHA,
            formal_source_tree=FORMAL_SOURCE_TREE,
            runner=runner,
            node=context[2],
        )

    assert len(runner.calls) == 1
    assert (
        context[0] / "operation-binding-drift-raw.json"
    ).read_bytes() == response
    assert not (
        context[0] / "operation-binding-drift-receipt.json"
    ).exists()


def test_run_operation_push_rejects_wrong_echoed_path(context):
    _capture(context, "initial", [_status(), _probe(), _identity()])
    local_path = context[0].parent / "payload"
    local_path.mkdir()
    remote_path = f"/huyang2/zoology/artifacts/{RUN_ID}/payload"
    response = _operation_response(
        "push",
        local_path=str(local_path),
        remote_path=f"{remote_path}-wrong",
    )

    with pytest.raises(gate.AdmissionGateError, match="path echo differs"):
        gate.run_operation(
            context[1],
            context[0],
            RUN_ID,
            "wrong-path",
            "push",
            "initial",
            gate._module_sha256(),
            local_path=str(local_path),
            remote_path=remote_path,
            runner=OperationFakeRunner(response),
            node=context[2],
        )

    assert not (context[0] / "operation-wrong-path-receipt.json").exists()


@pytest.mark.parametrize(
    ("local_path_kind", "remote_path", "message"),
    (
        ("outside", "/huyang2/zoology/allowed", "outside the repository"),
        ("inside", "/tmp/forbidden", "outside /huyang2/zoology"),
    ),
)
def test_run_operation_rejects_noncanonical_push_paths_before_helper(
    context, local_path_kind, remote_path, message
):
    _capture(context, "initial", [_status(), _probe(), _identity()])
    inside = context[0].parent / "inside-payload"
    inside.mkdir()
    local_path = context[1] if local_path_kind == "outside" else inside
    runner = OperationFakeRunner(_operation_response("push"))

    with pytest.raises(gate.AdmissionGateError, match=message):
        gate.run_operation(
            context[1],
            context[0],
            RUN_ID,
            "invalid-path",
            "push",
            "initial",
            gate._module_sha256(),
            local_path=str(local_path),
            remote_path=remote_path,
            runner=runner,
            node=context[2],
        )

    assert runner.calls == []
    assert not (
        context[0] / "operation-invalid-path-attempt.json"
    ).exists()


def test_run_operation_push_timeout_is_620_seconds_and_has_no_receipt(context):
    _capture(context, "initial", [_status(), _probe(), _identity()])
    local_path = context[0].parent / "timeout-payload"
    local_path.mkdir()
    remote_path = f"/huyang2/zoology/artifacts/{RUN_ID}/timeout"

    class PushTimeoutRunner:
        calls = []

        def __call__(self, node, helper, arguments, timeout_seconds):
            self.calls.append((arguments, timeout_seconds))
            raise subprocess.TimeoutExpired(
                [str(node), str(helper), *arguments],
                timeout_seconds,
                output=b'{"command":"push"',
            )

    runner = PushTimeoutRunner()
    with pytest.raises(gate.AdmissionGateError, match="timed out"):
        gate.run_operation(
            context[1],
            context[0],
            RUN_ID,
            "push-timeout",
            "push",
            "initial",
            gate._module_sha256(),
            local_path=str(local_path),
            remote_path=remote_path,
            runner=runner,
            node=context[2],
        )

    assert runner.calls[0][1] == 620
    assert not (
        context[0] / "operation-push-timeout-receipt.json"
    ).exists()


def test_run_operation_successful_stage_reentry_is_rejected(context):
    _capture(context, "initial", [_status(), _probe(), _identity()])
    arguments = {
        "remote_command": "true",
        "runner": OperationFakeRunner(_operation_response("exec")),
        "node": context[2],
    }
    gate.run_operation(
        context[1],
        context[0],
        RUN_ID,
        "one-shot",
        "exec",
        "initial",
        gate._module_sha256(),
        **arguments,
    )

    with pytest.raises(FileExistsError, match="stage output already exists"):
        gate.run_operation(
            context[1],
            context[0],
            RUN_ID,
            "one-shot",
            "exec",
            "initial",
            gate._module_sha256(),
            remote_command="true",
            runner=OperationFakeRunner(_operation_response("exec")),
            node=context[2],
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


@pytest.mark.parametrize(
    ("attribute", "value", "message"),
    (
        (
            "EXPECTED_PYTHON_EXECUTABLE",
            "/nonexistent/frozen-python",
            "Python executable differs",
        ),
        ("EXPECTED_PYTHON_VERSION", "0.0.0", "Python version differs"),
    ),
)
def test_python_runtime_drift_rejects_before_helper(
    context, monkeypatch, attribute, value, message
):
    monkeypatch.setattr(gate, attribute, value)
    runner = FakeRunner([])

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

    assert runner.calls == []
    assert list(context[0].iterdir()) == []


def test_capture_cli_fails_closed_on_python_version_drift(
    context, monkeypatch, capsys
):
    monkeypatch.setattr(gate, "EXPECTED_PYTHON_VERSION", "0.0.0")

    exit_code = gate.main(
        [
            "capture",
            "--helper",
            str(context[1]),
            "--output-dir",
            str(context[0]),
            "--run-id",
            RUN_ID,
            "--phase",
            "initial",
            "--module-sha256",
            gate._module_sha256(),
        ]
    )

    assert exit_code == 1
    assert "Python version differs" in capsys.readouterr().err
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
