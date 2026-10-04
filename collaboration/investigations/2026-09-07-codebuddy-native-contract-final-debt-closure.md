# CodeBuddy Native Contract Final Debt Closure

Date: 2026-09-07
Scope: final native verification / executable evidence gathering only
Implementation: none

## 1. Final gate

    ENVIRONMENT_BLOCKED

The required bounded sequence could not be completed:

    Read -> Edit -> repository-local command/test -> settled success

The probe was run from an ordinary host execution context with CodeBuddy's
cwd explicitly set to a disposable repository. CodeBuddy successfully edited
the marker, but the authorized Bash command was denied before execution. No
new `spawn EPERM` was observed in this run.

This closure does not declare Milestone 5, create an implementation plan,
modify Runtime production code, modify existing tests, update
`PROJECT_STATE.md`, or create `CodeBuddyPlugin`.

## 2. Safety boundary

The disposable fixture was created under:

    D:\PythonProject\dsh-runtime\.tmp-codebuddy-final-debt\repo

It contained only `marker.txt`, `check_local.py`, and a child-process probe
fixture. A disposable settings file was used. The real DSH Runtime repository
was never used as CodeBuddy's cwd. No `--add-dir`, `--sandbox`, `-y`,
`--dangerously-skip-permissions`, or `bypassPermissions` was used.

After evidence collection, the complete temporary directory was removed and
verified absent. No sentinel or child process was left by this task.

## 3. Full happy-path probe

The probe used:

    codebuddy.cmd --print
    --output-format json
    --input-format text
    --max-turns 6
    --no-session-persistence
    --tools Read,Edit,Bash
    --settings <disposable settings>
    --permission-mode dontAsk

The disposable settings contained the narrow rules:

    Read
    Edit
    Bash(python:*)

The task prompt required CodeBuddy to read `marker.txt` and `check_local.py`,
replace `before-command` with `after-command`, run exactly
`python check_local.py`, and report success only if both operations succeeded.

Observed:

    CodeBuddy cwd: D:\PythonProject\dsh-runtime\.tmp-codebuddy-final-debt\repo
    process exit: 0
    marker.txt: after-command\n
    command-observed.txt: absent
    LOCAL_TEST_OK: absent

The JSON event stream contained Read and Edit calls, then a Bash
`function_call_result` with:

    Error: Permission to use Bash has been denied because this tool requires
    approval but permission prompts are not available in non-interactive mode.

The final session event reported `subtype=success` and `is_error=false`, but
its final text explicitly said the command did not run. Therefore the probe is
not a PASS. This confirms again that process exit code and session-level
success are insufficient native/task success evidence.

Classification:

    Read/Edit: PASS
    Bash permission authorization in this run: ENVIRONMENT_BLOCKED
    repository-local command/test: ENVIRONMENT_BLOCKED
    full happy path: ENVIRONMENT_BLOCKED

## 4. Workspace boundary

Not executed. The task explicitly required the command-enabled boundary probe
only after the full happy path passed. Since Bash did not execute, no
inside-cwd or explicitly authorized outside-cwd read/write observation was
collected.

The prior evidence remains authoritative: approval-based denial must not be
described as hard filesystem confinement. The command-enabled boundary is
still `NOT VERIFIED` / `ENVIRONMENT_BLOCKED`, not `HARD NATIVE CONFINEMENT`.

## 5. Descendant cleanup / timeout

Not executed. The task required a real controlled child only after the full
happy path passed. No child PID or survivor observation was produced in this
run.

Cleanup classification remains:

    ENVIRONMENT_BLOCKED

The existing ownership hypothesis is unchanged: if later evidence proves
descendants survive top-level termination, CodeBuddy-specific bounded process
tree mechanics belong first to a future CodeBuddy capability, not to a new
generic ProcessManager or Executor redesign.

## 6. Result normalization confirmation

The minimum rule is confirmed by this run:

    candidate success
      = final session result successful
        AND every required function/tool result successful
        AND required filesystem/command effects occurred

Here, the final session result was nominally successful, but the required Bash
function result contained a permission error and the required command effect
was absent. The invocation must therefore normalize as unsuccessful:

    PluginResult.output: usable final assistant text only on no-error success
    PluginResult.error: best native diagnostic
    StopReason: FAILED

Outer DSH timeout remains distinct and maps to `StopReason.TIMED_OUT` under the
existing Executor contract. No new event DTO, provider result, envelope, or
agent-event hierarchy is justified.

## 7. Remaining native debt

The following remain open:

1. Obtain a safe, non-dangerous non-interactive Bash authorization path that
   actually reaches native execution in the ordinary host context.
2. Complete the repository-local Read/Edit/Bash/test settlement evidence.
3. With command execution authorized, determine the actual workspace boundary
   for inside-cwd and outside-cwd/absolute-path probes.
4. Verify controlled child behavior under top-level termination and classify
   cleanup as top-level termination sufficient, process-tree termination
   required, or native interrupt required.
5. Independently verify the stable error/output schema and durable semantics of
   `--no-session-persistence` if they remain required by product design.

The earlier `spawn EPERM` blocker remains resolved for the ordinary host
execution context. This run adds no contrary evidence and does not reopen that
investigation.

## 8. Ownership sanity check

No evidence requires changing Controller, Executor, WorkspaceManager,
CodexPlugin, the existing Plugin abstraction, or Runtime ownership. M3's
continuation seam remains sufficient for the intended future direction:

    DSH -> CodeBuddy primary executor -> Planner
        -> Codex read-only verifier -> Planner terminal Decision
        -> DSH task completion

The native gate is blocked by executable CodeBuddy permission/process evidence,
not by a demonstrated Runtime architecture gap.
