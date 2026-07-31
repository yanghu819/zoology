# Experiment: E-GDN-MQAR-BASELINE-003

## 1. Metainfo

- Plan: `P-BASELINE-003`
- Run: `gdn-mqar-single-baseline-clockbracket-20260731t034656z`
- State: `failed`
- Approved UTC: `2026-07-31T03:46:56Z`
- Formal capture started UTC: `2026-07-31T03:53:01.853365Z`
- Ended UTC: `2026-07-31T03:53:12.647071Z`
- Approval: the user's instruction `continue`
- Target: logical AIStation `GPU2`
- Remote root: `/huyang2/zoology`
- Formal source SHA: `13f880b5fe61619a1006ef33610de69fbabaaec1`
- Formal source tree: `ed83a7188351ca2cce8aba46d1cb3b108ce31ec2`
- Parent experiment: `P-BASELINE-002`, terminal `failed`

This is a separately tracked run with a new all-lowercase identifier and a new
suite. It does not recapture, reopen, overwrite, or launch either failed run.
The exact formal source and scientific setting remain unchanged because
`P-BASELINE-002` was rejected before status capture or worker launch.

## 2. Hypothesis

Local official-grid harness index 5 should provide a persuasive single-setting
Gated DeltaNet MQAR baseline: final overall `valid/accuracy >= 0.98`, near the
official PNG reading of approximately 0.99, while using a 67,072-byte
state-size proxy. `0.96 <= accuracy < 0.98` is only visually compatible;
final KV256 accuracy `>=0.88` is diagnostic, not an upstream threshold.

## 3. Configuration

- Local official-grid harness index: `5`
- `d_model`: `128`
- Learning rate: `0.0031622776601683794` (`10^-2.5`)
- Seed and data seed: `123`
- Maximum epochs: `32`
- Hard timeout and grace: `10,800/60` seconds
- Train/test examples: `180,000/7,000`
- Train/test batches: `256/32`
- Vocabulary: `8192`
- Optimizer/scheduler: AdamW with cosine decay
- Weight decay: `0.1`
- Early stop: strictly when an epoch's `valid/accuracy > 0.99`

No model, data, optimizer, stopping rule, metric, width, learning rate, seed,
epoch budget, or threshold may change.

## 4. Environment and admission

- AIStation workspace: `63e6715f-0e16-4128-87f2-97d867d2d602`
- GPU: `NVIDIA A100-SXM4-80GB`
- GPU UUID: `GPU-573c7ed1-1c51-8334-299b-edf2ff3440e6`
- Hostname: `c1psj7eh98ftq-0`
- Boot ID: `08d861e6-ce7b-4fe8-ba78-de529efd1b31`
- Approved helper SHA-256:
  `628aefaa2de3eb09ad5e6e1397e04280650e01847da2d9192566137405230226`

The formal source must be a clean detached checkout. Exactly one seven-file
clock bundle may be captured under the new run ID. It must bind the unchanged
Running GPU2 workspace, hostname, boot ID, a bracket of at most 15 seconds,
at least 12,060 seconds remaining, and a completed terminal. Publication and
launch run in one GPU2 process, with a second host/boot/age check no more than
60 seconds after the selected remote-before timestamp. Controller and worker
admissions remain unchanged.

## 5. Commands

Initialize only the new suite:

```bash
export AISTATION_TARGET=GPU2
export ZOOLOGY_EXPECTED_GIT_SHA=13f880b5fe61619a1006ef33610de69fbabaaec1
./run.sh init-baseline \
  /huyang2/zoology/runs/gdn-mqar-single-baseline-clockbracket-20260731t034656z
```

Capture, upload unchanged, then publish and launch exactly once:

```bash
python3 -m repro.aistation_clock_bracket capture \
  --helper /Users/torusmini/.codex/skills/aistation-skill/scripts/aistation_api.js \
  --output-dir artifacts/gdn-mqar-single-baseline-clockbracket-20260731t034656z/controller \
  --run-id gdn-mqar-single-baseline-clockbracket-20260731t034656z \
  --formal-source-sha 13f880b5fe61619a1006ef33610de69fbabaaec1

./.venv/bin/python -m repro.aistation_clock_bracket publish-and-launch \
  --bundle-dir \
  /huyang2/zoology/artifacts/gdn-mqar-single-baseline-clockbracket-20260731t034656z/controller \
  --suite-dir \
  /huyang2/zoology/runs/gdn-mqar-single-baseline-clockbracket-20260731t034656z
```

