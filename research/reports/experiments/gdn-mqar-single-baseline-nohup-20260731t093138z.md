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

Approval does not allocate a GPU. The new logical GPU2 request remains
`Pending`, so this record has no start time, hostname, boot ID, GPU UUID, or
active resource-allocation row. The plan may move to `in-progress` only after
that exact request becomes `Running`, the approved helper probes it, all
prelaunch gates pass, and the one formal launch is actually admitted.

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
- Current request state: `Pending`
- Expected GPU after allocation: `NVIDIA A100-SXM4-80GB`
- Approved helper:
  `/Users/torusmini/.codex/skills/aistation-skill/scripts/aistation_api.js`
- Remote work directory: `/huyang2/zoology`
- Formal suite:
  `/huyang2/zoology/runs/gdn-mqar-single-baseline-nohup-20260731t093138z`
- Remote run artifact root:
  `/huyang2/zoology/artifacts/gdn-mqar-single-baseline-nohup-20260731t093138z`
- Detached-process smoke control directory:
  `/huyang2/zoology/artifacts/gdn-mqar-single-baseline-nohup-20260731t093138z/detach-smoke-control`
- Formal one-shot control directory:
  `/huyang2/zoology/artifacts/gdn-mqar-single-baseline-nohup-20260731t093138z/formal-launch-control`

No host, boot ID, GPU UUID, Python version, PyTorch version, or remaining lease
is asserted while the request is `Pending`. Once the same request is
`Running`, the approved helper must probe GPU2 and record those values. GPU1
must not be queried or mutated.

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
4. The harmless smoke directory is the only expected pre-formal artifact.
   The formal suite, local controller directory, and formal one-shot control
   directory must remain absent until their designated one-time operations.
5. Before formal capture, an ordinary read-only GPU2 status check must still
   show enough slack to satisfy the unchanged `12,060`-second formal
   controller floor. Exactly one seven-file clock bundle may then be captured.
6. The captured bundle must bind the same Running workspace request, hostname,
   boot ID, helper identity, formal source, a remote bracket of at most 15
   seconds, and at least `12,060` seconds remaining.
7. Formal start exclusively creates the one-shot control directory without
   `mkdir -p`. Its existence consumes the only start attempt. Neither a helper
   retry nor manual re-entry is permitted, even if the wrapper, SSH transport,
   publication, admission, worker, or training later fails.
8. The durable wrapper must record its own PID and the Python child's PID,
   start ticks, and exact command before waiting. The child command must be one
   unchanged `python -u -m repro.aistation_clock_bracket publish-and-launch`
   invocation. The wrapper must atomically write the child's exit code, end
   UTC, and evidence hashes. Missing terminal evidence is failure, not grounds
   to launch again.
9. That same Python child performs immutable publication, the second
   host/boot/age check, and the only controller/worker launch. Publication and
   launch may not be split across processes or commands.

The exact durable-wrapper file, its SHA-256, and its audited launch command are
intentionally not asserted in this approval snapshot because the wrapper does
not yet exist. They are mandatory prelaunch evidence and must be frozen in Git
before formal capture or launch. Until then, the experiment remains blocked
from entering `in-progress`.

## 5. Commands

While the request is `Pending`, the only permitted AIStation operation is a
read-only status check of logical GPU2 through the approved helper:

```bash
export AISTATION_HELPER=\
/Users/torusmini/.codex/skills/aistation-skill/scripts/aistation_api.js
node "${AISTATION_HELPER}" status GPU2
```

Do not probe, SSH, initialize paths, or start another environment while the
request remains `Pending`. Once the exact request becomes `Running`, first
bind and verify the environment and exact formal source:

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

The harmless detached-process smoke must run before suite initialization or
formal capture. It must use its exclusive smoke control directory, return from
the helper immediately, remain alive beyond 20 seconds, and atomically write a
non-GPU terminal sentinel. Its exact audited command and evidence hashes must
be added to this section before execution.

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

Upload the completed seven-file bundle unchanged. The formal launch command is
deliberately omitted until the durable wrapper exists, has been audited, and
its exact file hash and invocation are frozen in Git. The eventual helper call
may only create the absent formal one-shot control directory, start that
audited wrapper once, and return immediately. All later monitoring commands
must be read-only and must never relaunch or re-enter the start path.
