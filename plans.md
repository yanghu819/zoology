# Zoology Gated DeltaNet reproduction ledger

The primary metric is final `valid/accuracy` on the historical standard MQAR
test mixture. The official plot selects the best final accuracy across four
learning rates for each official state-size value.

## A. Active plans

| ID | State | Insight | Mechanism | Prediction | Expected upside | Budget | Kill criteria | Next decision | Resource | Actual result | Record |
| -- | ----- | ------- | --------- | ---------- | --------------- | ------ | ------------- | ------------- | -------- | ------------- | ------ |

## B. Completed plans

| ID | State | Actual result | Record |
| -- | ----- | ------------- | ------ |
| P-REPRO-001 | failed | Cells 00–06 completed validly on logical GPU2. Cell07 never entered training: its worker-side admission check reduced the reported 11,638 seconds by 231 seconds of setup age, leaving 11,407 seconds, 53 seconds below the frozen 11,460-second floor. The terminal is `failed`/exit 1, the suite is incomplete, and the predeclared no-retry rule stopped the experiment. There is no aggregate or full three-width frontier. The verified partial archive SHA-256 is `05a5f5d25e909496e34a5dce1c3a7dfa2b8b381ae148e1630debf8e83a2fea1f`. | `research/reports/experiments/gdn-mqar-official-20260729T134504Z-ec17472161bc.md` |

## C. Resource allocation

| Resource | Plan | Run | Git SHA | GPU UUID | Started UTC | Ended UTC | State |
| -------- | ---- | --- | ------- | -------- | ----------- | --------- | ----- |
| GPU2 | P-REPRO-001 | `gdn-mqar-official-20260729T134504Z-ec17472161bc` | `ec17472161bc8abed3c413ada99bd9579b94fbfe` | Per-cell attestations | 2026-07-29T13:45:04Z | 2026-07-29T16:25:57Z | failed |

## D. Durable lessons

| Recorded UTC | Plan | Evidence | Lesson | Consequence |
| ------------ | ---- | -------- | ------ | ----------- |
| 2026-07-29T13:14:26Z | P-REPRO-001 | The matching upstream causal-conv1d wheel required `GLIBC_2.32` on GPU2's GLIBC 2.31 host. A same-version source build required at most GLIBC 2.14 and matched the reference forward and gradients on the channel-last BF16 width-4 path. | Matching CUDA, Torch, Python, and C++ ABI labels do not guarantee host GLIBC compatibility. | Pin the sdist, compiler inputs, and output wheel hashes; inspect ELF symbol versions and execute the real target-layout CUDA forward/backward before a wheel enters smoke. |
| 2026-07-29T16:25:57Z | P-REPRO-001 | Cell07 passed the controller-side time check, but setup consumed enough time that the worker-side recheck saw 11,407 seconds against a required 11,460. It failed before creating a claim, training log, run directory, or score. | A two-stage lease gate needs launch slack at least as large as worst-case setup and validation time; merely clearing the first gate is not sufficient. | Future suites should encode that slack before launch. This frozen suite remains failed: do not erase the terminal, retry the cell, or reinterpret partial scores as a completed reproduction. |

## E. Submission records

This is a reproduction study, not a competition submission.
