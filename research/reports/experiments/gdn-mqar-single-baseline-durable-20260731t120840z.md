# Experiment: E-GDN-MQAR-BASELINE-006

## 1. Metainfo

- Plan: `P-BASELINE-006`
- Run: `gdn-mqar-single-baseline-durable-20260731t120840z`
- State: `approved`
- Proposed UTC: `2026-07-31T12:08:40Z`
- Approved UTC: `2026-07-31T14:13:12Z`
- Approval: the user explicitly authorized replacing the expired GPU2
  environment with a fresh otherwise-identical GPU2 environment and retiring
  the old one after the proposal was pushed and GitHub-verified
- Target: logical AIStation `GPU2` only
- GPU2 workspace discovery: request
  `5186b27a-139a-4eb7-8b99-4ad64683c64f` was `Halt` with reported remaining
  time `-312` seconds; rebuild/open is approved but not yet invoked
- Remote root: `/huyang2/zoology`
- Formal source SHA:
  `13f880b5fe61619a1006ef33610de69fbabaaec1`
- Formal source tree:
  `ed83a7188351ca2cce8aba46d1cb3b108ce31ec2`
- Operational-control commit:
  `8740ccc65fe6b2627a47f82d4d05b9a6de0bff2e`
- Operational-control tree:
  `7d9e3c706f932a0d69043a4464eba53acd7aa871`
- Parent experiment: `P-BASELINE-005`, terminal `failed`

The production `_validate_run_id` parser accepted the all-lowercase run ID,
and its local report and artifact paths were absent before this proposal was
created. No AIStation status, probe, workspace request, remote directory,
formal capture, worker, training, model, metric, or score was created for P006
while preparing this record. GPU1 was not queried or mutated.

P006 is a newly approved experiment. It does not reopen, delete, rename,
retry, or reinterpret P001–P005. The approval applies only to rebuilding the
literal expired GPU2 row and executing this already-frozen single run. It does
not authorize GPU1, another scientific setting, a retry, or relaxed gates.

## 2. Hypothesis

Local official-grid harness index 5 is a persuasive single-setting Gated
DeltaNet MQAR baseline. On the historical standard test mixture, the unchanged
cell should finish with overall final `valid/accuracy >= 0.98`, near the
official PNG's approximately 0.99 visual reading, and final KV256 accuracy
`>= 0.88`, while using a 67,072-byte state-size proxy.

P005 already passed locked setup, dependency checks, cache preparation, and a
real A100 GDN/MQAR smoke. Its formal hypothesis remained untested because the
live lease was opened before the control layer was finished; the mandatory
status gate later saw only 12,040 seconds. P006 tests one operational
hypothesis: if the complete preflight, init, clock, and formal-launch chain is
committed and audited before allocation, a fresh lease can be spent on the
unchanged model rather than on orchestration.

This is not a new architecture idea and not a table-filling ablation. No model,
data, optimizer, seed, width, learning rate, epoch budget, metric, threshold,
or official comparison rule changes. The expected information gain is binary
and decision-changing: either the official single GDN cell completes under a
fully reproducible contract, or its valid failure is archived without a retry.

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

No additional learning rate, width, seed, cell, or retry is authorized. The
0.98, 0.96, and 0.88 thresholds are immutable. A complete valid result with
overall accuracy at least 0.98 and KV256 accuracy at least 0.88 is strong and
may receive an `exp/score-{score}-{sha}` tag. An overall result from 0.96 to
below 0.98 is only visually compatible and receives no strong-result tag. A
lower complete valid result is a negative result. Any incomplete, invalid, or
timed-out run is terminal failed.

## 4. Environment and admission

- AIStation target: logical `GPU2` only
- Fresh request state after approval: must become `Running`
- Initial remaining-time floor: `13,200` seconds
- Pre-capture ordinary-status floor: `12,120` seconds
- Formal captured remaining-time floor: `12,060` seconds
- Maximum formal remote clock bracket: `15` seconds
- Maximum capture-to-remote-publish age: `60` seconds
- Approved helper:
  `/Users/torusmini/.codex/skills/aistation-skill/scripts/aistation_api.js`
- Approved helper SHA-256:
  `628aefaa2de3eb09ad5e6e1397e04280650e01847da2d9192566137405230226`
- Local AIStation admission-gate SHA-256:
  `68fa3af301f7b88d3bffb3fd17add8db2db9ae26d2e573a32f2944f02465121b`
- Local AIStation admission-gate test SHA-256:
  `ed27e732d980e29db7e7f2536aaa038a496a93dc1940e6fd6485c2d68feb06a4`
- Linux exact-test gate SHA-256:
  `1c7188f3c5cd204a435d29fc118fce5a7f35e2061529e02877b2198eda3d45c4`
