# Milestone 4-A — Minimal Repository Analysis Implementation Design

Date: 2026-09-06  
Status: design only; implementation not started  
Production files changed in this phase: none  
Test files changed in this phase: none

## 1. Repository evidence

Milestone 2 and Milestone 3 remain closed:

```text
Milestone 2 — External Capability Integration
IMPLEMENTATION COMPLETE
REAL-SERVICE VERIFICATION DEFERRED

Milestone 3 — Bounded Planner-Driven Task Continuation
IMPLEMENTATION COMPLETE
VERIFICATION PASS
```

The current baseline was re-run before this design was written:

```text
.venv\Scripts\python.exe -m pytest -q
41 passed in 1.00s
```

The duration is not contractual; the baseline is `41 passed`.

Relevant repository facts:

- `dsh_runtime/state.py` defines the caller-visible `TaskState` data boundary. It currently contains `goal`, logical `workspace_id`, invocation budget, timeout, lifecycle/result fields, and DSH-owned `allow_workspace_write`.
- `dsh_runtime/controller.py` receives a `TaskState`, uses the injected Planner or default `SimplePlanner`, resolves the workspace, invokes `Executor`, and owns terminal task transitions.
- `dsh_runtime/planner.py` currently maps the initial task to Echo and maps every post-invocation evaluation to a terminal Decision.
- `dsh_runtime/plugins/codex.py` already accepts a bounded `prompt` parameter, uses `ExecutionContext.goal` as fallback, and derives native authority from `ExecutionContext.allow_workspace_write` rather than from plugin parameters.
- `tests/test_codex_plugin.py` already proves deterministic local Codex success, logical workspace propagation, read-only authority mapping, and Controller-to-Codex execution when a custom test Planner selects Codex.
- `tests/test_runtime.py` already proves the Milestone 3 post-result Planner contract, including latest-result observation and terminal result ownership.
- The repository has no implemented `app/`, HTTP route, CLI task adapter, or other caller service. `资料库/CODEX_CONTEXT.md` describes `POST /agent/tasks` as an intended Phase 1 acceptance shape, but no such production entrypoint exists in the current file tree.

The real Codex service debt remains independent. Milestone 4-A uses only the deterministic local app-server stub and does not retry real Codex service verification.

## 2. Current caller/task construction path

The actual executable caller path today is direct Python construction:

```text
caller/test code
  -> TaskState(goal=..., workspace_id=..., ...)
  -> DSHController(registry, planner?, workspace_manager?).run(task)
  -> Planner.next_action(task)
```

Repository examples construct `TaskState` directly in `tests/test_runtime.py`, `tests/test_codex_plugin.py`, and semantic-hardening tests. There is no higher-level request object that can carry a separate business intent.

The conceptual HTTP example in `资料库/CODEX_CONTEXT.md:995-1040` accepts only a `goal` and describes the original Echo workflow. It is design context, not an implemented caller boundary. Therefore the smallest current caller contract must be expressed on `TaskState`, without introducing a second request or context owner.

The caller must express:

```text
what business task is requested:
Repository Analysis
```

It must not express:

```text
plugin = codex
provider = codex
capability = codex
```

The mapping from business task to concrete Plugin remains Planner policy.

## 3. Recommended business-intent representation

### Recommendation

Add one concrete business task kind to the existing `TaskState` owner:

```python
class TaskKind(str, Enum):
    DEFAULT = "default"
    REPOSITORY_ANALYSIS = "repository_analysis"
```

Then add an optional/defaulted field to `TaskState`, preferably at the end of the dataclass fields to avoid shifting existing positional constructor arguments:

```python
task_kind: TaskKind = TaskKind.DEFAULT
```

The caller shape becomes conceptually:

```python
TaskState(
    goal="Inspect the repository structure and summarize the important modules.",
    task_kind=TaskKind.REPOSITORY_ANALYSIS,
    workspace_id="logical.test",
)
```

The caller names the requested business operation. The Planner later decides that the existing Codex Plugin is the appropriate bounded capability for that operation.

### Why this is business intent

`REPOSITORY_ANALYSIS` describes the work product requested by the caller. It does not identify an implementation, provider, process, or protocol. The same business task could theoretically be implemented by another capability in a future milestone without changing the caller contract. That separation is the required:

```text
business intent -> Planner decision -> concrete Plugin
```

`TaskState` is the correct existing owner because it is already the task input and lifecycle object passed to every Planner evaluation. The Planner is the correct existing owner for translating the task kind into an action Decision. No second owner is required.

### Alternatives considered

#### Reuse free-form `goal` with a reserved prefix

Rejected. A prefix such as `repository-analysis:` would mix user task text with routing syntax, make the Planner parse an untyped string, and create a brittle natural-language-like policy. It also gives no clear boundary between the requested work and its description.

