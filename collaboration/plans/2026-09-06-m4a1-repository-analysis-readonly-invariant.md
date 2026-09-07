# Milestone 4-A.1 — Repository Analysis Read-only Invariant

Date: 2026-09-06  
Status: design only; implementation not started

## Repository evidence

The approved workflow is:

```text
TaskKind.REPOSITORY_ANALYSIS
  -> SimplePlanner
  -> Decision(plugin="codex", params={"prompt": task.goal})
  -> existing Controller / Executor / CodexPlugin path
```

Current authority ownership is already settled:

```text
TaskState.allow_workspace_write
  -> Controller ExecutionContext.allow_workspace_write
  -> CodexPlugin native authority mapping
```

The repository currently has no `TaskState.__post_init__`, task-input validator, or generic invalid-state owner. The actual caller path is direct Python construction of `TaskState`, followed by `DSHController.run(task)`. There is no implemented HTTP/API layer that could serve as a stronger input boundary.

Existing rejection patterns are local and deterministic:

- `CodexPlugin` rejects invalid constructor combinations with `ValueError`.
- `WorkspaceManager` rejects invalid workspace input before invocation with `WorkspaceResolutionError`; Controller maps workspace preflight failure to the existing failed-task boundary.
- `PluginRegistry` rejects duplicate registration and missing lookup with exceptions.
- An initial terminal Planner Decision is handled as a task failure, but that is an execution decision boundary, not task-input validation.

Nothing in the repository supports silently normalizing caller authority. `CodexPlugin` must continue to consume DSH authority and must not infer or repair it from plugin parameters.

## Options considered

| Option | Behavior | Assessment |
|---|---|---|
| A. `TaskState` construction/input validation | Reject the cross-field combination before a Controller run starts | Recommended: `TaskState` already owns caller/task input, and the actual caller constructs it directly |
| B. Existing Planner boundary | Let Planner detect the combination and reject/return a terminal Decision | Not recommended: Planner rejection would be confused with ordinary task failure, would not run when budget is zero, and would make task-input validity depend on a particular Planner |
| C. Caller precondition only | Document that callers must not pass `allow_workspace_write=True` | Rejected: the current direct Python constructor accepts the invalid combination, and comments/tests do not form an executable invariant |

## Recommended existing owner

Use `TaskState` as the deterministic input-validation boundary. The minimum future implementation is:

```python
class TaskState:
    ...

    def __post_init__(self) -> None:
        if not isinstance(self.task_kind, TaskKind):
            raise TypeError("task_kind must be a TaskKind")
        if (
            self.task_kind is TaskKind.REPOSITORY_ANALYSIS
            and self.allow_workspace_write
        ):
            raise ValueError("Repository Analysis tasks must be read-only")
```

`TaskKind` remains a concrete business-task enum owned by `dsh_runtime/state.py`:

```python
class TaskKind(str, Enum):
    DEFAULT = "default"
    REPOSITORY_ANALYSIS = "repository_analysis"
```

The `task_kind` field should remain typed as `TaskKind`, default to `TaskKind.DEFAULT`, and be placed after existing dataclass fields so existing positional constructor ordering is not shifted.

This rejects the invalid combination without changing the submitted authority. It does not force `allow_workspace_write=False`, mutate the task, or delegate authority to Planner/Plugin.

## Invalid-input behavior

The answer to the required questions is:

1. Yes. `REPOSITORY_ANALYSIS + allow_workspace_write=True` is an illegal task input for this Milestone 4 workflow.
2. The minimum deterministic rejection boundary is `TaskState` construction/input validation.
3. Yes. The existing `TaskState` owner can carry both the business task kind and its input invariant; no second owner is needed.
4. No. Controller does not need a new branch.
5. No. This rejection occurs before a task enters the Controller lifecycle. It does not add `TaskStatus`, does not map to `FAILED`, and does not alter invocation failure/timeout semantics. The caller receives the construction exception and may decide how to report an invalid request outside Runtime execution.
6. Add focused tests for the invalid combination, the raw-string type boundary, and the valid read-only default.
7. Yes. The future production surface remains `state.py` plus the previously approved `planner.py` change.
8. Yes. `controller.py`, `executor.py`, `CodexPlugin`, `WorkspaceManager`, `Registry`, and `PluginResult` remain unchanged.

The distinction is intentional:

