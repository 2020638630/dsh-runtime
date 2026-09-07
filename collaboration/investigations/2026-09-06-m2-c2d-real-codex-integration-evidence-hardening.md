# Milestone 2-C.2d — Real Codex Integration Evidence Hardening

Date: 2026-09-06  
Verdict: `ENVIRONMENT_BLOCKED`

## 1. Scope

This investigation attempted to extend the deterministic Codex-backed capability evidence to the real local Codex executable. The Runtime contracts and ownership decisions from 2-C.2c were preserved. No new framework or lifecycle abstraction was introduced.

## 2. Environment

- OS: Windows 10 build 22631
- Codex executable: `C:\Users\Administrator\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe`
- Codex version: `codex-cli 0.153.0`
- Node: `v20.14.0`
- Repository cwd: `D:\PythonProject\dsh-runtime`
- Real attempts used disposable `CODEX_HOME` directories under `%TEMP%`.
- Authority under test: `allow_workspace_write=False`, mapped by `CodexPlugin` to `approvalPolicy=never`; the native response reported a read-only sandbox.
- Investigation deadline: 45 seconds for the Plugin smoke; 12 seconds for the direct protocol diagnosis after `turn/start`.

No credentials, raw reasoning, raw JSON-RPC, or raw stderr was added to Runtime results or normal logs.

## 3. Existing proven boundary

The real process reached:

```text
DSHController -> Executor -> CodexPlugin
  -> codex app-server --stdio
  -> initialize
  -> thread/start(ephemeral=true, cwd propagated)
  -> turn/start
```

The deterministic path additionally proves final answer parsing, bounded `PluginResult`, authority mapping, timeout cleanup, cancellation cleanup, and safe diagnostics.

## 4. Real successful-turn attempt

The bounded real invocation returned:

```text
success=false
stop_reason=timed_out
error=plugin execution timed out
cleanup_error=null
duration_ms=45021
```

The direct sanitized protocol diagnosis observed:

```text
initialize response
thread/start response: ephemeral=true, cwd=D:\PythonProject\dsh-runtime
turn/start response: status=inProgress
remoteControl/status/changed
thread/started
thread/status/changed
turn/started
item/started
no turn/completed within the 12-second diagnostic window
```

Therefore this environment does not prove a real model final answer or `PluginResult(success=True)`. Executor timeout governance and process cleanup did complete.

## 5. 45-second timeout diagnosis

The real app-server stderr (reviewed only in the investigation process) reported bounded warnings for unavailable network requests to the featured-plugin backend and GitHub plugin synchronization, plus the expected PowerShell shell-snapshot warning and native-root-certificate warning. The service/model turn did not progress to terminal completion.

The evidence supports:

```text
Runtime protocol startup: proven
Codex executable: proven
ephemeral thread and cwd: proven
model/service completion: unavailable in this environment
```

The evidence does not distinguish account authentication from service/network policy with certainty. It is therefore classified as external environment/service unavailability, not a Runtime failure.

## 6. Real read-only evidence

A real read-only turn was attempted with a disposable `CODEX_HOME` and workspace. The invocation stalled before any tool or file-change item was emitted and settled at the bounded deadline. The marker workspace remained unchanged, but this is only pre-tool side-effect evidence; it is not proof of native denial for a requested write.

Authoritative native read-only behavior remains unknown because no real file-change request was reached.

## 7. Workspace-write evidence

A real workspace-write model turn was not allowed to proceed beyond the same pre-tool service boundary. No write side effect occurred. This does not prove or disprove native `workspace-write` behavior.

## 8. Authority escalation evidence

Deterministic stub evidence proves that a Plugin parameter such as `allow_workspace_write=False` cannot override the DSH-owned `ExecutionContext` authority. The real native mapping is visible in the real `thread/start` response as a read-only sandbox for the false case, but a real write request was not reached. No `danger-full-access` or bypass mode was used.

## 9. Cancellation / interrupt evidence

Real timeout settlement was observed. `CodexPlugin` attempted its best-effort `turn/interrupt`, then closed stdin and terminated the process tree; Executor returned `TIMED_OUT` after settlement. The run did not produce a terminal `turn/completed`, so interrupt acknowledgement and Codex-side cancellation semantics remain unknown.

Deterministic tests separately prove cancellation propagation, interrupt-attempt behavior, forced cleanup fallback, and quiescence observation.

