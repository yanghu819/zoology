import subprocess
from pathlib import Path

from repro.validate_contract import _tracked_content_tree_sha256


def test_vendor_digest_ignores_untracked_bytecode(tmp_path: Path):
    repo = tmp_path / "repo"
    vendor = repo / "vendor" / "flash-linear-attention"
    vendor.mkdir(parents=True)
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    tracked = vendor / "kernel.py"
    tracked.write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "add", "vendor/flash-linear-attention/kernel.py"],
        check=True,
    )
    baseline = _tracked_content_tree_sha256(repo, vendor)

    bytecode = vendor / "__pycache__" / "kernel.cpython-310.pyc"
    bytecode.parent.mkdir()
    bytecode.write_bytes(b"untracked bytecode")
    assert _tracked_content_tree_sha256(repo, vendor) == baseline

    tracked.write_text("VALUE = 2\n", encoding="utf-8")
    assert _tracked_content_tree_sha256(repo, vendor) != baseline
