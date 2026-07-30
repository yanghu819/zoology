# Research program: Zoology Gated DeltaNet MQAR reproduction

## Goal

Reproduce the three publicly configured Gated DeltaNet frontier points in
Zoology's standard MQAR accuracy-versus-state-size plot and compare them with
the official evidence without inventing unavailable exact scores.

## Frozen scientific contract

- Upstream result-publication snapshot: `b386338b37ce46a9257afc0a64786b0dc5a37676`.
- Vendored FLA source: `d30c0833f9286bd5bf43c20395db53c6bab97a2d`.
- Widths: 64, 128, 256.
- Learning rates: `1e-3`, `10^-2.5`, `1e-2`, `10^-1.5`.
- Seed: 123.
- Maximum epochs: 32; early stop only when `valid/accuracy > 0.99`.
- No scientific change to model, data, optimizer, batch size, validation, or
  the historical state-size proxy.

## Evidence boundary

The official repository provides a PNG and two inaccessible W&B launch IDs,
not a numeric table, lockfile, cache, checkpoint, or exact training SHA.
Accordingly, the output can establish a configuration-level reproduction.
It cannot establish bitwise identity or an exact-score delta against W&B.

## Iteration rule

This is one reproduction, not an autoresearch sweep. Compatibility repairs
must preserve the frozen scientific fields and are allowed only before the
formal launch. After formal launch, there is no automatic retry.

## Approved single-setting baseline

After the incomplete 12-cell suite, the user approved one new standalone
baseline run rather than completing the grid. It is a separately archived
rerun, not statistically independent evidence. The setting is frozen to the
official-grid configuration assigned local harness index 5: `d_model=128`,
learning rate `10^-2.5`, seed/data seed 123, and the unchanged 32-epoch
historical configuration.

This selection is explicitly pilot-informed. The three valid partial d128 cells
from the prior failed formal 12-cell reproduction are used here as pilot
evidence: they occupied a narrow final-accuracy range, and the chosen interior
learning rate was the best of those three. The d128 point is more informative
than d256 for a one-run baseline because it targets approximately 0.99 accuracy
with 67,072 bytes of state, about one quarter of d256's state-size proxy.

The strong baseline threshold, final overall `valid/accuracy >= 0.98`, is a
project decision line frozen before this run, not an upstream threshold. The
interval `0.96 <= accuracy < 0.98` is only compatible with the approximate
official 0.99 PNG reading after subtracting the project's pre-existing 0.03
visual-reading tolerance; this is not a confidence interval or error bar.
Final KV256 accuracy `>=0.88` is a pilot-informed non-official diagnostic and
never replaces the official overall metric. Falling below it records a
diagnostic anomaly and prevents unqualified adoption as this fork's canonical
baseline, but does not change the overall-accuracy classification.

This run may establish only that one fixed official configuration is close to
the published plot. It cannot claim the official best-of-four point, a complete
learning-rate sweep, or the three-width frontier.
