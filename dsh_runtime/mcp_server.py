"""Small stdio MCP adapter for the existing one-shot Runtime entrypoint.

Only the MCP lifecycle, ping, tools/list, and tools/call methods are exposed.
Each accepted tool call starts exactly one ``dsh_runtime.entrypoint`` process;
the adapter adds no retries and stores no request or result data.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


_RUNTIME_ROOT = Path(__file__).resolve().parents[1]
_PROTOCOL_VERSION = "2025-06-18"
_SUPPORTED_PROTOCOL_VERSIONS = {
    "2024-11-05",
    "2025-03-26",
    _PROTOCOL_VERSION,
}
_TOOL_NAME = "dsh_runtime"
_TASK_KIND = "repository_change"
_TOOL_DESCRIPTION = (
    "Run one explicitly authorized DSH-Runtime repository-change task. "
    "This write-capable tool invokes the existing Runtime exactly once, never "
    "retries, and returns the terminal TaskState JSON. Use only when the user "
    "authorized a repository change."
)
_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "goal": {
            "type": "string",
            "minLength": 1,
            "description": "The user-requested repository change.",
        },
        "workspace_id": {
            "type": "string",
            "minLength": 1,
            "description": "The Runtime workspace identifier.",
        },
        "workspace_path": {
            "type": "string",
            "minLength": 1,
            "description": "The explicit path to the target workspace.",
        },
        "task_kind": {
            "type": "string",
            "enum": [_TASK_KIND],
            "description": "Only repository_change is enabled by this adapter.",
        },
    },
    "required": ["goal", "workspace_id", "workspace_path", "task_kind"],
    "additionalProperties": False,
}
_TOOL_DEFINITION = {
    "name": _TOOL_NAME,
    "title": "DSH Runtime repository change",
    "description": _TOOL_DESCRIPTION,
    "inputSchema": _INPUT_SCHEMA,
}
_SECRET_PATTERN = re.compile(
    r"(?i)(authorization\s*[:=]\s*bearer\s+|"
    r"(?:api[_-]?key|access[_-]?token|secret|password)\s*[:=]\s*)"
    r"([^\s,;\"']+)"
)


def _required_text(field: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _decode_terminal_state(stdout: str) -> dict[str, Any]:
    records = [line for line in stdout.splitlines() if line.strip()]
    if len(records) != 1:
        raise RuntimeError(
            "DSH Runtime returned an invalid process response: expected one JSON record"
        )
    try:
        task_state = json.loads(records[0])
    except json.JSONDecodeError as exc:
        raise RuntimeError("DSH Runtime returned malformed terminal JSON") from exc
    if not isinstance(task_state, dict):
        raise RuntimeError("DSH Runtime returned a non-object terminal response")
    return task_state


def _safe_diagnostic(stderr: str) -> str:
    diagnostic = _SECRET_PATTERN.sub(r"\1[REDACTED]", stderr.strip())
    return diagnostic[:2000]


def dsh_runtime(arguments: object) -> dict[str, Any]:
    """Validate one tool call and return its terminal Runtime TaskState."""

    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object")
    expected_fields = {"goal", "workspace_id", "workspace_path", "task_kind"}
    if set(arguments) != expected_fields:
        raise ValueError("arguments must contain exactly the four documented fields")

    goal = _required_text("goal", arguments.get("goal"))
    workspace_id = _required_text("workspace_id", arguments.get("workspace_id"))
    workspace_path = _required_text("workspace_path", arguments.get("workspace_path"))
    task_kind = arguments.get("task_kind")
    if task_kind != _TASK_KIND:
        raise ValueError("task_kind must be repository_change")

    request = {
        "goal": goal,
        "workspace_id": workspace_id,
        "workspace_path": workspace_path,
        "task_kind": _TASK_KIND,
    }
    completed = subprocess.run(
        [sys.executable, "-m", "dsh_runtime.entrypoint"],
        cwd=_RUNTIME_ROOT,
        input=json.dumps(request, ensure_ascii=False, separators=(",", ":")),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        diagnostic = _safe_diagnostic(completed.stderr)
        suffix = f": {diagnostic}" if diagnostic else ""
        raise RuntimeError(
            f"DSH Runtime process failed with exit code {completed.returncode}{suffix}"
        )
    if completed.stderr.strip():
        raise RuntimeError(
            "DSH Runtime returned unexpected stderr despite a successful process exit"
        )
    return _decode_terminal_state(completed.stdout)


class MCPServer:
    """Implements the stdio MCP subset required by the Codex adapter."""

    def __init__(self) -> None:
        self._initialized = False

    def handle(self, message: object) -> dict[str, Any] | None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return self._error(None, -32600, "Invalid Request")

        method = message.get("method")
        if not isinstance(method, str):
            return self._error(message.get("id"), -32600, "Invalid Request")
        request_id = message.get("id")

        if method == "initialize":
            return self._initialize(request_id, message.get("params"))
        if request_id is None:
            if method == "notifications/initialized":
                self._initialized = True
            return None
        if method == "ping":
            return self._result(request_id, {})
        if not self._initialized:
            return self._error(request_id, -32002, "Server not initialized")
        if method == "tools/list":
            return self._result(request_id, {"tools": [_TOOL_DEFINITION]})
        if method == "tools/call":
            return self._call_tool(request_id, message.get("params"))
        return self._error(request_id, -32601, f"Method not found: {method}")

    def _initialize(self, request_id: object, params: object) -> dict[str, Any]:
        if request_id is None or not isinstance(params, dict):
            return self._error(request_id, -32602, "Invalid initialize parameters")
        requested_version = params.get("protocolVersion")
        if not isinstance(requested_version, str):
            return self._error(request_id, -32602, "protocolVersion is required")
        protocol_version = (
            requested_version
            if requested_version in _SUPPORTED_PROTOCOL_VERSIONS
            else _PROTOCOL_VERSION
        )
        return self._result(
            request_id,
            {
                "protocolVersion": protocol_version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "dsh_runtime", "version": "1.0.0"},
                "instructions": _TOOL_DESCRIPTION,
            },
        )

    def _call_tool(self, request_id: object, params: object) -> dict[str, Any]:
        if not isinstance(params, dict) or params.get("name") != _TOOL_NAME:
            return self._error(request_id, -32602, "Unknown tool or invalid parameters")
        try:
            task_state = dsh_runtime(params.get("arguments"))
        except Exception as exc:
            return self._result(
                request_id,
                {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
            )
        serialized = json.dumps(task_state, ensure_ascii=False, separators=(",", ":"))
        return self._result(
            request_id,
            {
                "content": [{"type": "text", "text": serialized}],
                "structuredContent": task_state,
                "isError": False,
            },
        )

    @staticmethod
    def _result(request_id: object, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: object, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }


def main() -> int:
    server = MCPServer()
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            response = MCPServer._error(None, -32700, "Parse error")
        else:
            response = server.handle(message)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
            sys.stdout.write("\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