- Linux exact-test gate test SHA-256:
  `77ae472c59ba8b620a7779d21b3783572ab37ab371da7e5b067e96d7158bc0a5`
- Durable Linux exact-test envelope SHA-256:
  `164e6d8cb4b3dfd03455e6ef3825e6ba80a31ae73effa6a2509478946eab13c1`
- Durable Linux exact-test envelope test SHA-256:
  `680b0124a789d35464f9494fb65137fe349b91a787ad46b19c14def97c46b0ea`
- Frozen local Python invocation: `/usr/bin/python3`
- Frozen resolved Python executable:
  `/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3.9`
- Frozen local Python version: `3.9.6`
- GitHub branch verification: operational commit
  `8740ccc65fe6b2627a47f82d4d05b9a6de0bff2e` matched `git ls-remote`
- Local operational-control matrix: `85 passed`, `49 skipped`, `0 failed`;
  all skips require Linux `/proc`/`setsid`
- Frozen five-module collection: exactly `53` tests; the formal run still
  requires the GPU2 Linux gate to prove `53 passed / 0 skipped`
- Durable preflight-v2 SHA-256:
  `3b1d5b682624be4149ae1ff30e9860f2904c794f047c579e00131bf7e25c93cd`
- Durable preflight-v2 test SHA-256:
  `c5786fb484434a6e32d56c86038ae071a9ef0c035cfb6491f476729d9c9ad5be`
- Durable init-baseline SHA-256:
  `26ed9ba1dd0cff7cd2c15a2ab372077b79abd33e5c69ce7dcd8a4d3a77a27541`
- Durable init-baseline test SHA-256:
  `b0bd42aed32f6773d86e446a8a411be79b4b70578fd3d8ef923fc49ca735cac7`
- Durable formal starter SHA-256:
  `6e2eea84a1386598da5e5d48df85a9c0264f212b008ac265fd63bf2a00133b44`
- Durable formal wrapper SHA-256:
  `e326e8dd999ae7870eeeffc5429e588f53ca31ad2b896c27be691725f117e4eb`
- Detached-process smoke SHA-256:
  `59339b6977bac9c763d469a6e2dbe22de51563b27188f3b6b0b7d8acb3980d13`
- Legacy durable-preflight SHA-256:
  `3264d8d2fc52f924da801c4bb201ca2ecbc66eaf4edbf032097a6e419a28b3fc`
- Durable formal control-test SHA-256:
  `361919534b2f8a02b8c8fa84564e0f23925cf2c9488089cd310d0493079e7355`
- Detached-process smoke-test SHA-256:
  `abbf2f330c8e9d4fa5071d17be32c9a054684c98681df57762db3e579cdf326e`
- Legacy durable-preflight test SHA-256:
  `40a46386675158cfa656ad6b372cb1571ce5c7df2a5753c26a90ac7c746e0ce0`

Admission is fail-closed:

1. No AIStation request or remote P006 path may be created before explicit
   approval. After approval, the approved helper first saves `status GPU2`.
   Halt may use `open GPU2`; Pending or Queuing is wait-only and must not be
   probed; Running is usable only after a newly saved status reports at least
   13,200 seconds. A lower Running lease fails P006 rather than being restarted
   or silently reused. GPU1 must never be queried, probed, opened, stopped, or
   mutated.
2. The frozen local admission module invokes the approved helper itself. For
   phase `initial`, it samples local wall and monotonic clocks, saves the exact
   `status GPU2` stdout bytes exclusively, and validates one literal Running
   GPU2 request, exact `NVIDIA-A100-SXM4-80GB:1`, and at least 13,200 seconds
   before it is allowed to call `probe GPU2`. Only after the probe binds one
   A100 and hostname may its fixed `exec GPU2` command read the same host's
   Linux boot ID and remote UTC Unix time. It then saves all three raw JSON
   responses unchanged and writes a canonical, self-verified observation that
   binds their SHA-256 values, the local clock bracket, request, resource,
   host, boot ID, remote time, helper, Node path, and frozen module hash. Each
   helper call has a 30-second timeout and the helper hash is checked before
   and after it. Any mismatch consumes the phase and terminates P006 before a
   remote formal path is created; the program contains no open/restart action.
3. `/huyang2/zoology` must be a clean detached checkout of the exact formal
   SHA and tree. The existing repo-local `.venv`, caches, wheels, models, data,
   artifacts, and runs may be reused; no persistent path outside
   `/huyang2/zoology` is allowed. After initial admission, every helper `exec`
   or `push` that can advance the run is owned by `run-operation`. It writes an
   exclusive attempt before calling the helper, preserves the exact stdout,
   rejects both outer and inner failure, and commits a receipt binding the
   command or paths, workspace, parent observation/binding, helper, module,
   frozen local Python runtime, timeout, and evidence hashes. A failed or
   duplicate stage consumes P006; a direct helper call may only poll read-only
   terminal/process state and can never authorize the next stage.
