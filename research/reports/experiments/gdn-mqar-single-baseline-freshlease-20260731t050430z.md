# Experiment: E-GDN-MQAR-BASELINE-004

## 1. Metainfo

- Plan: `P-BASELINE-004`
- Run: `gdn-mqar-single-baseline-freshlease-20260731t050430z`
- State: `failed`
- Approved UTC: `2026-07-31T05:04:30Z`
- Started UTC (fresh GPU2 observation): `2026-07-31T05:06:56Z`
- Ended UTC (post-timeout remote observation): `2026-07-31T05:17:13Z`
- Approval: the user's reply `继续` after the explicit fresh-GPU2/new-experiment handoff
- Target: logical AIStation `GPU2`
- Remote root: `/huyang2/zoology`
- Formal source SHA: `13f880b5fe61619a1006ef33610de69fbabaaec1`
- Formal source tree: `ed83a7188351ca2cce8aba46d1cb3b108ce31ec2`
- Parent experiment: `P-BASELINE-003`, terminal `failed`

This is a separately approved experiment with a genuinely new lowercase run
ID and fresh GPU2 lease. It does not reopen, rename, delete, recapture, or
retry any prior run ID. The scientific setting remains unchanged because no
standalone baseline worker has yet launched and therefore no model result
exists to select from.

The run ID passed the production `_validate_run_id` parser before allocation;
both its local artifact path and report path were absent.

## 2. Hypothesis

Local official-grid harness index 5 should provide a persuasive single-setting
Gated DeltaNet MQAR baseline: final overall `valid/accuracy >= 0.98`, near the
official PNG reading of approximately 0.99, while using a 67,072-byte
state-size proxy. `0.96 <= accuracy < 0.98` is only visually compatible;
final KV256 accuracy `>=0.88` is diagnostic, not an upstream threshold.

The prior formal capture proved that code, helper identity, workspace identity,
host identity, boot identity, and bracket timing were valid. It stopped only
because 11,999 seconds remained against the unchanged 12,060-second
controller floor. This experiment obtains a fresh GPU2 lease and checks for
at least 13,200 seconds before spending time on setup.

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
- Model: two-layer historical hybrid, BaseConv kernel 3 followed by two-head
  Gated DeltaNet
- Gated DeltaNet output gate: disabled
- Gated DeltaNet decay and short convolution: enabled
- Short-convolution width: `4`
- Position embedding: disabled
- Embedding weights: tied
- Embedding dropout: `0.1`

No model, data, optimizer, stopping rule, metric, width, learning rate, seed,
epoch budget, or threshold may change.

## 4. Environment and admission

- AIStation target: logical `GPU2` only
- Fresh workspace ID: `2c6882d9-a24c-4ad6-876b-c8ec3ea995a6`
- GPU UUID: `GPU-573c7ed1-1c51-8334-299b-edf2ff3440e6`
- Hostname: `adcgefkb1vqkn-0`
- Boot ID: `08d861e6-ce7b-4fe8-ba78-de529efd1b31`
- Initial remaining time before setup: `14,366` seconds
- Expected GPU: `NVIDIA A100-SXM4-80GB`
- Approved helper:
  `/Users/torusmini/.codex/skills/aistation-skill/scripts/aistation_api.js`
- Approved helper SHA-256:
  `628aefaa2de3eb09ad5e6e1397e04280650e01847da2d9192566137405230226`
- Python: `3.10.11`
- uv: `0.9.27`
- PyTorch: `2.7.0+cu126`
- torchvision: `0.22.0+cu126`

Before setup, the fresh GPU2 status must be `Running` with at least 13,200
seconds remaining and `probe` must show the expected A100. The formal source
must be a clean detached checkout. Exactly one seven-file clock bundle may be
captured under this run ID. It must bind the unchanged Running GPU2 workspace,
hostname, boot ID, a bracket of at most 15 seconds, and at least 12,060 seconds
remaining. Publication and launch run in one GPU2 process, with a second
host/boot/age check no more than 60 seconds after the selected remote-before
timestamp. Controller and worker admissions remain unchanged.

