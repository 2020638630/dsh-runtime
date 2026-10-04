# M5-B2 — Bounded CodeBuddyPlugin Capability Implementation

Date: 2026-09-07
Scope: M5-B2 implementation plus review-fix slice
Status: `M5-B2 REVIEW FIX IMPLEMENTED`

Milestone 5 remains incomplete. M5-B3 registry/workflow wiring and M5-B4
end-to-end verification were not started.

## A. Files changed

Added production:

- `dsh_runtime/plugins/codebuddy.py`

Added focused tests:

- `tests/test_codebuddy_plugin.py`

No registry registration was added. `PROJECT_STATE.md`, Planner, Controller,
TaskKind, Executor, Plugin protocol, WorkspaceManager, CodexPlugin, and
EchoPlugin were not modified by B2. The pre-existing M5-B1 working-tree
changes in `state.py`, `planner.py`, `controller.py`, and
`tests/test_runtime.py` remain preserved.

## CodeBuddyPlugin contract

`CodeBuddyPlugin.name` is `codebuddy`. The plugin requires a non-empty prompt,
an existing directory in `ctx.cwd`, and `ctx.allow_workspace_write is True`.
It does not infer authority from prompt text or params and does not mutate
TaskState.

The native invocation is launched with `shell=False`, `ctx.cwd`, and:

    codebuddy.cmd --print
      --output-format json
      --input-format text
      --max-turns 6
      --no-session-persistence
      --tools Read,Edit,Bash
      --settings <private temporary settings file>
      --permission-mode dontAsk
      --allowedTools=Bash(python:*)
      <prompt>

No `-y`, `--dangerously-skip-permissions`, `bypassPermissions`, `--add-dir`,
unrestricted Bash rule, or CLI sandbox flag is supplied.

## Settings and native normalization

Each invocation creates a private temporary JSON settings artifact:

    {
      "permissions": {
        "defaultMode": "dontAsk",
        "allow": ["Read", "Edit", "Bash(python:*)"]
      }
    }

The artifact and private stdout/stderr capture files are deleted on success,
native failure, parser failure, and cancellation. Output is read with a bound;
diagnostics are truncated before crossing the PluginResult boundary.

The parser accepts only the observed top-level JSON event-array shape; a root
object or nested `type=result` mapping is rejected. The final top-level event
must be `type=result` with `subtype=success` and `is_error=false`, and must
contain non-empty final `result` assistant text. Every emitted
`function_call_result`/tool-result event is inspected for native error,
permission denial, non-zero exit, signal, skipped/unexecuted status, and
equivalent error diagnostics. A tool failure therefore prevents false
success even when process exit and final session status are nominally
successful.

The result mapping uses the existing `PluginResult`: successful native
settlement returns bounded final assistant text; malformed JSON, missing
final result, native failure, permission/tool failure, max-turn exhaustion,
non-zero process exit, and spawn failure return unsuccessful results.

## Cancellation and process cleanup

The plugin retains the native root process handle. On cancellation it invokes
private CodeBuddy-specific process-tree cleanup, bounded by
`cleanup_grace_seconds`, then waits for root/process settlement and temporary
artifact cleanup before re-propagating cancellation. Windows cleanup uses
`taskkill /PID <root> /T /F` through a separately bounded async helper. Only a
confirmed zero taskkill result counts as tree cleanup success. Any non-zero or
untrusted tree result remains a cleanup failure even if a root-process kill
fallback settles the root; that fallback never proves descendant settlement.
No generic process abstraction or Executor change was introduced.

Normal completion does not invoke forced process-tree cleanup. Cleanup errors
are surfaced through the existing Executor `cleanup_error` path while timeout
continues to normalize as `StopReason.TIMED_OUT`; outer caller cancellation
remains observable as `asyncio.CancelledError`.

The plugin treats `ctx.cwd` as the logical DSH operating scope. It does not
claim hard filesystem confinement, consistent with the accepted native
evidence.

## C. Tests added/changed

The focused test module was extended with deterministic regressions for both
review blockers: non-zero/untrusted tree cleanup, fallback settlement,
cleanup-diagnostic preservation, cancellation precedence, nested final-result
rejection, unexpected root rejection, and recursive native/tool failure
inspection. Existing command, cwd, permission, native success/failure,
malformed response, timeout, and cleanup tests remain in place.

## D. Validation evidence

Focused B2 suite after review fixes:

    .venv\Scripts\python.exe -m pytest -q tests\test_codebuddy_plugin.py
    20 passed

