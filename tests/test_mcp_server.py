from __future__ import annotations

import io
import json
import subprocess
from types import SimpleNamespace
from typing import Any

import pytest

from dsh_runtime import mcp_server


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

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed.append({"args": args, **kwargs})
        return subprocess.CompletedProcess(args, 0, json.dumps(terminal), "")

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
    assert json.loads(invocation["input"]) == _arguments()
    assert invocation["encoding"] == "utf-8"
    assert invocation["errors"] == "strict"
    assert invocation["capture_output"] is True
    assert invocation["check"] is False


def test_tool_request_escapes_surrogates_before_utf8_subprocess_encoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments = _arguments(goal="inspect \udc94")
    observed: dict[str, Any] = {}
    terminal = _task_state()

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed.update(kwargs)
        return subprocess.CompletedProcess(args, 0, json.dumps(terminal), "")

    monkeypatch.setattr(mcp_server.subprocess, "run", fake_run)

    assert mcp_server.dsh_runtime(arguments) == terminal
    assert observed["encoding"] == "utf-8"
    assert observed["input"].isascii()
    assert json.loads(observed["input"]) == arguments


def test_settled_business_failure_is_returned_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    terminal = _task_state(status="failed")
    calls = 0

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(args, 0, json.dumps(terminal), "")

    monkeypatch.setattr(mcp_server.subprocess, "run", fake_run)

    assert mcp_server.dsh_runtime(_arguments()) == terminal
    assert calls == 1


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
        (2, "", "entrypoint transport failure: invalid request", "exit code 2"),
        (0, "not json\n", "", "malformed terminal JSON"),
        (0, "{}\n{}\n", "", "one JSON record"),
        (0, "{}\n", "unexpected warning", "unexpected stderr"),
    ],
)
def test_process_and_transport_failures_surface_without_retry(
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
    stdout: str,
    stderr: str,
    message: str,
) -> None:
    calls = 0

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
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

    def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 0, json.dumps(terminal), "")

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
