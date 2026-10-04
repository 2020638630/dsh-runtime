# CodeBuddy Non-Interactive Bash Approval Verification

Date: 2026-09-07
Scope: close the native debt around non-interactive Bash authorization and
continue the command, boundary, process, and result-normalization evidence
Implementation: none

## 1. Final conclusion

The installed CodeBuddy CLI recognizes `Bash` as the command tool. A narrow
non-interactive allow configuration also works at the permission-evaluation
layer: CodeBuddy emitted a Bash function call for the exact disposable test
command without an approval-denied result.

The command then failed at process creation with:

    Error: spawn EPERM

The edit completed, but the repository-local test never started. Therefore
command execution, command-enabled workspace boundaries, and command-child
cleanup remain blocked by the local Windows/CodeBuddy execution environment.

Final verdict:

    ENVIRONMENT_BLOCKED

This is not a Runtime architecture finding. No CodeBuddyPlugin, Milestone 5,
implementation plan, Runtime production change, existing test change, or
`PROJECT_STATE.md` update was made.

## 2. Native version and local help evidence

Installed executable:

    D:\Program Files\node-js\codebuddy.cmd

Installed version:

    codebuddy.cmd --version
    2.143.0

Relevant local `--help` output confirms:

- `--print` for non-interactive output and exit;
- `--output-format text|json|stream-json` in print mode;
- `--input-format text|stream-json` in print mode;
- `--max-turns` for an agentic-turn bound;
- `--permission-mode` values including `dontAsk` and `auto`;
- `--tools` values including the documented example `Bash,Edit,Read`;
- `--allowedTools` for process-level permission rules;
- `--settings <file-or-json>`;
- `--no-session-persistence`;
- `--add-dir`, `--sandbox`, and the high-risk
  `--dangerously-skip-permissions` option.

The installed product documentation further distinguishes:

    --tools
      tool exposure / capability surface

    permissions.allow / --allowedTools
      permission authorization

The built-in permission documentation records prefix rules such as
`Bash(python:*)` and exact rules such as `Bash(npm run lint)`. It also records
that unresolved non-interactive approval is converted to denial.

## 3. Disposable fixture

All write and command probes used only:

    D:\PythonProject\dsh-runtime\.tmp-codebuddy-native-approval\repo

Fixture files:

    marker.txt
      before-command

    check_local.py
      assert marker.txt == after-command
      write command-observed.txt with LOCAL_TEST_OK
      print LOCAL_TEST_OK

    verification-settings.json
      disposable permission settings

No DSH Runtime path was used as CodeBuddy cwd. No unrelated directory was
granted. No CLI `--sandbox`, `--add-dir`, `-y`, or
`--dangerously-skip-permissions` was used. The temporary repository and its
sentinels contained no credentials or sensitive data.

## 4. Primary dontAsk plus explicit allow probe

Disposable settings file:

    {
      "permissions": {
        "defaultMode": "dontAsk",
        "allow": [
          "Read",
          "Edit",
          "Bash(python:*)"
        ]
      }
    }

Tool exposure remained explicitly bounded:

    --tools Read,Edit,Bash

Invocation:

    codebuddy.cmd --print --output-format json --input-format text \
      --max-turns 6 --no-session-persistence \
      --tools Read,Edit,Bash \
      --settings verification-settings.json \
      --permission-mode dontAsk \
      "Read marker.txt and check_local.py. Replace before-command with
       after-command in marker.txt. Then run exactly python check_local.py
       from the current working directory. Do not use another command or
       access outside the current working directory. Reply success only if
       both operations succeed."

Observed function calls in the JSON event stream:

    Read marker.txt
    Read check_local.py
    Edit marker.txt: before-command -> after-command
    Bash: python check_local.py

The Bash call was not reported as approval-denied. Its function result was:

    Error: spawn EPERM

CodeBuddy then attempted a second tool call with an internal
`dangerouslyDisableSandbox: true` input; that attempt also returned
`Error: spawn EPERM`. This internal tool input was emitted by CodeBuddy after
the first failure. The verification itself did not pass a CLI permission
bypass, `-y`, `bypassPermissions`, or an unrelated directory.

Observed filesystem state:

    marker.txt = after-command
    command-observed.txt = absent

The final CodeBuddy message correctly explained that the edit succeeded but
the test did not run. The process exit code was nevertheless `0`.

Classification:

    permission authorization: PASS
    repository-local command execution: ENVIRONMENT_BLOCKED

The allow rule is therefore proven at the permission layer, but the required
native command execution is not usable in this environment.

## 5. CLI allow-rule confirmation

A second disposable invocation used the process-level form:

    --allowedTools Read Edit Bash(python:*)
    --tools Read,Edit,Bash
    --permission-mode dontAsk

The resulting JSON again contained a Bash function call with:

    command: python check_local.py

Both normal and internal sandbox-disabled attempts returned `Error: spawn
EPERM`. This confirms the matcher is not the blocking layer. A prior exact
settings probe using `Bash(python check_local.py)` and `Bash(python:*)` under
`acceptEdits` did not authorize the command, but the corrected `dontAsk` plus
explicit allow configuration did.

## 6. PreToolUse hook investigation

The installed local documentation describes `PreToolUse` hooks and the
structured output:

    {
      "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow"
      }
    }

A disposable hook was configured to allow only the exact command
`python check_local.py` and deny every other command. The hook did not produce
an observed allow decision in the non-interactive run; Bash remained denied in
that form. The corrected explicit `permissions.allow` probe did produce a Bash
call, which exposed the lower `spawn EPERM` failure.

No conclusion is drawn that hooks are universally unusable. This task has not
produced executable evidence that a hook can safely overcome the local spawn
restriction.

## 7. Workspace boundary

