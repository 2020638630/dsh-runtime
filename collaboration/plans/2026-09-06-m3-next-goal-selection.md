# Milestone 3 — Next Goal Selection

Date: 2026-09-06  
Scope: goal selection, requirement discovery, and planning only  
Production implementation: not started

## Current proven baseline

Milestone 2 is closed as `IMPLEMENTATION COMPLETE`; real-service verification is deferred as `ENVIRONMENT_BLOCKED`. The current proven Runtime shape remains:

```text
DSHController
  ↓
Executor
  ↓
Plugin.execute()
  ↓
Concrete bounded capability
  ↓
PluginResult
  ↓
TaskState
```

The settled ownership decisions are retained:

- DSH owns the business loop and terminal task decisions.
- Executor owns invocation timeout/cancellation governance and result normalization.
- A concrete Plugin owns bounded native/product mechanics and cleanup.
- `Plugin.execute()` is sufficient.
- `ExecutionHandle`, `ProcessManager`, provider abstractions, and generic permission/process DTOs remain unjustified.
- `workspace_id` remains logical identity.

The real Codex verification debt is external-service evidence, not a Milestone 3 architecture requirement. It is not reopened here.

## Repository observations

Files and areas inspected:

- `dsh_runtime/controller.py`
- `dsh_runtime/planner.py`
- `dsh_runtime/state.py`
- `dsh_runtime/runtime/executor.py`
- `dsh_runtime/runtime/plugin.py`
- `dsh_runtime/runtime/registry.py`
- `dsh_runtime/workspace/manager.py`
- `dsh_runtime/plugins/echo.py`
- `dsh_runtime/plugins/codex.py`
- `tests/test_runtime.py`
- `tests/test_runtime_semantic_hardening.py`
- `tests/test_disposable_lifecycle.py`
- `tests/test_codex_plugin.py`
- Milestone 2 closure, investigation, plan, and handover documents under `collaboration/`

Current regression baseline:

```text
.venv\Scripts\python.exe -m pytest -q
33 passed in 0.93s
```

The most important current behavior is:

1. `TaskState` already has `max_iterations`, `iteration`, `MAX_ITERATIONS`, result, and error fields.
2. `DSHController` already owns a `while task.iteration < task.max_iterations` loop and asks the Planner for a `Decision`.
3. The controller currently returns immediately after the first invocation, whether that invocation succeeds or fails. The loop therefore does not yet express a multi-step task.
4. `SimplePlanner` always returns the deterministic `echo` capability. Codex is available through the Plugin seam and custom planners can select it in tests, but no concrete product requirement currently specifies default Codex routing.
5. Executor and Plugin lifecycle semantics are already covered by executable evidence and are not candidates for re-investigation.
6. `TaskState.artifacts` exists but has no producer/consumer contract or demonstrated workflow requirement.

## Candidate 1 — Bounded planner-driven task continuation

### Requirement

Allow a real DSH task to perform more than one bounded business action when the Planner says another action is needed, while preserving DSH ownership of continuation and terminal decisions.

This is narrower than an agent framework: it is a contract for a bounded sequence of Planner decisions inside the existing Controller loop.

### Evidence

- `TaskState.max_iterations` and `TaskState.iteration` already model a bounded task budget.
- `TaskStatus.MAX_ITERATIONS` already exists.
- `DSHController.run()` already has the intended loop shape and Planner call, but returns after the first action.
- `collaboration/designs/2026-09-05-m2-b-minimal-external-invocation-contract.md` explicitly assigns business iteration continuation/stop decisions to DSH and Planner.
- Existing tests only prove one-action completion, zero-iteration behavior, and failure/timeout terminal mapping; none proves a second Planner decision.

### Existing owner

`DSHController`, with the existing `SimplePlanner`/Planner protocol supplying the next `Decision`. `TaskState` remains the state owner. Executor and Plugins remain unchanged owners of invocation mechanics.

