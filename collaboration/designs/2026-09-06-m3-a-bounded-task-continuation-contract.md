# Milestone 3-A — Bounded Task Continuation Contract

Date: 2026-09-06  
Scope: semantic and contract clarification only  
Implementation status: not started

## Existing executable/runtime evidence

Inspected:

- `dsh_runtime/controller.py`
- `dsh_runtime/planner.py`
- `dsh_runtime/state.py`
- `dsh_runtime/runtime/executor.py`
- `dsh_runtime/runtime/plugin.py`
- `tests/test_runtime.py`
- `tests/test_runtime_semantic_hardening.py`
- Milestone 2 closure and integration evidence
- `collaboration/plans/2026-09-06-m3-next-goal-selection.md`

Current full regression:

```text
.venv\Scripts\python.exe -m pytest -q
33 passed in 0.93s
```

The current executable path is:

```text
DSHController
  -> Planner.next_action(TaskState)
  -> Executor.execute(...)
  -> Plugin.execute(...)
  -> PluginResult
  -> TaskState transition
```

The Controller has a `while task.iteration < task.max_iterations` shape, but currently returns immediately after the first settled invocation. The existing loop therefore does not yet implement continuation.

## Current Planner contract

The current `Decision` is:

```python
Decision(plugin: str | None, params: dict[str, Any])
```

It represents one capability invocation only. It cannot express a terminal/no-more-action decision.

The current Planner receives only `TaskState`. It is called before the invocation and cannot currently observe a prior settled invocation through a post-result call. `SimplePlanner` always returns an `echo` invocation.

The existing seam is sufficient for continuation ownership, but the Planner contract needs one minimal terminal-decision extension before a multi-step workflow can be unambiguous.

## Current TaskState iteration semantics

### `iteration`

Current code increments `task.iteration` immediately after `Executor.execute()` returns, before applying the task result. Therefore the evidence-backed meaning is:

> `iteration` is the number of settled capability invocation attempts in the current task.

This includes a normal result, failure, timeout, and unknown-plugin failure returned by Executor. A workspace-resolution failure occurs before an invocation and currently leaves `iteration` unchanged.

It is not a count of Planner evaluations, successful invocations, or zero-based current-action index.

### `max_iterations`

The proposed contract keeps `max_iterations` as the maximum number of settled capability invocations. Planner evaluations, including the post-result terminal evaluation at the budget boundary, do not consume this budget.

### `MAX_ITERATIONS`

The current zero-budget test establishes that `max_iterations=0` performs no invocation and ends in `TaskStatus.MAX_ITERATIONS`. Under the continuation contract, `MAX_ITERATIONS` means:

> DSH has no remaining invocation budget and the Planner has not supplied a terminal task-success decision.

It is not an invocation failure and not a Plugin stop reason.

## Result ownership and semantic gap

`TaskState.result` is currently written by `apply_success()` at the task-completion boundary and is asserted by existing tests as the final task result. It must remain the final task result; it must not silently become an invocation history or latest-result collection.

Continuation requires the Planner to be able to inspect the previous successful invocation when deciding whether the task is complete. The smallest justified state addition is one single-slot `last_invocation_result` value on `TaskState` (not a history collection), populated after a successful invocation and before the post-result Planner evaluation. On a terminal Planner decision, DSH copies that value into the final `TaskState.result` through the existing success transition.

If later evidence shows that the Planner should receive result data without storing it on task state, an equivalent explicit Planner argument could be considered. That is not selected here because the current Planner already receives `TaskState`, and one latest-result slot is the smallest compatible seam for the current code.

The PluginResult remains an invocation outcome. It does not gain a continuation flag.

## Semantic gap

For:

```text
max_iterations = 2

Planner -> Decision A
Invocation A -> COMPLETED
Planner -> Decision B
Invocation B -> COMPLETED
```

the current code has no valid answer to who decides task completion because it returns after A and has no terminal Planner decision. A successful PluginResult cannot by itself mean successful TaskState completion once multiple business actions are possible.

The contract must therefore permit DSH to evaluate the Planner after a successful invocation, including after the final invocation budget is consumed. A terminal Planner decision consumes no invocation budget.

## Candidate continuation models

### Model A — Post-result Planner decision

```text
Planner -> action Decision
  -> Executor / Plugin
  -> settled invocation result
  -> DSH records latest result
  -> Planner evaluates the settled task state
      -> terminal decision
      or
      -> next action Decision
```

Fit:

- Preserves DSH ownership of continuation and terminal task transitions.
- Allows Planner to inspect the previous successful result.
- Keeps Executor responsible for exactly one bounded invocation.
- Preserves PluginResult as invocation outcome rather than business-loop control.
- Allows a terminal Planner evaluation after the final invocation budget without consuming another invocation.

Required minimal evolution:

