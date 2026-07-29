from pathlib import Path

import pytest

from repro.aggregate import _publish_immutable_text


def test_aggregate_publication_is_idempotent(tmp_path: Path):
    output = tmp_path / "aggregate.json"

    _publish_immutable_text(output, '{"score": 1}\n')
    _publish_immutable_text(output, '{"score": 1}\n')

    assert output.read_text(encoding="utf-8") == '{"score": 1}\n'
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        _publish_immutable_text(output, '{"score": 2}\n')


def test_aggregate_publication_rejects_symlink(tmp_path: Path):
    outside = tmp_path / "outside.json"
    outside.write_text("keep\n", encoding="utf-8")
    output = tmp_path / "aggregate.json"
    output.symlink_to(outside)

    with pytest.raises(RuntimeError, match="cannot safely read"):
        _publish_immutable_text(output, '{"score": 1}\n')
    assert outside.read_text(encoding="utf-8") == "keep\n"