```text
invalid TaskState input
    -> construction exception, no task lifecycle

valid task + failed invocation
    -> existing FAILED task semantics

valid task + timed-out invocation
    -> existing TIMED_OUT task semantics
```

## TaskKind comparison and caller contract

The caller contract should require a `TaskKind` enum member, not a raw string. Python type annotations alone do not enforce this at runtime, so the proposed `TaskState` construction validation must reject:

```python
TaskState(goal="...", task_kind="repository_analysis")
```

with `TypeError`.

After that constructor contract is satisfied, Planner code may safely use:

```python
task.task_kind is TaskKind.REPOSITORY_ANALYSIS
```

This is preferable to `==`: because `TaskKind` subclasses `str`, a raw string can compare equal to the enum value and would make an unvalidated caller input route ambiguously. No generic HTTP parsing or string-normalization layer is needed.

`TaskState` remains mutable for existing lifecycle fields. Post-construction mutation of `task_kind` to a raw string is outside the caller construction contract and is not a supported input path; adding a separate mutation/immutability mechanism would exceed this requirement.

## Test requirement

Future implementation should add deterministic tests, without real Codex service calls:

### `tests/test_runtime.py`

- `TaskState(task_kind=TaskKind.REPOSITORY_ANALYSIS, allow_workspace_write=True)` raises `ValueError`.
- `TaskState(task_kind="repository_analysis")` raises `TypeError`.
- `TaskState(task_kind=TaskKind.REPOSITORY_ANALYSIS)` is valid and retains `allow_workspace_write is False`.
- Production `SimplePlanner` routes the enum member to Codex and retains the existing terminal post-result behavior.
- Default task construction still follows Echo compatibility.

### `tests/test_codex_plugin.py`

The normal production Planner integration test should construct a valid Repository Analysis task without custom plugin parameters that attempt to grant authority. The existing local stub capture must continue to prove:

```text
approvalPolicy = "never"
no workspace-write sandbox mapping
```

The test should also preserve the existing prompt, logical workspace, one-invocation, post-result terminal Decision, and final `TaskState.result` assertions from the Milestone 4-A design.

No test should accept `allow_workspace_write=True` for the Repository Analysis task kind merely because the Codex Plugin would map it correctly; that combination is invalid before Plugin invocation.

## Production change impact

### Likely changed files

`dsh_runtime/state.py`

- Add the concrete `TaskKind` enum if not already present.
- Add the typed/defaulted `task_kind` field.
- Add local construction validation for enum type and the read-only cross-field invariant.
- Do not normalize authority or alter lifecycle/result methods.

`dsh_runtime/planner.py`

- Use the validated enum member with `is` for the approved initial Repository Analysis route.
- Keep post-result `Decision(plugin=None)` behavior unchanged.
- Keep default Echo behavior unchanged.
- Do not inspect or rewrite `allow_workspace_write`.

### Files that remain unchanged

```text
dsh_runtime/controller.py
dsh_runtime/runtime/executor.py
dsh_runtime/runtime/plugin.py
dsh_runtime/runtime/registry.py
dsh_runtime/workspace/manager.py
dsh_runtime/plugins/codex.py
dsh_runtime/plugins/echo.py
```

No new `TaskStatus`, Controller branch, permission policy, validator owner, context object, router, or plugin parameter is introduced.

## Final verdict

```text
READY_FOR_IMPLEMENTATION
```

The existing `TaskState` owner can reject the invalid combination deterministically before Runtime execution. Planner remains responsible only for business-intent-to-action mapping, and all settled Controller, Executor, workspace, authority, and Codex lifecycle ownership remains intact.

## Revised minimum implementation sequence

Do not execute this sequence in Milestone 4-A.1:

1. In `state.py`, add/retain the concrete `TaskKind` enum and typed defaulted field; add constructor validation for enum membership and `REPOSITORY_ANALYSIS + allow_workspace_write=True`.
2. In `planner.py`, use `is TaskKind.REPOSITORY_ANALYSIS` for the initial mapping to Codex and retain the existing post-result terminal branch.
3. Add the focused state/type/invariant tests and the normal production Planner local-stub test.
4. Run focused tests, then `.venv\Scripts\python.exe -m pytest -q`.
5. Stop after deterministic local evidence; do not retry real Codex service verification.

This phase changed no production files and no test files, and did not start Milestone 4 implementation.