#### Add `plugin`, `provider`, or `capability` to `TaskState`

Rejected. Those fields would make the caller select an implementation rather than express business intent. They would also bypass the Planner boundary and turn the task input into caller-driven routing.

#### Configure `SimplePlanner` globally for Codex

Rejected. The requirement is task-specific. A Planner-wide mode cannot express Echo and Repository Analysis tasks in the same runtime without another caller-to-Planner channel, and it would make Codex the policy of the Planner instance rather than a decision derived from the task.

#### Create `TaskContext`, `RequestContext`, `CapabilityRequest`, or a task envelope

Rejected. The current `TaskState -> Planner` seam already carries the required data. No executable evidence shows that a second input owner is needed.

#### Use a generic string `intent: str`

Not preferred. It would be smaller syntactically but would create an unbounded catch-all field. A concrete `TaskKind` with one evidence-backed value keeps the first contract deterministic and narrow.

## 4. Planner initial/post-result behavior

The existing Milestone 3 contract is sufficient and must be reused without Controller special cases.

Recommended deterministic Planner behavior:

```python
def next_action(self, task: TaskState) -> Decision:
    if task.iteration > 0:
        return Decision(plugin=None)
    if task.task_kind is TaskKind.REPOSITORY_ANALYSIS:
        return Decision(plugin="codex", params={"prompt": task.goal})
    return Decision(plugin="echo", params={"text": task.goal})
```

Semantically:

```text
Repository Analysis initial evaluation
    -> Decision(plugin="codex", params={"prompt": task.goal})

successful Codex invocation
    -> iteration += 1
    -> last_invocation_result = bounded final answer
    -> post-result Planner evaluation
    -> Decision(plugin=None)
    -> Controller commits TaskState.result
    -> COMPLETED
```

The post-result branch is selected by `iteration > 0`, exactly as the existing Echo compatibility path is. It does not inspect plugin name, success text, or Codex-specific state. A failed or timed-out Codex invocation returns from the Controller before post-result Planner evaluation, preserving existing failure boundaries.

With `max_iterations=0`, the Controller still skips Planner and invocation. With the normal default budget, the Repository Analysis workflow performs exactly one invocation and then receives the explicit terminal Decision.

No code of the form below is permitted:

```python
if codex_success:
    task.status = TaskStatus.COMPLETED
```

## 5. Codex Decision parameter mapping

The first workflow is fixed to read-only Repository Analysis. The Planner should construct exactly the bounded input needed by the existing Codex Plugin:

```python
Decision(
    plugin="codex",
    params={"prompt": task.goal},
)
```

No `model` parameter is needed for this workflow. The existing Plugin accepts it optionally, but model selection is not part of the approved requirement.

Current Codex evidence shows:

- `CodexPlugin.execute()` reads `params["prompt"]` and validates non-empty text.
- `ctx.goal` remains the Plugin fallback, but the Planner should pass `prompt` explicitly so the business goal to prompt propagation is directly testable.
- `DSHController` resolves `task.workspace_id` with `WorkspaceManager` and passes the resulting cwd through `ExecutionContext`.
- `TaskState.allow_workspace_write` defaults to `False` and is passed by the Controller to `ExecutionContext`.
- `CodexPlugin` maps the false authority to its existing read-only native mode.
- Codex creates one ephemeral invocation and owns its existing protocol, timeout cleanup, and process settlement mechanics.

The Repository Analysis acceptance input therefore uses the existing default:

```text
allow_workspace_write = False
```

No plugin parameter may override that authority. A caller explicitly supplying `allow_workspace_write=True` is outside this first read-only workflow; Milestone 4-A does not create a new permission policy or silently rewrite DSH authority.

## 6. TaskState.result formation

The current code already supports the required result path without modification:

```text
Codex PluginResult(success=True, output=bounded final answer)
    -> Executor normalizes stop reason to COMPLETED
    -> Controller increments iteration
    -> Controller stores result.output in last_invocation_result
    -> Planner receives the updated TaskState
    -> Planner returns terminal Decision
    -> Controller calls task.apply_success(last_invocation_result)
    -> TaskState.result = bounded final answer
    -> TaskStatus.COMPLETED
```

The relevant Controller behavior is already present in `dsh_runtime/controller.py:73-122`, and the TaskState distinction is already covered by the Milestone 3 closure:

```text
last_invocation_result = latest successful invocation output for Planner
result = final successful task result only
```

There is no semantic gap here. `TaskState.result` must not be populated directly from the initial Codex success before the post-result Planner evaluation.

## 7. Existing owner analysis

