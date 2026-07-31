# Experiment: E-GDN-MQAR-BASELINE-005

## 1. Metainfo

- Plan: `P-BASELINE-005`
- Run: `gdn-mqar-single-baseline-nohup-20260731t093138z`
- State: `failed`
- Approved UTC: `2026-07-31T09:31:38Z`
- Terminal decision UTC: `2026-07-31T10:29:07Z`
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
`Running` and passed the approved helper probe, as recorded in Section 4. P005
then failed its frozen lease gate before suite initialization or formal clock
capture. It never entered `in-progress`; no controller, launch, worker, GDN
training, model, or score was created.

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
- Durable preflight control directory:
  `/huyang2/zoology/artifacts/gdn-mqar-single-baseline-nohup-20260731t093138z/preflight-control`
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
- Audited durable-preflight commit:
  `53944577bb47532f61a1d8357394d15c905b695c`
- Durable-preflight SHA-256:
  `3264d8d2fc52f924da801c4bb201ca2ecbc66eaf4edbf032097a6e419a28b3fc`

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

All four operational scripts are frozen in the audited commits and hashes
above. Independent review gave the starter/wrapper and preflight a `GO`: the
formal argv occurs once, process identity is bound through Linux `/proc`, every
signal path revalidates PPID plus start ticks, descriptors are detached, and
terminal records are atomic. The preflight additionally gates the starter
record before any step and records early/signal failures. Local validation
reported `76 passed, 2 skipped` for the original control/clock/reproduction
suites and `3 passed, 5 skipped` for all focused control tests; all skips are
Linux-only integration paths. The real GPU2 detached smoke below is the first
required Linux execution gate.

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

Upload the four committed scripts directly into the ignored remote artifact
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
node "${AISTATION_HELPER}" push GPU2 -- \
  /Users/torusmini/Documents/zoology-worktrees/baseline-002/research/control/durable_preflight.sh \
  "${LAUNCHER}/durable_preflight.sh"
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

After that diagnostic passes, the following is the only preflight start. It
must return promptly; read-only polling must show four successful steps and a
completed terminal before suite initialization:

```bash
"${LAUNCHER}/durable_preflight.sh" start \
  --script-sha256 \
  3264d8d2fc52f924da801c4bb201ca2ecbc66eaf4edbf032097a6e419a28b3fc \
  --control-dir "${RART}/preflight-control"
```

This one-shot worker executes only `./setup.sh`, `./run.sh check`, `./run.sh
cache`, and `./run.sh smoke`, in that order and once each. A nonzero step,
missing start/terminal evidence, source drift, or formal-path appearance fails
P005 without a preflight restart.

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

## 6. Execution and evidence

The initial frozen status/probe bracket reported the exact approved workspace
`Running` on the expected A100 with `13,658` seconds remaining. The remote
repository was the clean detached formal SHA/tree, and the local operational
commits and four remote launcher files were independently hash-matched.

The one detached-process diagnostic started through the helper at
`2026-07-31T10:06:47Z`; the helper returned at `10:06:49Z`. Its remote worker
was a session leader with no controlling TTY and ran from `10:02:38Z` through
`10:03:23Z` on the offset remote clock, exactly 45 seconds. Its terminal and
attempt/start/worker hashes all validated, while the formal suite, controller,
and one-shot formal control remained absent.

The one durable preflight helper call returned successfully at
`2026-07-31T10:25:23Z`. Its detached GPU2 worker ran from remote
`10:21:12Z` through `10:24:07Z`; all four frozen steps returned zero:

- `setup=0`
- `check=0`
- `cache=0`
- `smoke=0`

The real A100 smoke reached about 3,065 MiB and reported
`gdn_mqar_smoke=pass` after compiling/executing the Gated DeltaNet kernel and a
one-epoch MQAR end-to-end run. This proves the environment and GDN path work;
it is deliberately not the requested formal baseline result.

The mandatory pre-capture status check at
`2026-07-31T10:29:06Z`–`10:29:07Z` then reported only `12,040` seconds. That is
80 seconds below the frozen conservative `12,120` gate and 20 seconds below
the unchanged `12,060` controller floor. P005 therefore stopped before
`init-baseline`, formal capture, controller publication, formal start, worker,
training, model, or score. The local/remote evidence both assert counts of
zero for all of those formal actions.

An overlong first closeout transport command hit the helper's 20-second limit;
a read-only check proved that it created none of its four target files. A
small uploaded closeout script with frozen local/remote SHA then created the
evidence once. The pulled, independently checked evidence contains no links,
special files, model, data, or checkpoint:

- Remote evidence archive SHA-256:
  `5298be0cf2cf2e782d92932ea97cbfda6d66319f3a9a8eb403b3d93b88c321e1`
- Remote inventory SHA-256:
  `d00a9a077fbc4a7eae26ff42e7fe71dc725887ee9cab5c3e9aadb29d799cfb2b`
- Remote evidence files: `30`; archive regular files including inventory: `31`
- Complete local evidence archive SHA-256:
  `8d18c4168520dac828b84f294fbae5225dbe879b7e5bfe3a0f3359804ba76f21`
- Complete local inventory SHA-256:
  `f37cf4a7153ea69b5c3514920dd024fa9352fa53a2a2dc78f7ed6df282ad6551`
- Complete evidence files: `38`; archive regular files including inventory:
  `39`

## 7. Results

There is no formal `valid/accuracy`, KV256 slice, epoch record, checkpoint, or
model for P005. The requested GDN baseline did not run. The only learning
execution was the explicitly non-formal one-epoch smoke, whose purpose was
path validation rather than reproduction scoring.

## 8. Official comparison

No numerical comparison with the official Zoology GDN point is valid because
P005 produced no formal baseline metric. The official visual reading remains
approximately `0.99`; reproduced accuracy and delta are blank. No
`exp/score-*` tag is permitted.

## 9. Decision and reusable lesson

P005 is terminal `failed` and must not be captured, initialized, or launched
later under this run ID. The model hypothesis is still untested.

The operational insight is blunt: we opened the scarce GPU lease while still
building and reviewing transport controls. The controls are now proven, but
the lease clock paid for that engineering. This violates the spirit of the
Bitter Lesson at the workflow level: reliable general automation should be
prepared before scarce compute is allocated, not handcrafted while the GPU
waits. A separately approved fresh attempt should reuse these exact audited
controls immediately, add a prebuilt durable `init-baseline` envelope before
opening GPU2, and perform no new design or audit work on the live lease.
