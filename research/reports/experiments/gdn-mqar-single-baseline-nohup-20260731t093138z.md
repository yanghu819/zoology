# Experiment: E-GDN-MQAR-BASELINE-005

## 1. Metainfo

- Plan: `P-BASELINE-005`
- Run: `gdn-mqar-single-baseline-nohup-20260731t093138z`
- State: `approved`
- Approved UTC: `2026-07-31T09:31:38Z`
- Approval: the user's reply `continue` after being told that P005 required
  explicit approval
- Target: logical AIStation `GPU2` only
- GPU2 workspace request: `5186b27a-139a-4eb7-8b99-4ad64683c64f`
- Workspace request state at approval: `Pending`
- Remote root: `/huyang2/zoology`
- Formal source SHA: `13f880b5fe61619a1006ef33610de69fbabaaec1`
- Formal source tree: `ed83a7188351ca2cce8aba46d1cb3b108ce31ec2`
- Parent experiment: `P-BASELINE-004`, terminal `failed`

The run ID passed the production `_validate_run_id` parser before approval,
and its local report, local artifact directory, remote suite directory, and
remote run-specific artifact directory were absent. This is a new experiment;
it does not reopen, recapture, relaunch, rename, or delete any earlier run.

Approval did not itself allocate a GPU. The same request later became
`Running` and passed the approved helper probe, as recorded in Section 4. The
plan remains `approved`, without an active resource-allocation row, until all
prelaunch gates pass and the one formal launch is actually admitted. Merely
preparing the allocation does not claim that GDN training has started.

## 2. Hypothesis

Local official-grid harness index 5 should provide a persuasive single-setting
Gated DeltaNet MQAR baseline: final overall `valid/accuracy >= 0.98`, near the
official PNG reading of approximately 0.99, while using a 67,072-byte
state-size proxy. `0.96 <= accuracy < 0.98` is only visually compatible;
final KV256 accuracy `>= 0.88` is diagnostic, not an upstream threshold.

P004 already showed that the exact source, cached environment, real-GPU smoke,
suite initialization, formal clock capture, and immutable evidence publication
can pass. Its only observed blocker was process lifetime: the foreground helper
timed out after 23.8136 seconds and the publishing Python process disappeared
before admission. P005 tests one operational intervention: keep the exact same
`publish-and-launch` Python process alive independently of the SSH transport.
It does not change the learning problem, model, data, optimizer, seed, budget,
metric, or acceptance thresholds.

Before consuming the formal capture, a harmless detached-process smoke must
prove that a non-GPU child survives for more than 20 seconds after the helper
returns. This smoke tests only remote process lifetime. It must not create or
modify the formal suite, clock bundle, admission records, launch request,
worker, training data, model, or score.

## 3. Configuration

- Local official-grid harness index: `5`
- `d_model`: `128`
- Learning rate: `0.0031622776601683794` (`10^-2.5`)
- Seed and data seed: `123`
- Maximum epochs: `32`
- Strong overall threshold: `0.98`
- Visual-compatibility floor: `0.96`
- Final KV256 diagnostic threshold: `0.88`
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

No model, data, optimizer, scheduler, stopping rule, metric, width, learning
rate, seed, epoch budget, timeout, or threshold may change. No additional
learning rate, width, seed, or experiment cell is authorized.

The only formal operational change from P004 is how the unchanged tracked
`publish-and-launch` process is hosted: a remote durable wrapper starts that
single Python process under `nohup`, redirects standard input from
`/dev/null`, writes regular stdout/stderr logs, waits for the child, and writes
its terminal record atomically. `nohup` means that the process survives an SSH
disconnect; it does not split evidence publication from admission or launch.

## 4. Environment and admission

- AIStation target: logical `GPU2` only
- Approved workspace request:
  `5186b27a-139a-4eb7-8b99-4ad64683c64f`
- Current request state: `Running`
- Status/probe bracket: `2026-07-31T10:02:07Z` through
  `2026-07-31T10:02:11Z` (`1785492127` through `1785492131`)
- Remaining time in that status response: `13,658` seconds
- Hostname: `catqp8qe5bcfj-0`
- Boot ID: `08d861e6-ce7b-4fe8-ba78-de529efd1b31`
- GPU UUID: `GPU-1522da54-4d66-ddda-298e-422ca5bb6516`
- GPU: `NVIDIA A100-SXM4-80GB`, `0/81,920 MiB`, `0%` at probe
- Approved helper:
  `/Users/torusmini/.codex/skills/aistation-skill/scripts/aistation_api.js`
