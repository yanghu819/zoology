"""Fail closed before runtime state can escape the project directory."""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
from pathlib import Path


RUNTIME_DIRECTORIES = (
    ".cache",
    ".cache/cuda",
    ".cache/huggingface",
    ".cache/pip",
    ".cache/pycache",
    ".cache/tmp",
    ".cache/torch",
    ".cache/torch-extensions",
    ".cache/triton",
    ".cache/uv",
    ".cache/wandb",
    ".cache/wandb-config",
    ".cache/wandb-data",
    ".cache/xdg",
    ".cache/xdg-config",
    ".cache/xdg-data",
    "artifacts",
    "artifacts/wandb",
    "checkpoints",
    "data",
    "models",
    "predictions",
    "runs",
    "wandb",
    "wheels",
)
ENVIRONMENT_DIRECTORIES = (".cache/uv-bootstrap", ".venv")
RUNTIME_FILES = (
    "wheels/causal_conv1d-1.5.3.post1+cu12torch2.7cxx11abiTRUE-cp310-cp310-linux_x86_64.whl",
    "wheels/causal_conv1d-1.5.3.post1+cu12torch2.7cxx11abiTRUE-cp310-cp310-linux_x86_64.whl.partial",
)
IMPORT_SOURCE_DIRECTORIES = (
    "repro",
    "zoology",
    "vendor/flash-linear-attention",
)
IGNORED_IMPORT_SUFFIXES = frozenset({".pyc", ".pyo", ".so"})
NON_SOURCE_TOP_LEVELS = frozenset(
    {
        ".cache",
        ".git",
        ".venv",
        "artifacts",
        "checkpoints",
        "data",
        "models",
        "predictions",
        "runs",
        "wandb",
        "wheels",
    }
)


def _lexical_absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _require_real_directory(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise RuntimeError(f"runtime directory is missing {path}: {error}") from error
    if not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError(f"runtime path is not a real directory: {path}")


def _ensure_directory(path: Path) -> None:
    if path.exists() or path.is_symlink():
        _require_real_directory(path)
        return
    path.mkdir()
    _require_real_directory(path)


def _require_regular_if_present(path: Path) -> None:
    if not (path.exists() or path.is_symlink()):
        return
    try:
        metadata = path.lstat()
    except OSError as error:
        raise RuntimeError(f"cannot stat runtime file {path}: {error}") from error
    if not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError(f"runtime path is not a regular file: {path}")


def _git_paths(root: Path, *args: str) -> set[Path]:
    try:
        output = subprocess.check_output(
            ["git", "-C", str(root), *args],
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as error:
        detail = error.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"cannot inspect Git source paths: {detail}") from error
    return {
        Path(raw.decode())
        for raw in output.split(b"\0")
        if raw
    }


def reject_importable_source_shadows(root: Path) -> None:
    """Reject untracked code that Git cleanliness or the vendor hash can miss."""
    root = _lexical_absolute(root)
    untracked = _git_paths(
        root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
    )
    if untracked:
        raise RuntimeError(
            "source checkout contains untracked paths: "
            f"{sorted(path.as_posix() for path in untracked)}"
        )

    ignored = _git_paths(
        root,
        "ls-files",
        "--others",
        "--ignored",
        "--exclude-standard",
        "-z",
        "--",
        *IMPORT_SOURCE_DIRECTORIES,
    )
    dangerous = []
    for relative in ignored:
        if relative.suffix not in IGNORED_IMPORT_SUFFIXES:
            continue
        if (
            relative.suffix in {".pyc", ".pyo"}
            and "__pycache__" in relative.parts
        ):
            continue
        dangerous.append(relative.as_posix())

    for directory, child_directories, filenames in os.walk(
        root,
        topdown=True,
        followlinks=False,
    ):
        directory_path = Path(directory)
        if directory_path == root:
            child_directories[:] = [
                name
                for name in child_directories
                if name not in NON_SOURCE_TOP_LEVELS
            ]
        for filename in filenames:
            path = directory_path / filename
            if path.suffix not in IGNORED_IMPORT_SUFFIXES:
                continue
            relative = path.relative_to(root)
            if (
                path.suffix in {".pyc", ".pyo"}
                and "__pycache__" in relative.parts
            ):
                continue
            dangerous.append(relative.as_posix())
    if dangerous:
        raise RuntimeError(
            "source checkout contains ignored importable shadow artifacts: "
            f"{sorted(set(dangerous))}"
        )


def ensure_runtime_paths(
    root: Path,
    *,
    require_environments: bool = False,
) -> Path:
    """Validate physical containment and create the standard runtime roots."""
    root = _lexical_absolute(root)
    _require_real_directory(root)
    if Path(os.path.realpath(root)) != root:
        raise RuntimeError(f"project root cannot contain symbolic links: {root}")

    for relative in RUNTIME_DIRECTORIES:
        current = root
        for component in Path(relative).parts:
            current /= component
            _ensure_directory(current)

    for relative in ENVIRONMENT_DIRECTORIES:
        path = root / relative
        if path.exists() or path.is_symlink():
            _require_real_directory(path)
        elif require_environments:
            raise RuntimeError(f"required project-local environment is missing: {path}")

    for relative in RUNTIME_FILES:
        _require_regular_if_present(root / relative)
    for wheel in (root / "wheels").glob("*.whl"):
        _require_regular_if_present(wheel)
    return root


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--require-environments", action="store_true")
    parser.add_argument("--validate-source", action="store_true")
    args = parser.parse_args()
    root = ensure_runtime_paths(
        args.root,
        require_environments=args.require_environments,
    )
    if args.validate_source:
        reject_importable_source_shadows(root)
    print(root)


if __name__ == "__main__":
    main()
