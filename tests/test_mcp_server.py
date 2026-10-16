from __future__ import annotations

import hashlib
import io
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from dsh_runtime import mcp_server
from dsh_runtime.call_trace import (
    CALL_TRACE_PATH_ENV,
    CallTraceError,
    append_call_trace,
)


@pytest.fixture(autouse=True)
def _isolated_call_trace_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        CALL_TRACE_PATH_ENV,
        str(tmp_path / "calls.jsonl"),
    )


def _arguments(**overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "goal": "make the requested change",
        "workspace_id": "workspace.test",
        "workspace_path": "D:/workspace",
        "task_kind": "repository_change",
    }
    arguments.update(overrides)
    return arguments


def _task_state(*, status: str = "completed") -> dict[str, Any]:
    return {
        "task_id": "task-test",
        "task_kind": "repository_change",
        "workspace_id": "workspace.test",
        "status": status,
        "iteration": 2,
        "result": "terminal result" if status == "completed" else None,
        "error": None if status == "completed" else "settled failure",
        "last_invocation_result": "terminal result",
    }


def test_tool_runs_one_entrypoint_process_with_explicit_change_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[dict[str, Any]] = []
    terminal = _task_state()

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        observed.append({"args": args, **kwargs})
        return subprocess.CompletedProcess(
            args, 0, json.dumps(terminal).encode("utf-8"), b""
        )

    monkeypatch.setattr(mcp_server.subprocess, "run", fake_run)

    result = mcp_server.dsh_runtime(_arguments())

    assert result == terminal
    assert len(observed) == 1
    invocation = observed[0]
    assert invocation["args"] == [
        mcp_server.sys.executable,
        "-m",
        "dsh_runtime.entrypoint",
    ]
    assert invocation["cwd"] == mcp_server._RUNTIME_ROOT
    assert json.loads(invocation["input"].decode("utf-8")) == _arguments()
    assert isinstance(invocation["input"], bytes)
    assert "encoding" not in invocation
    assert "errors" not in invocation
    assert "text" not in invocation
    assert invocation["capture_output"] is True
    assert invocation["check"] is False
    assert CALL_TRACE_PATH_ENV not in invocation["env"]


def test_tool_request_escapes_surrogates_before_utf8_subprocess_encoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments = _arguments(goal="inspect \udc94")
    observed: dict[str, Any] = {}
    terminal = _task_state()

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        observed.update(kwargs)
        return subprocess.CompletedProcess(
            args, 0, json.dumps(terminal).encode("utf-8"), b""
        )

    monkeypatch.setattr(mcp_server.subprocess, "run", fake_run)

    assert mcp_server.dsh_runtime(arguments) == terminal
    assert observed["input"].isascii()
    assert json.loads(observed["input"].decode("ascii")) == arguments


def test_settled_business_failure_is_returned_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    terminal = _task_state(status="failed")
    calls = 0

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(
            args, 0, json.dumps(terminal).encode("utf-8"), b""
        )

    monkeypatch.setattr(mcp_server.subprocess, "run", fake_run)

    assert mcp_server.dsh_runtime(_arguments()) == terminal
    assert calls == 1


