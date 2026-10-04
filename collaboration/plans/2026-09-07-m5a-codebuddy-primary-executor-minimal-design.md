# Milestone 5A — CodeBuddy Primary Executor / Verified Repository Change
# Minimal Implementation Design

Date: 2026-09-07
Status: DESIGN ONLY
Milestone: M5 — CodeBuddy Primary Executor / Verified Repository Change Workflow
Phase: M5-A — Minimal Implementation Design

## 1. Mission and product boundary

The first write-capable DSH business workflow is:

    DSH
      -> CodeBuddy primary executor
      -> Planner post-execution evaluation
      -> Codex read-only verifier
      -> Planner terminal Decision
      -> DSH-owned TaskState completion

CodeBuddy is the builder. It receives the requested repository task and may
perform the explicitly supported file edits and repository-local Python check.
Codex is an independent read-only verifier of the resulting workspace. DSH
owns task submission, governance, sequencing, invocation budget, and final
task state.

This design accepts the empirically established product boundary:

    CodeBuddy executes under the host user's filesystem authority.
    DSH workspace is a logical operating boundary, not a hard security boundary.

The first M5 workflow must therefore not be represented as security-isolated
from paths outside its workspace. `WorkspaceManager` still supplies the
logical workspace's resolved cwd to both capabilities, but cwd alone is not an
OS-level sandbox. If product security requires hard filesystem enforcement,
that is a reconsideration gate, not a speculative addition to this design.

No sandbox, container, VM, `--add-dir`, unrestricted Bash, or generic
filesystem policy is part of minimal v1.

## 2. Accepted baseline and native facts

The accepted Runtime baseline is:

    M1: CLOSED
    M2: IMPLEMENTATION COMPLETE;
        real Codex service verification DEFERRED / ENVIRONMENT_BLOCKED
    M3: CLOSED / VERIFICATION PASS
    M4: CLOSED / VERIFICATION PASS
    formal regression baseline: 46 passed

The accepted CodeBuddy native facts are:

    ordinary-host CodeBuddy --print: PASS
    authentication: PASS
    Read/Edit and same-cwd mutation: PASS
    non-interactive narrow Bash authorization: PASS
    repository-local Python command/test: PASS
    minimum result normalization: CLOSED
    spawn EPERM blocker: RESOLVED
    workspace boundary: NO RELIABLE CONFINEMENT OBSERVED
    descendant cleanup: PROCESS_TREE_TERMINATION REQUIRED

The frozen native success rule is:

    successful invocation
      = final session result successful
        AND all required function/tool results successful
        AND required filesystem/command effects occurred

Process exit code or session-level success alone is never sufficient.

## 3. Repository-owner analysis

The current implementation was inspected before defining the footprint.

### TaskState and TaskKind

`dsh_runtime/state.py` currently owns caller input, lifecycle, iteration,
budget, latest successful invocation output, final result, and authority. It
already rejects `REPOSITORY_ANALYSIS` when write authority is requested. A
distinct write intent is required; reusing that kind would weaken the M4
read-only invariant.

### Planner and Decision

`dsh_runtime/planner.py` owns business-intent routing and returns the existing
`Decision(plugin, params)` object. It can select one action after another, but
its terminal Decision currently has no failure payload.

### Controller

`dsh_runtime/controller.py` owns the loop, resolves cwd, invokes one action,
increments iteration after settlement, calls Planner again, and commits the
terminal TaskState transition. A successful plugin result is currently always
committed as task success when Planner returns a terminal Decision.

That behavior is correct for existing M1–M4 flows but cannot express a
successful Codex invocation whose verifier report is negative. The smallest
evidence-backed extension is for an existing terminal `Decision` to carry a
failure outcome and for Controller to apply that outcome. This is an owner
extension, not a new workflow owner.

### Executor, Plugin protocol, and PluginResult

`dsh_runtime/runtime/executor.py` already owns one bounded invocation,
timeout, cancellation intent, cleanup settlement, and StopReason
normalization. `dsh_runtime/runtime/plugin.py` already carries cwd, DSH write
authority, output, error, cleanup_error, and StopReason. No generic process
handle or Plugin protocol change is required.

### Registry and workspace

`PluginRegistry` is an in-memory name-to-plugin registry with duplicate
registration checks. It can register one concrete CodeBuddy plugin without a
registry redesign. `WorkspaceManager` already maps a logical workspace to a
resolved local cwd and is sufficient for the CodeBuddy -> Codex handoff.

### Existing capabilities and tests

