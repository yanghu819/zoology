# Experiment: E-GDN-MQAR-BASELINE-002

## 1. Metainfo

- Plan: `P-BASELINE-002`
- Run: `gdn-mqar-single-baseline-clockbracket-20260731T023001Z`
- State: `in-progress`
- Approved UTC: `2026-07-31T02:30:01Z`
- Started UTC (GPU2 remote observation): `2026-07-31T03:18:10Z`
- Approval: the user's post-closeout instruction `continue`
- Target: logical AIStation `GPU2`
- Remote root: `/huyang2/zoology`
- Run directory:
  `/huyang2/zoology/runs/gdn-mqar-single-baseline-clockbracket-20260731T023001Z`
- Parent experiment: `P-BASELINE-001`, terminal `failed`
- Formal source SHA: `13f880b5fe61619a1006ef33610de69fbabaaec1`
- Formal source tree: `ed83a7188351ca2cce8aba46d1cb3b108ce31ec2`

This is a separately approved experiment with a new plan, run, suite, source
snapshot, and evidence graph. It does not reopen, repair, overwrite, or retry
the immutable failed suite
`gdn-mqar-single-baseline-20260730T031705Z`. The scientific setting is retained
because the earlier worker never launched and therefore produced no model
evidence.

## 2. Hypothesis

The official-grid configuration assigned local harness index 5 should provide
a persuasive single-setting Gated DeltaNet MQAR baseline: near the official
PNG reading of approximately 0.99 while using a 67,072-byte state-size proxy,
about one quarter of the d256 point.

The prior experiment failed before request creation because a local
observation timestamp was 42 seconds ahead of the remote controller clock.
The admission logic itself was correct: it rejected a timestamp beyond the
frozen 30-second future tolerance even though remaining lease time was ample.

This experiment uses a conservative clock-domain bridge rather than relaxing
that gate. One unchanged `status GPU2` response is bracketed by two
hostname, boot-ID, and Unix-time calls executed on the same GPU2 workspace.
The timestamp from immediately before the status query is selected as
`ZOOLOGY_REMAINING_OBSERVED_UNIX`. It is an intentionally early lower bound,
so the existing admission subtracts at least the true elapsed age.

The decisions are frozen before launch:

- bracket workspace is identical and Running in all three responses;
- hostname and Linux boot ID are identical in both remote responses;
- remote and local bracket durations are each at most 15 seconds;
- reported remaining time is at least the unchanged 12,060-second controller
  floor;
- final overall `valid/accuracy >= 0.98`: strong project baseline pass;
- `0.96 <= accuracy < 0.98`: strong hypothesis rejected, but compatible with
  the approximate 0.99 PNG reading under the project's 0.03 visual tolerance;
- final overall accuracy `< 0.96`: below the visual compatibility band;
- final KV256 accuracy `< 0.88`: non-official diagnostic anomaly.

The 0.98, 0.96, and 0.88 thresholds are unchanged from `P-BASELINE-001`.
No result from the prior partial suite is reused as this run's score.

## 3. Configuration

- Selected official-grid configuration: local harness index `5`
- `d_model`: `128`
- Learning rate: `0.0031622776601683794` (`10^-2.5`)
- Seed and data seed: `123`
- Maximum epochs: `32`
- Early stop: strictly when an epoch's `valid/accuracy > 0.99`
- Optimizer: AdamW
- Weight decay: `0.1`
- Scheduler: cosine decay
- Train/test batches: `256/32`
- Vocabulary: `8192`
- Train/test examples: `180,000/7,000`
- Model: two-layer historical hybrid, BaseConv kernel 3 followed by
  two-head Gated DeltaNet
- Gated DeltaNet output gate: disabled
- Gated DeltaNet decay and short convolution: enabled
- Short-convolution width: `4`
- Position embedding: disabled
- Embedding weights: tied
- Embedding dropout: `0.1`
- Scored metric: final overall `valid/accuracy`
- Diagnostic only: best validation accuracy and final KV256 accuracy
- Hard timeout: `10,800` seconds, plus `60` seconds kill grace