4. The exact committed remote upload manifest contains 19 files: eight tracked
   control sources, five frozen test modules, five byte-identical shell runtime
   copies at the launcher root, and the root Python exact-test runtime. Before
   preflight/init/formal controls, suite, controller, capture, or formal-launch
   paths exist, the detached Linux envelope returns within five seconds after
   binding its worker; the worker then runs the Python gate independently of
   the helper's short SSH lifetime. The gate verifies the exact launcher
   inventory and every source/test/runtime hash, then runs only the five frozen
   durable-control modules. It hides CUDA; disables inherited pytest plugins,
   options, config, conftest, cache, user site, and Python path; and keeps temp,
   basetemp, pycache, log, JUnit, exit, attempt, process, and terminal evidence
   under the run artifact. It has a 300-second timeout and accepts only pytest
   exit zero plus structurally verified JUnit counts of exactly 53 passed and
   zero skipped, failed, errored, or disabled tests. Its sole verifier requires
   exact evidence/hash closure, absent preflight/init/formal paths, and no live
   supervisor, worker, gate PID, or process group. A missing environment,
   residual process, or drift is a consumed failed gate, never permission to
   bypass testing.
5. Durable preflight-v2 then executes exactly `./setup.sh`, `./run.sh check`,
   `./run.sh cache`, and `./run.sh smoke`, once and in that order. `start`
   returns asynchronously: only read-only polling may wait for its terminal and
   every bound PID/process group to disappear. Its verifier is invoked exactly
   once after those conditions hold and must accept the full 19-file evidence
   chain. A failed/missing terminal or verifier consumes P006 and is not
   restarted.
6. Durable init-baseline exclusively creates the suite and its own control
   directory, runs `./run.sh init-baseline` once, requires selected index 5 and
   the exact fresh 11-entry suite inventory, and follows the same asynchronous
   start, read-only terminal/process wait, and one-verifier rule. Its required
   `init-baseline-control/worker-claim.json` is control evidence; the suite's
   `claims/`, `launches/`, and `logs/` directories must remain empty, with no
   formal baseline claim, launch record, training log, clock bundle, controller,
   or model yet.
7. The same frozen local admission module runs phase `pre-capture`. Before any
   helper call it revalidates the complete initial observation and raw hashes.
   Its fresh status must retain the request and at least 12,120 seconds before
   probe; probe and identity must retain the A100, host, and boot ID; remote
   time must not move backwards. The phase writes and self-verifies a second
   canonical observation linked by the initial-observation hash. Exactly one
   formal capture may then run. Its immutable seven-file bundle must bind the
   same request, host, boot ID, helper, formal source and tree, no more than a
   15-second bracket, and at least 12,060 seconds remaining. `bind-clock` then
   consumes one exclusive binding attempt and cross-binds both observations,
   all seven bundle hashes, the formal SHA/tree, and the frozen runtimes;
   `verify-binding` must reproduce it exactly before publication.
8. The local capture parent `artifacts/<run-id>` must remain completely absent
   until the capture command exclusively creates it. Admission/status/test logs
   use `artifacts/admission-<run-id>` instead. The remote artifact root may
   already contain the launcher and operational controls. After capture, the
   complete local `controller/` directory is recursively uploaded once to the
   absent remote controller path through a binding-parent operation receipt.
   A second binding-parent operation validates all seven names and per-file
   SHA-256 values on the remote host before the formal start command is entered.
9. Exactly one durable formal start may publish that bundle and launch the
   unchanged baseline worker. Remote publication must occur no more than 60
   seconds after the captured `selected_observed_unix`; a stale bundle is
   terminal failure and may not be recaptured. The formal start is itself a
   binding-parent operation receipt; existence of either that local operation
   attempt or the remote formal-launch control consumes the only start.
   Monitoring is read-only; no helper retry, manual re-entry, second capture,
   second start, or threshold relaxation is permitted.

## 5. Planned commands and evidence

