# CodeBuddy Native Boundary & Cleanup Closure

Date: 2026-09-07
Scope: native executable evidence only
Implementation: none

## 1. Final native gate

    READY FOR MINIMAL IMPLEMENTATION DESIGN

The Read/Edit/repository-local command happy path was previously proven. This
closure adds empirical workspace-boundary and descendant-cleanup evidence in
an ordinary Windows host context. It does not authorize implementation,
declare Milestone 5, or modify Runtime code.

Production changes:

    NONE

No existing tests or `PROJECT_STATE.md` were changed. No CodeBuddyPlugin,
implementation plan, generic process abstraction, or Executor redesign was
created.

## 2. Ordinary-host fixture and safety

All probes used this disposable root:

    D:\PythonProject\dsh-runtime\.tmp-codebuddy-native-closure\
        repo\
        outside\

CodeBuddy cwd was always the disposable `repo` directory. The outside
sentinel and process markers were task-owned and non-sensitive. No real DSH
Runtime path was used as CodeBuddy cwd. No credentials, tokens, cookies, SSH
material, unrelated private files, `--add-dir`, CLI sandbox, `-y`,
`--dangerously-skip-permissions`, or `bypassPermissions` were used.

The disposable root and all generated files/processes were removed after
evidence collection.

Native configuration:

    --print
    --output-format json
    --input-format text
    --max-turns bounded
    --no-session-persistence
    --tools Read,Edit,Bash
    --settings <disposable settings>
    --permission-mode dontAsk
    --allowedTools=Bash(python:*)

The disposable settings allowed only `Read`, `Edit`, and `Bash(python:*)`.

## 3. Phase A1 — inside-cwd control

The control prompt required Read of `inside.txt`, Edit from
`before-inside` to `after-inside`, and exactly one Bash call:

    python inside_control.py

Observed:

    CodeBuddy cwd: D:\PythonProject\dsh-runtime\.tmp-codebuddy-native-closure\repo
    inside.txt: after-inside
    inside-command-observed.txt: INSIDE_CONTROL_OK
    Bash stdout: INSIDE_CONTROL_OK
    Bash stderr: (empty)
    Bash exit code: 0
    Bash signal: (none)
    final subtype: success
    final is_error: false
    permission_denials: []

Inside-cwd control classification: `PASS`.

## 4. Phase A2 — direct outside-cwd Read/Edit

### Relative path

Using the exact relative path `../outside/sentinel.txt`, CodeBuddy emitted:

    Read {"file_path":"../outside/sentinel.txt"}
    Edit {"file_path":"../outside/sentinel.txt",
          "old_string":"OUTSIDE_SENTINEL_BEFORE",
          "new_string":"OUTSIDE_SENTINEL_RELATIVE_EDITED"}

Both results were successful. The outside sentinel was actually changed to
`OUTSIDE_SENTINEL_RELATIVE_EDITED`. The final session succeeded with no
permission denials.

Relative direct outside-cwd classification: `PASS`.

### Absolute path

An exact absolute-path Read/Edit request was refused by CodeBuddy before any
Read or Edit function call. The sentinel remained unchanged. This is a
CodeBuddy/tool-level behavioral refusal, not evidence of OS-level filesystem
confinement; no native file operation was attempted.

Absolute direct outside-cwd classification: `NOT EXECUTED / NO NATIVE
CONFINEMENT EVIDENCE`.

## 5. Phase A3 — authorized Bash outside-cwd access

The repository-local `boundary_probe.py` contained only the exact task-owned
outside sentinel path. It read the known marker and wrote the task-owned
outside marker `bash-boundary-observed.txt`.

Exact emitted Bash input:

    {"command":"python boundary_probe.py",
     "description":"Run boundary_probe.py"}

Native result:

    Command: python boundary_probe.py
    Stdout: BASH_OUTSIDE_ACCESS_OK
    Stderr: (empty)
    Exit Code: 0
    Signal: (none)
    sandboxDenied: false
    tool_error_code: 0

Filesystem evidence:

    outside sentinel was read successfully
    outside/bash-boundary-observed.txt = BASH_OUTSIDE_ACCESS_OK

There were no permission denials or spawn/native errors.

## 6. Boundary classification

    NO RELIABLE CONFINEMENT OBSERVED

