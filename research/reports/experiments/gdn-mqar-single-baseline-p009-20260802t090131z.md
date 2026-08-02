# Experiment: E-GDN-MQAR-BASELINE-009

## 1. Metainfo

- Plan: `P-BASELINE-009`
- Run: `gdn-mqar-single-baseline-p009-20260802t090131z`
- State: `approved / watcher activation and fresh allocation pending`
- Watcher phase: `armed-unallocated`
- Proposed UTC: `2026-08-02T09:01:31Z`
- Approved UTC: `2026-08-02T09:01:31Z`
- Approval: after P008 was closed as terminal failed and the assistant explicitly
  requested a separate `批准 P009`, the user replied `jixu`; this authorizes
  one separately tracked P009 with unchanged science, one active watcher, and
  one fresh literal-GPU2 allocation
- Target: logical AIStation `GPU2` only; GPU1 is outside scope and must never be
  queried, probed, opened, stopped, or mutated
- Parent: `P-BASELINE-008`, immutable terminal `failed` at GitHub-verified
  commit `9329eac8d56746ff273fc6642b809d18c18fa233`; P009 neither reopens nor
  retries P008 or its consumed request
- Parent request: `09747b2f-6916-4813-ab33-7aebb5ce3b3b`, last saved as `Halt`
  with placeholder `resource=GPU:1` and `remainTime=-292`
- Remote root: `/huyang2/zoology`
- Formal source commit:
  `13f880b5fe61619a1006ef33610de69fbabaaec1`
- Formal source tree:
  `ed83a7188351ca2cce8aba46d1cb3b108ce31ec2`
- GitHub-verified operational-control commit:
  `b69aeb8bedb387f321c1d771ae7c3157aec789df`
- GitHub-verified operational-control tree:
  `a33960686f52c8c8d5c6b44029229f0f9cfcf950`
- Durable Linux envelope SHA-256:
  `785ad8162bc831b762e84e0297effadf355893083b802fccc7ab5d10515a6f8d`
- Linux exact-test gate SHA-256:
  `2ceb337fbdd304222491511a6dca6010be4a600fcd19295420d598eb6b5546a4`
- Durable-envelope test SHA-256:
  `f352c7d610b3f29e1e6dd8acf78ed24479a15bf2b75b43caf6d6ac350ba307d6`
- Frozen admission module SHA-256:
  `68fa3af301f7b88d3bffb3fd17add8db2db9ae26d2e573a32f2944f02465121b`
- Approved helper SHA-256:
  `628aefaa2de3eb09ad5e6e1397e04280650e01847da2d9192566137405230226`
- Watcher prompt SHA-256:
  `b615ae0938fca8120633108d9c92796c532d3d2f15813503c53374aacb95b5b6`
- One-shot open controller SHA-256:
  `67d20c527bd3e5c886c43fa806046bc77e319e2beb6d8ecc18bfcfc0b7b5bdb3`
- Status-only watcher controller SHA-256:
  `4ef35323382781af8ad7eb4279e11ab1131c3c2d8e637dddb9c82225a981ec5d`
- Frozen image:
  `192.168.108.1:5000/pytorch/ptv-qianliujia:python310_torch2.7`
- Local operational-control verification inherited from the frozen operational
  commit: `107 passed`, `50 skipped`, `0 failed`; every skip required Linux
  `/proc`, `setsid`, or a controlling PTY

Both production run-ID validators accepted the all-lowercase run ID, and its
report, admission directory, artifact root, and run directory were absent
before this record was created. This record is not authority for any external
action until its commit, tree, and changed blobs are pushed and independently
verified from GitHub. The existing heartbeat remains paused with a stale P006
prompt until that verification. After verification, the same automation ID is
atomically updated to the exact frozen P009 prompt and activated before any
fresh allocation status or open action.

## 2. Hypothesis

Local official-grid harness index 5 is a persuasive single-setting Gated
DeltaNet MQAR baseline. On the historical standard test mixture, the unchanged
cell should finish with overall final `valid/accuracy >= 0.98`, near the
official PNG's approximately 0.99 visual reading, and final KV256 accuracy
`>= 0.88`, while using a 67,072-byte state-size proxy.

P008 did not test that science. Its fresh request was saved as Pending and next
saved as Halt, with no admission or remote use. Sparse continuation polling
could have missed a short Running lease. P009 therefore changes one operational
mechanism only: the GitHub-bound one-minute watcher must be demonstrably active
before the fresh allocation exists, and the main agent's frozen controller
writes a durable proof of that active configuration before its sole
status/open sequence can allocate.

