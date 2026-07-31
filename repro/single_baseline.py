"""Lifecycle contract for one pilot-informed official GDN baseline cell."""

from __future__ import annotations

import argparse
import json
import math
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from repro.aggregate import _publish_immutable_text
from repro.aistation_clock_bracket import (
    SUITE_CLOCK_FILE_MAP,
    SUITE_CLOCK_FILE_NAMES,
    validate_suite_clock_evidence,
)
from repro.cache_contract import sha256_file
from repro.configs.gdn_mqar_official import configs
from repro.suite_contract import (
    SUITE_MANIFEST_NAME,
    _active_cache_manifest,
    _cell_paths,
    _load_metric_rows,
    require_suite_location,
    validate_admission,
    validate_active_launch,
    validate_cell,
    validate_suite,
)


ROOT = Path(__file__).resolve().parents[1]
BASELINE_MANIFEST_NAME = "single-baseline-manifest.json"
BASELINE_RESULT_NAME = "single-baseline-result.json"
AISTATION_STATUS_NAME = SUITE_CLOCK_FILE_MAP["aistation-status.json"]
CLOCK_BRACKET_NAME = SUITE_CLOCK_FILE_MAP["clock-bracket.json"]
CLOCK_CAPTURE_TERMINAL_NAME = SUITE_CLOCK_FILE_MAP["capture-terminal.json"]
CONTROLLER_ADMISSION_NAME = "controller-admission.json"
WORKER_ADMISSION_NAME = "worker-admission.json"
DEFAULT_SELECTED_INDEX = 5
CONTROLLER_ADMISSION_FLOOR = 12_060
WORKER_ADMISSION_FLOOR = 11_460
STRONG_ACCURACY_FLOOR = 0.98
KV256_DIAGNOSTIC_FLOOR = 0.88
SELECTION_RATIONALE = (
    "Pilot-informed selection: d_model=128 is the smallest committed GDN width "
    "with an official plot reading near 0.99, and learning rate 10^-2.5 was "
    "the best stable interior point among the three valid partial d_model=128 "
    "cells from the prior failed formal 12-cell reproduction, used here as "
    "pilot evidence."
)