| Existing owner | Current responsibility | Milestone 4-A treatment | Why this owner remains correct |
|---|---|---|---|
| `TaskState` | Caller-visible task input plus lifecycle/result state | Add one concrete `TaskKind` value/field with a default preserving Echo | It already crosses the caller → Planner boundary |
| `SimplePlanner` / Planner | Supplies action or terminal Decision | Map `REPOSITORY_ANALYSIS` to Codex on initial evaluation; return terminal after success | Business intent-to-action translation belongs here |
| `DSHController` | Loop, budget, invocation, terminal TaskState transition | No change | Existing Milestone 3 ownership already expresses the workflow |
| `Executor` | One invocation timeout/cancellation/settlement and StopReason normalization | No change | Codex remains one existing bounded invocation |
| `CodexPlugin` | Codex app-server lifecycle and bounded final answer | No change | No new protocol or lifecycle requirement exists |
| `WorkspaceManager` | Logical workspace to cwd resolution | No change | Existing path already propagates cwd before Plugin start |
| `PluginRegistry` | Static name-to-Plugin lookup | No change | Selection policy does not belong in the registry |
| `PluginResult` | One invocation outcome | No change | Existing output field already carries the bounded final answer |

## 8. Exact production files likely to change

### `dsh_runtime/state.py` — likely change

Current responsibility: defines `TaskStatus`, `TaskState`, task input fields, invocation accounting, and final/latest result slots.

Minimal proposed change:

- define the concrete `TaskKind` enum with `DEFAULT` and `REPOSITORY_ANALYSIS`;
- add a defaulted `task_kind` field to `TaskState`, placed after existing fields to preserve positional compatibility;
- do not alter `TaskStatus`, `iteration`, `result`, `last_invocation_result`, `allow_workspace_write`, or success/failure methods.

Why this owner is correct: `TaskState` is the only current caller-to-Planner data object and already owns task-level business input.

### `dsh_runtime/planner.py` — likely change

Current responsibility: defines `Decision` and the deterministic `SimplePlanner` policy.

Minimal proposed change:

- retain the existing post-invocation terminal rule;
- add one initial-evaluation branch for `TaskKind.REPOSITORY_ANALYSIS` that emits `Decision(plugin="codex", params={"prompt": task.goal})`;
- retain the existing Echo branch for `TaskKind.DEFAULT`.

Why this owner is correct: Planner owns business-level action selection and is the intended translation seam between task intent and concrete capability.

The exact minimum production change is therefore two files:

```text
dsh_runtime/state.py
dsh_runtime/planner.py
```

`dsh_runtime/__init__.py` need not change for the runtime semantics; callers can import the concrete task kind from `dsh_runtime.state`, matching the current test/import style. A package-root export would be an optional API ergonomics change and is not part of the minimum design.

## 9. Exact production files that should remain unchanged

The following files and responsibilities should remain unchanged for this goal:

```text
dsh_runtime/controller.py
dsh_runtime/runtime/executor.py
dsh_runtime/runtime/plugin.py
dsh_runtime/runtime/registry.py
dsh_runtime/workspace/manager.py
dsh_runtime/plugins/codex.py
dsh_runtime/plugins/echo.py
```

In particular, do not change:

- Controller completion logic or add a Codex success shortcut;
- Executor timeout, cancellation, settlement, or StopReason normalization;
- `ExecutionContext` or `PluginResult` shape;
- Codex protocol, process, ephemeral-thread, cleanup, or result parsing lifecycle;
- logical workspace identity or cwd resolution;
- authority mapping or permission policy;
- Registry lookup semantics;
- Echo behavior.

Do not introduce any new Runtime owner or framework.

## 10. Exact test files and acceptance scenarios

### `tests/test_runtime.py` — Planner/task-kind and compatibility coverage

Add deterministic unit scenarios for the production `SimplePlanner`:

1. `TaskKind.REPOSITORY_ANALYSIS` at `iteration == 0` returns `Decision(plugin="codex", params={"prompt": goal})`.
2. The same task at `iteration > 0` returns a terminal Decision regardless of `last_invocation_result` content.
3. A default `TaskState(goal="hello")` retains the existing Echo Decision and existing `test_echo_completes_task` behavior.

These tests must instantiate the production `SimplePlanner`, not a custom routing Planner.

### `tests/test_codex_plugin.py` — normal Controller-path integration coverage

Add a deterministic local-stub scenario that:

