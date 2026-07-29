# Reproducing Zoology's Gated DeltaNet MQAR result

This branch reproduces the three Gated DeltaNet configurations published for
Zoology's standard MQAR accuracy-versus-state-size plot. It deliberately does
not use current `main`: the closest public result-publication snapshot is
`b386338b37ce46a9257afc0a64786b0dc5a37676`.

## What is frozen

- 12 cells: `d_model={64,128,256}` crossed with four official learning rates.
- Seed 123, batch sizes `(256,32)`, at most 32 epochs, and strict early stopping
  only when final validation accuracy exceeds 0.99.
- The historical two-layer hybrid: BaseConv with kernel size 3 followed by
  Gated DeltaNet with two heads and its short convolution enabled.
- Vendored FLA commit `d30c0833f9286bd5bf43c20395db53c6bab97a2d`.
- Historical final-accuracy selection and state-size proxy.

The only scientific normalization is that all synthetic MQAR cache files are
generated once before scored model initialization. This removes the upstream
cache-hit/cache-miss RNG ambiguity and is recorded in a hashed manifest.

## Execution

Formal execution is intentionally accepted only from a clean, detached commit
at `/huyang2/zoology` on logical AIStation target `GPU2`.

```bash
./setup.sh
./run.sh smoke

export AISTATION_TARGET=GPU2
export ZOOLOGY_EXPECTED_GIT_SHA="$(git rev-parse HEAD)"
SUITE_DIR="/huyang2/zoology/runs/gdn-mqar-official-manual-$(date -u +%Y%m%dT%H%M%SZ)"
./run.sh init-suite "${SUITE_DIR}"

# Refresh this value from AIStation immediately before every cell.
export ZOOLOGY_REMAINING_SECONDS="<current GPU2 remainTime in seconds>"
export ZOOLOGY_REMAINING_OBSERVED_UNIX="<Unix second when status was read>"
./run.sh resume "${SUITE_DIR}"

# `resume` prints launch JSON and returns immediately. Poll the reported
# launch_dir/terminal.json; only then refresh status and launch the next cell.

# After all 12 terminal records say completed and suite validation passes:
./run.sh aggregate "${SUITE_DIR}"
```

`setup.sh` creates a project-local uv environment, checks it against the frozen
uv lock, requires the complete 52-file Linux CPython 3.10 wheelhouse, and
bootstraps the pinned uv binary from a hash-checked local wheel. It exports
hashes directly from `uv.lock`, syncs all 50 locked registry dependencies from
the local wheelhouse with index access disabled, and then installs the
separately hash-checked causal-conv1d wheel. That wheel was built on GPU2 from
the hash-locked `1.5.3.post1` sdist against CUDA 12.6 and Torch 2.7 because the
matching upstream binary requires GLIBC 2.32 while GPU2 provides GLIBC 2.31.
`repro/runtime_lock.json` records the rejected binary, source, toolchain, ABI,
ELF requirement, and final wheel hashes. The project itself is imported from
the frozen checkout rather than rebuilt as an editable wheel on the slow
shared filesystem. Before setup, download, or execution, a
shared path gate rejects symlinked runtime roots and untracked or ignored
importable source shadows; all bytecode is redirected into `.cache/pycache`.
`down.sh` materializes and manifests the synthetic data. `run.sh smoke` compiles
the smallest GDN kernel and the largest formal `d_model=256, seq_len=1024`
kernel, exercises forward and backward, and runs a one-epoch end-to-end MQAR
test.

AIStation's `remainTime` is a seconds countdown. A single cell has a three-hour
hard limit, so `run.sh resume` starts exactly one next cell only when the caller
provides at least 11,460 adjusted remaining seconds: the three-hour cell limit,
60 seconds of hard-kill grace, and a ten-minute shutdown buffer. The observation
timestamp makes the worker subtract setup and cache-preflight time before the
final admission decision; observations older than ten minutes are rejected.
Override `ZOOLOGY_MIN_REMAINING_SECONDS` only to make that infrastructure margin
larger. The expiring-session-unsafe `run.sh full` path is disabled.

`resume` reserves one launch atomically, starts its worker in a new session with
no controlling terminal, and returns launch JSON without waiting for training.
This is safe when the AIStation helper closes its SSH/PTTY connection after 20
seconds. Per-cell launcher state is stored under
`launches/run-NN/{request.json,launch.json,worker.pid,launcher.log}`. The worker
creates `terminal.json` atomically with its final exit code. A missing terminal
record means the worker was abruptly interrupted; it is never treated as a
completed cell. The model's stdout and stderr remain in `logs/run-NN.log`, while
preflight and worker-wrapper output go to `launcher.log`.

`init-suite` creates one persistent suite and binds it to the exact Git tree,
runtime lock, live GPU/runtime attestation, uv lock, source archive, and
data-cache manifest. Each `resume`
call revalidates those bindings and skips only a contiguous cell whose complete
metadata, config, model metadata, finite summary, metrics, and log all validate.
A new live attestation must match the suite's Python, Torch, Triton,
causal-conv1d, CUDA, GPU model, and driver before each cell starts. The physical
GPU UUID is recorded per cell but may change when logical GPU2 is reopened.
A partial or failed cell stops the suite without deleting, overwriting, or
silently retrying it. This makes an AIStation restart safe at a completed-cell
boundary: reopen GPU2, verify the detached checkout, query a fresh countdown,
and continue the same suite.

All caches, wheels, data, W&B offline state, and run artifacts stay below the
repository root. The top-level runtime roots are required to be physical
directories rather than symbolic links. Data, checkpoints, and generated
artifacts are ignored by Git. Each suite archives the exact Git source, cache
manifest, environment, per-cell resolved config (including every concrete MQAR
segment field), logs, metrics, summary, and source/cache hashes.

## Official comparison boundary

The official repository did not publish numeric GDN accuracies, its original
cache, a lockfile, checkpoints, or the exact pre-commit training tree. Its W&B
project is not anonymously accessible. Consequently:

- exact official accuracy remains `null`;
- the committed PNG is used only for clearly labeled approximate visual checks;
- the unexplained fourth GDN-colored point is excluded because no matching
  committed configuration exists;
- a successful run is called a configuration-level reproduction, never a
  bitwise or exact-score reproduction.