The command-enabled boundary probe was not executable because the command
could not be spawned. Therefore these facts remain unverified in the
command-capable configuration:

- inside-cwd command access;
- outside-cwd sentinel read;
- outside-cwd sentinel write;
- absolute-path confinement;
- command access outside the resolved cwd.

The prior file-only probe produced an approval-based denial outside cwd, but it
did not prove hard filesystem confinement. The current native classification
is therefore:

    ENVIRONMENT_BLOCKED

with the available lower-level observation remaining:

    APPROVAL-BASED DENIAL / TOOL-PERMISSION RESTRICTION

It is not valid to call this `HARD NATIVE CONFINEMENT` or `SANDBOX
CONFINEMENT` based on the current evidence.

## 8. Sandbox assessment

No CLI sandbox was adopted. The desired handoff remains:

    CodeBuddy writes physical cwd X -> Codex reads physical cwd X

Direct same-cwd file mutation already works without `--sandbox`. The command
probe's internal retry with sandbox disabled still failed at `spawn EPERM`, so
the current evidence does not show that enabling the CLI sandbox would solve
the problem.

Local `docker` and `podman` executables were unavailable. Sandbox requirement:

    NOT VERIFIED

No sandbox/worktree/export design is introduced.

## 9. Descendant process and cleanup behavior

Because the controlled Bash child command never spawned, no CodeBuddy-owned
child or descendant PID was created for observation. The local environment
also denied reliable process relationship inspection in the prior top-level
termination probe.

Preserved evidence from the previous artifact:

- the top-level print process can be externally terminated;
- complete descendant cleanup was not established.

Current classification:

    descendant process behavior: ENVIRONMENT_BLOCKED
    future cleanup classification: ENVIRONMENT_BLOCKED

It is not possible to choose between `TOP_LEVEL_TERMINATION SUFFICIENT`,
`PROCESS_TREE TERMINATION REQUIRED`, and `NATIVE INTERRUPT REQUIRED` from
this run. If later evidence shows descendants survive, the first ownership
hypothesis remains bounded CodeBuddyPlugin mechanics, not a generic process
owner or Executor redesign.

## 10. Settled-result normalization update

The new JSON probe produced a top-level event array containing Read, Edit, and
Bash function events followed by a final event with:

    subtype: success
    is_error: false

However, the same event array contained function results with:

    Error: spawn EPERM

and the filesystem/test evidence showed that the required command did not run.

This proves that a final session-level `result` event with
`subtype=success`/`is_error=false` is not by itself sufficient to classify the
repository task as a successful CodeBuddy execution.

Smallest evidence-backed rule:

1. Prefer JSON output for a future bounded invocation.
2. Parse the event sequence and locate the final `result` event.
3. Treat the session as successfully settled only when that result is a
   success and no `function_call_result` contains a native error, permission
   denial, spawn failure, or unexecuted required operation.
4. Normalize the final usable assistant text to `PluginResult.output` only in
   that no-error case.
5. If a tool-result error is present, or no successful final result exists,
   normalize the native diagnostic to `PluginResult.error` and mark the
   invocation unsuccessful with `StopReason.FAILED`.
6. Treat `Max turns (N) exceeded` and the observed service failure the same
   way: unsuccessful result with the native diagnostic. Outer DSH timeout
   remains the existing `StopReason.TIMED_OUT` path.
7. Never use exit code `0` alone as success evidence.

The observed `spawn EPERM` result is a native diagnostic, not a failure inside
`check_local.py`. No generic event DTO or result envelope is introduced.

Normalization classification: `PARTIAL`.

## 11. Session persistence

`--no-session-persistence` remained accepted and was used. DSH semantics do not
depend on session continuity. Durable disk behavior was not inspected and is
not part of the blocking command result.

Classification: `PARTIAL`.

## 12. Area classification

| Area | Classification | Evidence |
|---|---|---|
| exact command tool | PASS | local help and function calls identify `Bash` |
| dontAsk + explicit allow | PASS | Bash call reached execution layer without approval denial |
| repository-local command/test | ENVIRONMENT_BLOCKED | `spawn EPERM` before script execution |
| command-enabled workspace boundary | ENVIRONMENT_BLOCKED | no command process could be spawned |
| sandbox requirement | NOT VERIFIED | no sandbox adopted; Docker/Podman unavailable |
| descendant process behavior | ENVIRONMENT_BLOCKED | no child created/observable |
| future cleanup classification | ENVIRONMENT_BLOCKED | process-tree evidence unavailable |
| JSON result normalization | PARTIAL | session success coexisted with tool error |
| exit semantics | PARTIAL | spawn failure returned exit code 0 |
| session persistence | PARTIAL | flag accepted and used; disk effect unverified |

No native behavior is classified as `FAIL`; missing evidence and environment
restrictions are classified explicitly.

## 13. Gate and ownership sanity check

The native gate cannot advance to implementation design because the required
Read -> Edit -> repository-local command/test -> settled success sequence was
not executable, and the dependent workspace-boundary and descendant-cleanup
probes remain blocked.

No evidence requires changing:

- Controller;
- Executor;
- WorkspaceManager;
- CodexPlugin;
- the existing Plugin abstraction.

The current gap is local CodeBuddy/Windows process-spawn behavior. Any future
process-tree handling remains a CodeBuddyPlugin bounded mechanic if and only if
later native evidence establishes that it is needed.

Final verdict:

    ENVIRONMENT_BLOCKED

## 14. Files created or changed

Created:

- `collaboration/investigations/2026-09-07-codebuddy-noninteractive-bash-approval-verification.md`

Temporary disposable verification repository was removed after evidence
collection. No production code, existing tests, `PROJECT_STATE.md`, Runtime
abstraction, TaskKind, Planner, CodexPlugin, or CodeBuddyPlugin was changed.
