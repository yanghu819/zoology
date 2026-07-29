"""Create and validate the normalized synthetic-data cache manifest."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_FILE_COUNT = 12
EXPECTED_GENERATION_SEED = 123
OFFICIAL_CONFIG_SHA256 = (
    "dc29c0d5c908c60768f905afb3a683c6b14ad4774810d807fc1abcdbc767e672"
)
_FULL_GIT_OBJECT = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True)
class CacheProvenance:
    """Expected immutable provenance for one normalized cache."""

    cache_dir: Path
    filenames: tuple[str, ...]
    generation_seed: int
    torch_version: str


def _lexical_absolute(path: Path) -> Path:
    """Normalize ``.``/``..`` without following symbolic links."""
    return Path(os.path.abspath(os.fspath(path)))


def _require_real_directory(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise RuntimeError(f"cache directory is missing {path}: {error}") from error
    if not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError(f"cache path is not a real directory: {path}")


def _require_regular_file(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise RuntimeError(f"cache file is missing {path}: {error}") from error
    if not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError(f"cache path is not a regular file: {path}")


def _frozen_cache_path(root: Path) -> Path:
    return _lexical_absolute(root / "data" / "mqar-cache")


def ensure_frozen_cache_directory(root: Path = ROOT) -> Path:
    """Create the frozen cache without following project-local directory links."""
    root = _lexical_absolute(root)
    expected = _frozen_cache_path(root)
    _require_real_directory(root)
    for directory in (root / "data",):
        if directory.exists() or directory.is_symlink():
            _require_real_directory(directory)
        else:
            directory.mkdir()
            _require_real_directory(directory)
    if expected.exists() or expected.is_symlink():
        _require_real_directory(expected)
    else:
        expected.mkdir()
        _require_real_directory(expected)
    return expected


def segment_generation_seeds(data_config: Any) -> tuple[int, ...]:
    """Reproduce Zoology's legacy NumPy seed stream without changing global RNG."""
    random_state = np.random.RandomState(int(data_config.seed))
    train_seeds = random_state.randint(
        0,
        2**31,
        size=len(data_config.train_configs),
    )
    test_seeds = random_state.randint(
        2**31,
        2**32,
        size=len(data_config.test_configs),
    )
    return tuple(int(seed) for seed in (*train_seeds, *test_seeds))


def expected_cache_filenames(data_config: Any) -> tuple[str, ...]:
    """Derive exact cache names using the historical DataSegment cache key."""
    segments = (*data_config.train_configs, *data_config.test_configs)
    seeds = segment_generation_seeds(data_config)
    if len(segments) != len(seeds):
        raise RuntimeError("frozen data segments and derived seeds disagree")
    names = []
    for segment, seed in zip(segments, seeds):
        cache_key = json.dumps(
            {**segment.model_dump(), "_seed": seed},
            sort_keys=True,
        ).encode()
        names.append(f"data_{hashlib.md5(cache_key).hexdigest()}.pt")
    if len(names) != EXPECTED_FILE_COUNT or len(set(names)) != len(names):
        raise RuntimeError(
            "frozen data segments do not derive exactly "
            f"{EXPECTED_FILE_COUNT} unique cache files"
        )
    return tuple(sorted(names))


def frozen_cache_provenance(root: Path = ROOT) -> CacheProvenance:
    """Load the active frozen cache path and dependency version contract."""
    from repro.configs.gdn_mqar_official import configs

    expected_cache_dir = _frozen_cache_path(root)
    cache_dirs = {
        _lexical_absolute(Path(config.data.cache_dir)) for config in configs
    }
    if cache_dirs != {expected_cache_dir}:
        raise RuntimeError(
            "official cells must use the exact project-local frozen cache path: "
            f"expected={expected_cache_dir} actual={cache_dirs}"
        )
    data_configs = {config.data.model_dump_json() for config in configs}
    if len(data_configs) != 1:
        raise RuntimeError("official cells disagree on their frozen data config")

    runtime_lock_path = root / "repro" / "runtime_lock.json"
    try:
        runtime_lock = json.loads(runtime_lock_path.read_text(encoding="utf-8"))
        torch_version = runtime_lock["torch"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise RuntimeError(
            f"cannot load torch version from {runtime_lock_path}: {error}"
        ) from error
    if not isinstance(torch_version, str) or not torch_version:
        raise RuntimeError("runtime lock contains an invalid torch version")

    data_config = configs[0].data
    return CacheProvenance(
        cache_dir=expected_cache_dir,
        filenames=expected_cache_filenames(data_config),
        generation_seed=EXPECTED_GENERATION_SEED,
        torch_version=torch_version,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cache_files(cache_dir: Path) -> list[Path]:
    return sorted(cache_dir.glob("data_*.pt"))


def _git_output(repo_root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo_root), *args],
            text=True,
            stderr=subprocess.PIPE,
        ).strip()
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() if error.stderr else str(error)
        raise RuntimeError(f"git provenance check failed: {detail}") from error