def _load_object(path: Path) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise RuntimeError(f"cannot stat required JSON file {path}: {error}") from error
    if not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError(f"required JSON path is not a regular file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"cannot read valid JSON object {path}: {error}") from error
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object in {path}")
    return payload


def _parse_utc_timestamp(value: Any, field: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as error:
        raise RuntimeError(f"{field} is not a valid ISO timestamp") from error
    if timestamp.tzinfo is None or timestamp.utcoffset() != timezone.utc.utcoffset(
        timestamp
    ):
        raise RuntimeError(f"{field} is not an explicit UTC timestamp")
    return timestamp


def _require_exact_fields(
    payload: dict[str, Any],
    expected: set[str],
    label: str,
) -> None:
    actual = set(payload)
    if actual != expected:
        raise RuntimeError(
            f"{label} fields drifted: expected={sorted(expected)} "
            f"actual={sorted(actual)}"
        )


def _official_point(d_model: int) -> dict[str, Any]:
    baseline = _load_object(ROOT / "repro" / "official_baseline.json")
    matches = [
        point
        for point in baseline.get("plot_points", [])
        if int(point["d_model"]) == d_model
    ]
    if len(matches) != 1:
        raise RuntimeError(f"expected one official plot point for d_model={d_model}")
    return matches[0]


def _contract_fields(index: int, suite_manifest_sha256: str) -> dict[str, Any]:
    if index != DEFAULT_SELECTED_INDEX:
        raise ValueError(
            "the frozen single baseline must use local harness index "
            f"{DEFAULT_SELECTED_INDEX} from the official grid, got {index}"
        )
    config = configs[index]
    point = _official_point(int(config.model.d_model))
    visual_approx = float(point["official_accuracy_visual_approx"])
    visual_tolerance = float(point["visual_tolerance"])
    return {
        "schema_version": 1,
        "kind": "pilot-informed-fixed-official-grid-configuration-baseline",
        "selected_index": index,
        "selected_index_scope": "local reproduction harness index",
        "d_model": int(config.model.d_model),
        "learning_rate": float(config.learning_rate),
        "seed": int(config.seed),
        "max_epochs": int(config.max_epochs),
        "metric": "final valid/accuracy",
        "official_accuracy_exact": None,
        "official_accuracy_visual_approx": visual_approx,
        "visual_tolerance": visual_tolerance,
        "visual_compatibility_floor": visual_approx - visual_tolerance,
        "visual_compatibility_floor_provenance": (
            "The approximate 0.99 PNG reading minus the project's pre-existing "
            "0.03 visual-reading tolerance; it is not an upstream threshold, "
            "confidence interval, or error bar."
        ),
        "strong_accuracy_floor": STRONG_ACCURACY_FLOOR,
        "strong_accuracy_floor_provenance": (
            "A project decision threshold frozen before this standalone rerun; "
            "it is not published by upstream."
        ),
        "kv256_diagnostic_floor": KV256_DIAGNOSTIC_FLOOR,
        "kv256_diagnostic_floor_provenance": (
            "A non-official diagnostic threshold informed by the valid partial "
            "d128 cells from the prior failed formal reproduction, used here "
            "as pilot evidence; it never replaces final overall valid/accuracy."
        ),
        "selection_rationale": SELECTION_RATIONALE,
        "claim_boundary": (
            "This run can support only one fixed official-grid configuration. "
            "It cannot support a best-of-four width point or complete frontier."
        ),
        "full_frontier_claim_allowed": False,
        "suite_manifest_sha256": suite_manifest_sha256,
    }


def _started_paths(suite_dir: Path, index: int) -> list[Path]:
    paths = _cell_paths(suite_dir, index)
    return [
        path
        for path in (
            paths["metadata"],
            paths["run_dir"],
            paths["log"],
            paths["claim"],
            paths["launch_dir"],
        )
        if path.exists() or path.is_symlink()
    ]


def _reject_unexpected_evidence(suite_dir: Path) -> None:
    config = configs[DEFAULT_SELECTED_INDEX]
    selected_run_name = (
        f"{DEFAULT_SELECTED_INDEX:02d}__d{config.model.d_model}"
        f"__lr{float(config.learning_rate):.10g}"
    )
    allowed_root_names = {
        "logs",
        "claims",
        "launches",
        "source.tar.gz",
        "source.tar.gz.sha256",
        "cache-manifest.json",
        "cache-manifest.json.sha256",
        "nvidia-smi.txt",
        "runtime-attestation.json",
        SUITE_MANIFEST_NAME,
        BASELINE_MANIFEST_NAME,
        BASELINE_RESULT_NAME,
        AISTATION_STATUS_NAME,
        CONTROLLER_ADMISSION_NAME,
        f"run-{DEFAULT_SELECTED_INDEX:02d}-metadata.json",
        selected_run_name,
    }
    allowed_root_names.update(SUITE_CLOCK_FILE_NAMES)
    unexpected_root = sorted(
        path.name
        for path in suite_dir.iterdir()
        if path.name not in allowed_root_names
    )
    if unexpected_root:
        raise RuntimeError(
            f"single baseline has unexpected root evidence: {unexpected_root}"
        )

    nested_allowlists = {
        suite_dir / "logs": {f"run-{DEFAULT_SELECTED_INDEX:02d}.log"},
        suite_dir / "claims": {f"run-{DEFAULT_SELECTED_INDEX:02d}"},
        suite_dir / "launches": {f"run-{DEFAULT_SELECTED_INDEX:02d}"},
        suite_dir / "claims" / f"run-{DEFAULT_SELECTED_INDEX:02d}": {
            "runtime-attestation.json"
        },
        suite_dir / "launches" / f"run-{DEFAULT_SELECTED_INDEX:02d}": {
            "request.json",
            "launch.json",
            "worker.pid",
            "launcher.log",
            "terminal.json",
            WORKER_ADMISSION_NAME,
        },
        suite_dir / selected_run_name: {
            "summary.json",
            "resolved-config.json",
            "model-metadata.json",
            "metrics.jsonl",
            "failure.json",
        },
    }
    for directory, allowed_names in nested_allowlists.items():
        if not directory.exists() and not directory.is_symlink():
            continue
        try:
            metadata = directory.lstat()
        except OSError as error:
            raise RuntimeError(f"cannot stat baseline evidence {directory}") from error
        if not stat.S_ISDIR(metadata.st_mode):
            raise RuntimeError(
                f"baseline evidence path is not a real directory: {directory}"
            )
        unexpected = sorted(
            path.name for path in directory.iterdir() if path.name not in allowed_names
        )
        if unexpected:
            raise RuntimeError(
                f"single baseline has unexpected evidence in {directory}: {unexpected}"
            )


def _load_aistation_status(suite_dir: Path) -> tuple[dict[str, Any], str]:
    path = suite_dir / AISTATION_STATUS_NAME
    payload = _load_object(path)
    targets = payload.get("targets")
    if (
        payload.get("command") != "status"
        or payload.get("ok") is not True
        or not isinstance(targets, list)
        or len(targets) != 1
        or not isinstance(targets[0], dict)
    ):
        raise RuntimeError("AIStation status evidence is not one successful target")
    target = targets[0]
    if (
        target.get("wpName") != "GPU2"
        or target.get("wpStatus") != "Running"
        or not isinstance(target.get("wpId"), str)
        or not target["wpId"]
    ):
        raise RuntimeError("AIStation status evidence is not a running GPU2 row")
    try:
        remaining_seconds = int(target["remainTime"])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("AIStation GPU2 remainTime is not an integer") from error
    if remaining_seconds < 0:
        raise RuntimeError("AIStation GPU2 remainTime is negative")
    return target, sha256_file(path)


def _admission_path(suite_dir: Path, phase: str) -> Path:
    if phase == "controller":
        return suite_dir / CONTROLLER_ADMISSION_NAME
    if phase == "worker":
        return (
            suite_dir
            / "launches"
            / f"run-{DEFAULT_SELECTED_INDEX:02d}"
            / WORKER_ADMISSION_NAME
        )
    raise ValueError(f"unsupported admission phase: {phase}")


def _admission_floor(phase: str) -> int:
    if phase == "controller":
        return CONTROLLER_ADMISSION_FLOOR
    if phase == "worker":
        return WORKER_ADMISSION_FLOOR
    raise ValueError(f"unsupported admission phase: {phase}")


def _clock_evidence_hashes(suite_dir: Path) -> dict[str, str]:
    return {
        name: sha256_file(suite_dir / name)
        for name in SUITE_CLOCK_FILE_NAMES
    }


def record_admission(
    suite_dir: Path,
    phase: str,
    remaining_seconds: int,
    observed_unix: int,
) -> dict[str, Any]:
    """Publish one immutable controller or worker lease decision."""
    suite_dir = suite_dir.resolve()
    manifest = validate_baseline(suite_dir)
    proof, status_raw = validate_suite_clock_evidence(suite_dir)
    target, status_sha256 = _load_aistation_status(suite_dir)
    if status_raw != (suite_dir / AISTATION_STATUS_NAME).read_bytes():
        raise RuntimeError("validated AIStation status bytes drifted")
    status_remaining = int(target["remainTime"])
    if remaining_seconds != status_remaining:
        raise RuntimeError(
            "reported remaining seconds disagree with AIStation status evidence: "
            f"argument={remaining_seconds} status={status_remaining}"
        )
    if remaining_seconds != proof["reported_remaining_seconds"]:
        raise RuntimeError(
            "reported remaining seconds disagree with clock-bracket proof: "
            f"argument={remaining_seconds} "
            f"proof={proof['reported_remaining_seconds']}"
        )
    if observed_unix != proof["selected_observed_unix"]:
        raise RuntimeError(
            "observed Unix time disagrees with clock-bracket proof: "
            f"argument={observed_unix} "
            f"proof={proof['selected_observed_unix']}"
        )
    if target["wpId"] != proof["workspace_id"]:
        raise RuntimeError("AIStation workspace disagrees with clock-bracket proof")
    if phase == "worker":
        _validate_baseline_launch_mode(suite_dir, DEFAULT_SELECTED_INDEX)

    checked_at = datetime.now(timezone.utc)
    checked_unix = math.ceil(checked_at.timestamp())
    raw_age_seconds = checked_unix - observed_unix
    effective_age_seconds = max(raw_age_seconds, 0)
    adjusted_seconds = max(remaining_seconds - effective_age_seconds, 0)
    minimum_seconds = _admission_floor(phase)
    passed = False
    error_type = None
    error_message = None
    caught_error: BaseException | None = None
    try:
        validated_adjusted = validate_admission(
            remaining_seconds,
            observed_unix,
            minimum_seconds,
            now_unix=checked_unix,
        )
        if validated_adjusted != adjusted_seconds:
            raise RuntimeError("admission adjusted-seconds calculation drift")
        passed = True
    except BaseException as error:
        caught_error = error
        error_type = type(error).__name__
        error_message = str(error)

    payload = {
        "schema_version": 1,
        "phase": phase,
        "aistation_target": "GPU2",
        "aistation_workspace_id": target["wpId"],
        "aistation_workspace_status": target["wpStatus"],
        "aistation_status_sha256": status_sha256,
        "clock_bracket_sha256": sha256_file(
            suite_dir / CLOCK_BRACKET_NAME
        ),
        "clock_capture_terminal_sha256": sha256_file(
            suite_dir / CLOCK_CAPTURE_TERMINAL_NAME
        ),
        "clock_evidence_sha256": _clock_evidence_hashes(suite_dir),
        "baseline_manifest_sha256": sha256_file(
            suite_dir / BASELINE_MANIFEST_NAME
        ),
        "reported_remaining_seconds": remaining_seconds,
        "observed_unix": observed_unix,
        "observed_utc": datetime.fromtimestamp(
            observed_unix,
            timezone.utc,
        ).isoformat(),
        "checked_unix": checked_unix,
        "checked_utc": checked_at.isoformat(),
        "raw_age_seconds": raw_age_seconds,
        "effective_age_seconds": effective_age_seconds,
        "adjusted_remaining_seconds": adjusted_seconds,
        "minimum_remaining_seconds": minimum_seconds,
        "passed": passed,
        "error_type": error_type,
        "error": error_message,
    }
    _publish_immutable_text(
        _admission_path(suite_dir, phase),
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
    )
    if caught_error is not None:
        raise RuntimeError(
            f"{phase} admission failed after writing evidence: {caught_error}"
        ) from caught_error
    return payload


def _validate_admission_record(
    suite_dir: Path,
    phase: str,
) -> dict[str, Any]:
    manifest = validate_baseline(suite_dir)
    proof, status_raw = validate_suite_clock_evidence(suite_dir)
    target, status_sha256 = _load_aistation_status(suite_dir)
    if status_raw != (suite_dir / AISTATION_STATUS_NAME).read_bytes():
        raise RuntimeError("validated AIStation status bytes drifted")
    payload = _load_object(_admission_path(suite_dir, phase))
    expected_keys = {
        "schema_version",
        "phase",
        "aistation_target",
        "aistation_workspace_id",
        "aistation_workspace_status",
        "aistation_status_sha256",
        "clock_bracket_sha256",
        "clock_capture_terminal_sha256",
        "clock_evidence_sha256",
        "baseline_manifest_sha256",
        "reported_remaining_seconds",
        "observed_unix",
        "observed_utc",
        "checked_unix",
        "checked_utc",
        "raw_age_seconds",
        "effective_age_seconds",
        "adjusted_remaining_seconds",
        "minimum_remaining_seconds",
        "passed",
        "error_type",
        "error",
    }
    if set(payload) != expected_keys:
        raise RuntimeError(
            f"{phase} admission fields drifted: {sorted(payload)}"
        )
    try:
        remaining_seconds = int(payload["reported_remaining_seconds"])
        observed_unix = int(payload["observed_unix"])
        checked_unix = int(payload["checked_unix"])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(f"{phase} admission integers are invalid") from error
    if remaining_seconds != proof["reported_remaining_seconds"]:
        raise RuntimeError(
            f"{phase} admission remaining seconds drift from clock proof"
        )
    if observed_unix != proof["selected_observed_unix"]:
        raise RuntimeError(
            f"{phase} admission observed time drift from clock proof"
        )
    if remaining_seconds != int(target["remainTime"]):
        raise RuntimeError(
            f"{phase} admission remaining seconds drift from status"
        )
    checked_at = _parse_utc_timestamp(
        payload["checked_utc"],
        f"{phase} admission checked_utc",
    )
    if math.ceil(checked_at.timestamp()) != checked_unix:
        raise RuntimeError(f"{phase} admission checked time drift")
    baseline_created = _parse_utc_timestamp(
        manifest["created_utc"],
        "single baseline manifest created_utc",
    )
    if checked_at < baseline_created:
        raise RuntimeError(f"{phase} admission predates the baseline manifest")
    adjusted = validate_admission(
        remaining_seconds,
        observed_unix,
        _admission_floor(phase),
        now_unix=checked_unix,
    )
    raw_age = checked_unix - observed_unix
    expected = {
        "schema_version": 1,
        "phase": phase,
        "aistation_target": "GPU2",
        "aistation_workspace_id": target["wpId"],
        "aistation_workspace_status": "Running",
        "aistation_status_sha256": status_sha256,
        "clock_bracket_sha256": sha256_file(
            suite_dir / CLOCK_BRACKET_NAME
        ),
        "clock_capture_terminal_sha256": sha256_file(
            suite_dir / CLOCK_CAPTURE_TERMINAL_NAME
        ),
        "clock_evidence_sha256": _clock_evidence_hashes(suite_dir),
        "baseline_manifest_sha256": sha256_file(
            suite_dir / BASELINE_MANIFEST_NAME
        ),
        "reported_remaining_seconds": proof["reported_remaining_seconds"],
        "observed_unix": proof["selected_observed_unix"],
        "observed_utc": datetime.fromtimestamp(
            observed_unix,
            timezone.utc,
        ).isoformat(),
        "checked_unix": checked_unix,
        "checked_utc": checked_at.isoformat(),
        "raw_age_seconds": raw_age,
        "effective_age_seconds": max(raw_age, 0),
        "adjusted_remaining_seconds": adjusted,
        "minimum_remaining_seconds": _admission_floor(phase),
        "passed": True,
        "error_type": None,
        "error": None,
    }
    if payload != expected:
        raise RuntimeError(
            f"{phase} admission evidence drift: expected={expected} actual={payload}"
        )
    if target["wpId"] != proof["workspace_id"]:
        raise RuntimeError("AIStation workspace disagrees with clock-bracket proof")
    return payload


def _validate_baseline_launch_mode(suite_dir: Path, index: int) -> None:
    paths = _cell_paths(suite_dir, index)
    request = _load_object(paths["request"])
    launch = _load_object(paths["launch"])
    for name, payload in (("request", request), ("launch", launch)):
        if payload.get("worker_mode") != "_baseline-worker":
            raise RuntimeError(f"{name} does not declare baseline worker mode")
    _require_exact_fields(
        request,
        {
            "schema_version",
            "state",
            "cell_index",
            "requested_utc",
            "suite_dir",
            "worker_mode",
            "baseline_manifest_sha256",
            "controller_admission_sha256",
            "command",
        },
        "baseline request",
    )
    _require_exact_fields(
        launch,
        {
            "schema_version",
            "state",
            "cell_index",
            "worker_pid",
            "launched_utc",
            "suite_dir",
            "worker_mode",
            "baseline_manifest_sha256",
            "controller_admission_sha256",
            "launcher_log",
            "cell_log",
            "terminal_record",
            "command",
            "expected_git_sha",
            "aistation_target",
            "reported_remaining_seconds",
            "remaining_observed_unix",
            "minimum_remaining_seconds",
            "controller_minimum_remaining_seconds",
        },
        "baseline launch",
    )
    requested_utc = _parse_utc_timestamp(
        request["requested_utc"],
        "baseline request requested_utc",
    )
    launched_utc = _parse_utc_timestamp(
        launch["launched_utc"],
        "baseline launch launched_utc",
    )
    if launched_utc < requested_utc:
        raise RuntimeError("baseline launch predates its request")
    baseline_manifest_sha256 = sha256_file(
        suite_dir / BASELINE_MANIFEST_NAME
    )
    controller_admission = _validate_admission_record(
        suite_dir,
        "controller",
    )
    controller_checked_utc = _parse_utc_timestamp(
        controller_admission["checked_utc"],
        "controller admission checked_utc",
    )
    if requested_utc < controller_checked_utc:
        raise RuntimeError("baseline request predates controller admission")
    controller_admission_sha256 = sha256_file(
        suite_dir / CONTROLLER_ADMISSION_NAME
    )
    expected_command = [
        str(ROOT / "run.sh"),
        "_baseline-worker",
        str(index),
        str(suite_dir.resolve()),
        str(paths["launch_dir"].resolve()),
    ]
    expected_common = {
        "schema_version": 1,
        "cell_index": index,
        "suite_dir": str(suite_dir.resolve()),
        "worker_mode": "_baseline-worker",
    }
    for name, payload in (("request", request), ("launch", launch)):
        for key, expected_value in expected_common.items():
            if payload.get(key) != expected_value:
                raise RuntimeError(
                    f"{name} baseline field {key} drift: "
                    f"expected={expected_value!r} actual={payload.get(key)!r}"
                )
        if payload.get("command") != expected_command:
            raise RuntimeError(
                f"{name} baseline worker command drift: "
                f"expected={expected_command} actual={payload.get('command')}"
            )
        if payload.get("baseline_manifest_sha256") != baseline_manifest_sha256:
            raise RuntimeError(f"{name} baseline manifest hash drift")
        if (
            payload.get("controller_admission_sha256")
            != controller_admission_sha256
        ):
            raise RuntimeError(f"{name} controller admission hash drift")
    if request.get("state") != "requested":
        raise RuntimeError("baseline request state drift")
    if launch.get("state") != "launched":
        raise RuntimeError("baseline launch state drift")
    if launch.get("expected_git_sha") != _load_object(
        suite_dir / SUITE_MANIFEST_NAME
    ).get("git_sha"):
        raise RuntimeError("baseline launch Git SHA drift")
    if launch.get("aistation_target") != "GPU2":
        raise RuntimeError("baseline launch target is not GPU2")
    expected_paths = {
        "launcher_log": str(paths["launcher_log"].resolve()),
        "cell_log": str(paths["log"].resolve()),
        "terminal_record": str(paths["terminal"].resolve()),
    }
    for key, expected_value in expected_paths.items():
        if launch.get(key) != expected_value:
            raise RuntimeError(
                f"baseline launch {key} drift: "
                f"expected={expected_value!r} actual={launch.get(key)!r}"
            )
    if launch.get("minimum_remaining_seconds") != "11460":
        raise RuntimeError("baseline worker admission floor must be 11460 seconds")
    if launch.get("controller_minimum_remaining_seconds") != "12060":
        raise RuntimeError(
            "baseline controller admission floor must be 12060 seconds"
        )
    if launch.get("reported_remaining_seconds") != str(
        controller_admission["reported_remaining_seconds"]
    ):
        raise RuntimeError("launch remaining seconds disagree with admission")
    if launch.get("remaining_observed_unix") != str(
        controller_admission["observed_unix"]
    ):
        raise RuntimeError("launch observation time disagrees with admission")


def _validate_worker_admission(suite_dir: Path, index: int) -> dict[str, Any]:
    paths = _cell_paths(suite_dir, index)
    worker_admission = _validate_admission_record(suite_dir, "worker")
    terminal = _load_object(paths["terminal"])
    _require_exact_fields(
        terminal,
        {
            "schema_version",
            "state",
            "cell_index",
            "worker_pid",
            "exit_code",
            "ended_utc",
            "worker_admission_sha256",
        },
        "baseline terminal",
    )
    launch = _load_object(paths["launch"])
    launched_utc = _parse_utc_timestamp(
        launch["launched_utc"],
        "baseline launch launched_utc",
    )
    ended_utc = _parse_utc_timestamp(
        terminal["ended_utc"],
        "baseline terminal ended_utc",
    )
    worker_checked_utc = _parse_utc_timestamp(
        worker_admission["checked_utc"],
        "worker admission checked_utc",
    )
    if worker_checked_utc < launched_utc:
        raise RuntimeError("worker admission predates baseline launch")
    if ended_utc < worker_checked_utc:
        raise RuntimeError("baseline terminal predates worker admission")
    expected_terminal = {
        "schema_version": 1,
        "state": "completed",
        "cell_index": index,
        "worker_pid": launch["worker_pid"],
        "exit_code": 0,
    }
    for key, expected_value in expected_terminal.items():
        if terminal.get(key) != expected_value:
            raise RuntimeError(
                f"baseline terminal field {key} drift: "
                f"expected={expected_value!r} actual={terminal.get(key)!r}"
            )
    worker_admission_sha256 = sha256_file(
        paths["launch_dir"] / WORKER_ADMISSION_NAME
    )
    if terminal.get("worker_admission_sha256") != worker_admission_sha256:
        raise RuntimeError("terminal worker admission hash drift")
    return worker_admission


def initialize_baseline(suite_dir: Path, index: int) -> dict[str, Any]:
    """Create the immutable single-cell selection manifest in a fresh suite."""
    suite_dir = suite_dir.resolve()
    _reject_unexpected_evidence(suite_dir)
    validate_suite(suite_dir)
    for forbidden_name in (
        BASELINE_MANIFEST_NAME,
        BASELINE_RESULT_NAME,
        CONTROLLER_ADMISSION_NAME,
        *SUITE_CLOCK_FILE_NAMES,
    ):
        forbidden = suite_dir / forbidden_name
        if forbidden.exists() or forbidden.is_symlink():
            raise RuntimeError(
                f"single baseline suite has pre-existing evidence: {forbidden}"
            )
    started = {
        cell_index: [str(path) for path in _started_paths(suite_dir, cell_index)]
        for cell_index in range(len(configs))
        if _started_paths(suite_dir, cell_index)
    }
    if started:
        raise RuntimeError(f"single baseline suite is not fresh: {started}")

    suite_manifest_path = suite_dir / SUITE_MANIFEST_NAME
    payload = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        **_contract_fields(index, sha256_file(suite_manifest_path)),
    }
    manifest_path = suite_dir / BASELINE_MANIFEST_NAME
    with manifest_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, indent=2) + "\n")
    _reject_unexpected_evidence(suite_dir)
    return payload


