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
