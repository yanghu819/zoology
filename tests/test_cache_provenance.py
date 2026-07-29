import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from repro.cache_contract import (
    OFFICIAL_CONFIG_SHA256,
    CacheProvenance,
    expected_cache_filenames,
    frozen_cache_provenance,
    segment_generation_seeds,
    sha256_file,
    validate_manifest,
)
from repro.configs.gdn_mqar_official import configs


EXPECTED_SEEDS = (
    843_828_734,
    914_636_141,
    1_228_959_102,
    1_840_268_610,
    974_319_580,
    2_967_327_842,
    2_367_878_886,
    3_088_727_057,
    3_090_095_699,
    4_256_823_402,
    3_964_712_059,
    3_350_193_721,
)
EXPECTED_FILENAMES = (
    "data_0192c761df278911bb68046d8d1bd4bb.pt",
    "data_25f7a1e8f8e6d2ba1fdbfa481d66614a.pt",
    "data_2e72f812c43c426a106c777f791c5e7d.pt",
    "data_3a37505bc239830ae7a7070040e09f6a.pt",
    "data_5b0265b0978cc6b711cd76fcf34e8969.pt",
    "data_5e0c59f2a5df62cc996f523c97b0d10a.pt",
    "data_887e0e2a2ad624d1605904cb817a6ec8.pt",
    "data_8ef4855e77aa9e88588d018d5b0461f7.pt",
    "data_9892a64887c1ed56c1c7421f492d76ed.pt",
    "data_b53959d96a217faa44c26a74b7d53685.pt",
    "data_cc63c1430c7324d99a84abe992a11f41.pt",
    "data_d3faf35348337347822d1f5a2bc43c96.pt",
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args],
        text=True,
    ).strip()


def _commit(repo: Path, content: str) -> tuple[str, str]:
    (repo / "tracked.txt").write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", content],
        check=True,
    )
    return _git(repo, "rev-parse", "HEAD"), _git(repo, "rev-parse", "HEAD^{tree}")


@pytest.fixture
def git_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Cache Test"],
        check=True,
    )
    _commit(repo, "base")
    generation_sha, generation_tree = _commit(repo, "generation")
    _commit(repo, "current")
    return repo, generation_sha, generation_tree