1. registers the existing `CodexPlugin`;
2. constructs `TaskState(task_kind=TaskKind.REPOSITORY_ANALYSIS, goal=..., workspace_id=...)`;
3. uses `DSHController` with the default production `SimplePlanner`—no custom test Planner;
4. maps a logical workspace through the existing `WorkspaceManager`;
5. captures the stub `thread/start` parameters and asserts the resolved cwd and `ephemeral=True`;
6. asserts `approvalPolicy="never"` and no write authority/sandbox escalation;
7. asserts the bounded stub answer contains the exact `TaskState.goal` prompt;
8. asserts exactly one settled invocation, `TaskState.last_invocation_result`, final `TaskState.result`, and `TaskStatus.COMPLETED`;
9. asserts the Planner post-result terminal path is used by keeping the normal one-action contract rather than adding Controller special handling.

The existing direct Codex, workspace, permission, timeout, cleanup, and cancellation tests remain unchanged and continue to provide lower-level regression evidence.

### Existing failure-boundary coverage to preserve

The implementation must leave these invariants green:

```text
FAILED Codex invocation
    -> FAILED task
    -> no post-failure Planner evaluation

TIMED_OUT Codex invocation
    -> TIMED_OUT task
    -> no post-timeout Planner evaluation
```

If focused implementation tests add explicit routing failure/timeout scenarios, they should use the local stub and production Planner path where practical; they must not use real Codex service calls.

### Full regression

The implementation phase should run:

```text
.venv\Scripts\python.exe -m pytest -q
```

Expected shape:

```text
existing 41 passed
+ new focused tests
= all green
```

The exact duration is irrelevant.

## 11. Compatibility invariants

The following must remain true:

```text
Caller names Repository Analysis, never Codex.
Planner maps Repository Analysis to the existing Codex Plugin.
Default task kind retains Echo compatibility.
Successful invocation != successful task.
Codex success is observed through last_invocation_result first.
Only a post-result terminal Decision commits TaskState.result.
Failure and timeout do not trigger continuation Planner evaluation.
max_iterations still bounds settled invocations only.
Repository Analysis uses logical workspace identity and existing cwd resolution.
Repository Analysis is read-only under allow_workspace_write=False.
Codex remains ephemeral and bounded.
No real-service completion is claimed.
```

## 12. Reconsideration gate

Stop and report instead of implementing around the problem if executable evidence shows any of the following:

1. The current `TaskState -> Planner` seam cannot carry one concrete Repository Analysis task kind.
2. The workflow requires changing Controller or Executor ownership.
3. The existing post-result Planner contract cannot commit the bounded Codex output as the final `TaskState.result`.
4. A real implemented caller already has an equivalent business-intent selection path, so the supposed gap does not exist.
5. The actual workflow requires a second meaningful action, durable history, cancellation state, workspace side-effect observation, or another semantic not represented by the current contract.
6. Read-only authority cannot be preserved by the existing `allow_workspace_write=False` path without introducing a new generic permission policy.

These conditions would block this minimal design or require a new evidence-based goal. They do not authorize adding a generic abstraction as a workaround.

## 13. Explicit non-goals

This phase and the next implementation sequence do not authorize:

```text
Provider Framework
Router Framework
dynamic provider routing
automatic intent classification
natural-language classifier
Workflow Engine
Workflow DSL
TaskContext
PlannerContext
RequestContext
RoutingContext
CapabilityRequest
ProviderRequest
TaskEnvelope
Event Bus
ProcessManager
ExecutionHandle
AgentExecutor
ExternalAgent Framework
CodexAdapter
generic history
generic PermissionPolicy
generic process result DTO
retry / replanning
parallel actions
task DAG
task-level cancellation
workspace-write workflow
persistent sessions
Codex multi-turn
streaming
resume
rollback
usage / cost accounting
DSH -> CodeBuddy -> Codex routing
real Codex service retries
```

## 14. Implementation sequence recommendation

If implementation is explicitly authorized after this design review, the minimum sequence is:

1. Modify only `dsh_runtime/state.py` to add the concrete `TaskKind` and defaulted `task_kind` field without changing existing lifecycle/result semantics.
2. Modify only `dsh_runtime/planner.py` to map the initial `REPOSITORY_ANALYSIS` task kind to `Decision(plugin="codex", params={"prompt": task.goal})`, while retaining the post-result terminal branch and default Echo behavior.
3. Add the focused production-Planner tests in `tests/test_runtime.py` and normal Controller-path local-stub tests in `tests/test_codex_plugin.py`.
4. Run the focused tests, then the full regression. Confirm no Controller, Executor, Plugin, workspace, registry, or Codex lifecycle change was needed.
5. Stop after the deterministic local evidence. Do not retry real Codex service verification.

No step above is executed in Milestone 4-A.

## Verdict

```text
READY_FOR_IMPLEMENTATION
```

The existing `TaskState -> Planner -> Controller -> Executor -> CodexPlugin` seam can express the approved concrete workflow. The minimum design changes only the existing task-input and Planner policy owners, preserves Milestone 3 result semantics, and requires no new abstraction or Runtime ownership.
