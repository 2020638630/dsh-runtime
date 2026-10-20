# Official Harness tool admission probe

This is a nonproduction fixture for the public `@deepseek-ai/dsh@0.2.1-rc.2` Host. It does not launch DSH Runtime, evaluate governance, inspect a repository, or claim that a real Runtime call is safe. Keep it in an isolated `DSH_HOME`.

The package is installed through `dsh plugin --profile web add <tarball>`. It registers a `dsh_runtime_admission_probe` tool with an explicit `task_kind` enum. Its authenticated route `/api/dsh-runtime-tool-probe` runs three model-free negative checks through the official tool registry: no calling agent, invalid task type, and an already aborted signal. All three must reject. The probe tool returns `{ admitted: true }` only when the Host supplies a caller agent; that result is a fixture sentinel, **not** a governance decision.

The 2026-10-20 acceptance used the public npm package in a separate consumer directory and obtained:

```json
{"registered":true,"hasTaskKind":true,"noAgentRejected":true,"invalidTaskKindRejected":true,"preAbortedRejected":true}
```

Uninstall returned the isolated Profile to the preinstall configuration. The next test must verify a real parent agent/session identity in the official Host, then put a fail-closed Python governance decision before any Runtime process start. Never use this fixture in a daily Profile.
