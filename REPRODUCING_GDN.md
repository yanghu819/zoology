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
./run.sh full
```

`setup.sh` creates a project-local uv environment and checks the exact runtime.
`down.sh` materializes and manifests the synthetic data. `run.sh smoke` compiles
the smallest and largest GDN kernels, exercises forward and backward, and runs
a one-epoch end-to-end MQAR test. `run.sh full` then executes exactly 12 cells
sequentially with a three-hour hard limit per cell and no automatic retry.

All caches, wheels, data, W&B offline state, and run artifacts stay below the
repository root. Data, checkpoints, and generated artifacts are ignored by
Git. Each suite archives the exact Git source, cache manifest, environment,
per-cell resolved config, logs, metrics, summary, and source/cache hashes.

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
