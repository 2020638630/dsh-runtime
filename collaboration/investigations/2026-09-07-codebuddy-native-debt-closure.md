# CodeBuddy Native Contract Debt Closure

Date: 2026-09-07
Scope: repository-local command execution, workspace boundary, process cleanup,
and minimum settled-result normalization
Implementation: none

## 1. Executive conclusion

The installed CodeBuddy CLI has the correct native command tool name, `Bash`,
but the current non-interactive environment does not provide a safe approval
path for Bash execution. File editing works, while the required repository
local test command is denied before execution.

The requested v1 capability therefore remains unproven:

    read -> edit -> repository-local command/test -> settled result

No dangerous permission bypass was used. No sandbox was adopted. The
CodeBuddy native gate is not ready to advance to implementation design.

Final verdict:

    PARTIALLY READY – SPECIFIC NATIVE DEBT REMAINS

This artifact does not reopen Milestones 2, 3, or 4, declare Milestone 5,
modify Runtime production code, modify existing tests, update
`PROJECT_STATE.md`, or implement CodeBuddyPlugin.

## 2. Safety boundary and fixture

All new probes used only this disposable repository:

    D:\PythonProject\dsh-runtime\.tmp-codebuddy-native-debt\repo

The fixture contained:

- `marker.txt`, initially containing `before-command`;
- `check_local.py`, which asserts that the marker is `after-command`, writes
  `command-observed.txt`, and prints `LOCAL_TEST_OK`;
- a disposable Git metadata directory;
- a temporary settings file used for an exact permission-rule probe.

No DSH Runtime file was used as CodeBuddy's cwd. No unrelated parent directory
was granted with `--add-dir`. No `--sandbox` and no
`--dangerously-skip-permissions` were used.

## 3. Native command tool mapping

The installed `codebuddy.cmd --help` output identifies the built-in command
tool as `Bash`; its examples include `Bash,Edit,Read` and scoped forms such as
`Bash(git:*)`. The relevant candidate mapping was:

    --print
    --output-format text
    --input-format text
    --max-turns 5
    --no-session-persistence
    --tools Read,Edit,Bash
    --permission-mode acceptEdits

This is the smallest mapping that exposes read, edit, and command tools without
using a dangerous bypass. `--permission-mode acceptEdits` only auto-permitted
the file edit. Bash still required an approval unavailable in non-interactive
mode.

Observed with the mapping above:

- `marker.txt` was successfully edited;
- `python check_local.py` was not executed;
- CodeBuddy reported that Bash permission was required and unavailable;
- `command-observed.txt` was not created;
- the process nevertheless returned exit code `0`.

The same behavior occurred with `--permission-mode auto`. A CLI
`--allowedTools` probe using `Bash(python check_local.py)` and
`Bash(python:*)` did not produce a non-interactive Bash approval. A disposable
`permissions.allow` settings probe also did not produce one. None of these
probes used `bypassPermissions`.

Command mapping classification: `ENVIRONMENT_BLOCKED`.

The native product surface is identified, but this environment cannot supply
the approval needed to verify its command execution semantics safely.

## 4. Edit plus repository-local test evidence

Requested workflow:

    read marker.txt and check_local.py
    edit marker.txt: before-command -> after-command
    run exactly: python check_local.py
    reply: REPO_EDIT_TEST_OK on success

Observed result under `acceptEdits` + `Read,Edit,Bash`:

    edit: PASS
    command: blocked before execution
    test output: absent
    command-observed.txt: absent
    final CodeBuddy output: permission denial explanation
    process exit code: 0

The edit succeeded in the exact supplied cwd, but the full desired sequence is
not proven. The required local test was not run, so this area is
`ENVIRONMENT_BLOCKED`, not `FAIL`.

## 5. Workspace boundary

The prior artifact proved that file-only access outside cwd was denied by the
non-interactive approval system, but CodeBuddy explicitly said this did not
necessarily establish a hard path boundary.

The new command-enabled boundary probe could not proceed because Bash itself
was blocked before any command could run. Consequently, the following are not
proved for the command-capable configuration:

- outside-cwd sentinel read denial;
- outside-cwd sentinel write denial;
- absolute-path confinement;
- prevention of a command from leaving the resolved cwd.

Classification for command-enabled boundary: `ENVIRONMENT_BLOCKED`.

The native boundary classification supported by all available evidence is:

    APPROVAL-BASED DENIAL / TOOL-PERMISSION RESTRICTION

It is not `HARD NATIVE CONFINEMENT`, `SANDBOX CONFINEMENT`, or a proven
cwd-only filesystem jail. A future v1 mapping must not describe approval
denial as hard isolation.

## 6. Sandbox assessment

Sandbox was not adopted. The installed CLI documents `--sandbox` as a separate
container or E2B execution mode. Local `docker` and `podman` executables were
not available, so a container probe was not possible.

There is no evidence that sandbox is required to make the CLI invoke. Direct
same-cwd mutation already works without it. A sandbox would need separate
proof of physical workspace identity and result export; otherwise it breaks or
complicates the required handoff:

    CodeBuddy writes cwd X -> Codex reads cwd X

Sandbox requirement: `NOT VERIFIED`; no adoption decision is made from this
task. The current result is insufficient to replace the same-cwd contract with
a sandbox/worktree contract.

