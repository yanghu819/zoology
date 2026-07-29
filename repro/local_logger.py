"""Tee the historical W&B logger into deterministic local JSON artifacts."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch

from zoology.logger import WandbLogger

from repro.config_serialization import dump_full_config
from repro.numeric_contract import require_finite


def _jsonable(value: Any):
    if isinstance(value, torch.Tensor):
        if value.numel() != 1:
            raise ValueError("only scalar tensors may be logged")
        return value.detach().cpu().item()
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


class LocalArtifactLogger(WandbLogger):
    """Preserve official offline W&B logging and add plain-text audit artifacts."""

    def __init__(self, config):
        run_dir = os.environ.get("ZOOLOGY_LOCAL_RUN_DIR")
        if not run_dir:
            raise RuntimeError("ZOOLOGY_LOCAL_RUN_DIR must be bound before training")
        self.local_run_dir = Path(run_dir).resolve()
        self.local_run_dir.mkdir(parents=True, exist_ok=False)
        self.metrics_path = self.local_run_dir / "metrics.jsonl"
        self.latest_metrics: dict[str, Any] = {}
        self.best_valid_accuracy = None
        self.started_monotonic = time.monotonic()
        self.started_utc = datetime.now(timezone.utc).isoformat()
        super().__init__(config)

    def log_config(self, config):
        super().log_config(config)
        _atomic_json(
            self.local_run_dir / "resolved-config.json",
            dump_full_config(config),
        )

    def log_model(self, model, config):
        super().log_model(model, config)
        max_seq_len = max(c.input_seq_len for c in config.data.test_configs)
        _atomic_json(
            self.local_run_dir / "model-metadata.json",
            {
                "num_parameters": sum(
                    parameter.numel()
                    for parameter in model.parameters()
                    if parameter.requires_grad
                ),
                "state_size": model.state_size(sequence_length=max_seq_len),
            },
        )

    def log(self, metrics: dict):
        payload = {
            "logged_utc": datetime.now(timezone.utc).isoformat(),
            **_jsonable(metrics),
        }
        require_finite(payload)
        super().log(metrics)
        with self.metrics_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
        self.latest_metrics.update(payload)
        if "valid/accuracy" in payload:
            accuracy = float(payload["valid/accuracy"])
            if self.best_valid_accuracy is None or accuracy > self.best_valid_accuracy:
                self.best_valid_accuracy = accuracy

    def finish(self):
        super().finish()
        _atomic_json(
            self.local_run_dir / "summary.json",
            {
                "status": "completed",
                "started_utc": self.started_utc,
                "ended_utc": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": time.monotonic() - self.started_monotonic,
                "final_metrics": self.latest_metrics,
                "best_valid_accuracy": self.best_valid_accuracy,
            },
        )
