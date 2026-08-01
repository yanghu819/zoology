# Experiment: E-GDN-MQAR-BASELINE-008

## 1. Metainfo

- Plan: `P-BASELINE-008`
- Run: `gdn-mqar-single-baseline-p008-20260801t092653z`
- State: `approved / fresh GPU2 allocation pending`
- Proposed UTC: `2026-08-01T09:26:53Z`
- Approved UTC: `2026-08-01T09:26:53Z`
- Approval: after P007 was closed as a terminal pre-pytest control failure, the
  user explicitly said `继续迭代啊`; this authorizes one separately tracked P008
  with the same frozen science and one fresh literal-GPU2 allocation
- Target: logical AIStation `GPU2` only; GPU1 is outside scope and must never be
  queried, probed, opened, stopped, or mutated
- Parent: `P-BASELINE-007`, immutable `failed`; P008 neither reopens nor retries
  its consumed run ID
- Remote root: `/huyang2/zoology`
- Formal source commit:
  `13f880b5fe61619a1006ef33610de69fbabaaec1`
- Formal source tree:
  `ed83a7188351ca2cce8aba46d1cb3b108ce31ec2`
- GitHub-verified operational-control commit:
  `b69aeb8bedb387f321c1d771ae7c3157aec789df`
- GitHub-verified operational-control tree:
  `a33960686f52c8c8d5c6b44029229f0f9cfcf950`
- Operational-control parent:
  `e9ff2e7a83c51042fff85f0d9f0953dd1f339418`
- Durable Linux envelope SHA-256:
  `785ad8162bc831b762e84e0297effadf355893083b802fccc7ab5d10515a6f8d`
- Linux exact-test gate SHA-256:
  `2ceb337fbdd304222491511a6dca6010be4a600fcd19295420d598eb6b5546a4`
- Durable-envelope test SHA-256:
  `f352c7d610b3f29e1e6dd8acf78ed24479a15bf2b75b43caf6d6ac350ba307d6`
- Local operational-control verification: `107 passed`, `50 skipped`,
  `0 failed`; every skip required Linux `/proc`, `setsid`, or a controlling PTY
- Approval-time allocation context: request
  `b0411955-3f8d-445d-a164-2bd435f8be1f` remained the exact-A100 P007
  allocation, but a read-only continuation observation reported only
  `remainTime=8236`, below the unchanged 13,200-second initial admission floor

The report and run ID were absent and accepted by both production run-ID
validators before this record was created. No P008 artifact root, remote path,
suite, controller, capture, worker, training process, model, metric, or score
exists at approval. The short residual lease is not eligible for P008 remote
work. After this approval ledger is pushed and GitHub-verified, one no-clobber
status may be preserved and literal GPU2 may be restarted exactly once. The
new request and unchanged image must be ledgered and GitHub-verified before
admission.

## 2. Hypothesis

Local official-grid harness index 5 is a persuasive single-setting Gated
DeltaNet MQAR baseline. On the historical standard test mixture, the unchanged
cell should finish with overall final `valid/accuracy >= 0.98`, near the
official PNG's approximately 0.99 visual reading, and final KV256 accuracy
`>= 0.88`, while using a 67,072-byte state-size proxy.

P007 did not test that scientific hypothesis. Its worker claim proved the
detached Bash worker existed, but the starter inspected the outer
`setsid --fork --wait` transport process. Under the production helper's PTY,
that transient parent legitimately retained a controlling terminal and was
misclassified as the detached supervisor. The repaired control records the
transport honestly, binds the claimed Bash child as the durable supervisor,
and publishes `start.json` only after proving `PID=PGID=SID`, `tty_nr=0`, exact
executable, cwd, command line, hashes, and process start ticks.

This is one decision-changing operational intervention, not a scientific
ablation. No architecture, data, optimizer, seed, width, learning rate, epoch
budget, threshold, metric, or comparison rule changes.

## 3. Configuration

- Official-grid harness index: `5`
- `d_model`: `128`
- Learning rate: `0.0031622776601683794` (`10^-2.5`)
- Seed and data seed: `123`
- Maximum epochs: `32`
- Strong overall threshold: `0.98`
- Visual-only compatibility floor: `0.96`
- Final KV256 threshold: `0.88`
- Timeout and grace: `10,800/60` seconds
- Train/test examples: `180,000/7,000`
- Train/test batches: `256/32`
- Vocabulary: `8192`
- Optimizer/scheduler: AdamW with cosine decay
- Weight decay: `0.1`
- Early stop: strictly when an epoch's `valid/accuracy > 0.99`
- Model: two-layer historical hybrid, BaseConv kernel 3 followed by two-head
  Gated DeltaNet
- Gated DeltaNet output gate: disabled
- Gated DeltaNet decay and short convolution: enabled
- Short-convolution width: `4`
- Position embedding: disabled
- Embedding weights: tied
- Embedding dropout: `0.1`

No other cell, learning rate, width, seed, ablation, threshold change, or
formal retry is authorized. Only a complete valid result with overall accuracy
at least 0.98 and KV256 accuracy at least 0.88 may receive an
`exp/score-{score}-{sha}` tag. An overall result from 0.96 to below 0.98 is
visual-only and receives no strong-result tag. Any lower complete result is a
valid negative; any incomplete, invalid, or timed-out run is terminal failed.

