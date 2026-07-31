# Zoology Gated DeltaNet reproduction ledger

The primary metric is final `valid/accuracy` on the historical standard MQAR
test mixture. The official plot selects the best final accuracy across four
learning rates for each official state-size value.

## A. Active plans

| ID | State | Insight | Mechanism | Prediction | Expected upside | Budget | Kill criteria | Next decision | Resource | Actual result | Record |
| -- | ----- | ------- | --------- | ---------- | --------------- | ------ | ------------- | ------------- | -------- | ------------- | ------ |
| P-BASELINE-002 | in-progress | The previous run proved that an AIStation status value can be fresh while its locally stamped observation time is invalid in the remote controller's clock domain. A conservative timestamp taken from GPU2 immediately before the status query removes that clock-domain ambiguity without weakening the frozen freshness gate. | Run one new suite and the same official-grid index 5 setting. A tracked module exclusively preclaims one capture; snapshots the exact AIStation helper; brackets one unchanged `status GPU2` response between two GPU2 hostname, boot-ID, and Unix-time calls; requires one unchanged Running workspace/host/boot, at most a 15-second bracket, and at least 12,060 seconds remaining; writes a completed or failed terminal; and selects the remote-before timestamp. The seven-file completed bundle is hash-validated and immutably copied into the suite. One GPU2 process rechecks host, boot, and age no more than 60 seconds after observation, then publishes and launches without an intervening shell or host handoff. The old failed suite remains immutable. | The bracket and both existing admissions pass without changing the -30-second future bound, after which the unchanged model reaches final overall `valid/accuracy >= 0.98`; `0.96 <= accuracy < 0.98` is only visually compatible with the approximate official plot; final KV256 accuracy `>=0.88` is diagnostic. | Produce the originally requested single persuasive GDN MQAR baseline while spending no compute on another width, learning rate, seed, or table-filling cell. | One logical GPU2 cell; expect about 5 minutes for setup and about 18 minutes launch-to-terminal; 10,800-second hard timeout. Exactly one formal capture directory and one launch are allowed. Upload/archive transport may be retried only before publication when bytes and hashes remain unchanged. | Stop without retry on source/runtime/cache drift, pre-existing capture path, wrong row or workspace/host/boot drift, non-Running status, bracket span over 15 seconds, publication age over 60 seconds, remaining time below 12,060 seconds, failed capture terminal, failed admission, OOM, NaN, timeout, invalid evidence, or failed worker terminal. Do not relax 0.98/0.96/0.88 or the -30-second gate. | If overall and KV256 both pass, adopt this as the canonical baseline and stop. If overall passes but KV256 fails, record the anomaly and pause. Otherwise preserve the valid negative or infrastructure failure; do not launch another configuration automatically. | GPU2 (`63e6715f-0e16-4128-87f2-97d867d2d602`) | – | `research/reports/experiments/gdn-mqar-single-baseline-clockbracket-20260731T023001Z.md` |

## B. Completed plans

| ID | State | Actual result | Record |
| -- | ----- | ------------- | ------ |
| P-BASELINE-001 | failed | Controller admission failed closed before any request or worker was created. The saved GPU2 status was observed at Unix 1785391952 (`2026-07-30T06:12:32Z`) with 13,554 seconds remaining, but remote `checked_unix=1785391910` yielded `raw_age_seconds=-42`, beyond the frozen 30-second future-timestamp tolerance. No worker, training, terminal, metric, model, score, or retry exists; the model hypothesis remains untested. The independently verified 19-file evidence archive SHA-256 is `7037f8e9967520d6d7f83e7f7cad475647950cbff68a4515b2c19d05c325deab`. | `research/reports/experiments/gdn-mqar-single-baseline-20260730T031705Z.md` |
| P-REPRO-001 | failed | Cells 00–06 completed validly on logical GPU2. Cell07 never entered training: its worker-side admission check reduced the reported 11,638 seconds by 231 seconds of setup age, leaving 11,407 seconds, 53 seconds below the frozen 11,460-second floor. The terminal is `failed`/exit 1, the suite is incomplete, and the predeclared no-retry rule stopped the experiment. There is no aggregate or full three-width frontier. The verified partial archive SHA-256 is `05a5f5d25e909496e34a5dce1c3a7dfa2b8b381ae148e1630debf8e83a2fea1f`. | `research/reports/experiments/gdn-mqar-official-20260729T134504Z-ec17472161bc.md` |

## C. Resource allocation

| Resource | Plan | Run | Git SHA | GPU UUID | Started UTC | Ended UTC | State |
| -------- | ---- | --- | ------- | -------- | ----------- | --------- | ----- |
| GPU2 | P-REPRO-001 | `gdn-mqar-official-20260729T134504Z-ec17472161bc` | `ec17472161bc8abed3c413ada99bd9579b94fbfe` | Per-cell attestations | 2026-07-29T13:45:04Z | 2026-07-29T16:25:57Z | failed |
| GPU2 | P-BASELINE-001 | `gdn-mqar-single-baseline-20260730T031705Z` | `3890b00f620a8f43ff3af25c471fbc14268c6fdd` | `GPU-0da20a4f-5e67-e47d-7aab-8c6efa2864ad` | 2026-07-30T06:01:44Z | 2026-07-30T06:24:50Z | failed |
| GPU2 | P-BASELINE-002 | `gdn-mqar-single-baseline-clockbracket-20260731T023001Z` | `13f880b5fe61619a1006ef33610de69fbabaaec1` | `GPU-573c7ed1-1c51-8334-299b-edf2ff3440e6` | 2026-07-31T03:18:10Z | – | in-progress |

## D. Durable lessons

| Recorded UTC | Plan | Evidence | Lesson | Consequence |
| ------------ | ---- | -------- | ------ | ----------- |
| 2026-07-29T13:14:26Z | P-REPRO-001 | The matching upstream causal-conv1d wheel required `GLIBC_2.32` on GPU2's GLIBC 2.31 host. A same-version source build required at most GLIBC 2.14 and matched the reference forward and gradients on the channel-last BF16 width-4 path. | Matching CUDA, Torch, Python, and C++ ABI labels do not guarantee host GLIBC compatibility. | Pin the sdist, compiler inputs, and output wheel hashes; inspect ELF symbol versions and execute the real target-layout CUDA forward/backward before a wheel enters smoke. |
| 2026-07-29T16:25:57Z | P-REPRO-001 | Cell07 passed the controller-side time check, but setup consumed enough time that the worker-side recheck saw 11,407 seconds against a required 11,460. It failed before creating a claim, training log, run directory, or score. | A two-stage lease gate needs launch slack at least as large as worst-case setup and validation time; merely clearing the first gate is not sufficient. | Future suites should encode that slack before launch. This frozen suite remains failed: do not erase the terminal, retry the cell, or reinterpret partial scores as a completed reproduction. |
| 2026-07-30T06:24:50Z | P-BASELINE-001 | AIStation status was stamped at Unix 1785391952, while the remote controller checked at Unix 1785391910, producing a -42-second age and failing the frozen -30-second future-timestamp bound before request creation. | Freshness checks spanning hosts require a shared clock domain or an explicitly measured and bounded clock offset; ample lease time alone is insufficient. | Before any future separately approved formal launch, measure clock skew fail-closed or stamp status and admission in the same clock domain. Do not relax the current bound or retry this frozen run. |

## E. Submission records

This is a reproduction study, not a competition submission.