The commands below are the frozen execution contract. They run under local
/bin/bash only after a new explicit approval for P006. The approved helper may
be called directly only for allocation discovery and read-only quiescence
polls. Every operation that can advance remote state is executed exactly once
through the tracked admission module, which validates both the helper process
and its returned operation JSON.

    set -euo pipefail

    RUN_ID=gdn-mqar-single-baseline-durable-20260731t120840z
    LOCAL_ROOT=/Users/torusmini/Documents/zoology-worktrees/baseline-002
    REMOTE_ROOT=/huyang2/zoology
    SUITE=$REMOTE_ROOT/runs/$RUN_ID
    RART=$REMOTE_ROOT/artifacts/$RUN_ID
    LAUNCHER=$RART/launcher
    AISTATION_HELPER=/Users/torusmini/.codex/skills/aistation-skill/scripts/aistation_api.js
    HELPER_SHA=628aefaa2de3eb09ad5e6e1397e04280650e01847da2d9192566137405230226
    ADMISSION=$LOCAL_ROOT/artifacts/admission-$RUN_ID
    LOCAL_CONTROLLER=$LOCAL_ROOT/artifacts/$RUN_ID/controller
    PYTHON=/usr/bin/python3

    FORMAL_SHA=13f880b5fe61619a1006ef33610de69fbabaaec1
    FORMAL_TREE=ed83a7188351ca2cce8aba46d1cb3b108ce31ec2
    OPERATIONAL_SHA=8740ccc65fe6b2627a47f82d4d05b9a6de0bff2e
    OPERATIONAL_TREE=7d9e3c706f932a0d69043a4464eba53acd7aa871
    ADMISSION_GATE_SHA=68fa3af301f7b88d3bffb3fd17add8db2db9ae26d2e573a32f2944f02465121b
    LINUX_ENVELOPE_SHA=164e6d8cb4b3dfd03455e6ef3825e6ba80a31ae73effa6a2509478946eab13c1
    LINUX_GATE_SHA=1c7188f3c5cd204a435d29fc118fce5a7f35e2061529e02877b2198eda3d45c4
    PREFLIGHT_SHA=3b1d5b682624be4149ae1ff30e9860f2904c794f047c579e00131bf7e25c93cd
    INIT_SHA=26ed9ba1dd0cff7cd2c15a2ab372077b79abd33e5c69ce7dcd8a4d3a77a27541
    FORMAL_START_SHA=6e2eea84a1386598da5e5d48df85a9c0264f212b008ac265fd63bf2a00133b44
    FORMAL_WRAPPER_SHA=e326e8dd999ae7870eeeffc5429e588f53ca31ad2b896c27be691725f117e4eb

    cd "$LOCAL_ROOT"
    test "$($PYTHON -c 'import platform; print(platform.python_version())')" = 3.9.6
    test "$($PYTHON -c 'from pathlib import Path; import sys; print(Path(sys.executable).resolve(strict=True))')" = /Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3.9
    test "$(git rev-parse "$OPERATIONAL_SHA^{commit}")" = "$OPERATIONAL_SHA"
    test "$(git rev-parse "$OPERATIONAL_SHA^{tree}")" = "$OPERATIONAL_TREE"
    if [ ! -e "$ADMISSION" ] && [ ! -L "$ADMISSION" ]; then
      mkdir -- "$ADMISSION"
    else
      test -d "$ADMISSION"
      test ! -L "$ADMISSION"
      test "$($PYTHON -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve(strict=True))' "$ADMISSION")" = "$ADMISSION"
      # Resume here is allowed only while allocation discovery is still the
      # sole activity. Initial admission and every operation have other
      # explicit continuation points and must never replay this bootstrap.
      $PYTHON - "$ADMISSION" <<'PY'
    import re
    import sys
    from pathlib import Path

    root = Path(sys.argv[1])
    pattern = re.compile(r"(?:status-discovery|open)-[0-9]{4}[.]json")
    for path in root.iterdir():
        if path.is_symlink() or not path.is_file() or pattern.fullmatch(path.name) is None:
            raise SystemExit(1)
    PY
    fi

    next_numbered_path() {
      local prefix=$1
      $PYTHON - "$ADMISSION" "$prefix" <<'PY'
    import re
    import sys
    from pathlib import Path

    root = Path(sys.argv[1])
    prefix = sys.argv[2]
    pattern = re.compile(re.escape(prefix) + r"-([0-9]{4})[.]json")
    numbers = []
    for path in root.glob(prefix + "-*.json"):
        match = pattern.fullmatch(path.name)
        if path.is_symlink() or not path.is_file() or match is None:
            raise SystemExit(1)
        numbers.append(int(match.group(1)))
    number = max(numbers, default=0) + 1
    if number > 9999:
        raise SystemExit(1)
    candidate = root / f"{prefix}-{number:04d}.json"
    if candidate.exists() or candidate.is_symlink():
        raise SystemExit(1)
    print(candidate)
    PY
    }

    guarded_node() {
      local output=$1
      shift
      local helper_exit
      case "$output" in
        "$ADMISSION"/*) ;;
        *) return 1 ;;
      esac
      test ! -e "$output" || return 1
      test ! -L "$output" || return 1
      test -f "$AISTATION_HELPER" || return 1
      test ! -L "$AISTATION_HELPER" || return 1
      test "$(shasum -a 256 -- "$AISTATION_HELPER" | awk '{print $1}')" = "$HELPER_SHA" || return 1
      if (set -o noclobber; node "$AISTATION_HELPER" "$@" > "$output"); then
        helper_exit=0
      else
        helper_exit=$?
      fi
      test -f "$AISTATION_HELPER" || return 1
      test ! -L "$AISTATION_HELPER" || return 1
      test "$(shasum -a 256 -- "$AISTATION_HELPER" | awk '{print $1}')" = "$HELPER_SHA" || return 1
      test -f "$output" || return 1
      test ! -L "$output" || return 1
      return "$helper_exit"
    }

Allocation discovery uses only literal GPU2. Every response is saved under a
new name and never overwritten. Halt permits one open after approval;
Pending/Queuing permits only another uniquely named status poll. Neither a
discovery response nor open permits probing or source mutation. Only the
initial admission capture below can do that.

    DISCOVERY_RAW=$(next_numbered_path status-discovery) || exit 1
    guarded_node "$DISCOVERY_RAW" status GPU2
    read -r DISCOVERY_STATE DISCOVERY_WORKSPACE < <(
      $PYTHON - "$DISCOVERY_RAW" <<'PY'
    import json
    import sys
    from pathlib import Path

    response = json.loads(Path(sys.argv[1]).read_bytes())
    if response.get("command") != "status" or response.get("ok") is not True:
        raise SystemExit(1)
    targets = response.get("targets")
    if type(targets) is not list or len(targets) != 1:
        raise SystemExit(1)
    target = targets[0]
    state = target.get("wpStatus") if type(target) is dict else None
    workspace = target.get("wpId") if type(target) is dict else None
    if (
        target.get("wpName") != "GPU2"
        or target.get("resource") != "NVIDIA-A100-SXM4-80GB:1"
        or state not in {"Halt", "Pending", "Queuing", "Running"}
        or type(workspace) is not str
        or not workspace
    ):
        raise SystemExit(1)
    print(state, workspace)
    PY
    )

    if [ "$DISCOVERY_STATE" = Halt ]; then
      test -z "$(find "$ADMISSION" -maxdepth 1 -type f -name 'open-[0-9][0-9][0-9][0-9].json' -print -quit)"
      OPEN_RAW=$(next_numbered_path open) || exit 1
      guarded_node "$OPEN_RAW" open GPU2
      OPEN_STATE=$(
        $PYTHON - "$OPEN_RAW" "$DISCOVERY_WORKSPACE" <<'PY'
    import json
    import sys
    from pathlib import Path

    response = json.loads(Path(sys.argv[1]).read_bytes())
    if response.get("command") != "open" or response.get("ok") is not True:
        raise SystemExit(1)
    targets = response.get("targets")
    if type(targets) is not list or len(targets) != 1:
        raise SystemExit(1)
    target = targets[0]
    actions = response.get("actions")
    if (
        type(target) is not dict
        or target.get("wpName") != "GPU2"
        or target.get("wpId") != sys.argv[2]
        or target.get("wpStatus") not in {"Pending", "Queuing", "Running"}
        or actions != [{"target": "GPU2", "action": "start_requested", "previousStatus": "Halt"}]
    ):
        raise SystemExit(1)
    print(target["wpStatus"])
    PY
      )
      DISCOVERY_STATE=$OPEN_STATE
    fi

    # Pending/Queuing ends this controller turn as a temporary wait. Save a new
    # numbered status response on the next turn; do not probe or create another
    # request. Only Running falls through to capture.
    case "$DISCOVERY_STATE" in
      Pending|Queuing) exit 75 ;;
      Running) ;;
      *) exit 1 ;;
    esac

    # Only a fresh strict Running response reaches the admission capture:
    $PYTHON -m repro.aistation_admission_gate capture       --helper "$AISTATION_HELPER"       --output-dir "$ADMISSION"       --run-id "$RUN_ID"       --phase initial       --module-sha256 "$ADMISSION_GATE_SHA"
    $PYTHON -m repro.aistation_admission_gate verify       --output-dir "$ADMISSION"       --run-id "$RUN_ID"       --phase initial       --module-sha256 "$ADMISSION_GATE_SHA"

These four local functions are the only state-progressing helper transport
after initial admission. Binding-parent functions also revalidate the complete
clock binding before and after the helper call.

    run_initial_exec() {
      local stage=$1
      local remote_command=$2
      $PYTHON -m repro.aistation_admission_gate run-operation         --helper "$AISTATION_HELPER"         --output-dir "$ADMISSION"         --run-id "$RUN_ID"         --stage "$stage"         --command exec         --identity-parent initial         --module-sha256 "$ADMISSION_GATE_SHA"         --remote-command "$remote_command"
    }

    run_initial_push() {
      local stage=$1
      local local_path=$2
      local remote_path=$3
      $PYTHON -m repro.aistation_admission_gate run-operation         --helper "$AISTATION_HELPER"         --output-dir "$ADMISSION"         --run-id "$RUN_ID"         --stage "$stage"         --command push         --identity-parent initial         --module-sha256 "$ADMISSION_GATE_SHA"         --local-path "$local_path"         --remote-path "$remote_path"
    }

    run_binding_exec() {
      local stage=$1
      local remote_command=$2
      $PYTHON -m repro.aistation_admission_gate run-operation         --helper "$AISTATION_HELPER"         --output-dir "$ADMISSION"         --run-id "$RUN_ID"         --stage "$stage"         --command exec         --identity-parent binding         --module-sha256 "$ADMISSION_GATE_SHA"         --bundle-dir "$LOCAL_CONTROLLER"         --formal-source-sha "$FORMAL_SHA"         --formal-source-tree "$FORMAL_TREE"         --remote-command "$remote_command"
    }

    run_binding_push() {
      local stage=$1
      local local_path=$2
      local remote_path=$3
      $PYTHON -m repro.aistation_admission_gate run-operation         --helper "$AISTATION_HELPER"         --output-dir "$ADMISSION"         --run-id "$RUN_ID"         --stage "$stage"         --command push         --identity-parent binding         --module-sha256 "$ADMISSION_GATE_SHA"         --bundle-dir "$LOCAL_CONTROLLER"         --formal-source-sha "$FORMAL_SHA"         --formal-source-tree "$FORMAL_TREE"         --local-path "$local_path"         --remote-path "$remote_path"
    }

The source/artifact operation is one fixed remote command. A helper timeout or
any outer/inner failure consumes this stage and P006; it is not re-entered.

    REMOTE_CMD="set -eu; cd $REMOTE_ROOT; git fetch origin codex/repro-gdn-mqar-baseline-002; git checkout --detach $FORMAL_SHA; test \"\$(git rev-parse HEAD)\" = $FORMAL_SHA; test \"\$(git rev-parse HEAD^{tree})\" = $FORMAL_TREE; test -z \"\$(git status --porcelain=v1 --untracked-files=all)\"; test -d $REMOTE_ROOT/artifacts; test ! -e $RART; test ! -L $RART; mkdir -- $RART"
    run_initial_exec remote-source-and-artifact "$REMOTE_CMD"

The launcher is assembled from the GitHub-verified operational commit, not
from mutable working-tree bytes. It has exactly 19 files: eight tracked control
sources, five frozen target tests, five shell runtime copies, and one Python
runtime copy.

    LOCAL_LAUNCHER=$ADMISSION/launcher
    mkdir -p "$LOCAL_LAUNCHER/research/control" "$LOCAL_LAUNCHER/tests"
    for REL in       research/control/durable_linux_exact_test_gate.sh       research/control/durable_init_baseline.sh       research/control/durable_preflight_v2.sh       research/control/durable_publish_launch_start.sh       research/control/durable_publish_launch_wrapper.sh       research/control/detached_process_smoke.sh       research/control/durable_preflight.sh       research/control/linux_exact_test_gate.py       tests/test_durable_init_baseline_control.py       tests/test_durable_preflight_v2_control.py       tests/test_durable_publish_launch_control.py       tests/test_detached_process_smoke_control.py       tests/test_durable_preflight_control.py
    do
      git show "$OPERATIONAL_SHA:$REL" > "$LOCAL_LAUNCHER/$REL"
    done
    for NAME in       durable_linux_exact_test_gate.sh       durable_init_baseline.sh       durable_preflight_v2.sh       durable_publish_launch_start.sh       durable_publish_launch_wrapper.sh
    do
      cp "$LOCAL_LAUNCHER/research/control/$NAME" "$LOCAL_LAUNCHER/$NAME"
      chmod 700 "$LOCAL_LAUNCHER/$NAME"
    done
    cp "$LOCAL_LAUNCHER/research/control/linux_exact_test_gate.py"       "$LOCAL_LAUNCHER/linux_exact_test_gate.py"
    chmod 700 "$LOCAL_LAUNCHER/linux_exact_test_gate.py"
    test -z "$(find "$LOCAL_LAUNCHER" -type l -print -quit)"
    test "$(find "$LOCAL_LAUNCHER" -type f | wc -l | tr -d ' ')" = 19
    run_initial_push launcher-push "$LOCAL_LAUNCHER" "$LAUNCHER"

The following read-only poll is never an admission receipt. Each call writes a
new local raw response, validates literal GPU2 and the initial workspace, and
returns success only after terminal.json exists and every recorded PID and
process group is absent. A nonzero poll is repeated under a new sequence
number. Linux gate, preflight, and init polling are bounded to 420, 1,800, and
600 seconds respectively; exhausting a bound fails P006 rather than consuming
the lease indefinitely. A poll cannot authorize progress; the one verifier
operation does that.

    strict_poll() {
      local label=$1
      local control=$2
      local raw
      local remote_poll
      raw=$(next_numbered_path "readonly-$label-poll") || return 1
      remote_poll=$(cat <<REMOTE
    set -eu
    /huyang2/zoology/.venv/bin/python - "$control" <<'PY'
    from pathlib import Path
    import json
    import os
    import sys

    control = Path(sys.argv[1])
    if control.is_symlink() or not control.is_dir() or control.resolve() != control:
        raise SystemExit(1)
    terminal = control / "terminal.json"
    if terminal.is_symlink() or not terminal.is_file():
        raise SystemExit(1)

    pids = set()
    groups = set()

    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if type(child) is int and child > 0:
                    if key == "pid" or key.endswith("_pid"):
                        pids.add(child)
                    if (
                        "pgid" in key
                        or "pgrp" in key
                        or key == "sid"
                        or key.endswith("_sid")
                        or key in {"worker_pid", "gate_pid", "init_pid"}
                    ):
                        groups.add(child)
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for path in control.glob("*.json"):
        if path.is_symlink() or not path.is_file():
            raise SystemExit(1)
        try:
            walk(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            raise SystemExit(1)

    if any((Path("/proc") / str(pid)).exists() for pid in pids):
        raise SystemExit(1)
    for group in groups:
        try:
            os.killpg(group, 0)
        except ProcessLookupError:
            continue
        except PermissionError:
            raise SystemExit(1)
        else:
            raise SystemExit(1)
    print(terminal.read_text(encoding="utf-8"), end="")
    PY
    REMOTE
    )
      if ! guarded_node "$raw" exec GPU2 -- "$remote_poll"; then
        return 1
      fi
      $PYTHON - "$raw" "$ADMISSION/observation-initial.json" <<'PY'
    import json
    import sys
    from pathlib import Path

    response = json.loads(Path(sys.argv[1]).read_bytes())
    observation = json.loads(Path(sys.argv[2]).read_bytes())
    if response.get("command") != "exec" or response.get("ok") is not True:
        raise SystemExit(1)
    targets = response.get("targets")
    if type(targets) is not list or len(targets) != 1:
        raise SystemExit(1)
    target = targets[0]
    if (
        type(target) is not dict
        or target.get("wpName") != "GPU2"
        or target.get("wpId") != observation.get("workspace_id")
        or target.get("wpStatus") != "Running"
    ):
        raise SystemExit(1)
    result = target.get("exec")
    if (
        type(result) is not dict
        or result.get("ok") is not True
        or type(result.get("exitCode")) is not int
        or result.get("exitCode") != 0
        or type(result.get("stdout")) is not str
        or type(result.get("stderr")) is not str
    ):
        raise SystemExit(1)
    PY
    }

    poll_until_quiescent() {
      local label=$1
      local control=$2
      local budget_seconds=$3
      local deadline=$((SECONDS + budget_seconds))
      while ((SECONDS < deadline)); do
        if strict_poll "$label" "$control"; then
          return 0
        fi
        sleep 2
      done
      return 1
    }

The exact Linux gate is detached before the helper returns. Its unique verifier
runs only after the read-only quiescence poll succeeds.

    REMOTE_CMD="cd $REMOTE_ROOT && $LAUNCHER/durable_linux_exact_test_gate.sh start --run-id $RUN_ID --script-sha256 $LINUX_ENVELOPE_SHA --gate-sha256 $LINUX_GATE_SHA --control-dir $RART/linux-exact-test-envelope"
    run_initial_exec linux-exact-test-start "$REMOTE_CMD"
    poll_until_quiescent linux-exact-test "$RART/linux-exact-test-envelope" 420
    REMOTE_CMD="cd $REMOTE_ROOT && $LAUNCHER/durable_linux_exact_test_gate.sh verify --run-id $RUN_ID --script-sha256 $LINUX_ENVELOPE_SHA --gate-sha256 $LINUX_GATE_SHA --control-dir $RART/linux-exact-test-envelope"
    run_initial_exec linux-exact-test-verify "$REMOTE_CMD"

Preflight and init use the same start, read-only wait, and sole-verifier rule.
All paths and hashes are absolute and frozen.

    REMOTE_CMD="cd $REMOTE_ROOT && AISTATION_TARGET=GPU2 ZOOLOGY_EXPECTED_GIT_SHA=$FORMAL_SHA $LAUNCHER/durable_preflight_v2.sh start --script-sha256 $PREFLIGHT_SHA --suite-dir $SUITE --control-dir $RART/preflight-control"
    run_initial_exec preflight-start "$REMOTE_CMD"
    poll_until_quiescent preflight "$RART/preflight-control" 1800
    REMOTE_CMD="cd $REMOTE_ROOT && AISTATION_TARGET=GPU2 ZOOLOGY_EXPECTED_GIT_SHA=$FORMAL_SHA $LAUNCHER/durable_preflight_v2.sh verify --script-sha256 $PREFLIGHT_SHA --suite-dir $SUITE --control-dir $RART/preflight-control"
    run_initial_exec preflight-verify "$REMOTE_CMD"

    REMOTE_CMD="cd $REMOTE_ROOT && AISTATION_TARGET=GPU2 ZOOLOGY_EXPECTED_GIT_SHA=$FORMAL_SHA $LAUNCHER/durable_init_baseline.sh start --script-sha256 $INIT_SHA --suite-dir $SUITE --control-dir $RART/init-baseline-control"
    run_initial_exec init-start "$REMOTE_CMD"
    poll_until_quiescent init "$RART/init-baseline-control" 600
    REMOTE_CMD="cd $REMOTE_ROOT && AISTATION_TARGET=GPU2 ZOOLOGY_EXPECTED_GIT_SHA=$FORMAL_SHA $LAUNCHER/durable_init_baseline.sh verify --script-sha256 $INIT_SHA --suite-dir $SUITE --control-dir $RART/init-baseline-control"
    run_initial_exec init-verify "$REMOTE_CMD"

After init verification, pre-capture admission must retain the request, A100,
host, boot ID, monotonic remote time, and 12,120-second floor. The sole formal
capture creates the previously absent local parent, and bind-clock consumes the
one binding attempt before any controller upload.

    $PYTHON -m repro.aistation_admission_gate capture       --helper "$AISTATION_HELPER"       --output-dir "$ADMISSION"       --run-id "$RUN_ID"       --phase pre-capture       --module-sha256 "$ADMISSION_GATE_SHA"
    $PYTHON -m repro.aistation_admission_gate verify       --output-dir "$ADMISSION"       --run-id "$RUN_ID"       --phase pre-capture       --module-sha256 "$ADMISSION_GATE_SHA"
    test ! -e "$LOCAL_ROOT/artifacts/$RUN_ID"
    test ! -L "$LOCAL_ROOT/artifacts/$RUN_ID"
    $PYTHON -m repro.aistation_clock_bracket capture       --helper "$AISTATION_HELPER"       --output-dir "$LOCAL_CONTROLLER"       --run-id "$RUN_ID"       --formal-source-sha "$FORMAL_SHA"
    $PYTHON -m repro.aistation_admission_gate bind-clock       --output-dir "$ADMISSION"       --bundle-dir "$LOCAL_CONTROLLER"       --run-id "$RUN_ID"       --formal-source-sha "$FORMAL_SHA"       --formal-source-tree "$FORMAL_TREE"       --module-sha256 "$ADMISSION_GATE_SHA"
    $PYTHON -m repro.aistation_admission_gate verify-binding       --output-dir "$ADMISSION"       --bundle-dir "$LOCAL_CONTROLLER"       --run-id "$RUN_ID"       --formal-source-sha "$FORMAL_SHA"       --formal-source-tree "$FORMAL_TREE"       --module-sha256 "$ADMISSION_GATE_SHA"

The capture-to-publication clock is now running. No discovery or poll call may
intervene. The only allowed operations are controller push, absolute-path
remote bundle validation, and the one durable formal start, all with the
binding parent.

    run_binding_push controller-push "$LOCAL_CONTROLLER" "$RART/controller"
    REMOTE_CMD="cd $REMOTE_ROOT && /huyang2/zoology/.venv/bin/python -c 'from pathlib import Path; from repro.aistation_clock_bracket import validate_bundle; validate_bundle(Path(\"$RART/controller\"))'"
    run_binding_exec controller-remote-validate "$REMOTE_CMD"
    REMOTE_CMD="cd $REMOTE_ROOT && AISTATION_TARGET=GPU2 ZOOLOGY_EXPECTED_GIT_SHA=$FORMAL_SHA $LAUNCHER/durable_publish_launch_start.sh --starter-sha256 $FORMAL_START_SHA --wrapper $LAUNCHER/durable_publish_launch_wrapper.sh --wrapper-sha256 $FORMAL_WRAPPER_SHA --bundle-dir $RART/controller --suite-dir $SUITE --control-dir $RART/formal-launch-control"
    run_binding_exec formal-start "$REMOTE_CMD"

A stale-age rejection, any failed operation receipt, or any verifier failure is
terminal and is not retried. After formal start, monitoring is read-only until
the single baseline is terminal. Finalization must validate the complete suite,
record metadata bound to the formal SHA/tree and operation receipts, build a
complete safe inventory/archive under repo-local artifacts, pull and
independently verify it, then update this report, plans.md, the resource ledger,
and leaderboard.csv. Model, data, cache, checkpoint, and weight files must not
be uploaded to GitHub.

## 6. Artifacts

Not created. P006 is proposed and unapproved.

## 7. Results

Not run. No formal GDN metric exists for P006.

## 8. Conclusions

Approved for one fresh GPU2 rebuild and execution; not yet launched.

## 9. Submission record

Not applicable; this is a reproduction study.