`CodexPlugin` already provides a one-shot ephemeral read-only app-server path
and maps `allow_workspace_write=False` to `approvalPolicy=never`.
`EchoPlugin` preserves the default compatibility path. Existing tests prove
M3 continuation, budget, terminality, timeout, cleanup waiting, and Codex
workspace propagation. New M5 tests can use local bounded doubles and the
existing Codex stub; real service availability is not required for
deterministic M5 verification.

## 4. Business intent proposal

Add the distinct task kind:

    TaskKind.REPOSITORY_CHANGE = "repository_change"

Its semantic contract is different from M4:

    REPOSITORY_ANALYSIS
      = read-only investigation -> Codex

    REPOSITORY_CHANGE
      = authorized write-capable implementation -> CodeBuddy -> Codex review

For the first M5 version, `TaskState` validation should require:

    task_kind is REPOSITORY_CHANGE
      -> allow_workspace_write is True
      -> max_iterations is at least 2

The M5 caller should use `max_iterations=2`: one CodeBuddy invocation and one
Codex verification invocation. Planner terminates after verification, so this
version has no repair/retry loop even if a caller supplies a larger bound.
The existing global default `max_iterations=1` remains unchanged for Echo and
M4 compatibility; an M5 caller must opt into the two-invocation contract.

The task goal, logical workspace id, DSH authority flag, iteration count,
`last_invocation_result`, and final result remain the only task state needed.
No TaskContext or workflow DTO is introduced.

## 5. Minimal Planner sequence

The existing Planner seam is extended by task kind and iteration:

    REPOSITORY_CHANGE, iteration 0
      -> Decision(plugin="codebuddy", params={"prompt": task.goal})

    REPOSITORY_CHANGE, iteration 1
      -> Decision(plugin="codex", params={"prompt": verifier_prompt})

    REPOSITORY_CHANGE, iteration 2
      -> terminal Decision based on the settled Codex verifier output

The verifier prompt is constructed from the original task goal and instructs
Codex to inspect the current resolved workspace, remain read-only, and finish
with one exact business marker:

    DSH_VERIFICATION: PASS
    DSH_VERIFICATION: FAIL

The existing `last_invocation_result` carries the latest successful output.
The Planner does not need a history object: iteration identifies the stage and
the workspace carries the CodeBuddy effect. A successful CodeBuddy output is
not itself task success.

The Planner maps verifier output as follows:

    exact PASS marker
      -> terminal Decision(success=True)

    exact FAIL marker
      -> terminal Decision(success=False, terminal_error=<bounded report>)

    missing or malformed marker
      -> terminal Decision(success=False, terminal_error="invalid verifier result")

The bounded report may be retained in `last_invocation_result` and the task
error. No structured verifier DTO is required. A native Codex failure is
different: `CodexPlugin` returns unsuccessful, so existing Controller failure
handling ends the task before a post-result Planner call.

### Small terminal Decision extension

Extend the existing `Decision` with fields equivalent to:

    terminal_success: bool = True
    terminal_error: str | None = None

They are meaningful only when `plugin is None`. Existing `Decision(plugin=None)`
continues to mean terminal success, preserving all current tests. Controller's
terminal branch becomes:

    terminal_success
      -> task.apply_success(task.last_invocation_result)

    terminal failure
      -> task.apply_failure(terminal_error or bounded default)

The initial terminal-decision safety path remains task failure. This is the
smallest change that lets Planner own the business meaning of a negative
verification report while Controller remains the final TaskState owner.

## 6. CodeBuddyPlugin contract

Create exactly one concrete plugin:

    dsh_runtime/plugins/codebuddy.py
    name = "codebuddy"

It owns only CodeBuddy-specific bounded native mechanics.

### Invocation

The initial implementation surface is the proven CLI print mode:

    codebuddy.cmd --print
      --output-format json
      --input-format text
      --max-turns 6
      --no-session-persistence
      --tools Read,Edit,Bash
      --settings <task-scoped narrow settings>
      --permission-mode dontAsk
      --allowedTools=Bash(python:*)

The exact command and settings are private plugin configuration, not a
generic provider abstraction. `ctx.cwd` is passed as the process cwd. No
`--add-dir` or sandbox flag is passed. The first v1 bounded unit is one
CodeBuddy print invocation with a native max-turn bound of 6 and the outer
DSH `timeout_seconds` bound.

### Input and authority

