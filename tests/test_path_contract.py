import subprocess
from pathlib import Path

import pytest

from repro.path_contract import (
    ensure_runtime_paths,
    reject_importable_source_shadows,
)


@pytest.mark.parametrize("relative", (".cache", "runs"))
def test_runtime_roots_reject_directory_symlinks(
    tmp_path: Path,
    relative: str,
):
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / f"outside-{relative.removeprefix('.')}"
    outside.mkdir()
    (root / relative).symlink_to(outside, target_is_directory=True)

    with pytest.raises(RuntimeError, match="not a real directory"):
        ensure_runtime_paths(root)


def test_runtime_roots_are_created_inside_project(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()

    ensure_runtime_paths(root)

    for relative in (
        ".cache",
        "artifacts",
        "checkpoints",
        "data",
        "models",
        "runs",
        "wheels",
    ):
        path = root / relative
        assert path.is_dir()
        assert not path.is_symlink()


def test_runtime_environment_symlink_is_rejected(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside-venv"
    outside.mkdir()
    (root / ".venv").symlink_to(outside, target_is_directory=True)

    with pytest.raises(RuntimeError, match="not a real directory"):
        ensure_runtime_paths(root)


def _make_source_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "repro").mkdir(parents=True)
    (root / "zoology").mkdir()
    (root / "vendor" / "flash-linear-attention").mkdir(parents=True)
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    for relative in (
        "repro/tracked.py",
        "zoology/tracked.py",
        "vendor/flash-linear-attention/tracked.py",
    ):
        (root / relative).write_text("VALUE = 1\n", encoding="utf-8")
    (root / ".gitignore").write_text(
        "*.so\n*.py[cod]\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    return root


@pytest.mark.parametrize(
    "relative",
    (
        "sitecustomize.pyc",
        "other-package/shadow.so",
        "repro/shadow.pyc",
        "vendor/flash-linear-attention/shadow.so",
    ),
)
def test_source_guard_rejects_ignored_importable_shadows(
    tmp_path: Path,
    relative: str,
):
    root = _make_source_repo(tmp_path)
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"ignored import shadow")

    with pytest.raises(RuntimeError, match="ignored importable shadow"):
        reject_importable_source_shadows(root)


def test_source_guard_allows_standard_untracked_pycache(tmp_path: Path):
    root = _make_source_repo(tmp_path)
    bytecode = root / "repro" / "__pycache__" / "tracked.cpython-310.pyc"
    bytecode.parent.mkdir()
    bytecode.write_bytes(b"standard cache")

    reject_importable_source_shadows(root)
