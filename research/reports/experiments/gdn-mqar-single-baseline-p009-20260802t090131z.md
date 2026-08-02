# Experiment: E-GDN-MQAR-BASELINE-009

## 1. Metainfo

- Plan: `P-BASELINE-009`
- Run: `gdn-mqar-single-baseline-p009-20260802t090131z`
- State: `failed / Running resource mismatch before admission / no retry`
- Watcher phase: `terminal`
- Proposed UTC: `2026-08-02T09:01:31Z`
- Approved UTC: `2026-08-02T09:01:31Z`
- Ended UTC: `2026-08-02T10:41:29Z` (terminal raw/failure file mtime,
  Unix `1785667289`)
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
- GitHub-verified allocation-control approval commit:
  `fcc4afc1e9c8eb397f85335e72d9f778abcd836e`
- GitHub-verified allocation-control approval tree:
  `b1485aad203c9f96d90dad4f6fd5861658b86144`
- GitHub-verified allocation publication commit:
  `ad3a1c9eab1b45e14ac4e74aca9f23e2d6eaefc3`
- GitHub-verified allocation publication tree:
  `ebdd0ae43f4f050e65ae5a92792bde22e1ac6ce5`
- Active automation config SHA-256 at allocation:
  `84f7406cede086a527e31922740c0bd5c60872fdc78f83ea6a85a94b0fdb4616`
- Active automation `updated_at`: Unix milliseconds `1785664043694`
- Allocation attempt UTC/Unix: `2026-08-02T09:54:34Z` / `1785664474`
- Allocation completion UTC/Unix: `2026-08-02T09:54:40Z` / `1785664480`
- Frozen image:
  `192.168.108.1:5000/pytorch/ptv-qianliujia:python310_torch2.7`
- Local operational-control verification inherited from the frozen operational
  commit: `107 passed`, `50 skipped`, `0 failed`; every skip required Linux
  `/proc`, `setsid`, or a controlling PTY

Both production run-ID validators accepted the all-lowercase run ID, and its
report, admission directory, artifact root, and run directory were absent
before this record was created. The approval and canonical prompt comparison
fix were pushed and independently verified at the commit/tree above. The same
heartbeat automation was then atomically updated to the exact frozen P009
prompt and activated at one-minute cadence before any allocation status or
open action. Its exact config SHA-256 was bound into the immutable activation,
attempt, and completion receipts.

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
- P009 request: `7be58af7-4b46-4618-8c02-76bfd4acd950`
- Allocation response: `Pending`, placeholder `resource=GPU:1`,
  `remainTime=-`, unchanged frozen image, recorded
  `2026-08-02T09:54:40Z` / Unix `1785664480`
- Terminal status: the same request and image reported `Running`,
  `resource=GPU:1`, `remainTime=14301`, and no actions in sequence `0012`.
- P009 GPU UUID, host, boot ID, exact accelerator resource, and admitted lease:
  unavailable because admission never began

P009 consumed exactly one `open GPU2` action, never `restart`, after the active
watcher was verified and the fresh unchanged status still bound the predecessor
request as Halt with `remainTime=-292`. The controller wrote its exclusive
attempt receipt before the call and the response returned the new request above,
the unchanged image, exact `start_requested` from `Halt`, and one Pending active
request. This allocation action is permanently consumed. Its transition was
committed, pushed, and GitHub-verified at the allocation publication commit
above before the first post-ledger status.

Sequences `0002`-`0004` preserved Pending and `0005`-`0011` preserved
ImagePulling, each with a valid success receipt. Sequence `0012` caught Running
with 14,301 seconds but returned the generic `GPU:1` resource rather than exact
`NVIDIA-A100-SXM4-80GB:1`. The frozen status controller wrote a valid failure
receipt and stopped before invoking `repro.aistation_admission_gate`, probe,
SSH, CUDA inspection, identity capture, or remote mutation. This says nothing
about physical hardware identity. Per the fail-closed contract, every further
status, open, restart, stop, admission, probe, SSH, or remote action under P009
is forbidden.

## 5. Planned commands and evidence

1. **Complete and GitHub-verified.** The approval ledger, watcher prompt, and
   both no-clobber allocation controllers were published at commit
   `fcc4afc1e9c8eb397f85335e72d9f778abcd836e`.
2. **Complete.** Atomically update the existing
   `run-zoology-gpu2-single-baseline` heartbeat from its paused stale P006
   prompt to the exact frozen P009 prompt and `ACTIVE`, preserving the
   one-minute cadence and target thread. Its exact config hash was bound before
   allocation.
3. **Complete.** The main-agent controller freshly rebound the P008 request as
   Halt, then consumed the sole `open GPU2` and returned the new Pending P009
   request with an unchanged image and exact `start_requested` action.
4. **Complete and GitHub-verified.** The allocation transition, old/new request
   identities, raw hashes, and `monitoring` phase were published at commit
   `ad3a1c9eab1b45e14ac4e74aca9f23e2d6eaefc3` before any post-ledger status.
5. **Terminal.** Status sequences `0002`-`0004` were Pending and `0005`-`0011`
   were ImagePulling. Sequence `0012` bound the same request/image as Running
   with `remainTime=14301`, but its generic `GPU:1` resource failed the frozen
   exact-A100 guard. The valid failure receipt consumed monitoring and forbids
   another sequence or admission.
6. **Not reached.** No successful initial admission or in-progress publication
   exists.