The plugin accepts a non-empty prompt from Decision params or `ctx.goal`. It
requires a valid `ctx.cwd` and `ctx.allow_workspace_write=True` for the M5
write-capable task. It does not infer authority from prompt text.

The task-scoped settings allow exactly:

    Read
    Edit
    Bash(python:*)

This is tool exposure plus narrow tool authorization; it is not hard
filesystem confinement. Direct outside-cwd evidence means the plugin must not
claim that `cwd` prevents host-level access outside the logical workspace.

The first M5 command contract intentionally supports repository-local Python
checks. `git`, `pytest`, `npm`, arbitrary shell composition, and other command
families are not silently added. If a real product task requires them, that is
a native re-verification and reconsideration gate.

### Native result normalization

The plugin parses the private JSON event array without introducing a generic
event hierarchy. It locates the final session result and inspects every
required `function_call_result`.

It returns:

    PluginResult(success=True, output=<usable final assistant text>)

only when the final session result is successful, all required tool results
are successful, and required effects are observable. Otherwise it returns an
unsuccessful PluginResult with the best bounded native diagnostic. Permission
denial, spawn/native error, unexecuted required operation, max-turn
exhaustion, and native/service failure are failures even when CLI exit code or
session result is nominally successful. Executor supplies the normalized
StopReason.

### Process lifecycle and cleanup

The plugin launches the CLI with `shell=False`, retains the root process
handle, captures bounded stdout/stderr, and waits for settlement. It does not
delegate process ownership to Executor or create a ProcessManager.

On Runtime cancellation, the plugin performs CodeBuddy-specific cleanup before
re-raising cancellation. On Windows the private cleanup path terminates the
known CodeBuddy root with a bounded process-tree operation (for example
`taskkill /PID <root> /T /F`), waits for root settlement, and records a
cleanup diagnostic if the hierarchy cannot be settled. Platform-specific
process enumeration and termination remain private implementation details.

The plugin must not return from cancellation while known CodeBuddy/Bash
descendants remain unaccounted for. Cleanup failure is surfaced through the
existing `cleanup_error`/exception path so Executor retains timeout versus
cleanup facts. Outer timeout remains Executor-owned and maps to
`StopReason.TIMED_OUT`; plugin cleanup does not turn it into ordinary
success.

### Explicit non-responsibilities

CodeBuddyPlugin does not own:

    business loop
    Planner sequencing
    final TaskState
    cross-plugin coordination
    generic workflow state
    generic provider abstraction
    logical workspace lifecycle
    final verification semantics

## 7. Permission contract

The minimal v1 permission contract is concrete and narrow:

    DSH TaskState allow_workspace_write=True
      -> CodeBuddy acceptEdits-capable mapping
      -> tools Read,Edit,Bash
      -> permissions allow Read, Edit, Bash(python:*)
      -> permission-mode dontAsk
      -> no --add-dir, no sandbox, no dangerous bypass

`--tools` exposes the bounded capability surface. The settings and
`--allowedTools` rule authorize only the required command family. The plugin
must preserve the distinction and must not translate this into unrestricted
Bash or hard path isolation.

The expected first workflow is file mutation plus a repository-local Python
check. A command outside `Bash(python:*)` is a contract violation or a
reconsideration trigger, not an automatic permission widening.

## 8. Codex verification handoff

Reuse the existing `CodexPlugin` unchanged. The handoff is:

    CodeBuddy receives logical workspace X -> resolved cwd X
      -> CodeBuddy settles and returns normalized result
      -> Planner selects Codex
      -> Codex receives the same resolved cwd X
      -> Codex runs with allow_workspace_write=False
      -> Planner evaluates the verifier marker
      -> Controller commits terminal TaskState outcome

The resulting workspace is the cross-action artifact. No copy,
synchronization layer, session manager, or history object is introduced.
Codex's existing `approvalPolicy=never` read-only path remains the verifier
authority. Real Codex service verification remains separate M2 debt and is not
reopened by M5 design.

## 9. Failure and cancellation matrix

