# Milestone 3-B — Bounded Task Continuation Implementation

Date: 2026-09-06  
Status: implemented and verified

## Implemented contract

The implementation follows Model A from Milestone 3-A:

```text
initial Planner action
  -> one bounded Executor invocation
  -> settled successful result
  -> post-result Planner decision
      -> terminal Decision: COMPLETED
      -> action Decision with budget: next invocation
      -> action Decision without budget: MAX_ITERATIONS
```

Failure and timeout remain terminal. They do not trigger a post-failure or post-timeout Planner evaluation.

## Files changed

Production files changed for this milestone:

- `dsh_runtime/planner.py`
- `dsh_runtime/state.py`
- `dsh_runtime/controller.py`

Test files changed:

- `tests/test_runtime.py`
- `tests/test_codex_plugin.py`

Documentation changed:

- `collaboration/designs/2026-09-06-m3-a-bounded-task-continuation-contract.md`

The working tree contained earlier Milestone 2 changes; those were preserved. No unrelated cleanup or revert was performed.

## Decision change

`Decision.plugin` is now `str | None`.

```text
plugin != None -> action Decision
plugin == None -> terminal Decision
```

`Decision.is_terminal` provides the small semantic helper. No Decision hierarchy, command framework, or control taxonomy was added.

## TaskState change

`TaskState.last_invocation_result` is a single latest-successful-output slot.

```text
TaskState.result
    final result of a successfully completed task

TaskState.last_invocation_result
    latest successful invocation output visible to Planner
```

It is not history, an event log, an artifact collection, or a generic result envelope. `iteration` remains the number of settled invocation attempts and is incremented exactly once after `Executor.execute()` settles.

The implementation does not use `None` as the no-invocation sentinel; Planner call position and `iteration` distinguish the initial evaluation from post-success evaluation. A successful capability output of `None` is supported and tested.

## Controller continuation behavior

- `max_iterations=0` returns `MAX_ITERATIONS` before Planner evaluation or capability invocation.
- An initial terminal Decision is rejected as a bounded task failure; no-op task semantics were outside this milestone.
- A successful invocation stores `last_invocation_result` and invokes Planner again.
- A terminal post-result Decision commits the latest output to `TaskState.result` and enters `COMPLETED`.
- A post-result action executes only when invocation budget remains.
- An action returned at the budget boundary is not executed; the task enters `MAX_ITERATIONS` and does not commit a successful final result.
- Workspace preflight failure remains pre-invocation and does not advance `iteration`.

## SimplePlanner compatibility behavior

No Controller special case was added for `SimplePlanner` or `max_iterations == 1`.

`SimplePlanner` now supplies the compatibility behavior through the same Planner contract:

```text
initial evaluation       -> Echo action
post-success evaluation  -> terminal Decision
```

Therefore the existing Echo task still executes once, has `iteration == 1`, reaches `COMPLETED`, and exposes the Echo output as the final task result.

## Tests added or updated

Focused continuation tests cover:

- existing SimplePlanner single-action completion;
- two-step success with Planner observation of the latest result;
- failure stopping continuation and preventing a second Planner decision;
- timeout stopping continuation and preventing a second Planner decision;
- budget exhaustion without executing the next action or committing a final result;
- terminal evaluation exactly at the budget boundary;
- successful `None` output without using `None` as an invocation sentinel;
- zero-budget skipping the initial Planner evaluation;
- safe rejection of an initial terminal Decision;
- Controller-to-Codex test migration to explicit post-success terminal Decision.

## Verification

Focused tests:

```text
.venv\Scripts\python.exe -m pytest -q tests/test_runtime.py tests/test_codex_plugin.py
20 passed in 0.76s
```

Full regression:

```text
.venv\Scripts\python.exe -m pytest -q
41 passed in 0.97s
```

## Explicit no-change areas

No changes were made to:

```text
Executor timeout/cancellation governance
CodexPlugin protocol or cleanup lifecycle
process handling
StopReason normalization
workspace ownership
ExecutionHandle
ProcessManager
Provider Framework
ExternalAgent Framework
Workflow DSL
Event Bus
retry/replanning
resume
persistent session
Codex multi-turn
streaming
rollback
diff
usage/cost accounting
dynamic provider routing
```

Blocked real Codex service verification was not retried.

## Evidence-driven deviation from 3-A

The 3-B clarification changed the compatibility mechanism from a possible Controller-level legacy rule to a uniform Planner contract. `SimplePlanner` now returns the explicit terminal Decision after its successful Echo action, and the Controller applies one continuation algorithm to every Planner. The 3-A design document was updated only to record this clarification.

No new owner or lifecycle abstraction was required.
