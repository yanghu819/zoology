# Experiment: E-GDN-MQAR-BASELINE-001

## 1. Metainfo

- Plan: `P-BASELINE-001`
- Run: `gdn-mqar-single-baseline-20260730T031705Z`
- State: `failed`
- Approved UTC: `2026-07-30T03:17:05Z`
- Started UTC (verified resource allocation and preflight; not worker launch):
  `2026-07-30T06:01:44Z`
- Ended UTC (trusted local closeout observation): `2026-07-30T06:24:50Z`
- Formal worker launch: never occurred; controller admission failed before
  request creation
- Target: logical AIStation `GPU2`
- AIStation workspace: `dceb3cf7-78de-4c02-bf2c-a3f8d27efe5f`
- Host: `ec8ev3phfepdd-0`
- Physical GPU:
  `GPU-0da20a4f-5e67-e47d-7aab-8c6efa2864ad` (`NVIDIA A100-SXM4-80GB`)
- Remote root: `/huyang2/zoology`
- Run directory:
  `/huyang2/zoology/runs/gdn-mqar-single-baseline-20260730T031705Z`
- Formal source commit:
  `3890b00f620a8f43ff3af25c471fbc14268c6fdd`
- Formal source tree:
  `75d4da2c40d1f8ece0751c8dbd9da2342fd5a3c8`
- The remote must clean-checkout that commit in detached mode. The immutable
  suite manifest will independently capture and bind the same SHA and tree at
  initialization.

This was intended to be a separately archived standalone rerun of a setting
already observed among the valid partial cells of the prior failed formal
12-cell reproduction. Those partial results informed the selection, but the
new worker never launched. This failed attempt produced no new model sample,
independent or otherwise.

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

The command entered only the controller-admission phase. It atomically wrote a
failed `controller-admission.json` and returned exit code 1 before
`cell_launcher` created a request. No launch or worker command followed.

The following predeclared successful-closeout commands were therefore not run:

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

- Remote suite:
  `/huyang2/zoology/runs/gdn-mqar-single-baseline-20260730T031705Z`
- Complete failure-evidence archive:
  `gdn-mqar-single-baseline-20260730T031705Z-complete-failure-evidence.tar.gz`
- Archive SHA-256:
  `7037f8e9967520d6d7f83e7f7cad475647950cbff68a4515b2c19d05c325deab`
- Archive sidecar SHA-256:
  `da7899bc3a761e4159448951e889af6701a03b154a1879bc4d24036cbecc0b88`
- Nineteen-file inventory SHA-256:
  `80a780ee05293eee59c0403b898f6defee7abaaf9a6fa18278a7def5e17af889`
- Saved AIStation status SHA-256:
  `ae6c4265b099a6403b9821ffd928596ef1c24a4504dac8128fbfd48b08e190fc`
- Failed controller-admission SHA-256:
  `73eef5803a45bd8e36eb41eaef679b8028486ecefe2c7d1791c2cd2f49bd5acd`
- Preflight log SHA-256:
  `aa42ab85c4a758dddac9d93f77afa9a761aab0490c04bbc2f58a1fe958436e09`
- Initialization log SHA-256:
  `19c9734b730cdb0ee4a451129e344e626065b9e8400627f2673207f506436c00`
- Controller wrapper log SHA-256:
  `b66bf1b166a3f6f3b975b70515eb726a789207792572f39f6fb21643d71fa60b`
- Local safe extraction:
  `/Users/torusmini/Documents/zoology/artifacts/release-verify/gdn-mqar-single-baseline-20260730T031705Z-complete-failure-evidence/safe.5zn4zoyz`
- Neutral archive tag:
  `archive/gdn-mqar-single-baseline-20260730-failed-prelaunch`

The deterministic archive contains the ten immutable suite files, the three
empty lifecycle directories, and nine suite-external preflight,
initialization, and controller control files. The 19 regular files were
inventory-verified remotely before and after archiving, pulled unchanged, and
independently verified locally. Verification rejected links, special files,
unsafe paths, duplicate members, hash drift, unexpected lifecycle evidence,
and credential-like content, including inside the nested source snapshot.

No request, launch, worker admission, terminal, run metadata, training log,
metrics, summary, result, model, optimizer state, or checkpoint was created.
Consequently no model, data, checkpoint, or optimizer state is present in Git
or in the GitHub release.

## 7. Results

Preflight completed with status 0 at `2026-07-30T06:05:27Z`, and the frozen
single-baseline suite initialized with status 0 at
`2026-07-30T06:07:31Z`. Source SHA/tree, the runtime, cache, smoke test, GPU2
workspace, and fixed configuration all passed their prelaunch checks.

The saved AIStation response reported 13,554 seconds remaining and was stamped
at Unix `1785391952` (`2026-07-30T06:12:32Z`). The remote controller checked at
Unix `1785391910`, producing:

```text
raw_age_seconds=-42
allowed_future_tolerance_seconds=30
AIStation observation timestamp is implausibly in the future:
observed=1785391952 now=1785391910
```

The remaining-time amount was sufficient for the 12,060-second controller
floor. The failure was instead the 42-second disagreement between the status
collector's clock and the remote verifier's clock, which exceeded the frozen
30-second future-timestamp tolerance. The immutable admission record has
`passed=false`, and the controller wrapper exited 1.

| Measure | Outcome |
| ------- | ------- |
| Reproduced final `valid/accuracy` | Not evaluated; worker never launched |
| Strong threshold `>=0.98` | Not evaluated |
| Visual-compatibility floor `>=0.96` | Not evaluated |
| Final KV256 diagnostic `>=0.88` | Not evaluated |
| Delta versus official visual approximation | Not available |

There is no valid or invalid model score. In particular, the prior partial
suite's `0.9859620536` pilot observation is not reused as this run's result.
This run cannot be compared numerically with the approximate official 0.99
plot point.

## 8. Conclusions

Decision: `failed`.

This is an infrastructure/orchestration failure before launch, not a training
failure and not a model result. The frozen no-retry rule applies: the status
timestamp was not edited, the 30-second tolerance was not relaxed, and no
second controller or worker was launched. The single-configuration hypothesis
is neither supported nor rejected.

The reusable lesson is that freshness checks spanning two hosts need either a
shared clock domain or an explicitly measured and bounded clock offset. Ample
lease time alone is insufficient. Any future attempt must be a separately
approved experiment that measures clock skew before formal launch; it cannot
retroactively repair this run.

Because no training occurred, this attempt supplies no new evidence for or
against the published GDN result or the Bitter Lesson.

## 9. Submission record

This is a reproduction baseline, not a competition submission. No submission
was made. No `exp/score-*` tag exists because there is no score; only the
neutral failure-evidence archive is published.
