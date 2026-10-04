# CodeBuddy Non-Interactive Bash Authorization Root-Cause Probe

Date: 2026-09-07
Scope: non-interactive Bash authorization root-cause evidence only
Implementation: none

## 1. Decision

    BASH AUTHORIZATION = PASS

A safe narrow non-interactive authorization path was proven in an ordinary
Windows host context against a disposable repository. The exact intended
command `python check_local.py` was emitted and executed successfully.

The broader native gate remains:

    PARTIALLY READY – SPECIFIC NATIVE DEBT REMAINS

This probe intentionally stops here. It does not investigate workspace
boundary or descendant cleanup, and it does not declare Milestone 5, create an
implementation plan, modify Runtime production code, modify existing tests,
update `PROJECT_STATE.md`, or create `CodeBuddyPlugin`.

## 2. Ordinary-host safety boundary

All CodeBuddy invocations used the disposable cwd:

    D:\PythonProject\dsh-runtime\.tmp-codebuddy-bash-auth-rootcause\repo

The fixture contained only `marker.txt`, `check_local.py`, and the generated
`command-observed.txt`. No real DSH Runtime path was used as CodeBuddy cwd.
No `-y`, `--dangerously-skip-permissions`, `bypassPermissions`, `--add-dir`,
or CLI sandbox was used. Temporary artifacts were removed after the probe.

## 3. Exact emitted Bash input

The clean successful probe's JSON event stream contained this exact Bash
function call input:

    {
      "command": "python check_local.py",
      "description": "Run local check script"
    }

The command was not rewritten to `cd`, `cmd /c`, PowerShell, an absolute
executable, or a compound command. The clean probe emitted no other Bash
call. Read and Edit were emitted separately through their respective tools.

## 4. Settings-only control

The disposable settings file contained:

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

The invocation used:

    --print
    --output-format json
    --input-format text
    --max-turns 6
    --no-session-persistence
    --tools Read,Edit,Bash
    --settings <disposable settings>
    --permission-mode dontAsk

Observed settings-only result:

    exact Bash input: python check_local.py
    Bash result: Command: python check_local.py
                 Stdout: LOCAL_TEST_OK
                 Stderr: (empty)
                 Exit Code: 0
                 Signal: (none)
    marker.txt: after-command
    command-observed.txt: LOCAL_TEST_OK
    process exit: 0
    final subtype: success
    final is_error: false
    permission_denials: []

The final session text stated that both operations succeeded and included the
requested success marker. Settings-only authorization therefore passed.

## 5. CLI allowedTools A/B

The equivalent probe retained the settings configuration and added the
process-level allow value:

    --allowedTools "Bash(python:*)"

To preserve the value as one command-line argument in PowerShell, the clean
run used the equivalent argv spelling:

    --allowedTools=Bash(python:*)

The clean prompt explicitly required Read for file inspection, Edit for the
marker change, and exactly one Bash call for `python check_local.py`.

Observed clean A/B result:

    emitted tools: Read marker.txt
                   Read check_local.py
                   Edit marker.txt
                   Bash {"command":"python check_local.py", ...}
    Bash result: Command: python check_local.py
                 Stdout: LOCAL_TEST_OK
                 Stderr: (empty)
                 Exit Code: 0
                 Signal: (none)
    marker.txt: after-command
    command-observed.txt: LOCAL_TEST_OK
    process exit: 0
    final subtype: success
    final is_error: false
    permission_denials: []

CLI allow A/B therefore passed for the intended command.

## 6. Root-cause classification

The earlier final-debt run that reported a Bash permission denial is not
reproducible with the same settings-only configuration in the ordinary host
context. This probe does not have evidence to assign that earlier transient
decision to a stable product defect.

One intermediate CLI attempt passed `--allowedTools` as a variadic option
followed by the prompt. It produced one empty, one-turn successful session,
no tool calls, and no filesystem effects. This was an invocation-argument
placement/parsing error in the probe harness, not a Bash authorization result.

A subsequent CLI run with the same allow value emitted an extra `ls -la`
call before the intended command. `ls -la` did not match `Bash(python:*)` and
was denied, while the exact intended `python check_local.py` call matched and
succeeded. The final clean run prevented that unrelated discovery call and
had no permission denial.

Narrowest supported conclusion:

    A. TOOL INPUT DID NOT MATCH ALLOW RULE
       applies to the extra `ls -la` call only.

    The intended `python check_local.py` input does match the rule and is
    authorized successfully by both settings-only and CLI-allow paths.

No evidence supports classifying this as filesystem confinement, spawn
failure, or a CodeBuddy product incompatibility.

## 7. Result-normalization confirmation

The successful result satisfies the frozen minimum rule:

    final session success
    AND all required function/tool results successful
    AND required filesystem/command effects occurred

The previous failure rule remains unchanged: any tool native error,
permission denial, spawn failure, unexecuted required operation, max-turn
exhaustion, or native/service failure must normalize as unsuccessful with the
best native diagnostic and `StopReason.FAILED`. Outer DSH timeout remains
`StopReason.TIMED_OUT`.

No event DTO, provider result, result envelope, or generic process owner is
introduced.

## 8. Remaining native debt

This probe does not close:

1. command-enabled workspace-boundary behavior;
2. outside-cwd and absolute-path confinement evidence;
3. descendant-process behavior and timeout cleanup classification;
4. stable full output/error schema and `--no-session-persistence` durable
   semantics, if required by the eventual product contract.

Those probes require a separate explicitly authorized task and are not run
here because the artifact instructed this investigation to stop after Bash
authorization was proven.

## 9. Ownership and scope

No evidence requires changing Controller, Executor, WorkspaceManager,
CodexPlugin, the existing Plugin abstraction, or Runtime ownership. The
resolved native fact is limited to the safe command authorization path:

    dontAsk
      + Read/Edit/Bash tool exposure
      + narrow Bash(python:*) allow
      + ordinary host context
      + disposable cwd

The CodeBuddy `spawn EPERM` investigation remains closed and was not reopened.