def validate_baseline(
    suite_dir: Path,
    expected_index: int | None = None,
) -> dict[str, Any]:
    """Validate the immutable selection against source and official config."""
    suite_dir = suite_dir.resolve()
    _reject_unexpected_evidence(suite_dir)
    validate_suite(suite_dir)
    manifest_path = suite_dir / BASELINE_MANIFEST_NAME
    payload = _load_object(manifest_path)
    try:
        selected_index = int(payload["selected_index"])
        created_utc = datetime.fromisoformat(str(payload["created_utc"]))
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("single baseline manifest metadata is invalid") from error
    if created_utc.tzinfo is None:
        raise RuntimeError("single baseline manifest UTC timestamp lacks timezone")
    suite_manifest = _load_object(suite_dir / SUITE_MANIFEST_NAME)
    suite_created_utc = _parse_utc_timestamp(
        suite_manifest.get("created_utc"),
        "suite manifest created_utc",
    )
    baseline_created_utc = _parse_utc_timestamp(
        payload["created_utc"],
        "single baseline manifest created_utc",
    )
    if baseline_created_utc < suite_created_utc:
        raise RuntimeError("single baseline manifest predates suite initialization")
    if expected_index is not None and selected_index != expected_index:
        raise RuntimeError(
            "single baseline selected index mismatch: "
            f"expected={expected_index} actual={selected_index}"
        )
    expected = _contract_fields(
        selected_index,
        sha256_file(suite_dir / SUITE_MANIFEST_NAME),
    )
    actual = {key: payload.get(key) for key in expected}
    if actual != expected:
        raise RuntimeError(
            f"single baseline manifest contract drift: expected={expected} actual={actual}"
        )
    if set(payload) != {"created_utc", *expected}:
        raise RuntimeError(
            f"single baseline manifest has unexpected fields: {sorted(payload)}"
        )
    return payload