- Approved helper SHA-256:
  `628aefaa2de3eb09ad5e6e1397e04280650e01847da2d9192566137405230226`
- Python: `3.10.11`
- PyTorch/torchvision: `2.7.0+cu126` / `0.22.0+cu126`
- CUDA availability: `True`
- Remote work directory: `/huyang2/zoology`
- Formal suite:
  `/huyang2/zoology/runs/gdn-mqar-single-baseline-nohup-20260731t093138z`
- Remote run artifact root:
  `/huyang2/zoology/artifacts/gdn-mqar-single-baseline-nohup-20260731t093138z`
- Detached-process smoke control directory:
  `/huyang2/zoology/artifacts/gdn-mqar-single-baseline-nohup-20260731t093138z/detach-smoke-control`
- Formal one-shot control directory:
  `/huyang2/zoology/artifacts/gdn-mqar-single-baseline-nohup-20260731t093138z/formal-launch-control`
- Audited operational-control commit:
  `72156a43212eeecdcb24923215b5973f94412866`
- Detached-smoke SHA-256:
  `59339b6977bac9c763d469a6e2dbe22de51563b27188f3b6b0b7d8acb3980d13`
- Durable-starter SHA-256:
  `6e2eea84a1386598da5e5d48df85a9c0264f212b008ac265fd63bf2a00133b44`
- Durable-wrapper SHA-256:
  `e326e8dd999ae7870eeeffc5429e588f53ca31ad2b896c27be691725f117e4eb`

The binding command also reverified a clean detached formal SHA/tree and
`torch.cuda.is_available() == True`. GPU1 was not queried or mutated.

Admission is fail-closed:

1. Before setup, the exact request must be `Running`, probe as the expected
   A100, and report at least `13,200` seconds remaining.
2. The remote repository must be a clean detached checkout of the exact formal
   SHA and tree. The existing `.venv` and repo-local caches may be reused only
   if setup, dependency, cache-provenance, and real-GPU smoke checks pass.
3. The detached-process smoke control directory must be created exclusively
   without `mkdir -p`. Its child must survive the helper transport and produce
   its expected terminal sentinel after more than 20 seconds. A missing PID,
   log, or terminal sentinel fails P005 before formal capture.
4. Before suite initialization, the only permitted run-specific remote state
   is the immutable `launcher/` upload, one exclusive durable-preflight
   directory, and the completed harmless smoke directory. The formal suite,
   local controller directory, and formal one-shot control directory must
   remain absent until their designated one-time operations.
5. Before formal capture, an ordinary read-only GPU2 status check must still
   show at least `12,120` seconds. This is conservative launch headroom for the
   unchanged `12,060`-second controller floor plus the unchanged 60-second
   evidence-age window; neither formal threshold is lowered. Exactly one
   seven-file clock bundle may then be captured.
6. The captured bundle must bind the same Running workspace request, hostname,
   boot ID, helper identity, formal source, a remote bracket of at most 15
   seconds, and at least `12,060` seconds remaining.
7. Formal start exclusively creates the one-shot control directory without
   `mkdir -p`. Its existence consumes the only start attempt. Neither a helper
   retry nor manual re-entry is permitted, even if the wrapper, SSH transport,
   publication, admission, worker, or training later fails.
8. The durable wrapper must record its own PID and the Python child's PID,
   start ticks, and exact command before waiting. The child command must be one
   byte-identical-to-P004 `.venv/bin/python -m repro.aistation_clock_bracket
   publish-and-launch` invocation, without adding `-u` or splitting the command.
   The wrapper must atomically write the child's exit code, end
   UTC, and evidence hashes. Missing terminal evidence is failure, not grounds
   to launch again.
9. That same Python child performs immutable publication, the second
   host/boot/age check, and the only controller/worker launch. Publication and
   launch may not be split across processes or commands.

All three operational scripts are frozen in the audited commit and hashes
above. Independent review gave the starter/wrapper a formal-use `GO`: the
formal argv occurs once, process identity is bound through Linux `/proc`, every
signal path revalidates PPID plus start ticks, descriptors are detached, and
the terminal record is atomic. Local validation reported `76 passed, 2
skipped` for the control/clock/reproduction suites and `2 passed, 3 skipped`
for focused control tests; all skips are Linux-only integration paths. The
real GPU2 detached smoke below is the required Linux execution gate.

## 5. Commands