### Minimal shape

First clarify the smallest continuation policy, then implement only that policy:

- call Planner for each permitted iteration;
- increment and record the business iteration for each settled invocation;
- continue only when the result is a normal completion and the Planner/task policy says another action is needed;
- preserve immediate terminal mapping for failure and timeout;
- reach `MAX_ITERATIONS` only when the bounded budget is exhausted without a terminal success decision;
- keep each invocation on the existing `Executor.execute()` seam.

The exact success/continue signal must be discovered before implementation. It must not be smuggled into `PluginResult` as a generic agent-control protocol without a concrete requirement.

### Evidence needed to justify completion

- A scripted Planner returns two deterministic Decisions and both execute in order.
- The second invocation receives the same task identity and the correct incremented iteration correlation, if that field is shown to be required.
- Failure or timeout on iteration one prevents iteration two.
- A bounded task that never reaches a terminal success decision ends as `MAX_ITERATIONS`.
- Existing one-action Echo, Codex Plugin, timeout, cleanup, and semantic-hardening tests remain green.
- Structured lifecycle events show bounded iteration ordering without raw capability protocol leakage.

### What should NOT be built

- No Workflow DSL, Event Bus, AgentExecutor, ExternalAgent framework, or generic loop engine.
- No resume, persistent session, streaming, rollback, diff, usage/cost, or multi-turn Codex session.
- No `ExecutionHandle`, `ProcessManager`, or new owner for invocation lifecycle.

## Candidate 2 — Explicit DSH routing to one concrete capability

### Requirement

Make one real DSH workflow select the existing Codex Plugin through the Planner/Controller path, rather than proving Codex only through direct Executor tests and custom test Planners.

### Evidence

- `CodexPlugin` is registered and executable through the existing Plugin boundary.
- `tests/test_codex_plugin.py` proves Controller-to-Codex routing with a custom Planner and a disposable workspace.
- The production `SimplePlanner` still always returns `echo`; there is no user-facing or product-level rule saying when a task should select Codex.
- Milestone 2 established the capability seam but deliberately did not establish capability-selection policy.

### Existing owner

The Planner and DSH configuration boundary. The Codex Plugin should not decide when it is selected, and the Registry should remain a lookup mechanism rather than a policy engine.

### Minimal shape

Only after a concrete workflow is named, add the smallest Planner decision rule or injected Planner configuration needed to select `codex` for that workflow. Keep the decision parameters bounded and retain the existing workspace/authority mapping.

### Evidence needed to justify completion

- A named task workflow selects Codex through the normal Controller path.
- The selected logical workspace and authority intent reach the Plugin correctly.
- The workflow has deterministic tests using the local stub; real model verification remains separately gated.
- Echo behavior and unknown-plugin failure behavior remain unchanged.

### What should NOT be built

- No provider registry, capability discovery, dynamic loading, Factory, `CodexAdapter`, or generic provider hierarchy.
- No default Codex routing policy without a concrete user/workflow requirement.
- No repeated real-service retries as part of implementation.

## Candidate 3 — Task-level cancellation decision contract

### Requirement

Define how an externally cancelled DSH task should be represented at the TaskState boundary, if a real caller workflow requires observing cancellation as distinct from failure or timeout.

### Evidence

- Executor preserves caller `CancelledError` after waiting for Plugin cleanup.
- `TaskState` has `FAILED` and `TIMED_OUT` but no `CANCELLED` status.
- Deterministic lifecycle tests prove cancellation propagation and cleanup, but no Controller entrypoint currently requests or consumes task cancellation.
- The Milestone 2 contract documents cancellation as an ownership distinction but intentionally did not add a task-level cancellation status.

### Existing owner

`DSHController`/`TaskState` for task-level meaning, with Executor retaining invocation cleanup ownership. No cancellation context or generic cancellation framework is justified by current evidence.

### Minimal shape

