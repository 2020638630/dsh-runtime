# M5-B4 FINAL DETERMINISTIC END-TO-END VERIFICATION ARTIFACT

Date: 2026-09-08
Scope: resumed M5-B4 deterministic acceptance
Status: `M5-B4 VERIFICATION COMPLETE`

## A. Final scope

This was a verification-only resume. Production changes during the resumed
B4 slice: **NONE**.

The earlier F1 repair was already reviewed and closed before this resume. B4
does not expand the workflow, add retry, or change any production contract.

## B. Existing evidence carried forward

The following evidence was already present and was preserved, not rebuilt:

- golden repository-change PASS path;
- CodeBuddy success followed by Codex FAIL terminal path;
- CodeBuddy failure short-circuit before Codex;
- CodeBuddy timeout short-circuit before Codex;
- F1 per-invocation authority handoff: CodeBuddy write authority `True`,
  Codex verifier authority `False`;
- B1 Planner sequencing and terminal Decision semantics;
- B2 native normalization, timeout, cleanup, and process-tree tests;
- B3 production composition and caller construction tests.

## C. New evidence added

One focused test was added to
`tests/test_m5_repository_change_workflow.py`:

- `test_codebuddy_timeout_cleanup_error_remains_observable` proves a
  deterministic CodeBuddy cancellation cleanup failure remains visible in the
  existing Controller log boundary, while the task remains timed out and
  Codex is not invoked.

No production test hook, workflow owner, or additional native fixture was
added.

## D. Golden path

The preserved golden test executes through production bootstrap, caller,
Planner, Executor, Controller, and WorkspaceManager seams:

    REPOSITORY_CHANGE
    -> CodeBuddy write=True
    -> target.txt mutation in disposable workspace
    -> same resolved cwd
    -> Codex write=False
    -> Codex observes "changed"
    -> DSH_VERIFICATION: PASS
    -> iteration 2
    -> TaskStatus.COMPLETED

The test also verifies that iteration 0 selects CodeBuddy, iteration 1 selects
Codex, iteration 2 is terminal, and the final result is committed only after
verification.

## E. Negative path

The preserved negative test executes:

    CodeBuddy succeeds and mutates
    -> Codex read-only verifier observes the same workspace
    -> DSH_VERIFICATION: FAIL
    -> TaskStatus.FAILED
    -> exactly two plugin invocations
    -> no repair or retry

## F. Failure / timeout behavior

- CodeBuddy unsuccessful `PluginResult` produces task failure at iteration 1
  and invokes no Codex action.
- CodeBuddy timeout produces `TaskStatus.TIMED_OUT` at iteration 1 and
  invokes no Codex action.
- The new cleanup integration test forces deterministic cleanup failure during
  timeout and observes the `cleanup_error` diagnostic in the existing
  Controller logging boundary.
- B2 remains the owner of concrete CodeBuddy process-tree cleanup evidence;
  its focused suite continues to pass.

## G. Budget / terminality

The golden and negative scenarios each record exactly two plugin invocations.
Their third Planner call is terminal; neither selects a CodeBuddy repair nor a
Codex retry. Existing B1 runtime budget tests continue to prove
`MAX_ITERATIONS` behavior and no unauthorized extra action.

## H. 12-item acceptance matrix

| #  | Acceptance item                        | Evidence | Result |
| -- | -------------------------------------- | -------- | ------ |
| 1  | REPOSITORY_CHANGE caller contract      | B3 `tests/test_bootstrap.py`; B4 golden | PASS |
| 2  | Planner selects CodeBuddy first        | B1 `tests/test_runtime.py`; B4 golden planner observations | PASS |
| 3  | CodeBuddy mutates expected workspace   | B4 golden `test_golden_repository_change_runs_codebuddy_then_codex_in_same_workspace` | PASS |
| 4  | Controller continues to Codex          | B4 golden and negative workflow tests | PASS |
| 5  | Codex same cwd + read-only authority   | B4 golden/negative plus F1 authority regressions | PASS |
| 6  | PASS → COMPLETED at iteration 2        | B4 golden test | PASS |
| 7  | native/tool false-success prevented    | B2 `tests/test_codebuddy_plugin.py`; B4 failure short-circuit | PASS |
| 8  | CodeBuddy failure remains unsuccessful | B4 `test_codebuddy_failure_short_circuits_before_codex`; B2 focused suite | PASS |
| 9  | timeout + cleanup semantics            | B4 timeout and cleanup integration; B2 timeout/cleanup tests | PASS |
| 10 | process-tree cleanup contract          | B2 focused deterministic Windows/process cleanup tests | PASS |
| 11 | Codex FAIL → terminal FAILED           | B1 runtime tests; B4 negative workflow test | PASS |
| 12 | no third action / budget preserved     | B1 budget tests; B4 golden/negative exact invocation assertions | PASS |