This intervention predicts that the workflow will catch the first Running
state while at least 13,200 seconds remain and immediately execute the already
frozen strict admission. It is decision-changing because a successful
admission finally exercises the repaired production-PTY control and the single
scientific cell; another allocation loss instead falsifies the watcher/control
path without being misreported as a model result. No architecture, data,
optimizer, seed, width, learning rate, epoch budget, threshold, metric, or
comparison rule changes.

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
- Required resource at admission: exactly `NVIDIA-A100-SXM4-80GB:1`
- Initial remaining-time floor: `13,200` seconds
- Pre-capture remaining-time floor: `12,120` seconds
- Formal captured remaining-time floor: `12,060` seconds
- Maximum formal clock bracket: `15` seconds
- Maximum capture-to-publication age: `60` seconds
- Predecessor request: `09747b2f-6916-4813-ab33-7aebb5ce3b3b`
- Predecessor disposition: terminal P008 `Halt`; immutable prior evidence only
- P009 request: not created
- P009 GPU UUID, host, boot ID, resource, and lease: not observed

P009 may consume exactly one `open GPU2` action, never `restart`, and only after
the active watcher obtains a fresh unchanged status that still binds the
predecessor request as Halt. The open controller writes an exclusive attempt
receipt before the call, so any timeout or ambiguous response consumes the
sole allocation action. It requires a new request ID, unchanged image, exact
`start_requested` from `Halt`, and no more than one active request. The new
allocation transition must be committed, pushed, and GitHub-verified before a
subsequent status or admission.

Pending, Queuing, and ImagePulling are status-only. Running enters exactly one
`repro.aistation_admission_gate` phase-initial capture and verify; neither the
watcher nor the agent may probe or SSH directly. The gate must bind the
ledgered request, exact A100 string, GPU UUID, host, boot ID, helper-driven
probe/SSH/CUDA availability, stable identity, and at least 13,200 seconds before
any remote mutation. A failed gate, insufficient lease, generic resource,
identity drift, or Halt is terminal P009 failure and never authorizes a second
allocation.

## 5. Planned commands and evidence

1. **Approval ledger.** Commit this report, the P009 plans row, the exact
  watcher prompt, and both no-clobber allocation controllers. Push and verify
   the GitHub branch ref, commit, tree, parent, and every changed blob. No
   AIStation call is allowed before that verification.
2. **Watcher before allocation.** Atomically update the existing
   `run-zoology-gpu2-single-baseline` heartbeat from its paused stale P006
   prompt to the exact frozen P009 prompt and `ACTIVE`, preserving the
   one-minute cadence and target thread. Verify the automation view and config
   hash. While GitHub says `armed-unallocated`, the active heartbeat makes zero
   AIStation calls and is permanently forbidden from open/restart/stop.
3. **One allocation action.** The main agent exclusively runs the frozen open
   controller after proving the watcher ACTIVE. The controller first writes
   `watcher-activation-0001.json` with the automation config hash, then
   validates helper hash before and
   after one fresh `status GPU2`, requires the exact predecessor Halt state and
   unchanged image, writes `open-0001.attempt.json`, and invokes `open GPU2`
   exactly once. It requires a new request ID and exact start action. Raw
   stdout/stderr and success or failure receipts are exclusive and fsynced.
   Any failure is terminal; never call open or restart again.
4. **Allocation publication.** After the controller releases its operation
   lock, the main agent atomically reacquires the same lock before any ledger
   write; if busy, it makes zero writes and yields completely to heartbeat
   recovery. The sole lock owner, without another AIStation call, updates this
   report to watcher phase `monitoring`, plans.md, and the resource
   ledger with old/new request identities, state, image, raw hashes, controller
   hash, and UTC, and holds the lock through GitHub verification. Commit, push,
   and GitHub-verify before any next status, then release the lock. A
   heartbeat finding an unpublished immutable allocation receipt performs only
   publication recovery with zero new AIStation calls.