def _validate_git_provenance(
    manifest: dict[str, Any],
    repo_root: Path,
    current_revision: str,
) -> None:
    git_sha = manifest.get("git_sha")
    git_tree = manifest.get("git_tree")
    if not isinstance(git_sha, str) or _FULL_GIT_OBJECT.fullmatch(git_sha) is None:
        raise RuntimeError("cache manifest contains an invalid full git_sha")
    if not isinstance(git_tree, str) or _FULL_GIT_OBJECT.fullmatch(git_tree) is None:
        raise RuntimeError("cache manifest contains an invalid full git_tree")

    resolved_sha = _git_output(
        repo_root,
        "rev-parse",
        "--verify",
        f"{git_sha}^{{commit}}",
    )
    if resolved_sha != git_sha:
        raise RuntimeError("cache generation git_sha did not resolve exactly")
    resolved_tree = _git_output(
        repo_root,
        "rev-parse",
        "--verify",
        f"{git_tree}^{{tree}}",
    )
    if resolved_tree != git_tree:
        raise RuntimeError("cache generation git_tree did not resolve exactly")
    commit_tree = _git_output(repo_root, "rev-parse", f"{git_sha}^{{tree}}")
    if commit_tree != git_tree:
        raise RuntimeError("cache generation git_tree does not match git_sha")

    try:
        subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "merge-base",
                "--is-ancestor",
                git_sha,
                current_revision,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() if error.stderr else ""
        raise RuntimeError(
            "cache generation git_sha is not an ancestor of "
            f"{current_revision}{f': {detail}' if detail else ''}"
        ) from error


def validate_manifest(
    cache_dir: Path,
    *,
    provenance: CacheProvenance | None = None,
    repo_root: Path = ROOT,
    current_revision: str = "HEAD",
) -> dict[str, Any]:
    cache_dir = _lexical_absolute(cache_dir)
    provenance = provenance or frozen_cache_provenance(repo_root)
    expected_cache_dir = _lexical_absolute(provenance.cache_dir)
    if cache_dir != expected_cache_dir:
        raise RuntimeError(
            "cache directory is not the active frozen cache path: "
            f"expected={expected_cache_dir} actual={cache_dir}"
        )
    _require_real_directory(cache_dir)
    frozen_project_cache = _frozen_cache_path(repo_root)
    if expected_cache_dir == frozen_project_cache:
        _require_real_directory(_lexical_absolute(repo_root))
        _require_real_directory(_lexical_absolute(repo_root) / "data")

    manifest_path = cache_dir / "manifest.json"
    _require_regular_file(manifest_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"cannot read valid cache manifest: {error}") from error
    if not isinstance(manifest, dict):
        raise RuntimeError("cache manifest must be a JSON object")
    if manifest.get("schema_version") != 1:
        raise RuntimeError("unsupported cache-manifest schema")
    if manifest.get("origin") != "generated_by_frozen_prewarm":
        raise RuntimeError(f"untrusted cache origin: {manifest.get('origin')}")
    if manifest.get("official_config_sha256") != OFFICIAL_CONFIG_SHA256:
        raise RuntimeError("cache manifest is bound to a different config")
    if manifest.get("generation_seed") != provenance.generation_seed:
        raise RuntimeError(
            "cache generation seed mismatch: "
            f"expected={provenance.generation_seed} "
            f"actual={manifest.get('generation_seed')!r}"
        )
    if provenance.generation_seed != EXPECTED_GENERATION_SEED:
        raise RuntimeError(
            "provenance contract does not use the frozen generation seed "
            f"{EXPECTED_GENERATION_SEED}"
        )
    if manifest.get("cache_dir") != str(expected_cache_dir):
        raise RuntimeError(
            "cache manifest path mismatch: "
            f"expected={expected_cache_dir} actual={manifest.get('cache_dir')!r}"
        )
    if manifest.get("torch_version") != provenance.torch_version:
        raise RuntimeError(
            "cache torch version mismatch: "
            f"expected={provenance.torch_version} "
            f"actual={manifest.get('torch_version')!r}"
        )
    _validate_git_provenance(manifest, repo_root.resolve(), current_revision)

    entries = manifest.get("files")
    if not isinstance(entries, list) or len(entries) != EXPECTED_FILE_COUNT:
        raise RuntimeError(
            f"expected {EXPECTED_FILE_COUNT} cache entries, found "
            f"{len(entries) if isinstance(entries, list) else 'invalid'}"
        )
    if not all(isinstance(entry, dict) for entry in entries):
        raise RuntimeError("cache manifest file entries must be JSON objects")
    names = [entry.get("name") for entry in entries]
    if not all(isinstance(name, str) for name in names):
        raise RuntimeError("cache manifest contains an invalid filename")
    if len(set(names)) != EXPECTED_FILE_COUNT:
        raise RuntimeError("cache manifest contains duplicate filenames")
    expected_names = sorted(provenance.filenames)
    if len(expected_names) != EXPECTED_FILE_COUNT or len(set(expected_names)) != len(
        expected_names
    ):
        raise RuntimeError("provenance contract does not name 12 unique cache files")
    if sorted(names) != expected_names:
        raise RuntimeError(
            "cache manifest filenames do not match frozen segments/seeds"
        )
    actual_files = cache_files(cache_dir)
    if [path.name for path in actual_files] != expected_names:
        raise RuntimeError("cache files do not match the frozen manifest")

    entries_by_name = {entry["name"]: entry for entry in entries}
    for path in actual_files:
        _require_regular_file(path)
        entry = entries_by_name[path.name]
        try:
            expected_bytes = int(entry["bytes"])
            expected_sha256 = entry["sha256"]
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError(f"invalid cache entry for {path.name}") from error
        if (
            not isinstance(expected_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
        ):
            raise RuntimeError(f"invalid cache SHA-256 for {path.name}")
        if expected_bytes < 0 or path.stat().st_size != expected_bytes:
            raise RuntimeError(f"cache size drift: {path}")
        if sha256_file(path) != expected_sha256:
            raise RuntimeError(f"cache hash drift: {path}")
    return manifest