Existing lifecycle/semantic/runtime checks:

    .venv\Scripts\python.exe -m pytest -q tests\test_runtime.py tests\test_runtime_semantic_hardening.py tests\test_disposable_lifecycle.py
    50 passed

Full regression:

    .venv\Scripts\python.exe -m pytest -q
    79 passed

Additional compile check passed:

    .venv\Scripts\python.exe -m py_compile dsh_runtime\plugins\codebuddy.py tests\test_codebuddy_plugin.py

`git diff --check` passed.

Focused tests cover input/authority/cwd validation, exact argv and cwd,
settings content and cleanup, `shell=False`, final-output selection, malformed
and missing JSON, nested fake result rejection, unexpected root-object
rejection, native/session/tool/permission/max-turn/non-zero failures, bounded
timeout, caller cancellation, cancellation plus cleanup-failure propagation,
non-successful tree-termination fallback observability, and a Windows
task-owned root/descendant process-tree fixture. The Windows fixtures passed
on this host.

## Real ordinary-host direct-plugin smoke

`codebuddy.cmd` was available and the smoke used a disposable system-temp
repository containing `marker.txt` and `check_local.py`; the DSH repository
was not used as CodeBuddy's write cwd.

Result:

    REAL-HOST B2 VERIFICATION = ENVIRONMENT_BLOCKED

CodeBuddy did perform the same-cwd marker edit, but the required
`Bash(python:*)` check did not complete and native output reported
`Max turns (6) exceeded`. The plugin returned `success=False` with the
bounded native diagnostic. This is correctly classified as environment
blocked, not as deterministic B2 implementation failure; no false success was
reported and the disposable directory was cleaned.

## B. Fix summary

No required Runtime owner or generic abstraction was changed. Private stdout
and stderr temporary files are used instead of unbounded in-memory pipe
capture, so native output remains bounded even when a child emits a large
stream; they are treated as invocation-owned temporary artifacts.

## Diff boundary evidence

The relevant B2 diff is bounded to the private plugin and its focused tests:

- `dsh_runtime/plugins/codebuddy.py`: CodeBuddy-only subprocess invocation,
  bounded output capture, top-level final-result parsing, recursive native/tool
  failure inspection, and cancellation cleanup settlement.
- `tests/test_codebuddy_plugin.py`: deterministic command, parser, timeout,
  cancellation, cleanup-diagnostic, and Windows cleanup regressions.
- This implementation artifact: review-fix status and validation evidence.

`git status --short` at validation time:

    M dsh_runtime/controller.py
    M dsh_runtime/planner.py
    M dsh_runtime/state.py
    M tests/test_runtime.py
    ?? collaboration/implementations/2026-09-07-m5b1-business-intent-terminal-decision-implementation.md
    ?? collaboration/implementations/2026-09-07-m5b2-bounded-codebuddy-plugin-implementation.md
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
    ?? dsh_runtime/plugins/codebuddy.py
    ?? tests/test_codebuddy_plugin.py

The four tracked modifications and the other collaboration artifacts above
are pre-existing work from M5-B1/investigation handoff and were preserved.
The B2 implementation did not modify `runtime/plugin.py`,
`runtime/executor.py`, `runtime/registry.py`, or `PROJECT_STATE.md`; no
M5-B3 wiring was started.

1. Process-tree cleanup now settles before cancellation is re-propagated.
2. Only a confirmed zero `taskkill` result is tree-cleanup success.
3. Failed or untrusted tree cleanup falls back to bounded root settlement.
4. Tree-cleanup failure diagnostics remain attached after fallback settlement.
5. Outer cancellation remains `asyncio.CancelledError` and is not replaced by
   plugin failure.
6. Final session-result recognition is limited to the top-level event array.
7. Recursive native/tool failure inspection remains separate and active.

Review-fix implementation notes:

- tree cleanup no longer treats non-zero/untrusted taskkill as success;
  fallback root settlement keeps a cleanup diagnostic;
- final session-result recognition is top-level-only and separated from
  recursive tool/native failure inspection;
- outer cancellation remains cancellation while cleanup failure is observable
  through the existing Executor cleanup event/exception boundary.

Remaining M5 slices:

- M5-B3: registry/workflow wiring
- M5-B4: deterministic end-to-end workflow verification

Final status: `M5-B2 REVIEW FIX IMPLEMENTED`.
Milestone 5: `NOT COMPLETE`.
