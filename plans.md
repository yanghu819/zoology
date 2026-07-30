# Zoology Gated DeltaNet reproduction ledger

The primary metric is final `valid/accuracy` on the historical standard MQAR
test mixture. The official plot selects the best final accuracy across four
learning rates for each official state-size value.

## A. Active plans

| ID | State | Insight | Mechanism | Prediction | Expected upside | Budget | Kill criteria | Next decision | Resource | Actual result | Record |
| -- | ----- | ------- | --------- | ---------- | --------------- | ------ | ------------- | ------------- | -------- | ------------- | ------ |
| P-BASELINE-001 | approved | A pilot-informed d128 interior learning-rate point is more persuasive per unit compute than either repeating the unstable d64 group or using d256 capacity to hit the accuracy ceiling. It tests near-perfect MQAR recall with only 67,072 bytes of state. | Run exactly the official-grid configuration assigned local harness index 5: `d_model=128`, LR `10^-2.5`, seed/data seed 123, at most 32 epochs, and unchanged historical data/model/optimizer. This is a standalone single-setting rerun, not a best-of-four selection or statistically independent sample. | Final overall `valid/accuracy >= 0.98`; `0.96 <= accuracy < 0.98` is only visually compatible with the approximate official plot; final KV256 accuracy `>=0.88` is a diagnostic, not the official metric. The 0.98 strong line is a project decision threshold, 0.96 is the approximate 0.99 PNG reading minus the project's 0.03 visual tolerance, and 0.88 is a pilot-informed non-official diagnostic line. | One separately archived, high-signal baseline comparable to the official plot reading of approximately 0.99 without spending eleven more cells. | One logical GPU2 cell; prior same-setting training was 838 seconds; expect about 18 minutes launch-to-terminal; 10,800-second hard timeout. Controller admission is 12,060 seconds and worker admission is 11,460 seconds. | Stop without retry on source/runtime/cache drift, wrong GPU row, stale lease observation, OOM, NaN, timeout, invalid evidence, or failed terminal. A valid score in `[0.96, 0.98)` rejects the strong hypothesis but remains visually compatible; a score below 0.96 is below that visual band. KV256 below 0.88 does not change the official-overall classification but creates a diagnostic anomaly. | If overall and KV256 both pass, adopt it as the canonical baseline for this fork and stop. If overall passes but KV256 fails, record the anomaly and pause without automatic follow-up. Otherwise preserve the valid negative or infrastructure failure; do not launch another LR automatically. | GPU2 | – | `research/reports/experiments/gdn-mqar-single-baseline-20260730T031705Z.md` |

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
