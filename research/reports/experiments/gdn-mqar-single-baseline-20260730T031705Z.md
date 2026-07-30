# Experiment: E-GDN-MQAR-BASELINE-001

## 1. Metainfo

- Plan: `P-BASELINE-001`
- Run: `gdn-mqar-single-baseline-20260730T031705Z`
- State: `approved`
- Approved UTC: `2026-07-30T03:17:05Z`
- Target: logical AIStation `GPU2`
- Remote root: `/huyang2/zoology`
- Run directory:
  `/huyang2/zoology/runs/gdn-mqar-single-baseline-20260730T031705Z`
- Formal source: the clean detached Git HEAD captured by the immutable suite
  manifest at initialization. Its exact SHA and tree will be copied into
  section 6 after terminal validation.

This is a separately archived standalone rerun of a setting already observed
among the valid partial cells of the prior failed formal 12-cell reproduction.
Those partial results are used here as pilot evidence. This run is not a
statistically independent sample.

## 2. Hypothesis

The official-grid configuration assigned local harness index 5 should provide
a persuasive single-setting Gated DeltaNet MQAR baseline: near the official
PNG reading of approximately 0.99 while using a 67,072-byte state-size proxy,
about one quarter of the d256 point.

The setting was selected after seeing the three valid partial d128 cells from
the prior failed formal reproduction. Their final accuracies occupied a narrow
range, and learning rate `10^-2.5` was the best stable interior point. These
partial results are used as pilot evidence, so this is a pilot-informed
selection, not a blind replication.

The decision was frozen before launch:

- final overall `valid/accuracy >= 0.98`: strong project baseline pass;
- `0.96 <= accuracy < 0.98`: strong hypothesis rejected, but compatible with
  the approximate 0.99 PNG reading under the project's 0.03 visual tolerance;
- final overall accuracy `< 0.96`: below the visual compatibility band;
- final KV256 accuracy `< 0.88`: non-official diagnostic anomaly. It does not
  change the overall classification, but prevents unqualified adoption as
  this fork's canonical baseline.

The 0.98 threshold is a project decision, not an upstream threshold. The 0.88
line is a project diagnostic threshold informed by the valid partial d128
results from the prior failed formal reproduction. The 0.96 floor is not a
confidence interval or error bar.

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

No model, data, optimizer, epoch, stopping, or metric field may change after
launch. No other learning rate or width may run in this experiment.

## 4. Environment

- Upstream result-publication snapshot:
  `b386338b37ce46a9257afc0a64786b0dc5a37676`
- Vendored FLA:
  `d30c0833f9286bd5bf43c20395db53c6bab97a2d`
- Python: `3.10.11`
- uv: `0.9.27`
- PyTorch: `2.7.0+cu126`
- torchvision: `0.22.0+cu126`
- Formal execution requires:
  - exact pushed source SHA;
  - clean detached checkout;
  - physical root `/huyang2/zoology`;
  - literal logical target `GPU2`;
  - a fresh, saved AIStation status response naming `GPU2`, `Running`, and its
    workspace ID;
  - controller adjusted remaining time at least `12,060` seconds;
  - worker adjusted remaining time at least `11,460` seconds.

The 600-second gap between controller and worker floors is reserved for launch,
setup, cache validation, and runtime attestation. Both decisions are written
as immutable JSON and their hashes are bound into launch, terminal, and result
evidence. Controller admission hash-freezes the selection manifest. The final
result separately binds the complete request, launch, and terminal records by
SHA-256, together with every retained source, config, metric, log, and runtime
evidence file. Validation rejects any chronology outside manifest → controller
→ request → launch → worker → terminal.

## 5. Commands

Remote source and smoke:

```bash
cd /huyang2/zoology
git fetch origin codex/repro-gdn-mqar
git checkout --detach "${FORMAL_SOURCE_SHA}"
test -z "$(git status --porcelain)"
export AISTATION_TARGET=GPU2
export ZOOLOGY_EXPECTED_GIT_SHA="${FORMAL_SOURCE_SHA}"
./setup.sh
./run.sh check
./run.sh cache
./run.sh smoke
./run.sh init-baseline \
  /huyang2/zoology/runs/gdn-mqar-single-baseline-20260730T031705Z
```

The local controller saves one fresh
`aistation_api.js status GPU2` response and uploads it unchanged to:

```text
/huyang2/zoology/runs/gdn-mqar-single-baseline-20260730T031705Z/aistation-status.json
```

Formal launch:

```bash
export ZOOLOGY_REMAINING_SECONDS="${GPU2_REMAIN_TIME_FROM_SAVED_STATUS}"
export ZOOLOGY_REMAINING_OBSERVED_UNIX="${SAVED_STATUS_OBSERVED_UNIX}"
./run.sh launch-baseline \
  /huyang2/zoology/runs/gdn-mqar-single-baseline-20260730T031705Z
```

After the immutable terminal says `completed`:

```bash
./run.sh finalize-baseline \
  /huyang2/zoology/runs/gdn-mqar-single-baseline-20260730T031705Z
./run.sh validate-baseline \
  /huyang2/zoology/runs/gdn-mqar-single-baseline-20260730T031705Z
./.venv/bin/python -m repro.suite_contract validate-cell \
  --index 5 \
  --suite-dir \
  /huyang2/zoology/runs/gdn-mqar-single-baseline-20260730T031705Z
```

## 6. Artifacts

The immutable manifest, source snapshot, status response, controller and worker
admission records, launch record, terminal, resolved config, metrics, summary,
logs, result, file inventory, archive hashes, formal Git SHA/tree, GPU
attestation, and safe extraction verification will be recorded here after the
terminal state is validated.

Models and checkpoints are excluded from Git and from the GitHub release.

## 7. Results

No result exists before formal launch.

## 8. Conclusions

No conclusion is permitted before terminal and artifact validation.

## 9. Submission record

This is a reproduction baseline, not a competition submission. No submission
is planned.
