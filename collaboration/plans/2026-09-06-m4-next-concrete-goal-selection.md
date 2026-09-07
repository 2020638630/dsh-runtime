# Milestone 4 — Next Concrete Goal Selection

Date: 2026-09-06  
Scope: goal selection, concrete workflow discovery, and requirement analysis only  
Production implementation: not started

## Proven baseline

Milestone 2 and Milestone 3 are formally closed:

```text
Milestone 2 — External Capability Integration
IMPLEMENTATION COMPLETE
Real-service verification DEFERRED / ENVIRONMENT_BLOCKED

Milestone 3 — Bounded Planner-Driven Task Continuation
IMPLEMENTATION COMPLETE
VERIFICATION PASS
```

The current full regression baseline is:

```text
.venv\Scripts\python.exe -m pytest -q
41 passed in 1.04s
```

The duration is incidental; the baseline is `41 passed`.

Milestone 2 real Codex verification remains a separate debt. Its reopen gate is a minimal real Codex turn reaching `turn/completed`. This goal-selection task does not retry that service path.

## What the Runtime can now do

The repository proves the following bounded flow:

```text
DSHController
  -> Planner action Decision
  -> Executor one bounded invocation
  -> Plugin.execute()
  -> PluginResult
  -> Planner post-result Decision
  -> TaskState terminal transition
```

The settled ownership is:

- `DSHController` owns the business loop, invocation budget, continuation, and terminal task transition.
- `Planner` supplies a business-level action or terminal `Decision`.
- `Executor` owns one invocation's timeout/cancellation governance, settlement, and `StopReason` normalization.
- A concrete `Plugin` owns its bounded native mechanics.
- `PluginResult` reports one invocation outcome.
- `TaskState` owns task lifecycle, settled invocation count, final result, and the latest successful invocation result.

The continuation contract is executable: a successful invocation is observed by the Planner, a post-result terminal Decision commits the final result, and a further action is executed only while invocation budget remains. Failure and timeout remain terminal.

The available concrete capabilities are intentionally small:

- `EchoPlugin` provides a deterministic one-action baseline.
- `CodexPlugin` provides one bounded, ephemeral, app-server-backed Codex invocation through the existing Plugin seam.

## Current workflow gaps

### 1. Normal DSH flow cannot intentionally select Codex

`SimplePlanner.next_action()` unconditionally returns `Decision(plugin="echo", ...)` for the initial evaluation and a terminal Decision after the first successful invocation (`dsh_runtime/planner.py:19-23`). The production Controller can execute Codex, but only a custom Planner selects it in the current tests (`tests/test_codex_plugin.py:103-120`).

The repository context names Repository Analysis, Architecture Refactor, complex Debug, Code Review, cross-file modification, test-failure diagnosis, and Milestone Implementation as appropriate Codex tasks (`资料库/CODEX_CONTEXT.md:1372-1392`). No one of these is currently represented as a normal DSH caller workflow with an explicit selection rule.

### 2. Milestone 3's two-step behavior is proven synthetically, not as a product workflow

`tests/test_runtime.py:111-137` proves that a scripted Planner can execute two `RecordingPlugin` actions and observe the latest result. This validates Runtime semantics, but `first` and `second` are test doubles and do not correspond to two useful product capabilities. The repository has no second concrete capability whose output is required by a real next action.

Therefore, adding another generic continuation abstraction would not close a demonstrated product gap.

### 3. Task input carries a goal but no explicit business intent

`TaskState` carries `goal`, workspace identity, budget, timeout, and authority (`dsh_runtime/state.py:19-33`). The Planner can inspect the task, but there is no small caller-visible distinction between “echo this goal” and “perform read-only Repository Analysis with Codex.” Adding a generic context hierarchy is not justified; the missing evidence points to one concrete intent/selection input if Candidate 1 is accepted.

### 4. Artifacts and task cancellation have no concrete consumer

`TaskState.artifacts` exists but has no producer/consumer contract or tested workflow. Executor-level caller cancellation and cleanup are tested (`tests/test_codex_plugin.py:187-201`, `tests/test_disposable_lifecycle.py`), but no Controller caller needs a distinct task-level `CANCELLED` state. Both remain possible future requirements, not current Milestone 4 goals.

## Planner-boundary observations

The current Planner boundary is intentionally small:

```text
next_action(task: TaskState) -> Decision
Decision(plugin != None) -> action
Decision(plugin == None) -> terminal
```

Planner currently receives the complete `TaskState`, including `goal`, `workspace_id`, invocation budget, latest successful invocation result, and authority flag through the task. It can construct bounded plugin parameters, as custom test Planners already do for Codex.

The constraint is not that Planner cannot observe results or construct parameters. Milestone 3 proves that it can. The constraint is that the only production policy, `SimplePlanner`, hardcodes Echo and has no concrete task-selection rule. `SimplePlanner` is therefore a deterministic compatibility baseline, not evidence that Echo is product policy for every future DSH workflow.

No Planner redesign is warranted before a concrete workflow is named. The smallest plausible change is an explicit input/intent at the existing task boundary plus a narrow Planner rule for one named workflow.

## Candidate 1 — Explicit read-only Repository Analysis routing

### Concrete workflow

```text
Caller submits a Repository Analysis task with explicit Codex intent
  -> existing Planner selects Decision(plugin="codex", params={"prompt": goal})
  -> DSHController resolves the logical workspace
  -> CodexPlugin performs one bounded read-only invocation
  -> final bounded answer is committed to TaskState.result
  -> task reaches COMPLETED
```

### Current blocker

There is no caller-visible intent or capability-selection input, and `SimplePlanner` always chooses Echo. A normal DSH task cannot request this concrete workflow without injecting a custom Planner.

### Repository evidence

- `CodexPlugin` is already registered and executable through the existing `Plugin` boundary.
- `tests/test_codex_plugin.py:58-78` proves deterministic bounded Codex success, cwd propagation, ephemeral thread use, and read-only native permission mapping.
- `tests/test_codex_plugin.py:103-120` proves Controller-to-Codex routing, but only with a custom test Planner.
- `资料库/CODEX_CONTEXT.md:1382-1392` explicitly names Repository Analysis as an appropriate Codex use.
- `dsh_runtime/planner.py:19-23` proves the production Planner policy gap.

### Existing owner

Extend the existing `TaskState` input boundary and `Planner` policy. `DSHController`, `Executor`, `PluginRegistry`, `WorkspaceManager`, and `CodexPlugin` keep their current ownership. No new router or provider owner is needed.

### Smallest likely change

Add one explicit, concrete caller intent/selection value for the Repository Analysis workflow and teach the existing Planner to emit the Codex action only for that value. Keep `allow_workspace_write=False` for this first workflow and use the existing `goal` as the bounded prompt. The exact field name should be chosen during implementation design; it must not expand into `TaskContext`, dynamic routing, or a provider framework.

### Deterministic verification strategy

Use the existing local app-server stub and invoke the normal production Planner path rather than a custom test Planner. Assert that:

1. the named task intent selects `codex`;
2. the prompt and logical workspace reach the existing Codex Plugin;
3. read-only authority remains in force;
4. one successful invocation becomes the final `TaskState.result` and `COMPLETED`;
5. Echo compatibility, unknown-plugin handling, timeout, cleanup, and the full `41 passed` regression remain green.

No cloud-model quality or real-service verification is part of this acceptance boundary.

### Why now

This is the first concrete end-user workflow that uses the Milestone 2 capability and the Milestone 3 decision/continuation contract without inventing another infrastructure layer. It closes a visible product gap: an existing bounded capability is executable but not normally selectable.

### Why not yet / risks

- The repository currently has no public HTTP/task-submission adapter; the caller contract must stay as small as the workflow requires.
- A broad natural-language classifier would be speculative and non-deterministic. The first acceptance boundary should use explicit intent, not automatic semantic routing.
- Real Codex final-answer and side-effect behavior remains externally blocked and must not be conflated with local routing verification.

### Explicit non-goals

No dynamic provider routing, model router, automatic intent classifier, workspace-write workflow, Codex multi-turn session, streaming, retry/replanning, or real-service probe retry.

## Candidate 2 — First useful two-action repository workflow

### Concrete workflow

```text
Repository analysis action
  -> analysis result
  -> second action consumes that result
  -> terminal task result
```

### Current blocker

The repository does not contain a second concrete product capability that consumes a Codex analysis result. `EchoPlugin` can be scripted as the second action, but echoing an analysis is not a useful DSH workflow. The existing two-step test is deliberately synthetic.

### Repository evidence