## I. Production freeze confirmation

No production file changed during the resumed B4 verification. The frozen
production files remain unchanged during this slice:

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

## J. Validation results

### Final B4 focused

    .venv\Scripts\python.exe -m pytest -q tests\test_m5_repository_change_workflow.py
    5 passed

### F1 / B1 runtime

    .venv\Scripts\python.exe -m pytest -q tests\test_runtime.py
    32 passed

### B3

    .venv\Scripts\python.exe -m pytest -q tests\test_bootstrap.py
    3 passed

### B2

    .venv\Scripts\python.exe -m pytest -q tests\test_codebuddy_plugin.py
    20 passed

### Related runtime

    .venv\Scripts\python.exe -m pytest -q tests\test_runtime.py tests\test_runtime_semantic_hardening.py tests\test_disposable_lifecycle.py
    51 passed

### Full suite

    .venv\Scripts\python.exe -m pytest -q
    88 passed

### Compile/import sanity

    .venv\Scripts\python.exe -m py_compile dsh_runtime\bootstrap.py dsh_runtime\planner.py dsh_runtime\controller.py tests\test_bootstrap.py tests\test_codebuddy_plugin.py tests\test_m5_repository_change_workflow.py tests\test_runtime.py
    passed

    .venv\Scripts\python.exe -c "import dsh_runtime.bootstrap, dsh_runtime.controller, dsh_runtime.planner, tests.test_m5_repository_change_workflow; print('import ok')"
    import ok

### Diff check

    git diff --check
    passed

## K. Environment debt

Real-host CodeBuddy/Codex verification was not required and was not attempted
for deterministic M5 acceptance. The final acceptance is offline and uses
disposable temporary workspaces plus deterministic native-boundary doubles.

## Diff evidence

`git status --short` after final B4 validation:

    M dsh_runtime/controller.py
    M dsh_runtime/planner.py
    M dsh_runtime/state.py
    M tests/test_runtime.py
    ?? collaboration/implementations/2026-09-07-m5b1-business-intent-terminal-decision-implementation.md
    ?? collaboration/implementations/2026-09-07-m5b2-bounded-codebuddy-plugin-implementation.md
    ?? collaboration/implementations/2026-09-08-m5b3-minimal-production-assembly-caller-implementation.md
    ?? collaboration/implementations/2026-09-08-m5b4-deterministic-workflow-verification-blocked.md
    ?? collaboration/implementations/2026-09-08-m5b4-f1-per-invocation-authority-handoff-repair.md
    ?? collaboration/implementations/2026-09-08-m5b4-final-deterministic-end-to-end-verification.md
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

    dsh_runtime/controller.py |  40 ++++++--
    dsh_runtime/planner.py    |  54 +++++++++++
    dsh_runtime/state.py      |  10 ++
    tests/test_runtime.py     | 232 ++++++++++++++++++++++++++++++++++++++++++
    4 files changed, 327 insertions(+), 9 deletions(-)

Tracked B1/F1 changes, untracked B2/B3 files, and their artifacts are
pre-existing relative to this resumed B4 slice. The new resumed B4 changes
are limited to the cleanup integration test and this artifact.

Final status: `M5-B4 VERIFICATION COMPLETE`.
Reviewer decision: pending.
Milestone 5: `NOT COMPLETE`.