## 5. Commands

Obtain and verify only a fresh logical GPU2 lease, then use the exact formal
source:

```bash
export AISTATION_HELPER=\
/Users/torusmini/.codex/skills/aistation-skill/scripts/aistation_api.js
node "${AISTATION_HELPER}" restart GPU2
node "${AISTATION_HELPER}" status GPU2
node "${AISTATION_HELPER}" probe GPU2

cd /huyang2/zoology
git fetch origin codex/repro-gdn-mqar-baseline-002
git checkout --detach 13f880b5fe61619a1006ef33610de69fbabaaec1
test "$(git rev-parse HEAD)" = \
  13f880b5fe61619a1006ef33610de69fbabaaec1
test "$(git rev-parse HEAD^{tree})" = \
  ed83a7188351ca2cce8aba46d1cb3b108ce31ec2
test -z "$(git status --porcelain)"

export AISTATION_TARGET=GPU2
export ZOOLOGY_EXPECTED_GIT_SHA=13f880b5fe61619a1006ef33610de69fbabaaec1
./setup.sh
./run.sh check
./run.sh cache
./run.sh smoke
./run.sh init-baseline \
  /huyang2/zoology/runs/gdn-mqar-single-baseline-freshlease-20260731t050430z
mkdir -p \
  /huyang2/zoology/artifacts/gdn-mqar-single-baseline-freshlease-20260731t050430z
```

Capture, upload unchanged, then publish and launch exactly once:

```bash
python3 -m repro.aistation_clock_bracket capture \
  --helper /Users/torusmini/.codex/skills/aistation-skill/scripts/aistation_api.js \
  --output-dir artifacts/gdn-mqar-single-baseline-freshlease-20260731t050430z/controller \
  --run-id gdn-mqar-single-baseline-freshlease-20260731t050430z \
  --formal-source-sha 13f880b5fe61619a1006ef33610de69fbabaaec1

node "${AISTATION_HELPER}" push GPU2 -- \
  /Users/torusmini/Documents/zoology-worktrees/baseline-002/artifacts/gdn-mqar-single-baseline-freshlease-20260731t050430z/controller \
  /huyang2/zoology/artifacts/gdn-mqar-single-baseline-freshlease-20260731t050430z/

node "${AISTATION_HELPER}" exec GPU2 -- \
  "cd /huyang2/zoology && \
   ./.venv/bin/python -m repro.aistation_clock_bracket \
     publish-and-launch \
     --bundle-dir \
     /huyang2/zoology/artifacts/gdn-mqar-single-baseline-freshlease-20260731t050430z/controller \
     --suite-dir \
     /huyang2/zoology/runs/gdn-mqar-single-baseline-freshlease-20260731t050430z"
```

## 6. Artifacts

- Remote initialized and clock-published suite:
  `/huyang2/zoology/runs/gdn-mqar-single-baseline-freshlease-20260731t050430z`
- Complete failure-evidence archive:
  `gdn-mqar-single-baseline-freshlease-20260731t050430z-complete-failure-evidence.tar.gz`
- Neutral archive tag:
  `archive/gdn-mqar-single-baseline-20260731-p004-failed-publish-timeout`
- GitHub failure-evidence prerelease:
  `https://github.com/yanghu819/zoology/releases/tag/archive/gdn-mqar-single-baseline-20260731-p004-failed-publish-timeout`
- Archive SHA-256:
  `8809941714c4bdae5c7a4802ee49f9604bd818bce7b68b175261c7f0b9808215`
- Archive sidecar SHA-256:
  `b3c5c21d6f4f669357fefff1c8439b9c81d289ef3666749a41fe27407f87c378`
- Inventory SHA-256 (38 hashed evidence files):
  `56869372a3787060cb5f0deec49bc17b90913031b2dbd571d89c148edad75347`
- Local capture terminal SHA-256:
  `b84c3033b6c06887290503ae448d930857d86ca2fb18acd9b097a3b05fe5cba1`
- Published clock proof SHA-256:
  `f0ab3d7508621cb21cd13d369d52c840009fc1fbefc9de7582efd21e3791f627`
