# DSH Runtime Project State

Current Version:
v0.1.0-m4

Current Milestone:
Milestone 4 — Read-only Repository Analysis Workflow

Status:
CLOSED / VERIFICATION PASS

Completed milestones:

- Milestone 1 — DSH Runtime Skeleton: CLOSED
- Milestone 2 — External Capability Integration: IMPLEMENTATION COMPLETE; real-service verification DEFERRED / ENVIRONMENT_BLOCKED
- Milestone 3 — Bounded Planner-Driven Task Continuation: CLOSED / VERIFICATION PASS
- Milestone 4 — Read-only Repository Analysis Workflow: CLOSED / VERIFICATION PASS

Formal regression baseline:

    .venv\Scripts\python.exe -m pytest -q
    46 passed

Milestone 4 closure:

- The first concrete DSH workflow is read-only Repository Analysis.
- The caller expresses TaskKind.REPOSITORY_ANALYSIS, not a plugin, provider, or concrete capability.
- TaskState owns caller/task input and rejects REPOSITORY_ANALYSIS plus allow_workspace_write=True during construction.
- SimplePlanner maps Repository Analysis to CodexPlugin; default tasks retain Echo compatibility.
- Existing Controller, Executor, Plugin, Registry, WorkspaceManager, and CodexPlugin ownership is sufficient.
- Successful invocation remains distinct from successful task completion: last_invocation_result is evaluated by the post-result Planner before the terminal Decision commits TaskState.result and COMPLETED.
- The executable local-stub workflow proves two Planner calls, one settled invocation, and TaskState.iteration == 1.

Milestone 4 production scope:

    dsh_runtime/state.py
    dsh_runtime/planner.py

The following existing owners remain unchanged for Milestone 4:

    dsh_runtime/controller.py
    dsh_runtime/runtime/executor.py
    dsh_runtime/runtime/plugin.py
    dsh_runtime/runtime/registry.py
    dsh_runtime/workspace/manager.py
    dsh_runtime/plugins/codex.py
    dsh_runtime/plugins/echo.py

Non-claims and deferred work:

- Milestone 4 does not claim real Codex service completion, real final-answer delivery, write-side-effect behavior, interrupt acknowledgement, descendant process-tree behavior, or completion/deadline race verification.
- Real Codex service verification remains Milestone 2 debt and is independently deferred / environment-blocked.
- CodeBuddy integration, two-action workflows, provider/router frameworks, workspace-write workflows, task cancellation, and other future features require separate concrete requirements and executable evidence.

Reopen gate:

Milestone 4 remains closed unless executable evidence falsifies a frozen Milestone 4 invariant, including the read-only input invariant, production Planner routing, the Milestone 3 post-result completion path, Echo compatibility, or an M4-specific regression.

Current principle:

- DSH owns the loop.
- Planners translate business intent into bounded actions.
- Plugins are bounded execution units.
- If an existing Runtime owner can carry the responsibility, do not create a second owner.
- Plugins grow from real requirements.

Next:

Wait for a new concrete, evidence-driven requirement. Do not automatically begin another Milestone 4 feature or Next Concrete Goal Selection.
