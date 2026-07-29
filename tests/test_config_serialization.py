import json

from repro.config_serialization import dump_full_config
from repro.configs.gdn_mqar_official import configs


def test_dump_full_config_preserves_concrete_data_segment_fields():
    config = configs[0]
    payload = dump_full_config(config)
    archived_segment = payload["data"]["train_configs"][0]
    concrete_segment = config.data.train_configs[0]

    assert archived_segment == dump_full_config(concrete_segment)
    assert archived_segment["name"] == "multiquery_ar"
    assert archived_segment["num_kv_pairs"] == 4
    assert archived_segment["power_a"] == 0.01
    assert archived_segment["random_non_queries"] is True
    assert archived_segment["include_slices"] is True
    assert [
        segment["num_kv_pairs"]
        for segment in payload["data"]["train_configs"]
    ] == [4, 8, 16, 32, 64]
    assert [
        segment["num_kv_pairs"]
        for segment in payload["data"]["test_configs"]
    ] == [4, 8, 16, 32, 64, 128, 256]
    json.dumps(payload, allow_nan=False)


def test_dump_full_config_exposes_the_fields_default_dump_truncates():
    config = configs[0]

    default_segment = config.model_dump(mode="json")["data"]["train_configs"][0]
    full_segment = dump_full_config(config)["data"]["train_configs"][0]

    assert "num_kv_pairs" not in default_segment
    assert full_segment["num_kv_pairs"] == config.data.train_configs[0].num_kv_pairs