7. **Not reached.** No remote path, checkout, launcher upload, or advancing
   operation receipt exists.
8. **Not reached.** The repaired production-PTY/exact-53 gate was never started.
9. **Not reached.** No setup, preflight, initialization, or real-A100 smoke
   exists.
10. **Not reached.** No formal capture, publication, start, or worker exists.
11. **Complete locally.** No P009 remote path existed, so no remote pull was
    applicable. All allowed local controls and allocation/status evidence were
    inventoried, safely archived, independently inspected member-by-member, and
    bound below before terminal publication.

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
- Local terminal-archive helper SHA-256:
  `ede7fd2589108d312569becda37f190238487a026a4da53eecaac7264eca4167`
- Immutable watcher activation:
  `watcher-activation-0001.json`, SHA-256
  `efb695bc35fb59f6f11f89a9e6c383f6c02fcedfad19797f577a9fbcf30ef3aa`
- Fresh predecessor status stdout/stderr: `status-pre-open-0001.json` SHA-256
  `2ca7d98bfa0d2e01d2e5a27464a2b27090c43fc0467c3949b3f4f6cc2c3c7833`
  and empty stderr SHA-256
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- Exclusive open attempt: `open-0001.attempt.json`, SHA-256
  `d30e07d6c02d590628e0802d5aec72aa2079742a818a9469257557cf5f3acfb2`
- Open stdout/stderr: `open-0001.json` SHA-256
  `7a21ef18fb2a52b073f03c1d673eacff7c9ad44efc7fdb7d88f56a5dc1d089cf`
  and empty stderr SHA-256
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- Complete allocation receipt: `open-0001.receipt.json`, SHA-256
  `1cf3805dd54ddecf442dec53f51509850a88a8915db72f6ad1febb10b50b0fd5`
- Terminal sequence `0012` status stdout SHA-256:
  `b5be8ed907c46938065608cd242fe0f78329a8ca574ef718654fe9d1a9798bb2`
- Terminal sequence `0012` stderr is empty with SHA-256:
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- Terminal sequence `0012` failure-receipt SHA-256:
  `7e01b9cf0a8fcbcc199dc1b8374737cb7445a9ad03e683567631fd077f73e571`;
  no success receipt exists
- Complete safe inventory:
  `artifacts/gdn-mqar-single-baseline-p009-20260802t090131z/complete-failure-evidence-inventory.tsv`,
  SHA-256
  `62a7c6ebe8708ed6644e6252fb0a7c2329a8b0a4c32c88ac842916f202bec681`;
  it closes over `44` source files: three local allocation/archive helpers,
  one watcher prompt, and forty allocation/status evidence files
- Complete safe archive:
  `artifacts/gdn-mqar-single-baseline-p009-20260802t090131z/gdn-mqar-single-baseline-p009-20260802t090131z-complete-failure-evidence.tar.gz`,
  `18,153` bytes, SHA-256
  `08fa59c865a7752ff6bcecfffd1e3f43fddbf2418797e350328c7e345500f63c`;
  sidecar SHA-256
  `08525d65d9a928cb452715938ece369c51a5f1da674601eb0228d83a48d4b12d`
- Independent verification record:
  `artifacts/gdn-mqar-single-baseline-p009-20260802t090131z/complete-failure-evidence-verification.json`,
  SHA-256
  `74ccbb759b3f0d3d93b52af19ddcf1fd86729e8be09a506592c8f9bc0ebc1619`;
  the extracted archive has `45` regular files and `4` directories with zero
  links, special members, unsafe or duplicate paths, forbidden payloads, or
  credential-like fields, and all `44` inventory entries matched their source
  files byte-for-byte

All allocation evidence is under
`artifacts/admission-gdn-mqar-single-baseline-p009-20260802t090131z/` and
contains forty regular files. No P009 probe, SSH, admission, identity, remote
path, suite, Linux gate, preflight, initialization, formal capture/start,
worker, model, metric, or score exists. Because no remote path existed, no
remote pull was applicable. The archive contains no model weights, datasets,
caches, checkpoints, credentials, or secrets.

## 7. Results

Terminal failed before admission. The active watcher caught request
`7be58af7-4b46-4618-8c02-76bfd4acd950` as Running with 14,301 seconds, but the
reported `GPU:1` resource did not equal the frozen exact A100 string. This is an
operational resource-contract failure, not a statement about physical hardware
and not a scientific result. No worker, training metric, model, or score exists;
all accuracy thresholds are unevaluated.

## 8. Official comparison

No reproduced value exists, so no delta can be computed. The official visual
reference remains approximately 0.99 for the matching state-size point and is
not compared to an admission failure.

## 9. Decision and reusable lesson

P009 is terminal `failed / Running resource mismatch before admission`,
unretried, and must never receive another status, allocation, admission, probe,
SSH, capture, or launch action. The watcher-first intervention did remove the
P008 ambiguity: it caught Running while 14,301 seconds remained. The exact
resource contract nevertheless failed before admission, so the repaired PTY
control and unchanged Gated DeltaNet cell were never exercised and the model
hypothesis remains untested.

The reusable operational lesson is that active monitoring can catch a lease
without making a generic Running resource admissible. Exact accelerator
validation must remain before probe and remote access. This is a reproduction
study with no score; no P009 result tag, archive tag, or `exp/score-*` tag is
permitted. The heartbeat may be paused only after this terminal ledger is
GitHub-verified.