## 7. Descendant process and timeout behavior

The new Bash command could not be started, so a CodeBuddy-owned controlled
child process could not be created. OS-native process relationship inspection
was also denied in the prior top-level termination probe.

Already proven and preserved from the previous artifact:

- a print-mode process can remain alive while waiting for input;
- the top-level CLI process can be externally terminated;
- complete descendant survival/cleanup was not established.

New child-process evidence:

    parent PID: not usable for this task's command-enabled probe
    child PID: not observed
    post-termination survivor state: not observable

Classification: `ENVIRONMENT_BLOCKED`.

The required future contract cannot yet be classified as top-level termination
sufficient or process-tree termination required from native evidence.

## 8. Future cleanup classification

    ENVIRONMENT_BLOCKED

There is no print-mode native interrupt command in the installed CLI help. The
existing top-level termination evidence is not enough to prove descendant
cleanup. This remains a CodeBuddy-specific bounded lifecycle question, not
evidence for a generic `ProcessManager`, `ExecutionHandle`, or Executor
redesign.

If later native evidence shows descendants survive, the first ownership
hypothesis remains:

    CodeBuddyPlugin bounded internal process-tree mechanics

No generic process owner is justified by the current evidence.

## 9. Minimum settled-result normalization

The smallest evidence-backed rule is deliberately narrower than the complete
event schema:

1. In JSON mode, parse the top-level event sequence and select the final event
   whose type is `result`.
2. Treat the invocation as native success only when that result has
   `subtype=success`, `is_error=false`, and usable final result text.
3. Normalize that final text to `PluginResult.output`; native error is empty.
4. If no successful final result exists, normalize the captured native error
   text to `PluginResult.error` and mark the invocation unsuccessful.
5. Do not use process exit code alone: the invalid-model failure and the
   max-turn exhaustion both returned exit code `0`.
6. For an observed `Max turns (N) exceeded` bound, the safest existing Runtime
   mapping is an unsuccessful `PluginResult` with `StopReason.FAILED` and the
   bound diagnostic as `error`. It must not be treated as successful task
   completion. Outer DSH timeout remains distinct and is governed by the
   existing `StopReason.TIMED_OUT` path.

Evidence:

    success JSON:
      top-level array
      final result event: subtype=success, is_error=false
      result text present

    max-turn exhaustion:
      stderr/text: Max turns (1) exceeded
      no successful result event
      exit code: 0

    native/service failure:
      invalid model error on stderr
      no successful result event
      exit code: 0

Classification: `PARTIAL`.

This rule is sufficient to distinguish successful settlement from the two
observed failure classes without introducing a new result DTO. The exact
stable error schema and all stream-json event variants remain unverified.

## 10. Session persistence

`--no-session-persistence` remained accepted and was used in every new probe.
The task does not depend on session continuity. No SessionManager is proposed.

Durable disk behavior was not inspected. This remains a benign native detail
unless later evidence shows cross-task semantic leakage.

Classification: `PARTIAL`.

## 11. Area classification

| Area | Classification | Evidence |
|---|---|---|
| command tool name | PASS | installed help identifies `Bash` |
| safe Read/Edit/Bash mapping | ENVIRONMENT_BLOCKED | Bash approval unavailable non-interactively |
| edit + repo-local test | ENVIRONMENT_BLOCKED | edit passed; test never ran |
| command-enabled workspace boundary | ENVIRONMENT_BLOCKED | Bash blocked before boundary probe |
| sandbox requirement | NOT VERIFIED | sandbox not required for known direct-cwd edit; alternate path unavailable |
| descendant process behavior | ENVIRONMENT_BLOCKED | child command could not run; process inspection denied |
| future cleanup classification | ENVIRONMENT_BLOCKED | top-level termination known, tree cleanup unknown |
| successful result normalization | PARTIAL | final JSON result event observed previously |
| max-turn normalization | PARTIAL | bound diagnostic observed; exit code remained 0 |
| native/service failure normalization | PARTIAL | stderr failure observed; exit code remained 0 |
| session persistence | PARTIAL | flag accepted and used; durable effect unverified |

No native behavior observed here contradicts the desired v1 contract, so no
area is classified as `FAIL`. Missing evidence is classified as `PARTIAL`,
`NOT VERIFIED`, or `ENVIRONMENT_BLOCKED`.

## 12. Gate and ownership sanity check

The core gate is not satisfied because repository-local command/test execution,
command-enabled boundary behavior, and descendant cleanup are not proven.

No new evidence requires changing:

- Controller;
- Executor;
- WorkspaceManager;
- CodexPlugin;
- the existing Plugin abstraction.

The observed gap is native CodeBuddy permission/process behavior. If later
resolved, any process-tree handling should first be treated as bounded
CodeBuddyPlugin mechanics, not a generic Runtime owner.

Final verdict:

    PARTIALLY READY – SPECIFIC NATIVE DEBT REMAINS

## 13. Files created or changed

Created:

- `collaboration/investigations/2026-09-07-codebuddy-native-debt-closure.md`

Temporary verification files were removed after evidence collection. No
production code, existing test, `PROJECT_STATE.md`, Runtime abstraction,
TaskKind, Planner, CodexPlugin, or CodeBuddyPlugin was changed.