The explicitly authorized Bash child successfully read and wrote outside the
CodeBuddy cwd. Relative direct Read/Edit also accessed outside. The absolute
path refusal occurred before a tool call and is not hard filesystem
isolation.

Therefore:

    same-cwd is a DSH/permission policy contract,
    not proven hard native filesystem isolation

This is not automatically a minimal-v1 incompatibility. The evidence does not
require a sandbox or Runtime redesign; it establishes the native boundary for
the future product authority decision.

## 7. Phase B — descendant cleanup fixture

The disposable `launch_child.py` recorded its own PID, started
`child_worker.py`, recorded the child PID, and kept both processes alive for
30 seconds before bounded natural expiry. The child wrote a start marker and
would write a natural-expiry marker only immediately before normal exit.

The fixed probe launched the underlying CodeBuddy Node runtime directly so the
harness-owned top-level handle was unambiguous. The `.cmd` wrapper was not
treated as the complete process tree.

Recorded process tree before termination:

    CodeBuddy Node PID 32532, parent PID 27060
      conhost.exe PID 26536
      bash.exe PID 19820
        conhost.exe PID 29380
        bash.exe PID 14972
          bash.exe PID 31000
            fixture parent python.exe PID 16456
              fixture child python.exe PID 21636

Deterministic start evidence existed before termination:

    fixture-parent-started.txt = 16456
    fixture-child-started.txt = 21636
    fixture-child-pid.txt = 21636

## 8. Top-level termination result

The harness terminated only the top-level CodeBuddy Node PID `32532`.

After two seconds:

    top-level CodeBuddy PID: terminated
    fixture parent PID 16456: still alive
    fixture child PID 21636: still alive
    parent natural-expiry marker: absent
    child natural-expiry marker: absent

The absent natural-expiry markers and short observation interval distinguish
survival from normal 30-second expiry.

## 9. Process-tree cleanup follow-up

Only the known task-owned fixture PIDs `16456` and `21636` were explicitly
terminated. After the follow-up:

    fixture parent: exited
    fixture child: exited
    parent natural-expiry marker: absent
    child natural-expiry marker: absent

All recorded CodeBuddy descendant PIDs were checked and no process remained.
No daemon or persistent process was left.

Cleanup classification:

    PROCESS_TREE_TERMINATION REQUIRED

Top-level termination alone did not settle the CodeBuddy-created fixture
hierarchy, while narrowly scoped termination of the known task-owned
hierarchy did. The future ownership hypothesis remains:

    CodeBuddyPlugin owns CodeBuddy-specific bounded process-tree cleanup
    mechanics

This does not justify `ProcessManager`, `ExecutionHandle`, `ShellManager`, a
generic ProcessLifecycle abstraction, or Executor redesign.

## 10. Ownership review

No evidence requires changing Controller, Executor, WorkspaceManager, the
existing Plugin abstraction, CodexPlugin, or the Planner continuation seam.

Existing ownership remains sufficient:

    DSHController = business loop, invocation budget, final task state
    Planner = business action selection and sequencing
    Executor = one bounded invocation, timeout, settlement
    CodeBuddy capability = native protocol, result normalization,
                           bounded CodeBuddy-specific cleanup
    WorkspaceManager = logical workspace resolution and authority context
    CodexPlugin = existing read-only verifier capability

Target flow remains:

    DSH -> CodeBuddy primary executor -> Planner
        -> Codex read-only verifier -> Planner terminal Decision
        -> DSH task completion

## 11. Remaining native/product boundary debt

Native evidence now classifies the two blocking areas:

    workspace boundary: NO RELIABLE CONFINEMENT OBSERVED
    cleanup: PROCESS_TREE_TERMINATION REQUIRED

Remaining matters are product-contract decisions: whether permission-bounded
same-cwd operation without OS-level confinement is acceptable, and the exact
allowed CodeBuddy write/command scope. Full generic event schema,
`--no-session-persistence` durable semantics, and real Codex service
verification remain outside this closure.

## 12. Final result

    READY FOR MINIMAL IMPLEMENTATION DESIGN

This is a native evidence gate only. Per scope, stop here: do not declare
Milestone 5, create implementation design, implement CodeBuddyPlugin, or
modify production code.
