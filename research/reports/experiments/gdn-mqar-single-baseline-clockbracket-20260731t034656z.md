# Experiment: E-GDN-MQAR-BASELINE-003

## 1. Metainfo

- Plan: `P-BASELINE-003`
- Run: `gdn-mqar-single-baseline-clockbracket-20260731t034656z`
- State: `in-progress`
- Approved UTC: `2026-07-31T03:46:56Z`
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

Pending terminal validation. Models, datasets, checkpoints, and optimizer
state will not be uploaded.

## 7. Results

No result exists before formal launch.

## 8. Conclusions

No scientific conclusion is permitted before terminal validation.

## 9. Submission record

This is a reproduction baseline, not a competition submission.
