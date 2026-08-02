# Experiment: E-GDN-MQAR-BASELINE-008

## 1. Metainfo

- Plan: `P-BASELINE-008`
- Run: `gdn-mqar-single-baseline-p008-20260801t092653z`
- State: `failed / Halt before admission / no retry`
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
- Allocation replacement UTC: `2026-08-01T09:46:58Z` attempt;
  `2026-08-01T09:47:01Z` complete receipt
- Replacement request: `09747b2f-6916-4813-ab33-7aebb5ce3b3b`, returned
  `Pending` with placeholder `resource=GPU:1`, `remainTime=-`, and the unchanged
  image
- Ended UTC: `2026-08-02T05:11:06Z`

The report and run ID were absent and accepted by both production run-ID
validators before this record was created. The approval ledger was pushed and
GitHub-verified at exact commit `4aab2526d41862910c1b307e46396c9c2f56cbe8`.
The one authorized replacement then preserved the predecessor as Running on
the exact A100 with `remainTime=5264`, consumed the sole restart, and returned
the new Pending request above with the unchanged image and exact pause/resume
actions. That allocation transition was pushed and GitHub-verified at exact
commit `d6e39914f95dc6e6978ae47649fe089045f48fd0`. A subsequent no-clobber
status still found the request Pending. The next no-clobber status, observed at
`2026-08-02T05:11:06Z`, bound the same request and image but reported `Halt`,
placeholder `resource=GPU:1`, and `remainTime=-292`. The predeclared contract
makes Halt before admission terminal and forbids a second restart. No remote
P008 path, admission, suite, controller, capture, worker, training process,
model, metric, or score was created or observed by this workflow.

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
- Request before the consumed replacement:
  `b0411955-3f8d-445d-a164-2bd435f8be1f`
- Predecessor disposition: the one fresh status at `2026-08-01T09:46:58Z`
  bound it as Running on exact `NVIDIA-A100-SXM4-80GB:1` with
  `remainTime=5264`; the subsequent exact pause/resume replacement retired it
- Current request: `09747b2f-6916-4813-ab33-7aebb5ce3b3b`
- Current request disposition: `Halt`, placeholder `resource=GPU:1`,
  `remainTime=-292`; image unchanged; the single P008 restart is consumed and
  the run is terminal failed before admission

The request never reached a captured strict initial admission. There is no GPU
UUID, host, boot ID, admitted lease, probe, SSH, CUDA identity, or remote
mutation evidence. Sparse polling cannot prove whether AIStation briefly
scheduled the request between the saved Pending and Halt observations; it can
prove that this workflow never admitted or used it. The scientific hypothesis
therefore remains untested.

## 5. Planned commands and evidence

1. **Complete.** The P008 approval ledger is GitHub-verified at exact commit
   `4aab2526d41862910c1b307e46396c9c2f56cbe8`.
2. **Complete and GitHub-verified.** One fresh
   no-clobber literal-GPU2 status bound predecessor request `b0411955...` as
   Running on the exact A100 with 5,264 seconds. The sole restart returned new
   Pending request `09747b2f...`, unchanged image, placeholder `GPU:1`, and
   exact pause/resume actions. Commit `d6e3991...` binds this transition. No
   second restart is allowed.
3. **Terminal.** Status `0002` preserved Pending without actions. Status `0003`
   bound the same request and image as Halt with `remainTime=-292`. Per the
   frozen contract, P008 stopped without probe, SSH, admission, or restart.
4. **Not reached.** No remote path, checkout, launcher upload, or operation
   receipt exists.
5. **Not reached.** The production-PTY/exact-53 gate was never started.
6. **Not reached.** No preflight, initialization, or real-A100 smoke exists.
7. **Not reached.** No formal capture, publication, start, or worker exists.
8. **Complete locally.** Because no remote path existed, there was nothing to
   pull. The complete allowed local evidence was inventoried, safely archived,
   extracted under a separate verification directory, and checked
   member-by-member before the terminal ledger update.

