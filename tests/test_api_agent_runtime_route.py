import asyncio
import json
import logging

import pytest

from dsh_runtime.api_agent_connections import Connection, ConnectionCatalog
from dsh_runtime.api_agent_loop import ModelReply, ToolCall, TransportFailure
from dsh_runtime.api_agent_safe_trace import (
    RUNTIME_RUN_ID_ENV, SAFE_EVENT_TRACE_DIR_ENV,
)
from dsh_runtime.bootstrap import API_AGENT_CONNECTIONS_PATH_ENV, build_controller
from dsh_runtime.planner import SimplePlanner
from dsh_runtime.plugins.api_agent import ApiAgentPlugin
from dsh_runtime.role_config import ROLE_CONFIG_ENV, RoleConfig
from dsh_runtime.runtime.plugin import ExecutionContext
from dsh_runtime.state import TaskKind, TaskState


def config():
    api_role = {
        "adapter": "api_agent", "provider": "openrouter", "model": "vendor/model:free",
        "connection_ref": "trial", "max_requests": 3,
        "max_tool_calls": 2, "max_output_tokens": 100,
    }
    return {"schema_version": 2, "roles": {
        "worker": {"adapter": "codebuddy", "model": None},
        "reviewer": {"adapter": "codex", "model": None},
        "inspector": api_role,
    }}


def test_v2_routes_only_inspector_to_api_agent():
    roles = RoleConfig.from_document(config())
    planner = SimplePlanner(roles)
    decision = planner.next_action(TaskState(
        goal="inspect", task_kind=TaskKind.REPOSITORY_INSPECTION,
    ))
    assert decision.plugin == "api_agent"
    assert decision.allow_workspace_write is False
    assert decision.params["role_name"] == "inspector"
    assert decision.params["connection_ref"] == "trial"
    assert "api_key" not in decision.params


def test_api_worker_is_rejected_until_write_tools_are_qualified():
    document = config()
    document["roles"]["worker"] = document["roles"]["inspector"]
    with pytest.raises(ValueError, match="worker is unavailable"):
        RoleConfig.from_document(document)


def test_bootstrap_requires_explicit_external_connection_file(monkeypatch):
    monkeypatch.setenv(ROLE_CONFIG_ENV, json.dumps(config()))
    monkeypatch.delenv(API_AGENT_CONNECTIONS_PATH_ENV, raising=False)
    monkeypatch.setattr(
        "dsh_runtime.plugins.codebuddy._default_command",
        lambda: ("codebuddy.cmd",),
    )
    with pytest.raises(ValueError, match=API_AGENT_CONNECTIONS_PATH_ENV):
        build_controller()