## 6. Artifacts

- Remote initialized suite:
  `/huyang2/zoology/runs/gdn-mqar-single-baseline-clockbracket-20260731t034656z`
- Complete failure-evidence archive:
  `gdn-mqar-single-baseline-clockbracket-20260731t034656z-complete-failure-evidence.tar.gz`
- Archive SHA-256:
  `a820c4aee2706547b18341830c419d8b78ffad168c833c6837e81d8f514926d0`
- Archive sidecar SHA-256:
  `93d1bd09a2104c5eca014406f136ddfb07d8bd94821e4a9d71017fd5ca916cb5`
- Seventeen-file inventory SHA-256:
  `93c7105f067b277560c22366c0607e3c8c107adb1c564ef7c0cf94c8379fc1db`
- Failed capture terminal SHA-256:
  `cfed497e1998a810d43bb4a87551ce718ebe7189ee6ee8e61ad568f31364baec`
- Unchanged AIStation status SHA-256:
  `86014e77e4b73f1b10207eacd485da457407cd1f152bbc99262cc05d2bb19932`
- Suite manifest SHA-256:
  `b8815ab3e7454b4a4fbba58cbb8a6dbb5f2a421789ff67ef53130bc7aeeb3ef4`
- Local safe extraction:
  `/Users/torusmini/Documents/zoology-worktrees/baseline-002/artifacts/gdn-mqar-single-baseline-clockbracket-20260731t034656z/verify.BgT1GJ`

The archive contains the six-file failed controller capture, eight immutable
suite files, and three initialization control files. Remote and local hashes
match for all eleven remotely sourced files. Independent verification rejected
links, special files, unsafe or duplicate paths, hash drift, lifecycle
evidence that would imply a launch, and credential-like content. The nested
source snapshot contains 583 safe members.

No controller/worker admission, launch request, worker terminal, training log,
metrics, result, model, dataset payload, checkpoint, optimizer state, or score
exists. None is present in Git or the evidence archive.

## 7. Results

The capture used the exact formal source and approved helper. GPU2 remained
`Running` under workspace `63e6715f-0e16-4128-87f2-97d867d2d602`.
The before/after observations bound hostname `c1psj7eh98ftq-0`, boot ID
`08d861e6-ce7b-4fe8-ba78-de529efd1b31`, and remote Unix seconds
`1785469731..1785469737`.

The unchanged status response reported `remainTime=11999`. The frozen
controller floor was `12060`, so the exactly-once capture terminated with:

```text
AIStation GPU2 remaining time is below the frozen controller floor:
remaining=11999 required=12060
```

The shortfall was 61 seconds. Because the failure preceded canonical proof
creation, the failed bundle correctly contains six rather than seven files.
It was not uploaded or published, and `publish-and-launch` was not called.

| Measure | Outcome |
| ------- | ------- |
| Reproduced final `valid/accuracy` | Not evaluated; worker never launched |
| Strong threshold `>=0.98` | Not evaluated |
| Visual-compatibility floor `>=0.96` | Not evaluated |
| Final KV256 diagnostic `>=0.88` | Not evaluated |
| Delta versus official visual approximation | Not available |

## 8. Conclusions

Decision: `failed`.

This is a lease-budget failure before admission or launch, not a Gated
DeltaNet result. The unchanged floor rejected the run; no threshold was
relaxed and the consumed capture ID was not retried. The model hypothesis is
neither supported nor rejected.

The reusable lesson is that `Running` is not synonymous with enough remaining
lease for a formal worker. A future, separately approved experiment would need
a fresh GPU2 lease that clears the complete controller floor before its formal
capture. This experiment supplies no evidence for or against the Bitter
Lesson because no learning process ran.

## 9. Submission record

This is a reproduction baseline, not a competition submission. No submission
was made and no `exp/score-*` tag is permitted because there is no score.
