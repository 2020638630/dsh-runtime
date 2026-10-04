# M5-B4-F1 PER-INVOCATION AUTHORITY HANDOFF REPAIR ARTIFACT

Date: 2026-09-08
Scope: M5-B4-F1 authority handoff repair only
Status: `M5-B4-F1 IMPLEMENTATION COMPLETE`

The broader M5-B4 acceptance matrix remains paused pending review of this
narrow repair. No new B4 scenarios were added beyond the preserved blocker
tests.

## A. Root cause

Before F1, `DSHController` copied `TaskState.allow_workspace_write` into every
invocation's `ExecutionContext`. That treated task-level authorization as an
instruction to grant write authority to every action. For M5 this incorrectly
made the Codex verifier write-capable even though it must be read-only.

## B. Ownership

The repair preserves the intended ownership boundary:

- `TaskState.allow_workspace_write` is the caller-level authority ceiling.
- `Decision.allow_workspace_write` is optional per-invocation authority
  metadata owned by Planner decisions.
- `DSHController` materializes effective authority while enforcing the task
  ceiling.
- Plugins only consume the resulting `ExecutionContext`.

No authority object, permission policy, provider policy, or plugin-name special
case was introduced.

## C. Production diff

Only the authorized production owners changed:

### `dsh_runtime/planner.py`

- Added `Decision.allow_workspace_write: bool | None = None`.
- M5 iteration 0 CodeBuddy decision explicitly requests `True`.
- M5 iteration 1 Codex decision explicitly requests `False`.
- Existing verifier markers, sequencing, and terminal semantics remain
  unchanged.

### `dsh_runtime/controller.py`

Added generic effective-authority calculation before each invocation:

    if decision.allow_workspace_write is None:
        effective = task.allow_workspace_write
    else:
        effective = task.allow_workspace_write and decision.allow_workspace_write

The resulting `effective` value is passed to `ExecutionContext`. The
Controller does not inspect plugin names or task kinds for authority policy.

No other production file was changed by F1.

## D. Ceiling rule

The implementation enforces:

| TaskState ceiling | Decision request | Effective invocation authority |
|---|---:|---:|
| `False` | `None` | `False` |
| `False` | `True` | `False` |
| `True` | `None` | `True` |
| `True` | `False` | `False` |
| `True` | `True` | `True` |

Thus a read-only task cannot be escalated by a Planner decision, while a
write-authorized task can narrow an individual invocation.

## E. M5 handoff

The frozen M5 sequence now carries:

    iteration 0: CodeBuddy decision True
    TaskState ceiling: True
    CodeBuddy ExecutionContext: True

    iteration 1: Codex decision False
    TaskState ceiling: True
    Codex ExecutionContext: False

The preserved B4 golden and negative workflow tests verify the same resolved
cwd, CodeBuddy mutation, read-only Codex context, and terminal PASS/FAIL
behavior.

## F. Regression evidence

### F1 / preserved B4 focused evidence

    .venv\Scripts\python.exe -m pytest -q tests\test_m5_repository_change_workflow.py
    4 passed

Before F1: `2 passed, 2 failed`.
After F1: `4 passed`.

### Authority/runtime fix tests

    .venv\Scripts\python.exe -m pytest -q tests\test_runtime.py
    32 passed

The additional regression proves narrowing, inheritance, and the no-escalation
ceiling.

### B3 focused

    .venv\Scripts\python.exe -m pytest -q tests\test_bootstrap.py
    3 passed

### B2 focused

    .venv\Scripts\python.exe -m pytest -q tests\test_codebuddy_plugin.py
    20 passed

### Related runtime

    .venv\Scripts\python.exe -m pytest -q tests\test_runtime.py tests\test_runtime_semantic_hardening.py tests\test_disposable_lifecycle.py
    51 passed

### Full suite

    .venv\Scripts\python.exe -m pytest -q
    87 passed

### Compile/import sanity

    .venv\Scripts\python.exe -m py_compile dsh_runtime\planner.py dsh_runtime\controller.py tests\test_runtime.py tests\test_m5_repository_change_workflow.py
    passed

    .venv\Scripts\python.exe -c "from dsh_runtime.planner import Decision; from dsh_runtime.controller import DSHController; print(Decision(plugin='x').allow_workspace_write)"
    None

### Diff check

    git diff --check
    passed

## G. Preserved blocker closure

The original B4 authority blocker was retained without weakening its
assertions:

    before: 2 passed, 2 failed
    after:  4 passed

The expected Codex authority remains explicitly `False` in the B4 tests.

## H. Diff boundary

`git status --short` after F1 validation:

    M dsh_runtime/controller.py
    M dsh_runtime/planner.py
    M dsh_runtime/state.py
    M tests/test_runtime.py
    ?? collaboration/implementations/2026-09-07-m5b1-business-intent-terminal-decision-implementation.md
    ?? collaboration/implementations/2026-09-07-m5b2-bounded-codebuddy-plugin-implementation.md
    ?? collaboration/implementations/2026-09-08-m5b3-minimal-production-assembly-caller-implementation.md
    ?? collaboration/implementations/2026-09-08-m5b4-deterministic-workflow-verification-blocked.md
    ?? collaboration/implementations/2026-09-08-m5b4-f1-per-invocation-authority-handoff-repair.md
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

The tracked B1 changes remain in `state.py`, the existing Planner/Controller
M5-B1 portions, and `tests/test_runtime.py`. The F1 delta is limited to the
per-invocation authority field and effective-authority calculation in
`planner.py`/`controller.py`, plus the authority regression in
`tests/test_runtime.py`. B2/B3 files and artifacts remain pre-existing.

No real-host smoke was attempted. F1 is deterministic and does not require
live CodeBuddy or Codex services.

Final status: `M5-B4-F1 IMPLEMENTATION COMPLETE`.
Broader M5-B4 acceptance expansion: `PAUSED FOR REVIEW`.
Milestone 5: `NOT COMPLETE`.
