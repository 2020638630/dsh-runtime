# Codex DSH-Runtime Tool

This project includes a local stdio MCP server that exposes one write-capable
tool named `dsh_runtime`. It delegates to the existing one-shot
`dsh_runtime.entrypoint` process boundary and accepts only
`task_kind="repository_change"`.

## Setup

The stdio server uses only the Python standard library. The trusted-project
configuration in `.codex/config.toml` starts it with the project virtual
environment. From this project directory, verify registration with:

```powershell
codex mcp list
```

The server is configured to ask for approval on every tool call and allows up
to 20 minutes for the existing Runtime workflow to settle. Reopen the Codex
task after changing MCP configuration or editing `dsh_runtime/mcp_server.py` or
`dsh_runtime/json_stdio.py`, so the stdio server starts with the current code.

## Call contract

The tool requires `goal`, `workspace_id`, `workspace_path`, and
`task_kind="repository_change"`. It starts exactly one Python entrypoint
process per accepted call and never retries internally. A terminal TaskState,
including a settled `failed` status, is returned as structured tool data.
Process or transport failures are returned as tool errors.

For reconciliation, each accepted call writes an append-only lifecycle trace
to `%LOCALAPPDATA%/DSH-Runtime/calls.jsonl` on Windows or
`$XDG_STATE_HOME/dsh-runtime/calls.jsonl` (falling back to
`~/.local/state/dsh-runtime/calls.jsonl`) elsewhere. Set the absolute
`DSH_RUNTIME_CALL_TRACE_PATH` environment variable to choose another path. The
adapter fsyncs a `call_started` record before starting Runtime and a terminal
record after observing its result. If the start record cannot be persisted,
Runtime is not invoked. A call left with only `call_started` has no observed
terminal result and still requires reconciliation.

Trace records contain a random call ID, timestamps, lifecycle state, process
exit code, output byte counts and SHA-256 hashes, terminal TaskState status,
and a bounded error code/type. They do not contain the goal, workspace ID or
path, prompts, credentials, stdout/stderr contents, or the terminal result
body. `result_sha256` hashes the canonical terminal TaskState JSON; the stream
hashes cover the exact captured stdout and stderr bytes. A terminal TaskState
with status `failed` remains a returned business result, distinct from a
process or transport error.

This trace does not change Runtime authorization or claim filesystem
confinement beyond the existing Runtime workspace boundary.

The one-process rule applies to each tool invocation; it does not define a
caller's authorization for a later invocation. D2 business work follows the
adopted bounded retry series for the exact authorized request: one direct
authorization can cover up to three reserved attempts, and every attempt uses
a new identity and passes the complete current gate chain. A gate failure
before reservation consumes no attempt. After reservation, another attempt is
permitted only after a settled failure or proven `NOT_INVOKED` result and a
documented repair; an ambiguous result requires read-only reconciliation. A
successful result or three reserved attempts closes that series. Other
workflows, including Preflight, retain their separate authorization rules.

Use this tool only for an explicitly authorized repository change. When a
workflow requires this tool to be the first workspace-facing action, start a
fresh task with this project open and make the `dsh_runtime` call before using
other workspace tools. A settled non-success result ends that invocation; do
not replay the same identity or take over the repository change through
another tool. A later invocation is allowed only when the applicable workflow
authorization and its evidence gates permit it.
