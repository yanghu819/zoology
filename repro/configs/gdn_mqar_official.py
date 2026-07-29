"""Load the historical committed GDN sweep and change metadata paths only."""

from __future__ import annotations

import importlib.util
import math
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HISTORICAL_CONFIG = (
    ROOT / "zoology" / "experiments" / "030325_new_arch" / "configs.py"
)
EXPECTED_D_MODELS = (64, 128, 256)
EXPECTED_LEARNING_RATES = (
    1e-3,
    10 ** -2.5,
    1e-2,
    10 ** -1.5,
)


def _load_historical_module():
    spec = importlib.util.spec_from_file_location(
        "zoology_historical_gdn_config",
        HISTORICAL_CONFIG,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load historical config: {HISTORICAL_CONFIG}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _assert_scientific_contract(configs) -> None:
    if len(configs) != 12:
        raise AssertionError(f"expected 12 official configs, found {len(configs)}")

    actual = {
        (int(config.model.d_model), float(config.learning_rate))
        for config in configs
    }
    expected = {
        (d_model, learning_rate)
        for d_model in EXPECTED_D_MODELS
        for learning_rate in EXPECTED_LEARNING_RATES
    }
    if len(actual) != len(expected):
        raise AssertionError(f"duplicate or missing official cells: {actual}")
    for d_model, learning_rate in expected:
        if not any(
            actual_d == d_model
            and math.isclose(actual_lr, learning_rate, rel_tol=0, abs_tol=1e-15)
            for actual_d, actual_lr in actual
        ):
            raise AssertionError(f"missing official cell d={d_model}, lr={learning_rate}")

    first = configs[0]
    train_shape = [
        (c.input_seq_len, c.num_kv_pairs, c.num_examples)
        for c in first.data.train_configs
    ]
    test_shape = [
        (c.input_seq_len, c.num_kv_pairs, c.num_examples)
        for c in first.data.test_configs
    ]
    if train_shape != [
        (64, 4, 100_000),
        (128, 8, 20_000),
        (256, 16, 20_000),
        (256, 32, 20_000),
        (256, 64, 20_000),
    ]:
        raise AssertionError(f"historical train data drifted: {train_shape}")
    if test_shape != [
        (64, 4, 1_000),
        (64, 8, 1_000),
        (64, 16, 1_000),
        (128, 32, 1_000),
        (256, 64, 1_000),
        (512, 128, 1_000),
        (1024, 256, 1_000),
    ]:
        raise AssertionError(f"historical test data drifted: {test_shape}")

    for config in configs:
        mixer_configs = config.model.sequence_mixer.kwargs["configs"]
        gdn = mixer_configs[1]
        if config.model.name != "gated_delta_net":
            raise AssertionError(config.model.name)
        if config.model.n_layers != 2 or config.model.state_mixer.name != "torch.nn.Identity":
            raise AssertionError("historical two-layer/Identity contract drifted")
        if gdn["name"] != "zoology.mixers.gated_delta_net.GatedDeltaNet":
            raise AssertionError(gdn)
        if gdn["kwargs"] != {
            "l_max": 1024,
            "num_heads": 2,
            "use_gate": False,
            "use_short_conv": True,
            "conv_size": 4,
        }:
            raise AssertionError(gdn["kwargs"])
        if config.seed != 123 or config.data.seed != 123:
            raise AssertionError("historical seed drifted")
        if config.max_epochs != 32 or config.weight_decay != 0.1:
            raise AssertionError("historical optimizer budget drifted")
        if config.data.batch_size != (256, 32):
            raise AssertionError(config.data.batch_size)
        if config.early_stopping_metric != "valid/accuracy":
            raise AssertionError(config.early_stopping_metric)
        if config.early_stopping_threshold != 0.99:
            raise AssertionError(config.early_stopping_threshold)


def build_configs():
    """Return the 12 official configs with only local metadata paths redirected."""
    module = _load_historical_module()
    configs = list(module.configs)
    _assert_scientific_contract(configs)

    cache_dir = Path(
        os.environ.get("ZOOLOGY_DATA_CACHE", ROOT / "data" / "mqar-cache")
    ).resolve()
    for config in configs:
        config.data.cache_dir = str(cache_dir)
        # Run names are metadata only. The official file reused names across widths.
        config.run_id = (
            f"gdn-d{config.model.d_model}-lr{float(config.learning_rate):.10g}"
        )
        config.sweep_id = "zoology-gdn-official-b386338"
    return configs


configs = build_configs()