def prepare_baseline(suite_dir: Path, index: int) -> dict[str, Any]:
    """Require a fresh selected cell and a valid active launcher handshake."""
    suite_dir = suite_dir.resolve()
    manifest = validate_baseline(suite_dir, index)
    result_path = suite_dir / BASELINE_RESULT_NAME
    if result_path.exists() or result_path.is_symlink():
        raise RuntimeError("single baseline result exists before worker execution")
    suite_manifest = validate_suite(suite_dir)
    active_manifest = _active_cache_manifest()
    if sha256_file(active_manifest) != suite_manifest["cache_manifest_sha256"]:
        raise RuntimeError("active cache no longer matches the suite contract")

    for cell_index in range(len(configs)):
        started = _started_paths(suite_dir, cell_index)
        if cell_index == index:
            validate_active_launch(suite_dir, index)
            _validate_baseline_launch_mode(suite_dir, index)
            allowed = {_cell_paths(suite_dir, index)["launch_dir"]}
            unexpected = [path for path in started if path not in allowed]
            if unexpected:
                raise RuntimeError(
                    f"selected cell already has non-launch evidence: {unexpected}"
                )
        elif started:
            raise RuntimeError(
                f"non-selected cell {cell_index} has evidence: {started}"
            )
    return manifest


def _result_fields(suite_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    index = int(manifest["selected_index"])
    paths = _cell_paths(suite_dir, index)
    controller_admission = _validate_admission_record(
        suite_dir,
        "controller",
    )
    worker_admission = _validate_worker_admission(suite_dir, index)
    target, status_sha256 = _load_aistation_status(suite_dir)
    terminal = _load_object(paths["terminal"])
    _parse_utc_timestamp(
        terminal["ended_utc"],
        "baseline terminal ended_utc",
    )
    summary = _load_object(paths["summary"])
    final_metrics = summary.get("final_metrics")
    if not isinstance(final_metrics, dict):
        raise RuntimeError("single baseline summary lacks final_metrics")
    try:
        final_accuracy = float(final_metrics["valid/accuracy"])
        kv256_accuracy = float(
            final_metrics["valid/num_kv_pairs/accuracy-256"]
        )
        best_accuracy = float(summary["best_valid_accuracy"])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("single baseline summary metrics are incomplete") from error
    if not all(
        math.isfinite(value)
        for value in (final_accuracy, kv256_accuracy, best_accuracy)
    ):
        raise RuntimeError("single baseline summary contains nonfinite metrics")
    for name, value in (
        ("final valid/accuracy", final_accuracy),
        ("best valid/accuracy", best_accuracy),
        ("final KV256 accuracy", kv256_accuracy),
    ):
        if not 0.0 <= value <= 1.0:
            raise RuntimeError(
                f"single baseline {name} is outside [0, 1]: {value}"
            )
    metric_rows = _load_metric_rows(paths["metrics"])
    kv256_values = [
        float(row["valid/num_kv_pairs/accuracy-256"])
        for row in metric_rows
        if "valid/num_kv_pairs/accuracy-256" in row
    ]
    if not kv256_values:
        raise RuntimeError("single baseline metrics have no KV256 accuracy")
    if not math.isclose(
        kv256_accuracy,
        kv256_values[-1],
        rel_tol=0,
        abs_tol=1e-15,
    ):
        raise RuntimeError(
            "single baseline final KV256 accuracy disagrees with metrics"
        )

    visual_approx = float(manifest["official_accuracy_visual_approx"])
    strong_pass = final_accuracy >= float(manifest["strong_accuracy_floor"])
    visual_pass = final_accuracy >= float(manifest["visual_compatibility_floor"])
    kv256_pass = kv256_accuracy >= float(manifest["kv256_diagnostic_floor"])
    if strong_pass and kv256_pass:
        decision = "strong_baseline_pass"
    elif strong_pass:
        decision = "strong_baseline_pass_with_kv256_anomaly"
    elif visual_pass:
        decision = "visual_band_only"
    else:
        decision = "below_visual_band"
    return {
        "recorded_utc": terminal["ended_utc"],
        "schema_version": 1,
        "kind": manifest["kind"],
        "selected_index": index,
        "d_model": int(manifest["d_model"]),
        "learning_rate": float(manifest["learning_rate"]),
        "seed": int(manifest["seed"]),
        "metric": manifest["metric"],
        "final_valid_accuracy": final_accuracy,
        "best_valid_accuracy_diagnostic": best_accuracy,
        "final_kv256_accuracy_diagnostic": kv256_accuracy,
        "official_accuracy_exact": None,
        "official_accuracy_visual_approx": visual_approx,
        "delta_vs_visual_approx": final_accuracy - visual_approx,
        "visual_compatibility_floor": float(
            manifest["visual_compatibility_floor"]
        ),
        "strong_accuracy_floor": float(manifest["strong_accuracy_floor"]),
        "kv256_diagnostic_floor": float(manifest["kv256_diagnostic_floor"]),
        "visual_band_pass": visual_pass,
        "strong_baseline_pass": strong_pass,
        "kv256_diagnostic_pass": kv256_pass,
        "diagnostic_anomaly": not kv256_pass,
        "decision": decision,
        "full_frontier_claim_allowed": False,
        "aistation_target": "GPU2",
        "aistation_workspace_id": target["wpId"],
        "aistation_status_sha256": status_sha256,
        "clock_bracket_sha256": sha256_file(
            suite_dir / CLOCK_BRACKET_NAME
        ),
        "clock_capture_terminal_sha256": sha256_file(
            suite_dir / CLOCK_CAPTURE_TERMINAL_NAME
        ),
        "clock_evidence_sha256": _clock_evidence_hashes(suite_dir),
        "controller_adjusted_remaining_seconds": controller_admission[
            "adjusted_remaining_seconds"
        ],
        "worker_adjusted_remaining_seconds": worker_admission[
            "adjusted_remaining_seconds"
        ],
        "controller_admission_sha256": sha256_file(
            suite_dir / CONTROLLER_ADMISSION_NAME
        ),
        "worker_admission_sha256": sha256_file(
            paths["launch_dir"] / WORKER_ADMISSION_NAME
        ),
        "request_sha256": sha256_file(paths["request"]),
        "launch_sha256": sha256_file(paths["launch"]),
        "terminal_sha256": sha256_file(paths["terminal"]),
        "summary_sha256": sha256_file(paths["summary"]),
        "evidence_sha256": _result_evidence_hashes(suite_dir, paths),
        "baseline_manifest_sha256": sha256_file(
            suite_dir / BASELINE_MANIFEST_NAME
        ),
    }


def _result_evidence_hashes(
    suite_dir: Path,
    paths: dict[str, Path],
) -> dict[str, str]:
    evidence_paths = (
        suite_dir / "source.tar.gz",
        suite_dir / "source.tar.gz.sha256",
        suite_dir / "cache-manifest.json",
        suite_dir / "cache-manifest.json.sha256",
        suite_dir / "nvidia-smi.txt",
        suite_dir / "runtime-attestation.json",
        suite_dir / SUITE_MANIFEST_NAME,
        suite_dir / BASELINE_MANIFEST_NAME,
        *(suite_dir / name for name in SUITE_CLOCK_FILE_NAMES),
        suite_dir / CONTROLLER_ADMISSION_NAME,
        paths["metadata"],
        paths["log"],
        paths["runtime_attestation"],
        paths["summary"],
        paths["resolved_config"],
        paths["model_metadata"],
        paths["metrics"],
        paths["request"],
        paths["launch"],
        paths["worker_pid"],
        paths["launcher_log"],
        paths["terminal"],
        paths["launch_dir"] / WORKER_ADMISSION_NAME,
    )
    return {
        path.relative_to(suite_dir).as_posix(): sha256_file(path)
        for path in evidence_paths
    }


def finalize_baseline(suite_dir: Path) -> dict[str, Any]:
    """Validate terminal evidence and publish the immutable baseline result."""
    suite_dir = suite_dir.resolve()
    manifest = validate_baseline(suite_dir)
    index = int(manifest["selected_index"])
    validate_cell(suite_dir, index)
    _validate_baseline_launch_mode(suite_dir, index)
    for cell_index in range(len(configs)):
        if cell_index != index and _started_paths(suite_dir, cell_index):
            raise RuntimeError(f"non-selected cell {cell_index} has evidence")
    payload = {
        **_result_fields(suite_dir, manifest),
    }
    _publish_immutable_text(
        suite_dir / BASELINE_RESULT_NAME,
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
    )
    return payload


def validate_result(suite_dir: Path) -> dict[str, Any]:
    """Recompute all stable result fields from the archived cell evidence."""
    suite_dir = suite_dir.resolve()
    manifest = validate_baseline(suite_dir)
    validate_cell(suite_dir, int(manifest["selected_index"]))
    _validate_baseline_launch_mode(
        suite_dir,
        int(manifest["selected_index"]),
    )
    for cell_index in range(len(configs)):
        if (
            cell_index != int(manifest["selected_index"])
            and _started_paths(suite_dir, cell_index)
        ):
            raise RuntimeError(f"non-selected cell {cell_index} has evidence")
    result = _load_object(suite_dir / BASELINE_RESULT_NAME)
    expected = _result_fields(suite_dir, manifest)
    if result != expected:
        raise RuntimeError(
            f"single baseline result drift: expected={expected} actual={result}"
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    initialize_parser = subparsers.add_parser("initialize")
    initialize_parser.add_argument("--suite-dir", type=Path, required=True)

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--suite-dir", type=Path, required=True)
    prepare_parser.add_argument("--index", type=int, required=True)

    for name in ("admit-controller", "admit-worker"):
        admission_parser = subparsers.add_parser(name)
        admission_parser.add_argument("--suite-dir", type=Path, required=True)
        admission_parser.add_argument(
            "--remaining-seconds",
            type=int,
            required=True,
        )
        admission_parser.add_argument(
            "--observed-unix",
            type=int,
            required=True,
        )

    for name in ("selected-index", "finalize", "validate-result"):
        command_parser = subparsers.add_parser(name)
        command_parser.add_argument("--suite-dir", type=Path, required=True)

    args = parser.parse_args()
    args.suite_dir = require_suite_location(args.suite_dir)
    if args.command == "initialize":
        payload = initialize_baseline(
            args.suite_dir,
            DEFAULT_SELECTED_INDEX,
        )
    elif args.command == "prepare":
        payload = prepare_baseline(args.suite_dir, args.index)
    elif args.command == "admit-controller":
        payload = record_admission(
            args.suite_dir,
            "controller",
            args.remaining_seconds,
            args.observed_unix,
        )
    elif args.command == "admit-worker":
        payload = record_admission(
            args.suite_dir,
            "worker",
            args.remaining_seconds,
            args.observed_unix,
        )
    elif args.command == "selected-index":
        payload = validate_baseline(args.suite_dir)
        print(payload["selected_index"])
        return
    elif args.command == "finalize":
        payload = finalize_baseline(args.suite_dir)
    elif args.command == "validate-result":
        payload = validate_result(args.suite_dir)
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
