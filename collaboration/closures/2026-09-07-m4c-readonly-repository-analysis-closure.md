# Milestone 4-C — Read-only Repository Analysis Workflow Closure

Date: 2026-09-07
Status: closed and verified

## Closure result

    Milestone 4 — Read-only Repository Analysis Workflow
    CLOSED
    VERIFICATION PASS
    Regression baseline: 46 passed

This closure synthesizes the existing Milestone 4-B implementation record,
read-only invariant design, deterministic local-stub integration evidence, and
the current project state. No new Runtime behavior is introduced by this
record.

## Frozen conclusions

1. The first concrete DSH workflow now exists: read-only Repository Analysis.
2. The caller expresses the business intent TaskKind.REPOSITORY_ANALYSIS.
3. The caller does not select a plugin, provider, or concrete capability.
4. The Planner owns business-intent-to-concrete-capability selection.
5. TaskState remains the caller/task-input owner.
6. Repository Analysis is a read-only workflow.
7. REPOSITORY_ANALYSIS plus allow_workspace_write=True is illegal caller input and is rejected during TaskState input validation.
8. Production SimplePlanner normally routes Repository Analysis to CodexPlugin.
9. Existing Controller / Executor / CodexPlugin ownership is sufficient.
10. Milestone 3's post-result completion contract remains the only successful-task path:

        successful invocation
          -> last_invocation_result
          -> Planner post-result evaluation
          -> terminal Decision
          -> Controller terminal transition

11. A successful invocation is not itself a successful task.
12. DEFAULT -> Echo behavioral compatibility remains intact.
13. The formal full-regression baseline is 46 passed.
14. Milestone 2 real Codex service verification remains independently deferred / environment-blocked.

## Executable workflow evidence

The deterministic local-stub workflow exercises the normal production path:

    TaskKind.REPOSITORY_ANALYSIS
      -> production SimplePlanner
      -> CodexPlugin
      -> logical workspace / read-only authority
      -> bounded result
      -> last_invocation_result
      -> post-result Planner
      -> terminal Decision
      -> TaskState.result
      -> COMPLETED

The recorded evidence is:

    Planner calls = 2
    settled invocations = 1
    TaskState.iteration = 1

The local stub also verifies exact task-goal prompt propagation, logical
workspace/cwd propagation, ephemeral invocation, approvalPolicy="never", and
absence of sandbox escalation. No real Codex service was called.

## Ownership freeze

Milestone 4 production changes are limited to:

    dsh_runtime/state.py
    dsh_runtime/planner.py

These existing owners were not changed for Milestone 4:

    dsh_runtime/controller.py
    dsh_runtime/runtime/executor.py
    dsh_runtime/runtime/plugin.py
    dsh_runtime/runtime/registry.py
    dsh_runtime/workspace/manager.py
    dsh_runtime/plugins/codex.py
    dsh_runtime/plugins/echo.py

No second owner, router framework, provider framework, or generic permission
policy was introduced.

## Non-claims and deferred work

Milestone 4 closure does not claim verification of:

    real successful Codex model turn
    real final-answer delivery
    real requested-write denial
    real workspace-write side effect
    interrupt acknowledgement
    real descendant process-tree behavior
    real completion/deadline race

The existing real-service verification debt remains associated with Milestone
2. CodeBuddy integration, a two-action workflow, write-capable repository
workflow, task cancellation, and other future features are outside this
closure and require their own concrete requirement and executable evidence.

## Reopen gate

Milestone 4 remains closed unless executable evidence falsifies a frozen
Milestone 4 invariant. Examples include:

- Repository Analysis bypasses its read-only input invariant.
- Production Planner routing for Repository Analysis is broken.
- Task success bypasses the Milestone 3 post-result terminal Planner path.
- DEFAULT -> Echo compatibility breaks.
- Regression evidence exposes an M4-specific defect.

Real Codex service availability, CodeBuddy investigation, a future
write-capable workflow, or a useful two-action workflow do not by themselves
reopen Milestone 4. They belong to the existing deferred debt or a new
evidence-driven goal.

## Evidence references

- collaboration/implementations/2026-09-06-m4b-repository-analysis-workflow-implementation.md
- collaboration/plans/2026-09-06-m4a-repository-analysis-minimal-implementation-design.md
- collaboration/plans/2026-09-06-m4a1-repository-analysis-readonly-invariant.md
- collaboration/sessions/2026-09-06-m4b-handover.md

No production file or test file was changed for Milestone 4-C.
