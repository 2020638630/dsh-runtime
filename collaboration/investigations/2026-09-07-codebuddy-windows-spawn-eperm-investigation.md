# CodeBuddy Windows Bash `spawn EPERM` Root-Cause Investigation

Date: 2026-09-07
Status: Complete
Scope: Native execution environment/root-cause verification only

## Baseline

This investigation continues from
`2026-09-07-codebuddy-noninteractive-bash-approval-verification.md`.
That baseline had already established all of the following:

- CodeBuddy CLI 2.143.0 could authenticate and operate non-interactively.
- `dontAsk` plus an explicit `Bash(...)` allow rule admitted the requested tool call.
- CodeBuddy emitted the expected Bash function call.
- Native execution then failed with `Error: spawn EPERM`, including CodeBuddy's
  internal retry with `dangerouslyDisableSandbox: true`.
- A top-level CLI exit code of 0 and `result.subtype = success` did not override
  the native failure carried by the Bash function result.

No production code, existing tests, `PROJECT_STATE.md`, Runtime ownership, or
milestone state was changed during this investigation. All command probes ran
from a disposable repository at
`D:\PythonProject\dsh-runtime\.tmp-codebuddy-windows-spawn-eperm\repo`.

## Evidence

### 1. Ordinary host process control

From PowerShell in the disposable repository, `python check_local.py` and the
absolute Python executable both completed with exit code 0, printed
`LOCAL_TEST_OK`, and produced the expected local observation file. The resolved
interpreter was:

```text
C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe
Python 3.12.2
```

This ruled out a missing Python executable and a general inability of
PowerShell to start Python.

### 2. CodeBuddy Bash failure inside the managed execution sandbox

With only Bash exposed, `dontAsk`, and the explicit allow rule
`Bash(echo:*)`, CodeBuddy emitted:

```text
Bash {"command":"echo CB_NATIVE_OK"}
```

The function result was:

```text
Error: spawn EPERM
```

An absolute-Python Bash command was admitted by its explicit allow rule and
failed at the same point with the same `spawn EPERM`. No expected observation
file was created. Therefore the failure was not PATH lookup or Python-specific.

### 3. Windows shell resolution

The available shell paths were:

```text
C:\Windows\System32\bash.exe
C:\Program Files\Git\bin\bash.exe
C:\Program Files\Git\usr\bin\bash.exe
```

CodeBuddy's installed type declarations state that its Windows Bash tool uses
Git Bash and is disabled when Git Bash cannot be found. Git Bash was present,
and its executable ACL granted normal read-and-execute access to Users.

Inside the managed sandbox, direct Git Bash initialization reported:

```text
fatal error - couldn't create signal pipe, Win32 error 5
```

Node's `child_process.spawn()` of Git Bash failed synchronously with the same
`spawn EPERM` shape seen by CodeBuddy.

### 4. Generic Node spawn control

A Node control probe attempted three unrelated child processes from the same
temporary working directory:

- `cmd.exe /d /c echo NODE_CMD_OK`
- absolute Python with `--version`
- a child instance of the current Node executable

Inside the managed sandbox, all three failed synchronously:

```text
{"name":"cmd","phase":"spawn-throw","message":"spawn EPERM","code":"EPERM"}
{"name":"python","phase":"spawn-throw","message":"spawn EPERM","code":"EPERM"}
{"name":"node","phase":"spawn-throw","message":"spawn EPERM","code":"EPERM"}
```

The identical probe outside the managed sandbox succeeded for every child:

```text
NODE_CMD_OK
Python 3.12.2
NODE_CHILD_OK
```

Node also spawned Git Bash successfully outside the managed sandbox; Git Bash
printed `NODE_GIT_BASH_OK` and exited with code 0.

This A/B comparison identifies the failing boundary: the managed execution
sandbox used to launch the earlier verification prohibited Node child-process
creation. It was not a machine-wide Windows policy and was not specific to
Git Bash, Python, executable discovery, or CodeBuddy.

### 5. CodeBuddy end-to-end control outside the managed sandbox

The original semantic contract was repeated outside the managed sandbox, still
using all safety constraints:

```text
--print
--tools Bash
--allowedTools Bash(echo:*)
--permission-mode dontAsk
--no-session-persistence
```

No `-y`, `--dangerously-skip-permissions`, `bypassPermissions`, `--add-dir`, or
CLI sandbox option was used. CodeBuddy invoked Bash exactly once:

```text
Command: echo CB_NATIVE_OUTSIDE_SANDBOX_OK
Stdout: CB_NATIVE_OUTSIDE_SANDBOX_OK
Stderr: (empty)
Exit Code: 0
Signal: (none)
```

The function result contained native success evidence and CodeBuddy's final
result was also successful. This closes the original `spawn EPERM` blocker for
an ordinary host execution context.

## Interpretation of `dangerouslyDisableSandbox`

CodeBuddy's Bash documentation describes `dangerouslyDisableSandbox` as an
internal Bash-tool escape hatch that returns the command to CodeBuddy's normal
permission flow. On Windows, CodeBuddy's own Bash sandbox is not the active
Linux/macOS sandbox implementation. The earlier retry could not bypass the
outer managed execution sandbox that had launched the CodeBuddy process, so its
second `spawn EPERM` was expected and did not implicate CodeBuddy's permission
matcher.

## Result normalization

The prior normalization rule remains mandatory:

- CLI exit code 0 is transport/session completion only.
- `result.subtype = success` and `is_error = false` are not sufficient proof of
  native command success.
- A verifier must inspect the Bash `function_call_result`, including native
  stdout, stderr, exit code, signal, and error fields.

The successful outside-sandbox probe satisfies both levels: the Bash function
result reports exit code 0 with the expected stdout, and the final session
result is successful.

## Ownership and open questions

Runtime ownership remains unchanged. CodeBuddy still owns its CLI/tool
invocation and native Bash result; Planner owns planning semantics; the Codex
verifier owns independent read-only normalization and verification. This
investigation neither creates nor specifies a `CodeBuddyPlugin`.

The native spawn blocker itself has no remaining product-contract question.
The broader CodeBuddy-to-Planner-to-Codex product contract remains deferred to
an explicit future decision and is outside this investigation.

## Final verdict

SPAWN BLOCKER RESOLVED