No model, data, optimizer, epoch, stopping, metric, width, learning rate, seed,
or threshold may change after approval.

## 4. Environment

- Upstream result-publication snapshot:
  `b386338b37ce46a9257afc0a64786b0dc5a37676`
- Vendored FLA:
  `d30c0833f9286bd5bf43c20395db53c6bab97a2d`
- Python: `3.10.11`
- uv: `0.9.27`
- PyTorch: `2.7.0+cu126`
- torchvision: `0.22.0+cu126`
- Approved AIStation helper:
  `/Users/torusmini/.codex/skills/aistation-skill/scripts/aistation_api.js`
- Approved AIStation helper SHA-256:
  `628aefaa2de3eb09ad5e6e1397e04280650e01847da2d9192566137405230226`
- AIStation workspace request:
  `63e6715f-0e16-4128-87f2-97d867d2d602`
- Allocated GPU: `NVIDIA A100-SXM4-80GB`
- GPU UUID: `GPU-573c7ed1-1c51-8334-299b-edf2ff3440e6`
- GPU2 hostname: `c1psj7eh98ftq-0`
- GPU2 boot ID: `08d861e6-ce7b-4fe8-ba78-de529efd1b31`
- Formal execution requires:
  - exact pushed source SHA and tree;
  - clean detached checkout;
  - physical root `/huyang2/zoology`;
  - literal logical target `GPU2`;
  - one preclaimed seven-file clock-capture bundle produced by the tracked
    bracket module;
  - one unchanged saved AIStation status response naming `GPU2`, `Running`,
    and the same workspace as both clock responses;
  - the publishing process runs on the captured GPU2 hostname and Linux boot
    ID no more than 60 seconds after the selected remote timestamp;
  - controller adjusted remaining time at least `12,060` seconds;
  - worker adjusted remaining time at least `11,460` seconds.

The tracked bracket helper fails closed before formal admission. It does not
modify the raw status response, the admission implementation, the 30-second
future tolerance, or either remaining-time floor. Before its first helper
call, it exclusively creates the run-specific controller directory and writes
an attempt record. It snapshots the exact AIStation helper bytes, executes
those bytes in memory with the original helper path retained only for Node
dependency resolution, records the three raw responses and canonical proof,
then writes a terminal record hashing every preceding file. Any failed
capture leaves a durable failed terminal and cannot be recaptured under this
run ID.

On GPU2, the formal source rejects any missing, extra, non-regular, aliased,
or hash-drifting file; validates the attempt, helper snapshot, responses,
proof, completed terminal, run ID, formal SHA/tree, and suite manifest; checks
the current hostname, boot ID, and at-most-60-second publication age; and
immutably copies all seven files into the suite. Controller and worker
admissions revalidate that suite-local evidence and bind every clock-evidence
hash. The training configuration, model implementation, data, metric,
admission thresholds, and launch worker are otherwise unchanged.

The approved source hard-codes both the helper path and digest above; a
different caller-supplied JavaScript file or later helper drift fails before
capture. Suite publication uses exclusive per-file links. An interruption can
therefore leave a partial suite, but missing evidence makes admission fail
closed and this run remains terminally unretryable; partial publication can
affect availability, never authorize a worker.

## 5. Commands

Remote source, dependencies, cache, smoke, and initialization:

```bash
cd /huyang2/zoology
git fetch origin codex/repro-gdn-mqar-baseline-002
git checkout --detach "${FORMAL_SOURCE_SHA}"
test "$(git rev-parse HEAD)" = "${FORMAL_SOURCE_SHA}"
test -z "$(git status --porcelain)"
export AISTATION_TARGET=GPU2
export ZOOLOGY_EXPECTED_GIT_SHA="${FORMAL_SOURCE_SHA}"
./setup.sh
./run.sh check
./run.sh cache
./run.sh smoke
./run.sh init-baseline \
  /huyang2/zoology/runs/gdn-mqar-single-baseline-clockbracket-20260731T023001Z
```