First identify a concrete caller/API that needs cancellation to be observable. If it exists, add the smallest Controller mapping and state transition, plus focused tests for cleanup-before-propagation. If no such caller exists, keep the current propagation behavior and defer this goal.

### Evidence needed to justify completion

- A real caller can request cancellation at the Controller boundary.
- The task state distinguishes cancellation only where the caller needs that distinction.
- Plugin cleanup still settles before cancellation is reported.
- Timeout and product failure remain distinct.

### What should NOT be built

- No `CancellationContext`, cancellation token hierarchy, event bus, or generic stop-reason expansion without a concrete consumer.
- No change to the already-proven Executor ownership merely to expose hypothetical future cancellation.

## Candidate ranking

| Rank | Candidate | Current requirement evidence | Small bounded implementation | Architectural risk | Recommendation |
|---:|---|---|---|---|---|
| 1 | Bounded planner-driven task continuation | Strong: existing loop fields, controller seam, and documented DSH continuation ownership; current behavior visibly stops after one action | High | Low | Recommend investigation first |
| 2 | Explicit DSH routing to one concrete capability | Medium: Codex path exists, but no concrete selection policy or user workflow is specified | Medium | Low if policy is supplied; speculative otherwise | Defer until workflow is named |
| 3 | Task-level cancellation decision contract | Medium-low: propagation is proven, but no Controller caller needs a distinct state yet | Low-medium | Low | Defer pending caller requirement |

## Recommended Milestone 3 goal

```text
Recommended Milestone 3 goal:
Bounded planner-driven task continuation
```

### Why this goal now?

It is the smallest requirement that follows directly from behavior already represented in the repository. The Runtime has a Planner seam, a DSH-owned loop, iteration accounting, a maximum-iteration state, and a bounded Executor. The missing behavior is not a new capability abstraction; it is that a task configured for more than one iteration cannot currently perform a second action.

### Why is it a real requirement?

The current API advertises bounded iteration through `max_iterations` and `MAX_ITERATIONS`, while the Controller unconditionally returns after the first invocation. That is an observable semantic gap in an existing Runtime workflow, unlike generic provider extensibility or hypothetical future cancellation consumers.

### Why is the current architecture sufficient?

The existing `DSHController → Planner → Executor → Plugin → PluginResult` path already contains every owner needed. The change can remain inside DSH continuation policy and tests. No new lifecycle, provider, permission, or process owner is required.

### Minimum acceptance boundary

Before implementation, clarify one minimal continuation rule. Then prove with deterministic tests that:

1. A Planner can produce two bounded Decisions in sequence.
2. DSH executes them in order through the existing Executor.
3. Failure and timeout remain terminal and prevent further business iterations.
4. The iteration budget produces `MAX_ITERATIONS` when no terminal success decision is reached.
5. Existing single-action and all Milestone 2 regression tests remain green.

This goal should later be split only if evidence warrants it, likely into requirement clarification, minimal Controller implementation, and executable verification.

### Reconsideration / abstraction gates

Stop and reconsider before implementation if the continuation rule cannot be stated without introducing generic agent-control semantics, or if a test shows the existing Controller/Planner/TaskState seam cannot preserve ownership and bounded cleanup. Only concrete evidence of that failure may justify a new abstraction.

Do not reopen the real Codex verification debt unless a minimal real Codex turn reaches `turn/completed`. That debt does not block this goal's deterministic requirement discovery.

## No-change conclusions carried forward

Milestone 3 goal selection does not authorize implementation of:

```text
ExecutionHandle
ProcessManager
Provider Framework
ExternalAgent
AgentExecutor
CLIExecutionCapability
CodexAdapter
Factory
Event Bus
Workflow DSL
WorkspaceContext
CancellationContext
generic PermissionPolicy
generic process result DTO
streaming
resume
persistent session
multi-turn
rollback
diff
usage/cost accounting
```

No production files were changed during this goal-selection task.
