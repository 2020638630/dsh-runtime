# Milestone 4-B — Repository Analysis Workflow Implementation

Date: 2026-09-06  
Status: implementation complete and verified

## Scope and implementation summary

Implemented the approved workflow:

```text
TaskState(TaskKind.REPOSITORY_ANALYSIS)
  -> production SimplePlanner
  -> Codex action Decision with prompt=task.goal
  -> existing Controller / Executor / CodexPlugin path
  -> last_invocation_result
  -> post-result terminal Decision
  -> TaskState.result
  -> COMPLETED
```

The caller expresses the business task kind, not Codex. No Controller completion shortcut was added.

## Exact production files changed

### `dsh_runtime/state.py`

- Added `TaskKind.DEFAULT` and `TaskKind.REPOSITORY_ANALYSIS`.
- Added defaulted `TaskState.task_kind` after existing dataclass fields, preserving positional constructor order.
- Added construction validation:
  - raw/non-enum task kind raises `TypeError`;
  - Repository Analysis with `allow_workspace_write=True` raises `ValueError`;
  - authority is rejected, never silently rewritten;
  - invalid construction occurs before task lifecycle.

### `dsh_runtime/planner.py`

- Preserved the existing `iteration > 0` terminal Decision rule.
- Added initial Repository Analysis routing to `Decision(plugin="codex", params={"prompt": task.goal})`.
- Preserved default Echo routing.

No other production file was changed for Milestone 4-B.

## Exact test files changed

### `tests/test_runtime.py`

Added tests for raw task-kind rejection, write-enabled Repository Analysis rejection, valid read-only construction, production Planner routing, and post-result terminal behavior. Existing Echo, failure, timeout, budget, and continuation tests remain green.

### `tests/test_codex_plugin.py`

Added a deterministic local-stub test using a real `SimplePlanner` instance, not a custom routing Planner. It verifies prompt propagation, logical workspace/cwd, ephemeral invocation, read-only native mapping, two Planner calls, one settled invocation, final result ownership, and `COMPLETED`.

## TaskKind and validation behavior

The valid caller contract uses an enum member:

```python
TaskState(
    goal="...",
    task_kind=TaskKind.REPOSITORY_ANALYSIS,
)
```

Invalid inputs behave as follows:

```text
TaskState(task_kind="repository_analysis") -> TypeError

TaskState(
    task_kind=TaskKind.REPOSITORY_ANALYSIS,
    allow_workspace_write=True,
) -> ValueError
```

Neither case enters Controller lifecycle, becomes a `FAILED` task, or adds a new status.

## Normal Controller → Codex evidence

The production `SimplePlanner` test confirms:

```text
logical workspace -> expected cwd
ephemeral -> True
approvalPolicy -> never
sandbox -> absent
Planner calls -> 2
settled invocations -> 1
task iteration -> 1
```

The local stub answer contains the exact task goal and resolved cwd. The output is first stored in `last_invocation_result`, then committed to `TaskState.result` after the terminal Planner Decision.

The authority chain remains unchanged:

```text
TaskState.allow_workspace_write
  -> Controller ExecutionContext.allow_workspace_write
  -> CodexPlugin native mapping
```

## Compatibility and failure evidence

Default `TaskState(goal="hello")` still routes to Echo and completes. Existing failure and timeout behavior remains terminal without post-failure or post-timeout Planner evaluation. `max_iterations` semantics remain unchanged.

## Verification

Focused tests:

```text
.venv\Scripts\python.exe -m pytest -q tests/test_runtime.py tests/test_codex_plugin.py
27 passed in 0.80s
```

Full regression:

```text
.venv\Scripts\python.exe -m pytest -q
46 passed in 1.10s
```

The original `41 passed` baseline remains green with the new Milestone 4-B scenarios. No real Codex service was called; Milestone 2 real-service verification remains `DEFERRED / ENVIRONMENT_BLOCKED`.

## Git diff summary and unexpected evidence

Milestone 4-B touched only:

```text
dsh_runtime/state.py
dsh_runtime/planner.py
tests/test_runtime.py
tests/test_codex_plugin.py
```

The working tree already contained earlier uncommitted Milestone 2/3 changes and files. They were preserved; no reset, checkout, clean, or unrelated cleanup was performed.

These production owners remained unchanged:

```text
dsh_runtime/controller.py
dsh_runtime/runtime/executor.py
dsh_runtime/runtime/plugin.py
dsh_runtime/runtime/registry.py
dsh_runtime/workspace/manager.py
dsh_runtime/plugins/codex.py
dsh_runtime/plugins/echo.py
```

No unexpected repository evidence appeared. The existing TaskState → Planner → Controller → Executor → CodexPlugin seam was sufficient.

## Verdict

```text
IMPLEMENTATION_COMPLETE
VERIFICATION_PASS
```

Stop here. Do not extend Milestone 4, start a two-action workflow, add CodeBuddy routing, or retry real Codex service verification.
