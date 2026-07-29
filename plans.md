# Zoology Gated DeltaNet reproduction ledger

The primary metric is final `valid/accuracy` on the historical standard MQAR
test mixture. The official plot selects the best final accuracy across four
learning rates for each official state-size value.

## A. Active plans

| ID | State | Insight | Mechanism | Prediction | Expected upside | Budget | Kill criteria | Next decision | Resource | Actual result | Record |
| -- | ----- | ------- | --------- | ---------- | --------------- | ------ | ------------- | ------------- | -------- | ------------- | ------ |
| P-REPRO-001 | approved | Zoology's published GDN scatter is reproducible only from the 2025 result-publication snapshot, not current main; the committed evidence defines three widths and four learning rates but omits exact W&B accuracies and the original dependency/cache state. | Reproduce exactly the committed 3×4 GDN MQAR sweep from `b386338`, vendor its pinned FLA `d30c083`, prewarm the shared synthetic-data cache before scored initialization, retain seed/batches/epochs/optimizer/model unchanged, log offline, and compare the three LR-frontier points only with explicitly approximate raster values. | All 12 cells complete on GPU2; the frontier is approximately 0.89/0.99/1.00 at state sizes 17,152/67,072/265,216 bytes and each point falls within its predeclared visual tolerance. | Establish whether the public Zoology GDN claim survives a modern A800 stack while exposing rather than hiding the upstream provenance gaps. | One logical AIStation GPU2; one compile smoke, one 256-example end-to-end smoke, one cache prewarm, then exactly 12 official cells with no extra seed or LR; up to 3 hours per cell and no automatic retry. | Before formal launch, stop on source/FLA/config/GPU/path drift, failed forward/backward or end-to-end smoke, missing cache manifest, or non-detached/dirty source. During the suite, stop on the first invalid cell, nonfinite value, OOM, or timeout. Never add a seed, LR, width, batch change, or guessed fourth plot point to rescue the comparison. | Smoke miss: repair only the identified compatibility fault before any formal claim. Complete frontier within tolerance: mark done and report a configuration-level reproduction. Valid frontier mismatch: mark discarded and attribute only after checking environment/cache evidence. Invalid cell: mark failed and preserve partial artifacts without retry. | GPU2 | — | — |

## B. Completed plans

| ID | State | Actual result | Record |
| -- | ----- | ------------- | ------ |

## C. Resource allocation

| Resource | Plan | Run | Git SHA | GPU UUID | Started UTC | Ended UTC | State |
| -------- | ---- | --- | ------- | -------- | ----------- | --------- | ----- |

## D. Durable lessons

| Recorded UTC | Plan | Evidence | Lesson | Consequence |
| ------------ | ---- | -------- | ------ | ----------- |
| 2026-07-29T13:14:26Z | P-REPRO-001 | The matching upstream causal-conv1d wheel required `GLIBC_2.32` on GPU2's GLIBC 2.31 host. A same-version source build required at most GLIBC 2.14 and matched the reference forward and gradients on the channel-last BF16 width-4 path. | Matching CUDA, Torch, Python, and C++ ABI labels do not guarantee host GLIBC compatibility. | Pin the sdist, compiler inputs, and output wheel hashes; inspect ELF symbol versions and execute the real target-layout CUDA forward/backward before a wheel enters smoke. |

## E. Submission records

This is a reproduction study, not a competition submission.
