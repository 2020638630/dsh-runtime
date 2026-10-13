"""Small stdio MCP adapter for the existing one-shot Runtime entrypoint.

Only the MCP lifecycle, ping, tools/list, and tools/call methods are exposed.
Each accepted tool call starts exactly one ``dsh_runtime.entrypoint`` process;
the adapter adds no retries and stores only a privacy-limited lifecycle trace.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from dsh_runtime.call_trace import (
    append_call_trace,
    resolve_call_trace_path,
)
from dsh_runtime.json_stdio import iter_input_lines, write_json_line


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
_TASK_STATUSES = {
    "pending",
    "running",
    "completed",
    "failed",
    "timed_out",
    "max_iterations",
}


class _CallBoundaryFailure(Exception):
    def __init__(self, error_code: str, message: str, error_type: str | None = None):
        super().__init__(message)
        self.error_code = error_code
        self.error_type = error_type


def _required_text(field: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _decode_terminal_state(stdout: str) -> dict[str, Any]:
    records = [line for line in stdout.splitlines() if line.strip()]
    if len(records) != 1:
        raise _CallBoundaryFailure(
            "invalid_terminal_record_count",
            "DSH Runtime returned an invalid process response: expected one JSON record",
        )
    try:
        task_state = json.loads(records[0])
    except json.JSONDecodeError:
        raise _CallBoundaryFailure(
            "malformed_terminal_json",
            "DSH Runtime returned malformed terminal JSON",
            "JSONDecodeError",
        ) from None
    if not isinstance(task_state, dict):
        raise _CallBoundaryFailure(
            "terminal_response_not_object",
            "DSH Runtime returned a non-object terminal response",
        )
    return task_state


def _safe_diagnostic(stderr: str) -> str:
    diagnostic = _SECRET_PATTERN.sub(r"\1[REDACTED]", stderr.strip())
    return diagnostic[:2000]


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _captured_bytes(payload: object) -> bytes:
    if payload is None:
        return b""
    if not isinstance(payload, bytes):
        raise TypeError("Runtime subprocess output must be bytes")
    return payload


def _exception_type(exc: BaseException) -> str:
    name = type(exc).__name__
    return name if name.isidentifier() else "Exception"


def _append_started(path: Path, call_id: str) -> None:
    append_call_trace(
        path,
        {
            "schema_version": "1",
            "event": "call_started",
            "call_id": call_id,
            "timestamp": _timestamp(),
            "state": "started",
            "invocation_count": 1,
        },
    )


def _append_terminal(
    path: Path,
    *,
    call_id: str,
    started: float,
    state: str,
    returncode: int | None,
    stdout: bytes,
    stderr: bytes,
    task_status: str | None = None,
    result_sha256: str | None = None,
    error_code: str | None = None,
    error_type: str | None = None,
) -> None:
    try:
        append_call_trace(
            path,
            {
                "schema_version": "1",
                "event": "call_terminal",
                "call_id": call_id,
                "timestamp": _timestamp(),
                "state": state,
                "duration_ms": max(0, int((time.perf_counter() - started) * 1000)),
                "runtime_exit_code": returncode,
                "stdout_bytes": len(stdout),
                "stdout_sha256": _sha256(stdout),
                "stderr_bytes": len(stderr),
                "stderr_sha256": _sha256(stderr),
                "task_status": task_status,
                "result_sha256": result_sha256,
                "error_code": error_code,
                "error_type": error_type,
            },
        )
    except Exception:
        raise RuntimeError(
            f"DSH Runtime call {call_id} has no durable terminal trace; reconcile its outcome"
        ) from None


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
    request_bytes = json.dumps(
        request, ensure_ascii=True, separators=(",", ":")
    ).encode("ascii")
    call_id = str(uuid4())
    started = time.perf_counter()
    try:
        trace_path = resolve_call_trace_path()
        _append_started(trace_path, call_id)
    except Exception:
        raise RuntimeError(
            f"DSH Runtime call {call_id} has no durable start trace; Runtime was not invoked"
        ) from None

    try:
        completed = subprocess.run(
            [sys.executable, "-m", "dsh_runtime.entrypoint"],
            cwd=_RUNTIME_ROOT,
            input=request_bytes,
            capture_output=True,
            check=False,
        )
    except Exception as exc:
        _append_terminal(
            trace_path,
            call_id=call_id,
            started=started,
            state="transport_error",
            returncode=None,
            stdout=b"",
            stderr=b"",
            error_code="process_boundary_exception",
            error_type=_exception_type(exc),
        )
        raise RuntimeError(
            f"DSH Runtime process boundary failed ({call_id})"
        ) from None

    try:
        stdout_bytes = _captured_bytes(completed.stdout)
        stderr_bytes = _captured_bytes(completed.stderr)
    except Exception as exc:
        _append_terminal(
            trace_path,
            call_id=call_id,
            started=started,
            state="transport_error",
            returncode=completed.returncode,
            stdout=b"",
            stderr=b"",
            error_code="invalid_process_output_type",
            error_type=_exception_type(exc),
        )
        raise RuntimeError(
            f"DSH Runtime returned an invalid process output type ({call_id})"
        ) from None

    failure: _CallBoundaryFailure | None = None
    stdout = ""
    stderr = ""
    try:
        stdout = stdout_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        failure = _CallBoundaryFailure(
            "stdout_invalid_utf8",
            "DSH Runtime stdout is not valid UTF-8",
            "UnicodeDecodeError",
        )
    if failure is None:
        try:
            stderr = stderr_bytes.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            failure = _CallBoundaryFailure(
                "stderr_invalid_utf8",
                "DSH Runtime stderr is not valid UTF-8",
                "UnicodeDecodeError",
            )

    if failure is None and completed.returncode != 0:
        diagnostic = _safe_diagnostic(stderr)
        suffix = f": {diagnostic}" if diagnostic else ""
        failure = _CallBoundaryFailure(
            "nonzero_exit",
            f"DSH Runtime process failed with exit code {completed.returncode}{suffix}",
        )
    elif failure is None and stderr.strip():
        failure = _CallBoundaryFailure(
            "unexpected_stderr",
            "DSH Runtime returned unexpected stderr despite a successful process exit",
        )

    task_state: dict[str, Any] | None = None
    result_sha256: str | None = None
    if failure is None:
        try:
            task_state = _decode_terminal_state(stdout)
            canonical_result = json.dumps(
                task_state,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii")
            result_sha256 = _sha256(canonical_result)
        except _CallBoundaryFailure as exc:
            failure = exc
        except Exception as exc:
            failure = _CallBoundaryFailure(
                "adapter_processing_exception",
                "DSH Runtime response could not be processed",
                _exception_type(exc),
            )

    if failure is not None:
        state = (
            "process_error"
            if failure.error_code == "nonzero_exit"
            else "transport_error"
        )
        _append_terminal(
            trace_path,
            call_id=call_id,
            started=started,
            state=state,
            returncode=completed.returncode,
            stdout=stdout_bytes,
            stderr=stderr_bytes,
            error_code=failure.error_code,
            error_type=failure.error_type,
        )
        raise RuntimeError(f"{failure} (call_id={call_id})") from None

    assert task_state is not None
    task_status = task_state.get("status")
    if not isinstance(task_status, str) or task_status not in _TASK_STATUSES:
        task_status = None
    _append_terminal(
        trace_path,
        call_id=call_id,
        started=started,
        state="returned",
        returncode=completed.returncode,
        stdout=stdout_bytes,
        stderr=stderr_bytes,
        task_status=task_status,
        result_sha256=result_sha256,
    )
    return task_state


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
    for raw_line in iter_input_lines(sys.stdin):
        try:
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
            if not line.strip():
                continue
            message = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            response = MCPServer._error(None, -32700, "Parse error")
        else:
            response = server.handle(message)
        if response is not None:
            write_json_line(sys.stdout, response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