The request has left `Pending`; all AIStation actions remain restricted to
logical GPU2 through the approved helper:

```bash
export AISTATION_HELPER=\
/Users/torusmini/.codex/skills/aistation-skill/scripts/aistation_api.js
node "${AISTATION_HELPER}" status GPU2
node "${AISTATION_HELPER}" probe GPU2
```

The exact Running request is first bound to the environment and formal source:

```bash
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
```

Those four commands are the exact ordered preflight payload. They must run in
one detached, one-shot remote preflight envelope with separate step logs and
exit files plus an atomic terminal record; they must not be left in a
foreground helper session.

Upload the three committed scripts directly into the ignored remote artifact
tree; do not check out the operational commit into the formal repository:

```bash
RUN_ID=gdn-mqar-single-baseline-nohup-20260731t093138z
RART=/huyang2/zoology/artifacts/${RUN_ID}
LAUNCHER=${RART}/launcher
node "${AISTATION_HELPER}" exec GPU2 -- \
  'test ! -e /huyang2/zoology/artifacts/gdn-mqar-single-baseline-nohup-20260731t093138z && mkdir /huyang2/zoology/artifacts/gdn-mqar-single-baseline-nohup-20260731t093138z && mkdir /huyang2/zoology/artifacts/gdn-mqar-single-baseline-nohup-20260731t093138z/launcher'
node "${AISTATION_HELPER}" push GPU2 -- \
  /Users/torusmini/Documents/zoology-worktrees/baseline-002/research/control/detached_process_smoke.sh \
  "${LAUNCHER}/detached_process_smoke.sh"
node "${AISTATION_HELPER}" push GPU2 -- \
  /Users/torusmini/Documents/zoology-worktrees/baseline-002/research/control/durable_publish_launch_start.sh \
  "${LAUNCHER}/durable_publish_launch_start.sh"
node "${AISTATION_HELPER}" push GPU2 -- \
  /Users/torusmini/Documents/zoology-worktrees/baseline-002/research/control/durable_publish_launch_wrapper.sh \
  "${LAUNCHER}/durable_publish_launch_wrapper.sh"
```

Remote SHA-256 parity, regular-file status, and mode `0500` are mandatory. The
harmless detached-process smoke then runs exactly once before suite
initialization or formal capture:

```bash
"${LAUNCHER}/detached_process_smoke.sh" start \
  --script-sha256 \
  59339b6977bac9c763d469a6e2dbe22de51563b27188f3b6b0b7d8acb3980d13 \
  --control-dir "${RART}/detach-smoke-control"
```

The helper must return before its transport timeout. Read-only polling must
then prove a completed 45-second terminal, session leader, no controlling TTY,
the same host/boot, matching evidence hashes, and continued absence of the
formal suite, controller, and one-shot formal control. Never invoke the smoke
start path again after its control directory exists.

After that smoke passes, initialize only this new suite and perform the sole
formal capture:

```bash
./run.sh init-baseline \
  /huyang2/zoology/runs/gdn-mqar-single-baseline-nohup-20260731t093138z

python3 -m repro.aistation_clock_bracket capture \
  --helper /Users/torusmini/.codex/skills/aistation-skill/scripts/aistation_api.js \
  --output-dir artifacts/gdn-mqar-single-baseline-nohup-20260731t093138z/controller \
  --run-id gdn-mqar-single-baseline-nohup-20260731t093138z \
  --formal-source-sha 13f880b5fe61619a1006ef33610de69fbabaaec1
```

Upload the completed seven-file bundle unchanged. The following command,
called once through approved-helper `exec GPU2`, is the only permitted formal
start:

```bash
"${LAUNCHER}/durable_publish_launch_start.sh" \
  --starter-sha256 \
  6e2eea84a1386598da5e5d48df85a9c0264f212b008ac265fd63bf2a00133b44 \
  --wrapper "${LAUNCHER}/durable_publish_launch_wrapper.sh" \
  --wrapper-sha256 \
  e326e8dd999ae7870eeeffc5429e588f53ca31ad2b896c27be691725f117e4eb \
  --bundle-dir "${RART}/controller" \
  --suite-dir "/huyang2/zoology/runs/${RUN_ID}" \
  --control-dir "${RART}/formal-launch-control"
```

The formal start may only create the absent one-shot control directory, start
the unchanged single Python child, and return immediately. Once that control
directory exists, all monitoring is read-only and no command may relaunch or
re-enter the start path.
