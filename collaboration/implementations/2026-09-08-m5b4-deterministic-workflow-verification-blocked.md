# M5-B4 DETERMINISTIC END-TO-END VERIFICATION ARTIFACT

Date: 2026-09-08
Scope: M5-B4 deterministic verification only
Status: `M5-B4 BLOCKED BY PRODUCTION CONTRACT DEFECT`

## A. Scope

This was a verification-only slice. Production changes: **NONE**.

The focused deterministic workflow tests exposed a production authority
handoff defect. Per the M5-B4 defect discovery rule, the test evidence is
preserved and no production fix was attempted.

## B. Test architecture

New focused module:

    tests/test_m5_repository_change_workflow.py

The tests use disposable `tmp_path` workspaces and start through the B3
production seams:

    build_controller(workspace_manager=...)
    build_repository_change_task(...)
    DSHController.run(task)

The real production `PluginRegistry`, `Executor`, `SimplePlanner`,
`WorkspaceManager`, and `DSHController` remain in the path. The native
`CodeBuddyPlugin.execute` and `CodexPlugin.execute` boundaries are patched
with deterministic local async doubles; no model, network, authentication,
or live CLI service is required. The doubles mutate and inspect the same
temporary workspace.

## C. Golden path evidence and blocker

The golden-path test reaches the intended sequence:

    REPOSITORY_CHANGE
    -> Planner selects codebuddy
    -> CodeBuddy double mutates target.txt
    -> Controller invokes codex
    -> Codex double observes the mutation in the same cwd

The test then fails on the required read-only handoff assertion. Observed:

    CodeBuddy ctx.allow_workspace_write = True
    Codex ctx.allow_workspace_write = True   # actual, contract violation

Required:

    CodeBuddy ctx.allow_workspace_write = True
    Codex ctx.allow_workspace_write = False

The production cause is in `dsh_runtime/controller.py`: every invocation
constructs `ExecutionContext(... allow_workspace_write=task.allow_workspace_write)`.
The Controller forwards the repository-change task's write authority to the
Codex verifier instead of applying the approved read-only verifier handoff.
`CodexPlugin` correctly consumes the context it receives; changing it would
not fix the caller-to-verifier authority propagation.

This violates the M5-B4 authority contract and blocks a valid claim of
same-workspace **read-only** Codex verification. It requires a separate,
review-authorized production fix slice owned by the appropriate Runtime
authority boundary.

## D. Failure evidence

The B4 module contains four deterministic scenarios:

- golden PASS workflow: reaches mutation and verifier, fails on Codex
  authority being `True` instead of `False`;
- CodeBuddy success plus Codex `DSH_VERIFICATION: FAIL`: reaches the same
  authority mismatch before the terminal-failure assertions;
- CodeBuddy unsuccessful `PluginResult`: passes and short-circuits before
  Codex;
- bounded CodeBuddy timeout: passes with `TaskStatus.TIMED_OUT`, one
  invocation, and no Codex continuation.

Existing B1/B2 tests continue to cover terminal verifier failure, budget/no
third action, native failure normalization, cleanup, and process-tree
semantics independently.

## E. Acceptance matrix

| Acceptance case | Test/evidence | Result | Evidence |
|---|---|---|---|
| 1. Caller contract | B3 `test_repository_change_caller_builds_existing_task_state`; B4 task construction | Partial / existing seam passes | Existing `TaskState`, goal, logical workspace, write authority, and budget are correct; full workflow is blocked later. |
| 2. First Planner action | B4 golden test | Observed before blocker | Planner returns `codebuddy` with the original goal at iteration 0. |
| 3. CodeBuddy mutation | B4 golden and negative tests | Observed before blocker | Disposable `target.txt` becomes `changed`. |
| 4. Planner continuation | B4 golden and negative tests | Observed before blocker | Controller invokes Codex after settled CodeBuddy. |
| 5. Same workspace / read-only Codex | B4 golden and negative tests | **BLOCKED** | Same cwd is observed, but Codex authority is `True`, not required `False`. |
| 6. Positive PASS completion | B4 golden test | **BLOCKED** | Cannot accept the workflow while verifier authority is wrong. |
| 7. Native/tool false-success protection | B2 focused suite; B4 CodeBuddy failure short-circuit | Pass at existing boundaries | B2: 20 passed; unsuccessful first-stage result does not invoke Codex. |
| 8. CodeBuddy failure outcome | B4 failure-short-circuit test | Passed | Task is failed at iteration 1 and Codex count is zero. |
| 9. Timeout / cleanup integration | B4 timeout test; B2 timeout/cleanup tests | Partial | B4 timeout short-circuits; B2 retains concrete cleanup semantics. |
| 10. Process-tree cleanup | B2 deterministic suite | Passed at frozen B2 boundary | Reused B2 coverage; no duplicate B4 process-tree fixture. |
| 11. Negative Codex verification | B1 runtime tests plus B4 negative scenario | **BLOCKED** | B1 terminal FAIL semantics pass; B4 same-workspace scenario is blocked by authority mismatch. |
| 12. Budget / no third action | B1 runtime tests and Planner contract | Passed at existing boundary | B1 runtime suite remains green; no B4 production claim beyond the blocker. |