Kill criteria are fail-closed: helper/control hash drift; wrong row, image,
request, resource, host, boot ID, or GPU; ambiguous/multiple active requests;
failed restart; admission below 13,200; transport/start/TTY/identity/quiescence
failure; Linux count other than exact 53/0; source/tree/inventory/runtime drift;
pre-capture below 12,120; capture below 12,060; clock bracket above 15 seconds;
publication age above 60 seconds; a second capture/start/cell; invalid or
incomplete result; or timeout. Any such condition closes P008 terminally with
no retry.

## 6. Artifacts

Local no-clobber allocation evidence is under
`artifacts/admission-gdn-mqar-single-baseline-p008-20260801t092653z/`:

- Pre-restart status SHA-256:
  `81fc9d359c95037ef55abfb70dca18420b53dca945655bfa2e4da98298a79114`
- Restart-attempt SHA-256:
  `8b38c64ba86f38f49360773b4b9df353da118cd092f274521cac979419c76ab7`
- Raw restart-response SHA-256:
  `e93a04f66819a23ed09f966f0cc661b9008860fdcdb73dcdc0374a9924dff94f`
- Complete restart-receipt SHA-256:
  `8decfd34b70924222cd154969a91fd0394fbfa57335ed8a6de27723b7e0ca136`
- Both helper stderr files are empty with SHA-256
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- Helper SHA-256 before, during, and immediately before receipt:
  `628aefaa2de3eb09ad5e6e1397e04280650e01847da2d9192566137405230226`
- No-clobber restart-controller SHA-256:
  `aff68bba18d6deccd85cbec522ab7b38074a47d98f9e2ce88d76925dbc4fae7d`
- First post-ledger Pending status SHA-256:
  `b09979dc580fef831c6668a67508b949985a69ecfaff4f014976346d01c6ceb9`
- Terminal Halt status SHA-256:
  `2ca7d98bfa0d2e01d2e5a27464a2b27090c43fc0467c3949b3f4f6cc2c3c7833`
- Complete safe inventory:
  `artifacts/gdn-mqar-single-baseline-p008-20260801t092653z/complete-failure-evidence-inventory.tsv`,
  SHA-256
  `fc16ccde117e99de0a7faec7913855c27f21d356c0522724aba45fa3daffbe5f`;
  it closes over `14` source files: four one-shot local controllers and ten
  local allocation/status evidence files
- Complete safe archive:
  `artifacts/gdn-mqar-single-baseline-p008-20260801t092653z/gdn-mqar-single-baseline-p008-20260801t092653z-complete-failure-evidence.tar.gz`,
  `7,893` bytes, SHA-256
  `718984849f01b39d150c1e59b00443d931f14ac606202208a5bff758e2cc82a2`;
  sidecar SHA-256
  `3f9faed34bccffa08a0193a23b2318f78d8868fd843de7590be48e57eac31b7f`
- Independent verification record:
  `artifacts/gdn-mqar-single-baseline-p008-20260801t092653z/complete-failure-evidence-verification.json`,
  SHA-256
  `27d14da4696b02e9f7cd82d46b08e4b31477253eb90fd66b1c0a01fcf624eb64`;
  the extracted archive has `15` regular files and `3` directories with zero
  links, special members, forbidden model/data/checkpoint paths, or
  credential-like fields, and all `14` inventory entries matched exactly

No remote P008 path was created or observed by this workflow, so no remote pull
was applicable. The archive contains no model weights, datasets, caches,
checkpoints, or secrets.

## 7. Results

Terminal failed before admission. No worker, training metric, model, or score
exists. This is an allocation failure, not a scientific result.

## 8. Official comparison

No reproduced value exists, so no delta can be computed. The official visual
reference remains approximately 0.99 for the matching state-size point and is
not compared to an allocation failure.

## 9. Decision and reusable lesson

P008 is terminal `failed / Halt before admission`, unretried, and must never be
restarted or reopened. The one fresh allocation returned Pending, was still
Pending at the next saved status, and was Halt with `remainTime=-292` at the
following saved status. This workflow never obtained a strict admission and
never touched the remote environment. The repaired production-PTY control was
therefore not exercised, and the unchanged Gated DeltaNet accuracy hypothesis
remains untested. Sparse polling lost the only usable opportunity if the
request ever became Running: future separately approved allocation attempts
must have an active watcher that can immediately perform the GitHub-verified
strict admission while the lease is fresh. That is an operational lesson, not
permission to retry P008 or alter its science.
