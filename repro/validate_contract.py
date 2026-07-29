"""Validate source, dependency, config, and path contracts without GPU compute."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from repro.configs.gdn_mqar_official import configs


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_CONFIG_SHA256 = (
    "dc29c0d5c908c60768f905afb3a683c6b14ad4774810d807fc1abcdbc767e672"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _content_tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(path for path in root.rglob("*") if path.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(bytes.fromhex(_sha256(path)))
        digest.update(b"\n")
    return digest.hexdigest()


def main() -> None:
    historical_config = (
        ROOT / "zoology" / "experiments" / "030325_new_arch" / "configs.py"
    )
    actual_config_sha = _sha256(historical_config)
    if actual_config_sha != OFFICIAL_CONFIG_SHA256:
        raise RuntimeError(
            f"historical config hash drift: {actual_config_sha}"
        )
    if len(configs) != 12:
        raise RuntimeError("official sweep must contain exactly 12 runs")

    runtime_lock = json.loads(
        (ROOT / "repro" / "runtime_lock.json").read_text(encoding="utf-8")
    )
    if runtime_lock["remote_root"] != "/huyang2/zoology":
        raise RuntimeError(runtime_lock["remote_root"])
    vendor_root = ROOT / "vendor" / "flash-linear-attention"
    if not (vendor_root / "LICENSE").is_file():
        raise RuntimeError("vendored FLA license is missing")
    if (
        _content_tree_sha256(vendor_root)
        != runtime_lock["vendored_fla_content_sha256"]
    ):
        raise RuntimeError("vendored FLA content drift")

    snapshot = runtime_lock["zoology_result_snapshot"]
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", snapshot, "HEAD"],
        cwd=ROOT,
        check=True,
    )
    source_diff = subprocess.check_output(
        ["git", "diff", "--name-only", snapshot, "HEAD", "--", "zoology"],
        cwd=ROOT,
        text=True,
    ).strip()
    if source_diff:
        raise RuntimeError(f"historical Zoology source drift: {source_diff}")
    print("reproduction_contract=pass")


if __name__ == "__main__":
    main()