- Extend `Decision` to represent a terminal/no-action decision, preferably with `plugin=None` as the explicit terminal form.
- Add one latest-result slot to TaskState, or equivalently pass that value explicitly to Planner. This document selects the one-slot TaskState seam.
- Add the post-result Planner evaluation in DSHController during the later implementation phase.

Budget semantics: count settled capability invocations only; terminal Planner evaluations are free.

Backward compatibility is expressed through the Planner contract, not a Controller branch: `SimplePlanner` returns an Echo action initially and an explicit terminal Decision after the successful Echo invocation. For a multi-iteration Planner, the same terminal decision is required; an action returned after the budget is exhausted produces `MAX_ITERATIONS` without starting another invocation.

### Model B — Decision pre-declares continuation intent

```text
Planner -> Decision(action, terminal/continue intent)
  -> invocation
  -> Controller follows the previously declared intent
```

This makes an invocation decision carry business-control semantics before its result exists. It cannot cleanly express a terminal decision based on the result of the final action, and it creates an unnecessary agent-control protocol in `Decision`. It is not selected.

### Model C — Controller infers continuation automatically

Rules such as “success plus remaining budget means continue” or “success always means complete” are both insufficient:

- automatic continuation prevents a Planner-owned workflow from stopping after a successful intermediate action;
- automatic completion prevents a Planner-owned workflow from performing a required second action.

The Controller owns the transition, but it must consume an explicit Planner business decision. It must not infer the business plan from invocation success or remaining budget. Model C is rejected.

### Model D — PluginResult controls continuation

A `PluginResult.continue` field would move business-loop control into the capability boundary. CodexPlugin or another capability would then decide whether DSH performs another business action, violating the settled ownership model. The actual code provides no evidence supporting this direction. Model D is rejected.

## Recommended contract

```text
Recommended continuation model:
Model A — Post-result Planner decision
```

### 1. Planner decision semantics

The Planner produces either:

```text
action Decision:
    one bounded capability invocation

terminal Decision:
    no further invocation; task may complete successfully
```

The terminal form is explicit and is only valid after at least one successful invocation in this first contract. An initial terminal/no-op task is not part of this scope; `max_iterations=0` retains its existing `MAX_ITERATIONS` meaning.

### 2. Successful invocation semantics

Executor returns a normalized successful `PluginResult`. DSH increments `iteration`, records the successful output in the one-slot `last_invocation_result`, and asks Planner for the post-result decision.

- terminal Decision: DSH commits the latest output as final `TaskState.result` and enters `COMPLETED`;
- action Decision with remaining budget: DSH starts the next bounded invocation;
- action Decision with no remaining budget: DSH enters `MAX_ITERATIONS` without starting another invocation.

### 3. Terminal task semantics

Only DSHController applies the task-level terminal transition. A successful PluginResult is necessary for a successful continuation step, but is not by itself sufficient for multi-step task completion.

`TaskState.result` is populated as the final task result only when DSH commits `COMPLETED`.

### 4. Iteration increment semantics

Increment exactly once, after `Executor.execute()` settles and before DSH evaluates the post-result continuation decision. One iteration equals one settled capability invocation attempt.

Planner evaluations do not increment `iteration`. Workspace preflight failure before Executor invocation does not increment it.

### 5. `max_iterations` semantics

`max_iterations` bounds settled capability invocations, including unsuccessful attempts even though current failure and timeout are terminal and therefore normally stop earlier. It does not bound Planner evaluations.

### 6. `MAX_ITERATIONS` transition rule

After a successful invocation increments `iteration` to `max_iterations`, DSH still performs exactly one post-result Planner evaluation:

```text
terminal Decision -> COMPLETED
action Decision   -> MAX_ITERATIONS, no new invocation
```

If `max_iterations=0`, no invocation or post-result evaluation occurs and the existing `MAX_ITERATIONS` behavior remains.

### 7. Failure/timeout behavior

Failure and timeout remain terminal for the current continuation model:

```text
invocation FAILED    -> TaskState.FAILED, no next Planner action
invocation TIMED_OUT -> TaskState.TIMED_OUT, no next Planner action
```

No retry semantics are introduced. Plugin-internal bounded retry, if ever required by a concrete capability, is not a DSH business iteration.

### 8. Backward-compatibility rule

The existing one-action behavior remains valid:

- `max_iterations=1` plus the existing `SimplePlanner` action and successful Echo invocation remains `COMPLETED` with `iteration=1` and the same final result;
- normal failure, timeout, and unknown-plugin mappings remain unchanged;
- `max_iterations=0` remains `MAX_ITERATIONS` with no invocation;
- a Planner that returns another action after a multi-iteration budget is exhausted receives `MAX_ITERATIONS`, not an implicit successful task completion.

