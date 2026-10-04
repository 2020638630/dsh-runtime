# M5-B3 MINIMAL PRODUCTION ASSEMBLY / CALLER IMPLEMENTATION ARTIFACT

Date: 2026-09-08
Scope: M5-B3 design amendment only
Status: `M5-B3 IMPLEMENTATION COMPLETE`

M5-B4 remains not started. Milestone 5 is not complete.

## A. Blocking evidence closure

The previous M5-B3 attempt correctly stopped because the repository had no
production assembly/bootstrap seam and no production task-submission/caller
seam. `PluginRegistry` and direct `TaskState` construction existed only at
test call sites. The resumed implementation uses the explicit design
amendment authorizing one minimal composition/caller module.

## B. Files changed

### New production seam

- `dsh_runtime/bootstrap.py`

### Tests

- `tests/test_bootstrap.py`

### Documentation/artifact

- `collaboration/implementations/2026-09-08-m5b3-minimal-production-assembly-caller-implementation.md`

### Pre-existing working-tree changes preserved

- M5-B1 tracked changes in `dsh_runtime/state.py`,
  `dsh_runtime/planner.py`, `dsh_runtime/controller.py`, and
  `tests/test_runtime.py`.
- M5-B2 files `dsh_runtime/plugins/codebuddy.py` and
  `tests/test_codebuddy_plugin.py`, plus their existing implementation
  artifact and investigation/handover documents.

No pre-existing B1/B2 file was edited by B3.

## C. Composition root

`dsh_runtime/bootstrap.py:build_controller` is the single production
composition seam. It constructs and registers `EchoPlugin`, `CodexPlugin`,
and `CodeBuddyPlugin` in the existing `PluginRegistry`, then passes the
registry, an existing `SimplePlanner`, and an existing `WorkspaceManager` to
the existing `DSHController` constructor. `DSHController` constructs the
existing `Executor` through its normal constructor path.

The module contains no workflow loop, retry, continuation, routing policy,
terminal decision, or lifecycle logic. It only answers which existing
objects are instantiated and connected.

No execution convenience function was added: `DSHController.run` is already
the existing entry method, so adding another wrapper would enlarge the seam
without adding capability.

## D. Registry registration

The composition root performs the following ordinary registrations:

    registry.register(EchoPlugin())
    registry.register(CodexPlugin())
    registry.register(CodeBuddyPlugin())

Therefore `controller.executor.registry.get("codebuddy")` resolves to the
concrete `CodeBuddyPlugin`, while `echo` and `codex` remain available.

`PluginRegistry` is unchanged. Its name lookup, duplicate-registration error,
and missing-plugin semantics remain generic and untouched. No factory, router,
provider metadata, or provider-specific registry behavior was introduced.

## E. Caller construction

`dsh_runtime/bootstrap.py:build_repository_change_task` directly constructs
the existing `TaskState`:

    TaskState(
        goal=goal,
        workspace_id=workspace,
        task_kind=TaskKind.REPOSITORY_CHANGE,
        allow_workspace_write=True,
        max_iterations=2,
    )

The caller goal and caller-selected logical workspace are passed through
unchanged. The function does not select CodeBuddy or Codex, inspect
iterations, parse verifier markers, decide terminal success, or implement
retry.

## F. Ownership check

- `TaskState` retains task input, authority, budget, and lifecycle state.
- `SimplePlanner` retains CodeBuddy → Codex sequencing and verifier
  interpretation.
- `DSHController` retains the business loop and terminal TaskState
  transition.
- `Executor` retains bounded invocation, timeout, cancellation, and
  settlement semantics.
- `CodeBuddyPlugin` retains its native protocol and cleanup mechanics.
- `CodexPlugin` remains the read-only verifier capability.
- `WorkspaceManager` retains logical workspace resolution.

## G. Frozen-owner confirmation

The following remained unchanged by B3:

- `dsh_runtime/state.py`
- `dsh_runtime/planner.py`
- `dsh_runtime/controller.py`
- `dsh_runtime/plugins/codebuddy.py`
- `dsh_runtime/runtime/plugin.py`
- `dsh_runtime/runtime/executor.py`
- `dsh_runtime/runtime/registry.py`
- `dsh_runtime/workspace/manager.py`
- `dsh_runtime/plugins/codex.py`
- `dsh_runtime/plugins/echo.py`
- `tests/test_codebuddy_plugin.py`

## H. Tests and validation

### Focused B3 tests

    .venv\Scripts\python.exe -m pytest -q tests\test_bootstrap.py
    3 passed

These prove production composition, `echo`/`codex`/`codebuddy` availability,
concrete CodeBuddy resolution, unchanged duplicate-registration behavior, and
caller construction through the existing `TaskState`.

### M5-B1 / runtime regression

    .venv\Scripts\python.exe -m pytest -q tests\test_runtime.py
    31 passed

### M5-B2 focused regression

    .venv\Scripts\python.exe -m pytest -q tests\test_codebuddy_plugin.py
    20 passed

### Related runtime regression

    .venv\Scripts\python.exe -m pytest -q tests\test_runtime.py tests\test_runtime_semantic_hardening.py tests\test_disposable_lifecycle.py
    50 passed

### Full regression

    .venv\Scripts\python.exe -m pytest -q
    82 passed

### Compile/import sanity

    .venv\Scripts\python.exe -m py_compile dsh_runtime\bootstrap.py tests\test_bootstrap.py
    passed

    .venv\Scripts\python.exe -c "from dsh_runtime.bootstrap import build_controller, build_repository_change_task; c=build_controller(); t=build_repository_change_task('goal', 'dsh.main'); print(type(c).__name__, type(t).__name__, c.executor.registry.get('codebuddy').name)"
    DSHController TaskState codebuddy

### Diff check

    git diff --check
    passed

No new real-host CodeBuddy/Codex smoke was attempted; it is not required for
this assembly-only slice.

## I. Diff evidence

`git status --short` after B3 validation:

    M dsh_runtime/controller.py
    M dsh_runtime/planner.py
    M dsh_runtime/state.py
    M tests/test_runtime.py
    ?? collaboration/implementations/2026-09-07-m5b1-business-intent-terminal-decision-implementation.md
    ?? collaboration/implementations/2026-09-07-m5b2-bounded-codebuddy-plugin-implementation.md
    ?? collaboration/implementations/2026-09-08-m5b3-minimal-production-assembly-caller-implementation.md
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

`git diff --stat` (tracked changes only, because the existing B1/B2 and new
B3 files are not staged):

    dsh_runtime/controller.py |  31 +++++---
    dsh_runtime/planner.py    |  48 +++++++++++++
    dsh_runtime/state.py      |  10 +++
    tests/test_runtime.py     | 175 ++++++++++++++++++++++++++++++++++++++++++
    4 files changed, 256 insertions(+), 8 deletions(-)

The new B3 files are the untracked `bootstrap.py`, `test_bootstrap.py`, and
this artifact. The tracked diff is pre-existing M5-B1 work; the untracked
CodeBuddy files and related documents are pre-existing M5-B2 work. B3 did not
modify those earlier slices.

Final status: `M5-B3 IMPLEMENTATION COMPLETE`.
M5-B4: `NOT STARTED`.
Milestone 5: `NOT COMPLETE`.
