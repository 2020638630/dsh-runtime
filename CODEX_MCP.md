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
process per accepted call and never retries. A terminal TaskState, including a
settled `failed` status, is returned as structured tool data. Process or
transport failures are returned as tool errors. The adapter does not persist
the request or result, change Runtime authorization, or claim filesystem
confinement beyond the existing Runtime workspace boundary.

Use this tool only for an explicitly authorized repository change. When a
workflow requires this tool to be the first workspace-facing action, start a
fresh task with this project open and make the `dsh_runtime` call before using
other workspace tools. A settled non-success result ends that attempt; do not
retry or take over the repository change through another tool.