The local controller performs exactly one formal capture after initialization:

```bash
cd /Users/torusmini/Documents/zoology-worktrees/baseline-002
test ! -e \
  artifacts/gdn-mqar-single-baseline-clockbracket-20260731T023001Z/controller
python3 -m repro.aistation_clock_bracket capture \
  --helper \
  /Users/torusmini/.codex/skills/aistation-skill/scripts/aistation_api.js \
  --output-dir \
  artifacts/gdn-mqar-single-baseline-clockbracket-20260731T023001Z/controller \
  --run-id \
  gdn-mqar-single-baseline-clockbracket-20260731T023001Z \
  --formal-source-sha "${FORMAL_SOURCE_SHA}"
```

This is the run's only allowed capture command. Whether it completes or
fails, the exclusive controller directory remains claimed and no second
capture is permitted.

The seven-file bundle contains `capture-attempt.json`, the exact
`helper-snapshot.js`, raw before/status/after responses, canonical
`clock-bracket.json`, and `capture-terminal.json`. A completed terminal hashes
the preceding six files. The whole directory is uploaded unchanged:

```bash
export AISTATION_HELPER=\
/Users/torusmini/.codex/skills/aistation-skill/scripts/aistation_api.js
node "${AISTATION_HELPER}" exec GPU2 -- \
  "mkdir -p /huyang2/zoology/artifacts/gdn-mqar-single-baseline-clockbracket-20260731T023001Z"
node "${AISTATION_HELPER}" push GPU2 -- \
  /Users/torusmini/Documents/zoology-worktrees/baseline-002/artifacts/gdn-mqar-single-baseline-clockbracket-20260731T023001Z/controller \
  /huyang2/zoology/artifacts/gdn-mqar-single-baseline-clockbracket-20260731T023001Z/
```

Its exact remote path is:

```text
/huyang2/zoology/artifacts/gdn-mqar-single-baseline-clockbracket-20260731T023001Z/controller
```

Publication, extraction of the bound values from the suite-local proof, and
the only formal launch execute inside one tracked Python process reached by
one GPU2 helper call. The command rechecks hostname, boot ID, and age after
publication and immediately before invoking `run.sh`, preventing a different
host from being substituted between those actions:

```bash
node "${AISTATION_HELPER}" exec GPU2 -- \
  "cd /huyang2/zoology && \
   ./.venv/bin/python -m repro.aistation_clock_bracket \
     publish-and-launch \
     --bundle-dir \
     /huyang2/zoology/artifacts/gdn-mqar-single-baseline-clockbracket-20260731T023001Z/controller \
     --suite-dir \
     /huyang2/zoology/runs/gdn-mqar-single-baseline-clockbracket-20260731T023001Z"
```

After an immutable completed terminal:

```bash
./run.sh finalize-baseline \
  /huyang2/zoology/runs/gdn-mqar-single-baseline-clockbracket-20260731T023001Z
./run.sh validate-baseline \
  /huyang2/zoology/runs/gdn-mqar-single-baseline-clockbracket-20260731T023001Z
./.venv/bin/python -m repro.suite_contract validate-cell \
  --index 5 \
  --suite-dir \
  /huyang2/zoology/runs/gdn-mqar-single-baseline-clockbracket-20260731T023001Z
```

## 6. Artifacts

The immutable manifest, source snapshot, seven-file clock capture, controller
and worker admissions, launch record, terminal, resolved config, metrics,
summary, logs, result, file inventory, archive hashes, formal Git SHA/tree,
GPU attestation, and safe extraction verification will be recorded here after
the terminal state is validated. The result's evidence map must contain 29
independently recomputed hashes: the prior 23 baseline evidence files with the
single status file replaced by all seven clock-capture files.

Models, data payloads, checkpoints, and optimizer state are excluded from Git
and from any GitHub release.

## 7. Results

No result exists before formal launch.

## 8. Conclusions

No scientific conclusion is permitted before terminal and artifact
validation.

## 9. Submission record

This is a reproduction baseline, not a competition submission. No submission
is planned.
