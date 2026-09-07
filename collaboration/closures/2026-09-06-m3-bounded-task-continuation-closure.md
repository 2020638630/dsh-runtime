# Milestone 3 — Bounded Task Continuation Closure

Date: 2026-09-06  
Overall status: `IMPLEMENTATION COMPLETE`  
Verification status: `PASS`

## Proven Runtime continuation shape

The verified flow is:

```text
DSHController -> Planner action Decision -> Executor one bounded invocation
-> settled PluginResult -> Planner post-result Decision
-> terminal Decision: COMPLETED
or action Decision with budget: next invocation
or action Decision at exhausted budget: MAX_ITERATIONS
```

Ownership remains unchanged. DSHController owns the business loop, invocation budget, continuation decisions, and terminal `TaskState` transitions. Planner supplies business-level action or terminal decisions. Executor governs one invocation and its timeout/cancellation settlement. Plugin owns bounded native mechanics. PluginResult reports one invocation outcome. TaskState owns lifecycle, invocation count, final result, and latest successful invocation result.

## Planner decision contract

```text
Decision(plugin != None) -> action Decision
Decision(plugin == None) -> terminal Decision
```

No decision hierarchy or control-protocol framework was added. A successful invocation is not task completion; completion requires the post-result Planner to return an explicit terminal Decision.

`SimplePlanner` follows the same contract:

```text
initial evaluation      -> Echo action
post-success evaluation -> terminal Decision
```

The Controller contains no special case for `SimplePlanner` or `max_iterations == 1`.

## Invocation-budget semantics

`iteration` is the number of settled Executor invocation attempts. It increments exactly once after `Executor.execute()` settles. Planner evaluations do not consume budget, and workspace preflight failure does not increment it.

`max_iterations` bounds invocations, not Planner evaluations. With `max_iterations=0`, Planner and capability invocation are skipped and the task enters `MAX_ITERATIONS`.

At the final invocation boundary, the Planner is evaluated once more. A terminal Decision produces `COMPLETED`; an action Decision produces `MAX_ITERATIONS` without executing that action.

## Task result ownership

`TaskState.result` is written only when a terminal Planner Decision commits successful task completion. `TaskState.last_invocation_result` stores one latest successful invocation output for Planner observation. It is not history, an event log, or an artifact collection.

A successful capability output of `None` is supported; `iteration` and Planner call position distinguish it from the absence of a successful invocation. After budget exhaustion, the latest intermediate output is not committed as a successful final task result.

An initial terminal Decision is outside the contract and is deterministically represented as a task failure using the existing failure boundary. No no-op status was added.

## Executable evidence

The continuation tests prove:

- existing SimplePlanner/Echo single-action completion;
- two-step continuation and latest-result observation;
- failure and timeout terminality without a continuation decision;
- budget exhaustion without executing the next action or committing a final result;
- terminal evaluation at the exact budget boundary;
- successful `None` output handling;
- zero-budget skipping the initial Planner evaluation;
- safe initial terminal Decision rejection;
- unchanged Controller-to-Codex deterministic routing under the new Planner contract.

## Regression baseline

Focused verification:

```text
.venv\Scripts\python.exe -m pytest -q tests/test_runtime.py tests/test_codex_plugin.py
20 passed in 0.76s
```

Full regression:

```text
.venv\Scripts\python.exe -m pytest -q
41 passed in 0.98s
```

Exact wall-clock duration is not part of the contract.

## Preserved Milestone 2 boundaries

No changes were made to Executor timeout/cancellation governance, CodexPlugin protocol or process lifecycle, cleanup/quiescence behavior, StopReason normalization, workspace ownership, authority mapping, or real Codex verification state.

Blocked real Codex service verification was not retried. Its reopen gate remains a minimal real Codex turn reaching `turn/completed`.

## Explicit no-change decisions

The following remain out of scope and unjustified: `LoopManager`, `ContinuationManager`, `AgentExecutor`, `WorkflowEngine`, `Workflow DSL`, `Event Bus`, `TaskContext`, `PlannerContext`, `ResultHistory`, `ExecutionHandle`, `ProcessManager`, Provider Framework, ExternalAgent Framework, retry/replanning, parallel execution, task DAG, resume, persistent sessions, Codex multi-turn, streaming, rollback, diff, usage/cost accounting, and dynamic provider routing.

## Deferred requirements

Real Codex turn completion, dynamic Codex routing, task cancellation state, retry/replanning, parallel actions, task DAG, workflow DSL, persistent sessions, Codex multi-turn, streaming, resume, rollback, and usage/cost accounting are not required for Milestone 3 closure. Each requires an independent concrete requirement and evidence.

## Reopen gates

Reopen this goal only if executable evidence shows that the existing Controller/Planner/TaskState seam cannot preserve continuation ownership, a new workflow requires semantics not represented by action/terminal Decision and one latest-result slot, or a regression violates bounded invocation, final-result ownership, or failure/timeout terminality.

Do not reopen the architecture merely because future capabilities might need additional features.

## Next-session handoff

Milestone 3 — Bounded Planner-Driven Task Continuation is formally closed:

```text
IMPLEMENTATION COMPLETE
VERIFICATION PASS
```

The next session must treat continuation semantics and Milestone 2 lifecycle ownership as settled. No subsequent Milestone 3 feature is started by this closure.