## 10. Windows process-tree evidence

The deterministic process-backed tests prove parent process exit observation and cleanup within the tested helper boundary. The real Codex run confirmed bounded process cleanup for the Codex parent. A real Codex descendant-process tree was not observable after the service stall; universal Windows tree correctness is not claimed.

## 11. Popen / asyncio.to_thread settlement evidence

The real invocation settled without a reported cleanup error after the 45-second timeout. Deterministic tests cover the `Popen`/blocking-pipe path, timeout cancellation, process exit observation, and no indefinite invocation-owned worker in the tested lifecycle. The attempted standalone `asyncio.create_subprocess_exec` diagnostic hit Windows `PermissionError: [WinError 5]`; this was a diagnostic harness limitation and was not used to modify production code.

## 12. Timeout/completion race evidence

Deterministic semantic-hardening tests prove:

- Executor owns `TIMED_OUT` and a Plugin cannot forge it on success or ordinary failure.
- Failure text containing “timeout” is not classified as a Runtime timeout.
- Timeout results are returned only after Plugin cleanup settlement.
- Late Plugin completion cannot replace an already committed Runtime timeout.

No real completion-vs-deadline race was possible because the real turn never completed.

## 13. Production fixes

No production fix was required by the real evidence. Existing owners remain appropriate:

- Executor owns timeout/cancellation governance.
- CodexPlugin owns Codex protocol, process, interrupt, and cleanup mechanics.
- DSH owns logical workspace identity and authority intent.

One deterministic test assertion was corrected from an exact `30ms` wall-clock lower bound to a stable `20ms` lower bound. The probe still sleeps for `30ms`; the correction removes timer-resolution flakiness while preserving the tested invariant that settlement exceeds the `5ms` deadline.

## 14. Safe-diagnostic review

Real diagnostics were kept outside `PluginResult` and normal Runtime logs. The bounded result exposed only `success`, `error`, `stop_reason`, and `cleanup_error`. No thread ID, turn ID, raw protocol, stderr, reasoning, tool stream, PID, exit code, or signal was promoted to the generic result boundary.

## 15. Evidence matrix

| Capability | Deterministic evidence | Real local Codex evidence |
|---|---|---|
| executable startup | proven | proven |
| initialize | proven | proven |
| ephemeral thread | proven | proven |
| cwd propagation | proven | proven |
| successful model turn | stub only | not reached |
| final answer extraction | stub only | not reached |
| read-only native denial | parameter mapping only | not reached |
| workspace-write side effect | parameter mapping only | not reached |
| timeout ownership | proven | proven |
| cancellation cleanup | proven | bounded settlement observed |
| interrupt acknowledgement | stub/attempt only | unknown |
| descendant process tree | controlled helper only | unknown |
| safe bounded result | proven | proven for timeout |

## 16. Full regression

```text
.venv\\Scripts\\python.exe -m pytest -q
33 passed in 0.98s
```

## 17. Remaining unknowns

- Real account/authentication state versus service/network policy.
- Real model availability and terminal answer delivery.
- Native read-only denial for an actual requested file change.
- Native workspace-write side effect in a disposable workspace.
- Real interrupt acknowledgement and descendant process-tree behavior.
- Real completion/deadline race.

## 18. Final verdict

`ENVIRONMENT_BLOCKED`.

The Runtime/Codex integration reaches the expected real protocol boundary and settles bounded timeout cleanup correctly. The local service/network environment prevents the model turn from reaching `turn/completed`, so the milestone cannot honestly be classified as `PASS`. No required Runtime invariant was concretely violated, so this is not `FAIL`.

## 19. Architecture implications

The evidence reinforces the existing decisions:

```text
Plugin.execute() remains sufficient.
Executor remains the timeout/cancellation owner.
CodexPlugin owns Codex-specific mechanics.
ExecutionHandle and ProcessManager remain unjustified.
Process lifecycle remains an optional execution fact.
workspace_id remains logical identity.
Authority is decided by DSH and mapped by CodexPlugin.
```

## 20. Next recommendation

Keep the current bounded implementation and retry the real evidence only when the local Codex account/service/network path can complete a minimal model turn. At that point, rerun the read-only and workspace-write disposable tests before considering `PASS`; do not redesign Runtime around the current environment block.