## 4. Environment and admission

- AIStation target: literal logical row `GPU2`
- Approved helper:
  `/Users/torusmini/.codex/skills/aistation-skill/scripts/aistation_api.js`
- Approved helper SHA-256:
  `628aefaa2de3eb09ad5e6e1397e04280650e01847da2d9192566137405230226`
- Frozen admission module SHA-256:
  `68fa3af301f7b88d3bffb3fd17add8db2db9ae26d2e573a32f2944f02465121b`
- Required resource: exactly `NVIDIA-A100-SXM4-80GB:1`
- Initial remaining-time floor: `13,200` seconds
- Pre-capture remaining-time floor: `12,120` seconds
- Formal captured remaining-time floor: `12,060` seconds
- Maximum formal clock bracket: `15` seconds
- Maximum capture-to-publication age: `60` seconds
- Current request before the approved replacement:
  `b0411955-3f8d-445d-a164-2bd435f8be1f`
- Current request disposition: allocation-only predecessor; no P008 remote
  mutation is allowed because its observed residual lease was 8,236 seconds

The exact new request ID, image, status, GPU UUID, host, boot ID, initial lease,
and admission evidence are pending. Pending, Queuing, and ImagePulling remain
status-only. Running state is not admission: the frozen initial gate must bind
the ledgered request, exact resource, helper-driven probe/SSH/CUDA access,
stable identity, and at least 13,200 seconds before remote mutation.

## 5. Planned commands and evidence

1. Push and GitHub-verify this P008 approval ledger. Before that verification,
   do not call restart, probe, SSH, exec, push, or create a P008 remote path.
2. Preserve one fresh no-clobber literal-GPU2 status, validate the helper hash
   before and after, and restart literal GPU2 exactly once. The response must
   contain a new request ID and the unchanged image, with at most one active
   request. Record old and new allocations in this report and `plans.md`, then
   commit, push, and GitHub-verify that transition before further work.
3. Poll only literal GPU2. Pending, Queuing, or ImagePulling ends the turn.
   Halt before admission is terminal P008 allocation failure; there is no
   second restart. When Running, enter only through the frozen initial
   admission capture/verify and require the exact A100 plus at least 13,200
   seconds. After admission, bind the request/GPU/host/boot/lease evidence,
   mark P008 `in-progress`, and GitHub-verify that ledger transition before
   remote setup.
4. On `/huyang2/zoology`, fetch only from GitHub and clean-checkout detached
   formal source `13f880...`. Reuse only repo-local `.venv`, caches, wheels,
   artifacts, models, and runs. Upload the exact 19-file launcher assembled
   from operational commit `b69aeb8...`; every advancing exec/push is owned by
   an exclusive `run-operation` receipt.
5. Start the repaired durable Linux exact-test envelope once through the real
   helper PTY. Before any suite, preflight, init, capture, or training path is
   created, require `start.json` schema 2 to record a nonzero inherited
   transport TTY and the claimed Bash supervisor as `PID=PGID=SID` with
   `tty_nr=0`. After the helper transport closes, require terminal completion,
   transport/worker/gate quiescence, exact hash closure, and exactly
   `53 passed / 0 skipped / 0 failed / 0 errors / 0 disabled`. This one gate is
   also the production-PTY regression; it is never repeated or bypassed.
6. Only after exact 53/0, run audited setup/check/cache/real-A100 GDN smoke via
   durable preflight-v2, then durable init-baseline and their sole verifiers.
   Require the selected suite cell to remain exactly index 5.
7. Require at least 12,120 seconds before capture. Perform one formal clock
   capture with at least 12,060 seconds and a bracket at most 15 seconds; bind,
   verify, upload, and remotely validate the seven-file bundle. Make exactly
   one durable formal start within the 60-second publication-age limit and
   launch only the single index-5 worker.
8. Monitoring after launch is read-only. At terminal state, validate and safely
   archive allowed evidence without model/data/checkpoints, pull it, verify it
   independently, and update Sections 6-9, `plans.md`, resource allocation,
   and `leaderboard.csv` without overstating the result.

Kill criteria are fail-closed: helper/control hash drift; wrong row, image,
request, resource, host, boot ID, or GPU; ambiguous/multiple active requests;
failed restart; admission below 13,200; transport/start/TTY/identity/quiescence
failure; Linux count other than exact 53/0; source/tree/inventory/runtime drift;
pre-capture below 12,120; capture below 12,060; clock bracket above 15 seconds;
publication age above 60 seconds; a second capture/start/cell; invalid or
incomplete result; or timeout. Any such condition closes P008 terminally with
no retry.

## 6. Artifacts

Pending. No P008 artifact path or remote path exists at approval. Allowed
evidence will exclude model weights, datasets, caches, checkpoints, and secrets.

## 7. Results

Pending. No worker, training metric, model, or score exists.

## 8. Official comparison

Pending. The official visual reference remains approximately 0.99 for the
matching state-size point; no reproduced value exists yet.

## 9. Decision and reusable lesson

Approved for one fresh GPU2 allocation and one unchanged formal cell after the
new worker-bound envelope passes its one production-PTY/exact-53 gate. P007
remains immutable failed. No conclusion about Gated DeltaNet accuracy is
permitted until P008 reaches a complete validated terminal result.