| Situation | Normalized result / transition | Primary owner |
|---|---|---|
| CodeBuddy native success | `PluginResult.success=True`; Controller increments iteration; Planner selects Codex | CodeBuddyPlugin, then Planner |
| CodeBuddy native/tool failure | bounded diagnostic, unsuccessful result, task fails | CodeBuddyPlugin + Controller |
| CodeBuddy permission failure | unsuccessful result with permission diagnostic; no false success from exit 0 | CodeBuddyPlugin + Controller |
| CodeBuddy timeout | Executor cancels plugin, waits for cleanup, returns `TIMED_OUT`; task becomes timed out | Executor + CodeBuddyPlugin cleanup |
| CodeBuddy process-tree cleanup failure | timeout retains `cleanup_error`; caller cancellation is re-propagated after best-effort bounded cleanup | Executor + CodeBuddyPlugin |
| Codex native invocation failure | existing unsuccessful Codex result; task fails before terminal success | CodexPlugin + Controller |
| Codex verification success report | Planner returns terminal success Decision; Controller applies final result | Planner + Controller |
| Codex verification negative report | Planner returns terminal failure Decision with bounded report; Controller applies FAILED | Planner + Controller |
| Invocation budget exhausted | no next action; TaskState becomes `MAX_ITERATIONS`; no final success commit | DSHController |
| Planner terminal failure | existing Controller terminal owner applies `TaskState.FAILED` using Decision error | Planner + DSHController |
| Outer caller cancellation | Executor waits for Plugin cleanup, then preserves cancellation propagation | Executor + CodeBuddyPlugin |

No new StopReason or result hierarchy is introduced.

## 10. Minimum production footprint

| File / area | Classification | Reason |
|---|---|---|
| `dsh_runtime/state.py` | must change | add `REPOSITORY_CHANGE`; enforce explicit write authority and minimum two-invocation budget |
| `dsh_runtime/planner.py` | must change | CodeBuddy -> Codex sequencing, verifier prompt, terminal verifier outcome, Decision terminal-failure fields |
| `dsh_runtime/controller.py` | likely change, narrowly | apply terminal failure Decision while preserving DSH final-state ownership |
| `dsh_runtime/plugins/codebuddy.py` | must change / new | CLI launch, JSON/native normalization, bounded cleanup, CodeBuddy permission mapping |
| `dsh_runtime/runtime/registry.py` | registration/wiring only | existing registry semantics are sufficient; register `CodeBuddyPlugin` at the assembly/test boundary |
| `dsh_runtime/runtime/plugin.py` | should remain unchanged | existing context/result/StopReason fields cover the contract |
| `dsh_runtime/runtime/executor.py` | should remain unchanged | existing timeout, cancellation, cleanup settlement, and normalization are provider-agnostic |
| `dsh_runtime/workspace/manager.py` | should remain unchanged | existing logical workspace -> cwd propagation is sufficient |
| `dsh_runtime/plugins/codex.py` | should remain unchanged | existing bounded read-only verifier is reusable |
| `dsh_runtime/plugins/echo.py` | should remain unchanged | preserve DEFAULT compatibility |
| `tests/test_runtime.py` | likely extend | TaskKind, Planner sequence, terminal verifier failure, budget and final-state tests |
| `tests/test_codebuddy_plugin.py` | must add | local fake CLI/native JSON, permission mapping, normalization and cleanup tests |
| `tests/test_codex_plugin.py` | should remain unchanged initially | existing read-only handoff tests already cover cwd and Codex behavior |
| `tests/test_runtime_semantic_hardening.py` | likely extend or cover in new file | timeout/cleanup facts may be tested with a CodeBuddy-specific fake process |

The only existing-owner change not predicted by the earlier M4 baseline is
the narrow terminal failure Decision support, required by the product meaning
of a negative verifier report. No controller loop redesign is proposed.

## 11. Deterministic acceptance boundary

The future implementation must prove, with local bounded doubles/stubs:

1. A `TaskState` with `TaskKind.REPOSITORY_CHANGE`, explicit write authority,
   and a two-invocation budget is accepted; M4 Repository Analysis remains
   read-only and rejects write authority.
2. Production `SimplePlanner` selects `codebuddy` first with the original
   goal and the resolved logical workspace.
3. A deterministic CodeBuddy plugin double settles successfully and produces
   an expected workspace mutation.
4. Controller stores the settled CodeBuddy output and Planner selects Codex
   second without a special workflow owner.
5. Codex receives the same resolved cwd and read-only authority, settles with
   `DSH_VERIFICATION: PASS`, and Planner returns terminal success.
6. Controller produces `TaskStatus.COMPLETED`, iteration 2, and the expected
   final result only after the terminal Decision.
7. CodeBuddy JSON/session success plus a required tool error is normalized as
   failure; exit code 0 alone cannot pass.
8. CodeBuddy permission failure, native failure, and max-turn exhaustion are
   unsuccessful bounded results with diagnostics.
9. Executor timeout causes CodeBuddy process-tree cleanup, waits for
   settlement, returns `TIMED_OUT`, and preserves cleanup error facts.