- Published AIStation status SHA-256:
  `3b35c73d3641e74f952b739012e572b572736408bfd6f2ad58db6015bd9bdc8b`
- Suite manifest SHA-256:
  `8176c8dd4b16ef1b382586e1273c866fe51a4184025e86a7c0b4f19e051331be`
- Publish-timeout control record SHA-256:
  `8c705b20c4232f800f0e2f4f4ee226401576e4ebb45c96e9ab59efe335d83add`
- Local safe extraction:
  `/Users/torusmini/Documents/zoology-worktrees/baseline-002/artifacts/gdn-mqar-single-baseline-freshlease-20260731t050430z/verify.h27KZs`

The archive contains thirty-eight hashed evidence files plus the inventory
itself: the seven original local capture files, the fifteen-file
remote suite after immutable clock publication, fifteen setup/cache/smoke/init
control files, and one post-timeout observation record. Local post-pull hashing
verified all thirty collected remote-sourced files against the inventory; the
archive does not contain a separate remote-side thirty-file hash manifest.
Independent verification rejected links, special files, unsafe or duplicate
paths, hash drift, credential-like content, and lifecycle evidence that would
imply admission or launch. The seven clock files additionally have byte-for-byte
local-before/published pairs. The nested source snapshot contains 583 safe
members.

No controller admission, worker admission, launch request, worker terminal,
training log, metrics, result, model, dataset payload, checkpoint, optimizer
state, or score exists. None is present in Git or the evidence archive.

## 7. Results

Fresh GPU2 allocation and all five preflight steps completed successfully:
`setup=0`, `check=0`, `cache=0`, `smoke=0`, and `init=0`. The smoke used the
real A100 and reported `gdn_mqar_smoke=pass`.

The one formal capture completed under the exact formal source and approved
helper. It bound workspace `2c6882d9-a24c-4ad6-876b-c8ec3ea995a6`,
hostname `adcgefkb1vqkn-0`, boot ID
`08d861e6-ce7b-4fe8-ba78-de529efd1b31`, an eight-second remote bracket,
and `13,840` seconds remaining. All seven files published unchanged.

The approved helper then kept `publish-and-launch` in the foreground. Its SSH
execution ceiling expired after 23.8136 seconds and returned exit 124. At the
remote observation `2026-07-31T05:17:13Z`, all seven clock files existed in
the suite, but the publishing Python process count, admission count, launch
count, worker count, terminal count, and result count were all zero. GPU
memory and utilization were also zero. The command was not reissued.

| Measure | Outcome |
| ------- | ------- |
| Reproduced final `valid/accuracy` | Not evaluated; worker never launched |
| Strong threshold `>=0.98` | Not evaluated |
| Visual-compatibility floor `>=0.96` | Not evaluated |
| Final KV256 diagnostic `>=0.88` | Not evaluated |
| Delta versus official visual approximation | Not available |

## 8. Conclusions

Decision: `failed`.

This is a transport-lifetime failure after evidence publication but before
admission, not a Gated DeltaNet result. No threshold was relaxed and the
consumed run ID was not retried. The model hypothesis is neither supported nor
rejected.

The reusable lesson is plain: a command that must take longer than the SSH
helper's roughly 20-second limit must keep running after SSH disconnects.
`nohup` means the same remote Python process survives that disconnect; it does
not split publication from launch or weaken the same-process guarantee.
P-BASELINE-005 records that single operational intervention as proposed.

This experiment supplies no evidence for or against the Bitter Lesson because
no learning process ran.

## 9. Submission record

This is a reproduction baseline, not a competition submission. No submission
was made and no `exp/score-*` tag is permitted because there is no score.

The neutral failure-evidence tag and GitHub prerelease above were verified at
`2026-07-31T05:41:50Z`. The annotated tag resolves to audit-correction commit
`6e48ac24eae233dbff6e47d7e4060e62e875292c`. GitHub reports all three assets
as uploaded with SHA-256 digests matching the local archive, archive sidecar,
and inventory hashes in section 6.