def _write_cache(
    repo: Path,
    generation_sha: str,
    generation_tree: str,
) -> tuple[Path, CacheProvenance, dict]:
    cache_dir = repo / "cache"
    cache_dir.mkdir()
    provenance = CacheProvenance(
        cache_dir=cache_dir.resolve(),
        filenames=EXPECTED_FILENAMES,
        generation_seed=123,
        torch_version="2.7.0+cu126",
    )
    entries = []
    for index, name in enumerate(provenance.filenames):
        path = cache_dir / name
        path.write_bytes(f"frozen-{index}".encode())
        entries.append(
            {
                "name": name,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    manifest = {
        "schema_version": 1,
        "origin": "generated_by_frozen_prewarm",
        "cache_dir": str(cache_dir.resolve()),
        "official_config_sha256": OFFICIAL_CONFIG_SHA256,
        "generation_seed": 123,
        "torch_version": provenance.torch_version,
        "git_sha": generation_sha,
        "git_tree": generation_tree,
        "files": entries,
    }
    (cache_dir / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    return cache_dir, provenance, manifest


def _rewrite_manifest(cache_dir: Path, manifest: dict) -> None:
    (cache_dir / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )


def test_frozen_segments_derive_exact_seeds_and_filenames():
    data_config = configs[0].data
    assert segment_generation_seeds(data_config) == EXPECTED_SEEDS
    assert expected_cache_filenames(data_config) == EXPECTED_FILENAMES

    provenance = frozen_cache_provenance()
    assert provenance.filenames == EXPECTED_FILENAMES
    assert provenance.generation_seed == 123
    assert provenance.torch_version == "2.7.0+cu126"


def test_strict_manifest_accepts_ancestor_generation(
    git_repo: tuple[Path, str, str],
):
    repo, generation_sha, generation_tree = git_repo
    cache_dir, provenance, manifest = _write_cache(
        repo,
        generation_sha,
        generation_tree,
    )

    assert (
        validate_manifest(
            cache_dir,
            provenance=provenance,
            repo_root=repo,
        )
        == manifest
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("generation_seed", 124, "generation seed mismatch"),
        ("cache_dir", "/wrong/cache", "manifest path mismatch"),
        ("torch_version", "2.7.1", "torch version mismatch"),
        ("git_sha", "not-a-sha", "invalid full git_sha"),
        ("git_tree", "not-a-tree", "invalid full git_tree"),
    ],
)
def test_strict_manifest_rejects_provenance_drift(
    git_repo: tuple[Path, str, str],
    field: str,
    value,
    message: str,
):
    repo, generation_sha, generation_tree = git_repo
    cache_dir, provenance, manifest = _write_cache(
        repo,
        generation_sha,
        generation_tree,
    )
    manifest[field] = value
    _rewrite_manifest(cache_dir, manifest)

    with pytest.raises(RuntimeError, match=message):
        validate_manifest(
            cache_dir,
            provenance=provenance,
            repo_root=repo,
        )


def test_strict_manifest_rejects_non_active_cache_path(
    git_repo: tuple[Path, str, str],
):
    repo, generation_sha, generation_tree = git_repo
    cache_dir, provenance, _ = _write_cache(
        repo,
        generation_sha,
        generation_tree,
    )

    with pytest.raises(RuntimeError, match="not the active frozen cache path"):
        validate_manifest(
            cache_dir,
            provenance=replace(provenance, cache_dir=repo / "other-cache"),
            repo_root=repo,
        )


def test_strict_manifest_rejects_tree_not_owned_by_generation_commit(
    git_repo: tuple[Path, str, str],
):
    repo, generation_sha, generation_tree = git_repo
    cache_dir, provenance, manifest = _write_cache(
        repo,
        generation_sha,
        generation_tree,
    )
    assert generation_tree != _git(repo, "rev-parse", "HEAD^{tree}")
    manifest["git_tree"] = _git(repo, "rev-parse", "HEAD^{tree}")
    _rewrite_manifest(cache_dir, manifest)

    with pytest.raises(RuntimeError, match="does not match git_sha"):
        validate_manifest(
            cache_dir,
            provenance=provenance,
            repo_root=repo,
        )


def test_strict_manifest_rejects_nonancestor_generation(
    git_repo: tuple[Path, str, str],
):
    repo, generation_sha, _ = git_repo
    subprocess.run(
        ["git", "-C", str(repo), "checkout", "-q", "--detach", f"{generation_sha}^"],
        check=True,
    )
    sibling_sha, sibling_tree = _commit(repo, "sibling")
    subprocess.run(
        ["git", "-C", str(repo), "checkout", "-q", "--detach", generation_sha],
        check=True,
    )
    cache_dir, provenance, _ = _write_cache(repo, sibling_sha, sibling_tree)

    with pytest.raises(RuntimeError, match="is not an ancestor"):
        validate_manifest(
            cache_dir,
            provenance=provenance,
            repo_root=repo,
        )


def test_strict_manifest_rejects_cache_directory_symlink(
    git_repo: tuple[Path, str, str],
):
    repo, generation_sha, generation_tree = git_repo
    cache_dir, provenance, _ = _write_cache(
        repo,
        generation_sha,
        generation_tree,
    )
    outside = repo / "outside-cache"
    cache_dir.rename(outside)
    cache_dir.symlink_to(outside, target_is_directory=True)

    with pytest.raises(RuntimeError, match="not a real directory"):
        validate_manifest(
            cache_dir,
            provenance=provenance,
            repo_root=repo,
        )


def test_strict_manifest_rejects_cache_file_symlink(
    git_repo: tuple[Path, str, str],
):
    repo, generation_sha, generation_tree = git_repo
    cache_dir, provenance, _ = _write_cache(
        repo,
        generation_sha,
        generation_tree,
    )
    cache_path = cache_dir / provenance.filenames[0]
    outside = repo / "outside-data.pt"
    cache_path.rename(outside)
    cache_path.symlink_to(outside)

    with pytest.raises(RuntimeError, match="not a regular file"):
        validate_manifest(
            cache_dir,
            provenance=provenance,
            repo_root=repo,
        )


def test_strict_manifest_rejects_filename_not_derived_from_frozen_segments(
    git_repo: tuple[Path, str, str],
):
    repo, generation_sha, generation_tree = git_repo
    cache_dir, provenance, manifest = _write_cache(
        repo,
        generation_sha,
        generation_tree,
    )
    manifest["files"][0]["name"] = "data_00000000000000000000000000000000.pt"
    _rewrite_manifest(cache_dir, manifest)

    with pytest.raises(RuntimeError, match="filenames do not match"):
        validate_manifest(
            cache_dir,
            provenance=provenance,
            repo_root=repo,
        )
