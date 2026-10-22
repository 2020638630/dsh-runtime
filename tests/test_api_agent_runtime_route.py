import asyncio
import json
import logging

import pytest

from dsh_runtime.api_agent_connections import Connection, ConnectionCatalog
from dsh_runtime.api_agent_loop import ModelReply, ToolCall
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