def test_call_trace_persists_only_lifecycle_metadata_and_result_hashes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompt_marker = "PRIVATE_PROMPT_SENTINEL"
    result_marker = "PRIVATE_RESPONSE_SENTINEL"
    terminal = _task_state()
    terminal["result"] = result_marker
    stdout = json.dumps(terminal, ensure_ascii=False).encode("utf-8")
    calls = 0

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(args, 0, stdout, b"")

    monkeypatch.setattr(mcp_server.subprocess, "run", fake_run)

    result = mcp_server.dsh_runtime(_arguments(goal=prompt_marker))

    assert result == terminal
    assert calls == 1
    trace_path = mcp_server.resolve_call_trace_path()
    trace_text = trace_path.read_text(encoding="utf-8")
    records = [json.loads(line) for line in trace_text.splitlines()]
    assert [record["event"] for record in records] == [
        "call_started",
        "call_terminal",
    ]
    started, terminal_record = records
    assert started["state"] == "started"
    assert started["invocation_count"] == 1
    assert terminal_record["state"] == "returned"
    assert terminal_record["runtime_exit_code"] == 0
    assert terminal_record["task_status"] == "completed"
    assert terminal_record["stdout_bytes"] == len(stdout)
    assert terminal_record["stdout_sha256"] == hashlib.sha256(stdout).hexdigest()
    canonical_result = json.dumps(
        terminal,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    assert terminal_record["result_sha256"] == hashlib.sha256(
        canonical_result
    ).hexdigest()
    assert prompt_marker not in trace_text
    assert result_marker not in trace_text
    assert "workspace.test" not in trace_text
    assert "workspace_path" not in trace_text


def test_unrecognized_non_string_task_status_is_traced_without_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    terminal = _task_state()
    terminal["status"] = {"unexpected": "shape"}

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(
            args, 0, json.dumps(terminal).encode("utf-8"), b""
        )

    monkeypatch.setattr(mcp_server.subprocess, "run", fake_run)

    assert mcp_server.dsh_runtime(_arguments()) == terminal
    terminal_record = json.loads(
        mcp_server.resolve_call_trace_path().read_text(encoding="utf-8").splitlines()[-1]
    )
    assert terminal_record["state"] == "returned"
    assert terminal_record["task_status"] is None


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("state", [], "invalid state"),
        ("task_status", {"unexpected": "shape"}, "invalid task status"),
        ("error_code", [], "invalid error code"),
    ],
)
def test_call_trace_schema_rejects_unhashable_enum_fields(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    trace_path = tmp_path / "calls.jsonl"
    record = {
        "schema_version": "1",
        "event": "call_terminal",
        "call_id": "00000000-0000-0000-0000-000000000001",
        "timestamp": "2026-10-13T00:00:00Z",
        "state": "returned",
        "duration_ms": 0,
        "runtime_exit_code": 0,
        "stdout_bytes": 0,
        "stdout_sha256": "0" * 64,
        "stderr_bytes": 0,
        "stderr_sha256": "0" * 64,
        "task_status": None,
        "result_sha256": None,
        "error_code": None,
        "error_type": None,
    }
    record[field] = value

    with pytest.raises(CallTraceError, match=message):
        append_call_trace(trace_path, record)

    assert not trace_path.exists()


def test_invalid_utf8_output_leaves_hashed_transport_error_without_raw_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout = b"\xffprivate-response"
    stderr = b"api_key=TRACE_SECRET_SENTINEL"
    calls = 0

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(args, 0, stdout, stderr)

    monkeypatch.setattr(mcp_server.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="stdout is not valid UTF-8"):
        mcp_server.dsh_runtime(_arguments(goal="PROMPT_SECRET_SENTINEL"))

    assert calls == 1
    trace_text = mcp_server.resolve_call_trace_path().read_text(encoding="utf-8")
    terminal_record = json.loads(trace_text.splitlines()[-1])
    assert terminal_record["state"] == "transport_error"
    assert terminal_record["error_code"] == "stdout_invalid_utf8"
    assert terminal_record["error_type"] == "UnicodeDecodeError"
    assert terminal_record["stdout_bytes"] == len(stdout)
    assert terminal_record["stdout_sha256"] == hashlib.sha256(stdout).hexdigest()
    assert terminal_record["stderr_bytes"] == len(stderr)
    assert terminal_record["stderr_sha256"] == hashlib.sha256(stderr).hexdigest()
    assert "private-response" not in trace_text
    assert "TRACE_SECRET_SENTINEL" not in trace_text
    assert "PROMPT_SECRET_SENTINEL" not in trace_text


def test_start_trace_failure_prevents_runtime_invocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fail_trace(path: Path, record: dict[str, Any]) -> None:
        raise CallTraceError("injected trace write failure")

    def unexpected_run(*args: Any, **kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        pytest.fail("Runtime must not start without a durable call-start record")

    monkeypatch.setattr(mcp_server, "append_call_trace", fail_trace)
    monkeypatch.setattr(mcp_server.subprocess, "run", unexpected_run)

    with pytest.raises(RuntimeError, match="Runtime was not invoked"):
        mcp_server.dsh_runtime(_arguments())
    assert calls == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("goal", ""),
        ("workspace_id", " "),
        ("workspace_path", ""),
    ],
)
def test_invalid_required_argument_fails_before_starting_runtime(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
) -> None:
    def unexpected_run(*args: Any, **kwargs: Any) -> None:
        pytest.fail("invalid tool input must not start DSH Runtime")

    monkeypatch.setattr(mcp_server.subprocess, "run", unexpected_run)

    with pytest.raises(ValueError, match=field):
        mcp_server.dsh_runtime(_arguments(**{field: value}))