The compatibility rule must be explicit in the Planner implementation and tests; the Controller uses the same continuation rule for all Planners and does not special-case `SimplePlanner` or `max_iterations=1`.

## State transition table

| Current state / event | DSH action | Next task state | Iteration effect |
|---|---|---|---:|
| `PENDING`, `max_iterations=0` | Do not invoke | `MAX_ITERATIONS` | 0 |
| `RUNNING`, action Decision, budget available | Invoke through Executor | waiting for result | unchanged before settle |
| invocation success | Store latest output; evaluate Planner | `COMPLETED`, next invocation, or `MAX_ITERATIONS` | +1 |
| invocation failure | Apply failure | `FAILED` | +1 |
| invocation timeout | Apply timeout | `TIMED_OUT` | +1 |
| successful result + terminal Decision | Commit latest output | `COMPLETED` | no additional increment |
| successful result + action Decision, budget remains | Invoke next action | `RUNNING` | no additional increment |
| successful result + action Decision, budget exhausted | Do not invoke | `MAX_ITERATIONS` | no additional increment |
| workspace preflight failure | Do not invoke | `FAILED` | unchanged |

## Deterministic acceptance scenarios

These scenarios are design requirements for the later implementation phase; tests are not added in 3-A.

### Scenario 1 — Existing single-action completion

```text
max_iterations = 1
SimplePlanner -> Echo action
Echo -> success("hello")
```

Expected:

```text
Echo executes once
iteration = 1
Task = COMPLETED
TaskState.result = "hello"
```

This is preserved because `SimplePlanner` returns a terminal Decision during its post-success evaluation; the Controller uses no single-action compatibility branch.

### Scenario 2 — Two-step continuation

```text
Planner -> action A
A -> success("a")
Planner observes latest result -> action B
B -> success("b")
Planner observes latest result -> terminal Decision
```

With `max_iterations=2`, A and B each execute exactly once, in order; the terminal Planner evaluation is allowed after B; the task becomes `COMPLETED` and final result is `"b"`.

### Scenario 3 — Failure on first action

```text
A -> FAILED
```

Expected:

```text
no B
Task = FAILED
iteration = 1
```

No continuation Planner decision is requested after the failure.

### Scenario 4 — Timeout on first action

```text
A -> TIMED_OUT
```

Expected:

```text
no B
Task = TIMED_OUT
iteration = 1
```

Executor cleanup and timeout ownership remain exactly as proven in Milestone 2.

### Scenario 5 — Budget exhaustion

```text
max_iterations = 2
Planner -> A
A -> success
Planner -> B
B -> success
Planner -> action C
```

Expected:

```text
A executes once
B executes once
C does not execute
iteration = 2
Task = MAX_ITERATIONS
```

The latest invocation output may remain available in the one-slot internal/latest-result field, but it must not be committed as `TaskState.result` because the task did not reach successful terminal completion.

### Scenario 6 — Terminal Planner decision without a new invocation

The recommended contract allows this only after a successful invocation:

```text
A -> success
Planner -> terminal Decision
```

The terminal Decision consumes no iteration and commits A's output as the final task result. An initial terminal Decision with zero invocations is not allowed in this contract; zero budget retains `MAX_ITERATIONS`.

## Ownership check

The existing owners can express the contract:

```text
DSHController
    owns post-result Planner evaluation,
    continuation, budget, and terminal TaskState transition

Planner
    supplies action or terminal business decision

Executor
    governs one invocation's timeout, cancellation, cleanup settlement,
    and normalized StopReason

Plugin
    owns one bounded native/product invocation

PluginResult
    reports one invocation outcome only

TaskState
    stores task lifecycle, budget, final result,
    and at most one latest invocation result for Planner observation
```

No evidence requires a second owner. Do not introduce `AgentExecutor`, `LoopManager`, `WorkflowEngine`, `Workflow DSL`, `Event Bus`, `ExecutionHandle`, `ProcessManager`, `Provider Framework`, `ExternalAgent`, `ContinuationManager`, `TaskContext`, `PlannerContext`, or generic `ResultHistory`.

## Explicit non-goals

This contract does not introduce:

```text
multi-turn Codex sessions
persistent sessions
resume
streaming
rollback
diff
usage/cost accounting
task graph
DAG
parallel execution
branching workflow engine
automatic retry
dynamic provider routing
```

Milestone 3 continuation concerns DSH business actions. Each capability invocation remains bounded and replaceable.

## Implementation gate

Do not begin implementation until this contract is accepted as the intended semantics. If implementation evidence shows that the existing Controller + Planner + TaskState seam cannot express the post-result terminal decision without generic workflow machinery, a new design review is required before adding abstractions.

The next implementation work, if authorized, should be limited to the smallest changes required by this contract and its deterministic acceptance scenarios. It must not reopen Milestone 2 or retry blocked real Codex service verification.
