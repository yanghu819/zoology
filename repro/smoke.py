"""Compile both GDN sizes and execute a one-epoch end-to-end MQAR smoke."""

from __future__ import annotations

import os
from pathlib import Path

import torch

# Import pinned FLA directly so its real traceback is not hidden by Zoology's
# historical bare-except wrapper.
from fla.modules import FusedRMSNormSwishGate, RMSNorm, ShortConvolution  # noqa: F401
from fla.ops.gated_delta_rule import (  # noqa: F401
    chunk_gated_delta_rule,
    fused_recurrent_gated_delta_rule,
)
from zoology.mixers.gated_delta_net import GatedDeltaNet
import zoology.train as train_module

from repro.configs.gdn_mqar_official import configs
from repro.local_logger import LocalArtifactLogger


ROOT = Path(__file__).resolve().parents[1]


def kernel_smoke() -> None:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required")
    for d_model, seq_len in ((64, 64), (256, 256)):
        torch.manual_seed(123)
        model = GatedDeltaNet(
            d_model=d_model,
            num_heads=2,
            use_gate=False,
            use_short_conv=True,
            conv_size=4,
        ).cuda().train()
        inputs = torch.randn(
            2,
            seq_len,
            d_model,
            device="cuda",
            dtype=torch.float32,
            requires_grad=True,
        )
        outputs = model(inputs)
        if outputs.shape != inputs.shape or not torch.isfinite(outputs).all():
            raise RuntimeError(f"invalid GDN output for d_model={d_model}")
        outputs.square().mean().backward()
        if not all(
            parameter.grad is None or torch.isfinite(parameter.grad).all()
            for parameter in model.parameters()
        ):
            raise RuntimeError(f"invalid GDN gradient for d_model={d_model}")
    torch.cuda.synchronize()
    print(f"kernel_smoke_peak_bytes={torch.cuda.max_memory_allocated()}")


def end_to_end_smoke() -> None:
    config = configs[0].model_copy(deep=True)
    config.run_id = "gdn-mqar-end-to-end-smoke"
    config.max_epochs = 1
    config.early_stopping_metric = None
    config.data.cache_dir = str(ROOT / "data" / "smoke-cache")
    config.data.batch_size = (64, 32)
    config.data.train_configs = [config.data.train_configs[0].model_copy()]
    config.data.test_configs = [config.data.test_configs[0].model_copy()]
    config.data.train_configs[0].num_examples = 256
    config.data.test_configs[0].num_examples = 64

    smoke_root = Path(os.environ["ZOOLOGY_SMOKE_DIR"]).resolve()
    os.environ["ZOOLOGY_LOCAL_RUN_DIR"] = str(smoke_root / "end-to-end")
    os.environ["WANDB_RUN_ID"] = "zoology-gdn-smoke"
    train_module.WandbLogger = LocalArtifactLogger
    train_module.train(config)

    summary = smoke_root / "end-to-end" / "summary.json"
    if not summary.is_file():
        raise RuntimeError(f"end-to-end summary missing: {summary}")
    print(f"end_to_end_summary={summary}")


def main() -> None:
    kernel_smoke()
    end_to_end_smoke()
    print("gdn_mqar_smoke=pass")


if __name__ == "__main__":
    main()