- The bounded continuation contract and latest-result handoff are already proven in `tests/test_runtime.py:111-137`.
- The available production Plugins are Echo and one-shot Codex; there is no FilePlugin, artifact writer, verifier, or other real consumer.
- `TaskState.last_invocation_result` is intentionally one latest result, not generic history.

### Existing owner

If a real second capability is later identified, the existing Planner should construct the next Decision and the existing Controller should continue to own the loop. The second concrete Plugin would own its own native mechanics. No new loop owner is indicated.

### Smallest likely change

First name and justify the second product action. Until then, any implementation would either add a speculative capability or repackage the already-proven continuation test.

### Deterministic verification strategy

Only after a real second capability is named: local deterministic doubles or a capability-specific stub must prove result consumption, ordering, bounded budget, terminal result ownership, and failure/timeout behavior.

### Why now

Milestone 3 makes this workflow shape possible and provides a good pressure test for a real vertical slice.

### Why not yet / risks

There is currently no user requirement or product capability to make the second action useful. Selecting this now would be using the continuation loop to justify more infrastructure instead of solving a concrete DSH need.

### Explicit non-goals

No Workflow DSL, task DAG, generic history, event bus, parallel execution, or synthetic Echo-to-Echo workflow.

## Candidate 3 — Caller-observable task cancellation

### Concrete workflow

```text
Caller starts a long-running bounded Codex task
  -> caller requests cancellation
  -> Plugin cleanup settles
  -> caller observes a distinct task cancellation outcome
```

### Current blocker

The Executor already preserves caller cancellation after cleanup, but there is no current Controller-level caller/API that requests cancellation and no demonstrated requirement to distinguish `CANCELLED` from `FAILED` or `TIMED_OUT` in `TaskState`.

### Repository evidence

- `tests/test_codex_plugin.py:187-201` proves outer cancellation propagation after Codex cleanup.
- `tests/test_disposable_lifecycle.py` proves cancellation and cleanup ordering for local process/double lifecycles.
- `TaskStatus` has `FAILED` and `TIMED_OUT`, but no `CANCELLED` (`dsh_runtime/state.py:10-16`).
- Milestone 2 and 3 closures explicitly leave task-level cancellation as a deferred requirement.

### Existing owner

If a real caller appears, `DSHController` and `TaskState` should own task-level meaning. `Executor` and each Plugin should retain invocation cleanup and cancellation mechanics.

### Smallest likely change

Only after a caller boundary is identified, add the smallest Controller-to-TaskState mapping and focused tests. Do not add a cancellation framework or token hierarchy in advance.

### Deterministic verification strategy

Provide a real caller-level cancellation trigger in the test boundary, assert cleanup-before-observation, and preserve distinct timeout and failure outcomes.

### Why now

This is a plausible safety requirement for future long-running external work, and the lower-level evidence already exists.

### Why not yet / risks

There is no current caller to accept or observe the new state. Implementing it now would expand task semantics without a concrete workflow and could incorrectly promote an Executor fact into product policy.

### Explicit non-goals

No `CancellationContext`, event bus, generic cancellation framework, or change to the proven Executor ownership.

## Ranking

| Rank | Candidate | Concrete workflow evidence | Smallest bounded scope | End-to-end value now | Architecture risk | Decision |
|---:|---|---|---|---|---|---|
| 1 | Explicit read-only Repository Analysis routing | Strong: named in project context; Codex path and deterministic stub already exist; only normal Planner selection is missing | Small: one explicit intent/selection input plus narrow existing Planner rule | High | Low | Recommend |
| 2 | First useful two-action repository workflow | Medium for the Runtime shape, weak for product value: no real second capability or consumer exists | Unknown until a second action is named | Potentially high, currently unproven | Low if a concrete capability appears; speculative now | Defer |
| 3 | Caller-observable task cancellation | Lower: cleanup/propagation evidence exists, but no task-level caller requirement | Small-medium after caller boundary exists | Not demonstrated | Low if caller-driven; premature now | Defer |

## Runtime-semantic vs workflow-driven assessment

The next bottleneck is workflow-driven, not Runtime-internal.

Repository evidence supports that conclusion:

- Milestone 3 proves the Controller/Planner/Executor/Plugin/TaskState continuation semantics, including two-step execution, latest-result observation, bounded invocation count, terminal result ownership, and failure/timeout terminality.
- Milestone 2 proves a concrete Codex Plugin can be invoked through the existing seam, with workspace and authority mapping preserved.
- The current production Planner still always selects Echo, so the missing behavior is a concrete DSH task-selection policy and a minimal caller intent—not a missing loop, executor, process manager, provider framework, or continuation abstraction.

The current architecture should therefore be exercised by a named vertical workflow before any Runtime semantics are reopened.

## Recommended Milestone 4 goal

```text
Recommended Milestone 4 goal:
Enable an explicitly requested, read-only Repository Analysis task to select the existing Codex Plugin through the normal DSH Planner → Controller path and return its bounded final answer as the completed TaskState result.
```

### Why this goal now?

It is the smallest real DSH-level requirement that uses both closed milestones. The capability already exists, the bounded invocation and result contract already exist, and the project context names Repository Analysis as a valid Codex workflow. The remaining gap is observable and specific: normal DSH input cannot request that workflow.

### What concrete workflow becomes possible?

A caller can submit a Repository Analysis task with explicit Codex intent, a logical workspace, and read-only authority. The existing Planner selects Codex, the Controller resolves the workspace and runs one bounded invocation, and the final bounded answer becomes `TaskState.result` with `TaskStatus.COMPLETED`.

### What currently prevents that workflow?

`SimplePlanner` hardcodes Echo, and `TaskState` has no explicit input that distinguishes this named workflow from the Echo compatibility path. Codex routing is currently only demonstrated with a custom test Planner.

### Which existing owner changes?

Only the existing task-input/Planner boundary should change:

- `TaskState` may gain one concrete Repository Analysis intent/selection value if that is the smallest caller contract.
- `SimplePlanner` or the existing injected Planner policy may map that value to `Decision(plugin="codex", params=...)`.

The exact field and naming require implementation design after this goal is authorized; no implementation is part of this document.

### Which owners do not change?

`DSHController`, `Executor`, `PluginRegistry`, `WorkspaceManager`, `CodexPlugin`, `PluginResult`, and `TaskState` lifecycle/result ownership do not change. In particular:

- Controller remains the only business-loop and terminal-state owner.
- Executor remains the one-invocation timeout/cancellation/settlement owner.
- CodexPlugin remains the Codex-specific bounded native lifecycle owner.
- No new Runtime owner or framework is introduced.

### What is the minimum acceptance boundary?

1. A caller can express the named Repository Analysis intent without injecting a custom test-only Planner.
2. The normal Planner path emits a Codex action with a bounded prompt derived from the task goal.
3. The existing logical workspace and read-only authority mapping reach Codex unchanged.
4. A deterministic local Codex stub produces a bounded successful output.
5. The Controller performs exactly one invocation, stores the output as `TaskState.result`, and reaches `COMPLETED`.
6. Echo compatibility, failure/timeout/cleanup behavior, and the full regression baseline remain green.
7. The acceptance boundary does not claim successful real cloud-model verification; that remains gated separately by `turn/completed`.

### What evidence would invalidate the recommendation?

Reconsider this goal if any of the following becomes true:

- No real caller or DSH-level use case can be named for Repository Analysis.
- The caller already has an equivalent explicit selection path, making the proposed gap illusory.
- A deterministic test shows the existing TaskState → Planner → Controller seam cannot carry the one concrete intent without a generic context or routing framework.
- The desired workflow requires a second meaningful action, durable history, task cancellation, workspace side-effect observation, or another semantic not represented by the current contract; that would require a new candidate and separate evidence.
- The real Codex service reaches `turn/completed` and reveals a concrete result/permission/side-effect defect; that would reopen the Milestone 2 verification gate separately, not automatically change this goal.

## Explicit non-goals

This selection task authorizes no implementation and no production scaffolding. It does not authorize:

```text
ExecutionHandle
ProcessManager
AgentExecutor
LoopManager
ContinuationManager
WorkflowEngine
Workflow DSL
Event Bus
Provider Framework
ExternalAgent Framework
CodexAdapter
TaskContext
PlannerContext
generic history
generic PermissionPolicy
generic process result DTO
dynamic provider routing
automatic intent classification
retry/replanning
parallel execution
task DAG
task-level cancellation without a caller
workspace-write side-effect workflow
resume
persistent session
Codex multi-turn
streaming
rollback
diff
usage/cost accounting
real Codex service retries
```

No production files were changed during this goal-selection task.