10. A controlled CodeBuddy descendant survives root-only termination in a
    deterministic test fixture, while the plugin's bounded tree cleanup
    settles the known hierarchy.
11. A Codex `DSH_VERIFICATION: FAIL` report becomes Planner terminal failure
    and TaskState `FAILED`, with no repair/retry action.
12. A third action is never selected; invocation-budget exhaustion preserves
    existing `MAX_ITERATIONS` semantics.

These tests should use a fake CodeBuddy executable or deterministic local
wrapper for native mapping and the existing Codex app-server stub for verifier
routing. They must not require a live model service.

### Real-host verification boundary

Separate real CodeBuddy verification may later repeat the already-proven
ordinary-host disposable-repository contract: Read -> Edit ->
`python` check -> normalized settled result, plus the selected process-tree
cleanup behavior. It must never use the real DSH Runtime repository as cwd.
Real Codex service availability remains M2 debt and is not an M5 deterministic
acceptance prerequisite.

## 12. Implementation slices (not executed)

The smallest reviewable slices are:

### M5-B1 — business intent and terminal Decision contract

Add `REPOSITORY_CHANGE`, its TaskState authority/budget invariants, the
CodeBuddy/Codex Planner sequence, verifier marker evaluation, and the minimal
terminal failure Decision/Controller branch. Preserve DEFAULT and M4 tests.

### M5-B2 — bounded CodeBuddy capability

Add `CodeBuddyPlugin` with the exact CLI mapping, private JSON normalization,
cwd propagation, outer-cancellation response, and bounded Windows process-tree
cleanup. Add focused fake-native tests.

### M5-B3 — registry and workflow wiring

Register the concrete plugin at the existing assembly boundary and construct
the M5 task through the existing caller path. Do not alter registry semantics
or introduce a router/coordinator.

### M5-B4 — deterministic end-to-end verification

Prove CodeBuddy mutation -> same-workspace Codex read-only verification ->
Planner terminal Decision -> DSH TaskState completion, plus failure,
timeout/cleanup, negative verification, and budget cases.

No slice in this design has been performed.

## 13. Explicit non-goals

M5A does not include:

    WorkflowEngine
    AgentCoordinator
    Provider Framework or provider router
    ProcessManager
    ExecutionHandle
    ShellManager
    generic ProcessLifecycle abstraction
    generic PermissionPolicy
    generic filesystem sandbox framework
    TaskContext or PlannerContext
    event bus
    generic CodeBuddy event DTO hierarchy
    generalized multi-agent system
    repair/retry loop
    streaming or resume semantics
    rollback or worktree synchronization
    M4 redesign
    CodexPlugin rewrite
    Ollama integration
    persistent memory integration
    real Codex service retry

## 14. Reconsideration gates

Reopen the architecture only if executable evidence demonstrates one of the
following:

1. Existing TaskState cannot distinguish `REPOSITORY_CHANGE` from the frozen
   read-only `REPOSITORY_ANALYSIS` contract.
2. Existing Planner plus the narrow terminal Decision extension cannot express
   CodeBuddy -> Codex -> terminal success/failure deterministically.
3. Existing Executor cancellation cannot allow CodeBuddyPlugin to terminate
   its owned process hierarchy and settle while preserving timeout/cancellation
   semantics.
4. Hard filesystem confinement is a required product security property rather
   than a desirable assumption; the current soft authority boundary would then
   be insufficient.
5. The first supported task requires command families beyond
   `Bash(python:*)`, and no safe narrow native mapping can be proven without
   unrestricted or prohibited bypass permissions.
6. CodeBuddy's bounded native invocation cannot reliably normalize required
   tool results and filesystem effects.
7. Process-tree cleanup cannot be bounded and owned by CodeBuddyPlugin without
   changing the Runtime cancellation interface.
8. The same resolved workspace cannot be made visible to Codex without a
   synchronization/export mechanism.

No abstraction is introduced before one of these gates is supported by
executable evidence.

## 15. Final scope statement

This artifact is the M5-A minimal implementation design only. It records the
smallest evidence-backed extension of existing owners and the single concrete
CodeBuddy capability required by the approved business workflow.

    Production changes = NONE
    Existing test changes = NONE
    PROJECT_STATE.md changes = NONE
    M5 implementation complete = NOT DECLARED

Per instruction, stop after this design. Do not implement any slice, create
CodeBuddyPlugin, update project state, or declare Milestone 5 implementation
complete.