## F. Production freeze confirmation

No production file was modified by B4. The following remain unchanged during
this slice:

- `dsh_runtime/bootstrap.py`
- `dsh_runtime/state.py`
- `dsh_runtime/planner.py`
- `dsh_runtime/controller.py`
- `dsh_runtime/plugins/codebuddy.py`
- `dsh_runtime/plugins/codex.py`
- `dsh_runtime/plugins/echo.py`
- `dsh_runtime/runtime/plugin.py`
- `dsh_runtime/runtime/executor.py`
- `dsh_runtime/runtime/registry.py`
- `dsh_runtime/workspace/manager.py`

The new B4 test module is intentionally retained as minimal failing evidence.

## G. Validation evidence

### B4 focused

    .venv\Scripts\python.exe -m pytest -q tests\test_m5_repository_change_workflow.py
    2 failed, 2 passed

The two failures are the same authority-handoff defect described above.

### B3 focused

    .venv\Scripts\python.exe -m pytest -q tests\test_bootstrap.py
    3 passed

### B2 focused

    .venv\Scripts\python.exe -m pytest -q tests\test_codebuddy_plugin.py
    20 passed

### B1/runtime

    .venv\Scripts\python.exe -m pytest -q tests\test_runtime.py
    31 passed

### Related runtime

    .venv\Scripts\python.exe -m pytest -q tests\test_runtime.py tests\test_runtime_semantic_hardening.py tests\test_disposable_lifecycle.py
    50 passed

### Full regression including B4 evidence

    .venv\Scripts\python.exe -m pytest -q
    84 passed, 2 failed

### Pre-B4 regression isolation

    .venv\Scripts\python.exe -m pytest -q --ignore=tests\test_m5_repository_change_workflow.py
    82 passed

### Compile/import sanity

    .venv\Scripts\python.exe -m py_compile dsh_runtime\bootstrap.py tests\test_m5_repository_change_workflow.py
    passed

    .venv\Scripts\python.exe -c "import dsh_runtime.bootstrap, tests.test_m5_repository_change_workflow; print('import ok')"
    import ok

### Diff check

    git diff --check
    passed

## H. Diff evidence

`git status --short` after the B4 blocker evidence was preserved:

    M dsh_runtime/controller.py
    M dsh_runtime/planner.py
    M dsh_runtime/state.py
    M tests/test_runtime.py
    ?? collaboration/implementations/2026-09-07-m5b1-business-intent-terminal-decision-implementation.md
    ?? collaboration/implementations/2026-09-07-m5b2-bounded-codebuddy-plugin-implementation.md
    ?? collaboration/implementations/2026-09-08-m5b3-minimal-production-assembly-caller-implementation.md
    ?? collaboration/implementations/2026-09-08-m5b4-deterministic-workflow-verification-blocked.md
    ?? collaboration/investigations/2026-09-07-codebuddy-bash-authorization-root-cause.md
    ?? collaboration/investigations/2026-09-07-codebuddy-local-native-contract-verification.md
    ?? collaboration/investigations/2026-09-07-codebuddy-native-boundary-cleanup-closure.md
    ?? collaboration/investigations/2026-09-07-codebuddy-native-contract-final-debt-closure.md
    ?? collaboration/investigations/2026-09-07-codebuddy-native-debt-closure.md
    ?? collaboration/investigations/2026-09-07-codebuddy-noninteractive-bash-approval-verification.md
    ?? collaboration/investigations/2026-09-07-codebuddy-windows-spawn-eperm-investigation.md
    ?? collaboration/plans/2026-09-07-m5a-codebuddy-primary-executor-minimal-design.md
    ?? collaboration/sessions/2026-09-07-codebuddy-native-contract-handover.md
    ?? collaboration/sessions/2026-09-07-m5b1-handover.md
    ?? dsh_runtime/bootstrap.py
    ?? dsh_runtime/plugins/codebuddy.py
    ?? tests/test_bootstrap.py
    ?? tests/test_codebuddy_plugin.py
    ?? tests/test_m5_repository_change_workflow.py

`git diff --stat` (tracked changes only):

    dsh_runtime/controller.py |  31 +++++---
    dsh_runtime/planner.py    |  48 +++++++++++++
    dsh_runtime/state.py      |  10 +++
    tests/test_runtime.py     | 175 ++++++++++++++++++++++++++++++++++++++++++
    4 files changed, 256 insertions(+), 8 deletions(-)

The tracked diff is pre-existing M5-B1 work. `bootstrap.py`, CodeBuddy files,
and B3 documents are pre-existing B3/B2 work. The only new B4 implementation
file is `tests/test_m5_repository_change_workflow.py`, plus this blocker
artifact. No production diff belongs to B4.

## I. Remaining environment debt

No real-host CodeBuddy or Codex smoke was attempted. Deterministic B4 is
blocked independently by the production authority contract defect; no
`ENVIRONMENT_BLOCKED` classification is involved.

## Completion status

`M5-B4 BLOCKED BY PRODUCTION CONTRACT DEFECT`

Do not declare M5-B4 complete or Milestone 5 complete. A separate narrow
production fix authorization is required before rerunning the B4 acceptance
matrix.