5. **Status or initial admission.** Once the allocation transition is
   GitHub-verified, run the frozen status-only controller at most once per
   heartbeat with the next numbered no-clobber sequence and ledgered request.
   Pending, Queuing, or ImagePulling ends status-only. Halt closes P009. Running
   immediately enters the single frozen initial admission capture and verify;
   any exact-resource, request, identity, availability, or 13,200-second failure
   closes P009 before remote mutation. A status failure receipt or orphan raw
   status without a valid matching receipt is also terminal and forbids another
   status sequence.
6. **In-progress publication.** After successful initial admission, bind the
   request, exact resource, GPU UUID, host, boot ID, lease, helper/admission
   evidence, and UTC in the report/plans/resource ledger. Commit, push, and
   GitHub-verify before any remote setup.
7. **Exact source and launcher.** Through the admitted helper only, use
   exclusive run-operation receipts. In `/huyang2/zoology`, fetch from GitHub,
   clean checkout `--detach` the exact formal source, preserve repo-local
   `.venv`, caches, artifacts, models, and runs, and upload the exact frozen
   19-file launcher from operational commit `b69aeb8...`.
8. **Repaired production PTY gate.** Through the production helper PTY, run the
   repaired durable Linux envelope. It must publish a correctly detached
   worker, prove no controlling TTY and exact process identity, run exactly 53
   tests with 0 skipped, verify its JUnit/terminal/quiescence, and leave no
   residual process. Any deviation is terminal.
9. **Preflight and initialization.** Run the audited setup, check, cache,
   real-A100 GDN smoke, durable preflight plus verifier, and durable
   init-baseline plus verifier, each with a unique advancing-operation receipt.
   No live-lease design work or extra experiment is permitted.
10. **One formal capture and start.** Require a new admission with at least
    12,120 seconds before capture. Perform one formal clock capture with at
    least 12,060 seconds and bracket at most 15 seconds. Bind and verify the
    seven-file bundle, upload and remotely validate it, then make exactly one
    durable formal start within 60 seconds of publication. Launch only the
    index-5 worker. No second capture, start, or cell is allowed.
11. **Read-only monitoring and closeout.** Monitor after launch without
    mutation. At terminal state validate, safely archive allowed evidence,
    pull and independently verify it, and update Sections 6-9, plans.md,
    resource ledger, and leaderboard.csv without overstating. Commit, push,
    and GitHub-verify. Tag only a complete valid strong result, then pause the
    same heartbeat.

Kill criteria are fail-closed: watcher not active before allocation; watcher
lock/cadence/evidence drift; helper, prompt, controller, control, source, or tree
hash drift; wrong row, image, request, state, action, resource, host, boot ID,
or GPU; ambiguous or multiple active requests; allocation timeout; admission
below 13,200; transport/start/TTY/identity/quiescence failure; Linux count other
than exact 53/0; runtime or inventory drift; pre-capture below 12,120; capture
below 12,060; clock bracket above 15 seconds; publication age above 60 seconds;
a second allocation, admission, capture, start, or cell; invalid or incomplete
result; or timeout. Any such condition closes P009 with no retry.

## 6. Artifacts

Prepared GitHub-safe controls:

- Watcher prompt:
  `artifacts/gdn-mqar-single-baseline-p009-20260802t090131z/watcher/heartbeat-prompt.txt`
- One-shot open controller:
  `artifacts/gdn-mqar-single-baseline-p009-20260802t090131z/allocation-control/open_gpu2_once.py`
- Status-only controller:
  `artifacts/gdn-mqar-single-baseline-p009-20260802t090131z/allocation-control/status_gpu2_once.py`
- Future no-clobber allocation/admission evidence:
  `artifacts/admission-gdn-mqar-single-baseline-p009-20260802t090131z/`

No P009 allocation response, remote path, admission, suite, worker, model,
metric, archive, or score exists yet. Model weights, datasets, caches,
checkpoints, credentials, and secrets are forbidden from GitHub artifacts.

## 7. Results

Pending. The scientific cell has not started and no metric exists.

## 8. Official comparison

Pending. No reproduced value exists, so no delta can be computed. The official
visual reference remains approximately 0.99 for the matching state-size point.

## 9. Decision and reusable lesson

P009 is approved because the unchanged model hypothesis remains scientifically
untested and the next intervention is operationally decisive: the watcher is
established before consuming the only allocation action. This avoids spending
another lease under sparse polling. If the watcher and strict admission succeed,
the already-frozen repaired PTY gate and single baseline proceed without design
changes. If any watcher, allocation, admission, or later gate fails, P009 closes
terminally and unretried; no result or official comparison is inferred.