@pytest.mark.parametrize(
    "arguments",
    [
        None,
        [],
        {"goal": "change", "workspace_id": "workspace.test"},
        _arguments(unexpected="field"),
        _arguments(task_kind="repository_inspection"),
    ],
)
def test_invalid_tool_envelope_fails_closed_before_starting_runtime(
    monkeypatch: pytest.MonkeyPatch,
    arguments: object,
) -> None:
    def unexpected_run(*args: Any, **kwargs: Any) -> None:
        pytest.fail("invalid tool input must not start DSH Runtime")

    monkeypatch.setattr(mcp_server.subprocess, "run", unexpected_run)

    with pytest.raises(ValueError):
        mcp_server.dsh_runtime(arguments)


@pytest.mark.parametrize(
    ("returncode", "stdout", "stderr", "message"),
    [
        (2, b"", b"entrypoint transport failure: invalid request", "exit code 2"),
        (0, b"not json\n", b"", "malformed terminal JSON"),
        (0, b"{}\n{}\n", b"", "one JSON record"),
        (0, b"{}\n", b"unexpected warning", "unexpected stderr"),
    ],
)
def test_process_and_transport_failures_surface_without_retry(
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
    stdout: bytes,
    stderr: bytes,
    message: str,
) -> None:
    calls = 0

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(args, returncode, stdout, stderr)

    monkeypatch.setattr(mcp_server.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match=message):
        mcp_server.dsh_runtime(_arguments())
    assert calls == 1


def test_transport_diagnostic_redacts_common_secret_values() -> None:
    diagnostic = "Authorization: Bearer abc api_key=xyz"

    assert mcp_server._safe_diagnostic(diagnostic) == (
        "Authorization: Bearer [REDACTED] api_key=[REDACTED]"
    )


def test_mcp_lifecycle_and_tool_schema_are_advertised() -> None:
    server = mcp_server.MCPServer()
    init = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1"},
            },
        }
    )

    assert init is not None
    assert init["result"]["protocolVersion"] == "2025-06-18"
    assert init["result"]["capabilities"] == {"tools": {}}
    assert server.handle(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}
    ) is None
    listed = server.handle(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    )

    assert listed is not None
    assert [tool["name"] for tool in listed["result"]["tools"]] == ["dsh_runtime"]
    tool = listed["result"]["tools"][0]
    assert tool["inputSchema"]["required"] == [
        "goal",
        "workspace_id",
        "workspace_path",
        "task_kind",
    ]
    assert tool["inputSchema"]["properties"]["task_kind"]["enum"] == [
        "repository_change"
    ]
    assert tool["inputSchema"]["additionalProperties"] is False


def test_tool_call_returns_structured_terminal_result_without_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    terminal = _task_state()

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(
            args, 0, json.dumps(terminal).encode("utf-8"), b""
        )

    monkeypatch.setattr(mcp_server.subprocess, "run", fake_run)
    server = mcp_server.MCPServer()
    server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        }
    )
    server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "dsh_runtime", "arguments": _arguments()},
        }
    )

    assert response is not None
    result = response["result"]
    assert result["isError"] is False
    assert result["structuredContent"] == terminal
    assert json.loads(result["content"][0]["text"]) == terminal


def test_tool_call_reports_failure_as_tool_error() -> None:
    server = mcp_server.MCPServer()
    server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        }
    )
    server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "dsh_runtime",
                "arguments": _arguments(task_kind="repository_inspection"),
            },
        }
    )

    assert response is not None
    assert response["result"]["isError"] is True
    assert "repository_change" in response["result"]["content"][0]["text"]


def test_main_round_trips_surrogate_task_state_over_utf8_stdio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "clientInfo": {"name": "客户端"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "dsh_runtime", "arguments": _arguments()},
        },
    ]
    request_bytes = b"".join(
        json.dumps(request, ensure_ascii=False).encode("utf-8") + b"\n"
        for request in requests
    )
    stdout_buffer = io.BytesIO()
    monkeypatch.setattr(
        mcp_server.sys,
        "stdin",
        SimpleNamespace(buffer=io.BytesIO(request_bytes)),
    )
    monkeypatch.setattr(
        mcp_server.sys,
        "stdout",
        SimpleNamespace(buffer=stdout_buffer),
    )
    monkeypatch.setattr(
        mcp_server,
        "dsh_runtime",
        lambda _arguments: {"result": "结果" + chr(0xDC94)},
    )

    assert mcp_server.main() == 0
    responses = [
        json.loads(line)
        for line in stdout_buffer.getvalue().decode("utf-8").splitlines()
    ]

    assert [response["id"] for response in responses] == [1, 2]
    result = responses[1]["result"]
    expected = {"result": "结果" + chr(0xDC94)}
    assert result["structuredContent"] == expected
    assert json.loads(result["content"][0]["text"]) == expected