class FakeTransport:
    def __init__(self):
        self.calls = 0

    async def complete(self, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return ModelReply(
                tool_calls=(ToolCall("c1", "read_file", '{"path":"README.md"}'),),
                observed_model="vendor/model:free", output_tokens=5,
            )
        return ModelReply(
            text="README says isolated trial", observed_model="vendor/model:free",
            output_tokens=5,
        )


def test_plugin_runs_read_only_inspection_with_fake_model(tmp_path, caplog):
    (tmp_path / "README.md").write_bytes(b"isolated trial\n")
    fake = FakeTransport()
    catalog = ConnectionCatalog({"trial": Connection(
        "openrouter", "https://openrouter.ai/api/v1", "private-test-key",
    )})
    plugin = ApiAgentPlugin(catalog, transport_factory=lambda _connection: fake)
    decision = SimplePlanner(RoleConfig.from_document(config())).next_action(
        TaskState(goal="inspect", task_kind=TaskKind.REPOSITORY_INSPECTION)
    )
    context = ExecutionContext("task", "workspace", "inspect", cwd=str(tmp_path))
    with caplog.at_level(logging.INFO, logger="dsh_runtime"):
        result = asyncio.run(plugin.execute(context, decision.params))
    assert result.success and result.output == "README says isolated trial"
    assert fake.calls == 2
    assert (tmp_path / "README.md").read_bytes() == b"isolated trial\n"
    assert "api_agent_tool_settled" in caplog.text
    assert "api_agent_settled" in caplog.text
    assert "private-test-key" not in caplog.text


def test_plugin_rejects_write_context_without_calling_model(tmp_path):
    fake = FakeTransport()
    plugin = ApiAgentPlugin(ConnectionCatalog({"trial": Connection(
        "openrouter", "https://openrouter.ai/api/v1", "private-test-key",
    )}), transport_factory=lambda _connection: fake)
    decision = SimplePlanner(RoleConfig.from_document(config())).next_action(
        TaskState(goal="inspect", task_kind=TaskKind.REPOSITORY_INSPECTION)
    )
    context = ExecutionContext(
        "task", "workspace", "inspect", cwd=str(tmp_path), allow_workspace_write=True,
    )
    result = asyncio.run(plugin.execute(context, decision.params))
    assert result.success is False and fake.calls == 0


def test_plugin_writes_opt_in_safe_trace_outside_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_bytes(b"isolated trial\n")
    trace_dir = tmp_path / "evidence"
    monkeypatch.setenv(SAFE_EVENT_TRACE_DIR_ENV, str(trace_dir))
    monkeypatch.setenv(
        RUNTIME_RUN_ID_ENV, "dsh-runtime-00000000-0000-4000-8000-000000000002",
    )
    fake = FakeTransport()
    plugin = ApiAgentPlugin(ConnectionCatalog({"trial": Connection(
        "openrouter", "https://openrouter.ai/api/v1", "private-test-key",
    )}), transport_factory=lambda _connection: fake)
    decision = SimplePlanner(RoleConfig.from_document(config())).next_action(
        TaskState(goal="inspect", task_kind=TaskKind.REPOSITORY_INSPECTION)
    )
    context = ExecutionContext("task", "workspace", "inspect", cwd=str(workspace))
    result = asyncio.run(plugin.execute(context, decision.params))
    assert result.success and fake.calls == 2
    trace = next(trace_dir.glob("api-agent-safe-role-*.jsonl"))
    body = trace.read_text(encoding="utf-8")
    events = [json.loads(line) for line in body.splitlines()]
    assert [event["event_type"] for event in events] == [
        "started", "tool_call", "terminal",
    ]
    assert events[1]["tool_name"] == "read_file"
    assert events[2]["terminal_reason"] == "completed"
    assert "private-test-key" not in body
    assert "isolated trial" not in body
    assert (trace_dir / (trace.name + ".closed")).is_file()
    assert list(workspace.iterdir()) == [workspace / "README.md"]


def test_cancelled_api_agent_closes_trace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    trace_dir = tmp_path / "evidence"
    monkeypatch.setenv(SAFE_EVENT_TRACE_DIR_ENV, str(trace_dir))
    monkeypatch.setenv(
        RUNTIME_RUN_ID_ENV, "dsh-runtime-00000000-0000-4000-8000-000000000003",
    )

    class BlockingTransport:
        def __init__(self):
            self.started = asyncio.Event()

        async def complete(self, **_kwargs):
            self.started.set()
            await asyncio.Future()

    fake = BlockingTransport()
    plugin = ApiAgentPlugin(ConnectionCatalog({"trial": Connection(
        "openrouter", "https://openrouter.ai/api/v1", "private-test-key",
    )}), transport_factory=lambda _connection: fake)
    decision = SimplePlanner(RoleConfig.from_document(config())).next_action(
        TaskState(goal="inspect", task_kind=TaskKind.REPOSITORY_INSPECTION)
    )
    context = ExecutionContext("task", "workspace", "inspect", cwd=str(workspace))

    async def cancel_after_start():
        invocation = asyncio.create_task(plugin.execute(context, decision.params))
        await fake.started.wait()
        invocation.cancel()
        with pytest.raises(asyncio.CancelledError):
            await invocation

    asyncio.run(cancel_after_start())
    trace = next(trace_dir.glob("api-agent-safe-role-*.jsonl"))
    events = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    assert events[-1]["terminal_reason"] == "cancelled"
    assert (trace_dir / (trace.name + ".closed")).is_file()


def test_trace_inside_workspace_fails_before_model_request(tmp_path, monkeypatch):
    monkeypatch.setenv(SAFE_EVENT_TRACE_DIR_ENV, str(tmp_path / "evidence"))
    monkeypatch.setenv(
        RUNTIME_RUN_ID_ENV, "dsh-runtime-00000000-0000-4000-8000-000000000004",
    )
    fake = FakeTransport()
    plugin = ApiAgentPlugin(ConnectionCatalog({"trial": Connection(
        "openrouter", "https://openrouter.ai/api/v1", "private-test-key",
    )}), transport_factory=lambda _connection: fake)
    decision = SimplePlanner(RoleConfig.from_document(config())).next_action(
        TaskState(goal="inspect", task_kind=TaskKind.REPOSITORY_INSPECTION)
    )
    context = ExecutionContext("task", "workspace", "inspect", cwd=str(tmp_path))
    result = asyncio.run(plugin.execute(context, decision.params))
    assert not result.success and fake.calls == 0
    assert not (tmp_path / "evidence").exists()


def reviewer_config():
    document = config()
    document["roles"]["reviewer"] = document["roles"]["inspector"]
    document["roles"]["inspector"] = {"adapter": "codex", "model": None}
    return document


def test_api_reviewer_fake_model_has_read_only_closed_trace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_bytes(b"review target\n")
    trace_dir = tmp_path / "evidence"
    monkeypatch.setenv(SAFE_EVENT_TRACE_DIR_ENV, str(trace_dir))
    monkeypatch.setenv(
        RUNTIME_RUN_ID_ENV, "dsh-runtime-00000000-0000-4000-8000-000000000010",
    )

    class ReviewerTransport:
        def __init__(self):
            self.requests = 0

        async def complete(self, **kwargs):
            self.requests += 1
            assert kwargs["allowed_tools"] == frozenset({"read_file"})
            if self.requests == 1:
                return ModelReply(tool_calls=(ToolCall(
                    "review-read", "read_file", '{"path":"README.md"}',
                ),), observed_model="vendor/model:free", output_tokens=5)
            return ModelReply(
                text="Verified README.\nDSH_VERIFICATION: PASS",
                observed_model="vendor/model:free", output_tokens=5,
            )

    fake = ReviewerTransport()
    plugin = ApiAgentPlugin(ConnectionCatalog({"trial": Connection(
        "openrouter", "https://openrouter.ai/api/v1", "private-test-key",
    )}), transport_factory=lambda _connection: fake)
    decision = SimplePlanner(RoleConfig.from_document(reviewer_config())).next_action(
        TaskState(
            goal="change README", task_kind=TaskKind.REPOSITORY_CHANGE,
            allow_workspace_write=True, max_iterations=2, iteration=1,
        )
    )
    assert decision.allow_workspace_write is False
    context = ExecutionContext("task", "workspace", "review", cwd=str(workspace))
    result = asyncio.run(plugin.execute(context, decision.params))
    assert result.success and result.output.endswith("DSH_VERIFICATION: PASS")
    trace = next(trace_dir.glob("api-agent-safe-role-*.jsonl"))
    events = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    assert {event["role_name"] for event in events} == {"reviewer"}
    assert events[-1]["terminal_reason"] == "completed"
    assert (trace_dir / (trace.name + ".closed")).is_file()
    assert (workspace / "README.md").read_bytes() == b"review target\n"


def test_api_reviewer_provider_failure_closes_failed_trace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    trace_dir = tmp_path / "evidence"
    monkeypatch.setenv(SAFE_EVENT_TRACE_DIR_ENV, str(trace_dir))
    monkeypatch.setenv(
        RUNTIME_RUN_ID_ENV, "dsh-runtime-00000000-0000-4000-8000-000000000011",
    )

    class FailingTransport:
        async def complete(self, **_kwargs):
            raise TransportFailure("provider_timeout")

    plugin = ApiAgentPlugin(ConnectionCatalog({"trial": Connection(
        "openrouter", "https://openrouter.ai/api/v1", "private-test-key",
    )}), transport_factory=lambda _connection: FailingTransport())
    decision = SimplePlanner(RoleConfig.from_document(reviewer_config())).next_action(
        TaskState(
            goal="change README", task_kind=TaskKind.REPOSITORY_CHANGE,
            allow_workspace_write=True, max_iterations=2, iteration=1,
        )
    )
    result = asyncio.run(plugin.execute(
        ExecutionContext("task", "workspace", "review", cwd=str(workspace)),
        decision.params,
    ))
    assert not result.success and result.error == "api_agent provider_timeout"
    trace = next(trace_dir.glob("api-agent-safe-role-*.jsonl"))
    events = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    assert events[-1]["terminal_reason"] == "failed"
    marker = json.loads((trace_dir / (trace.name + ".closed")).read_text(encoding="utf-8"))
    assert marker["failure_code"] == "provider_timeout"
