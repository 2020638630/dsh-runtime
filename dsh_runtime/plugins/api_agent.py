"""Optional read-only API Agent Runtime plugin; no worker write path yet."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from dsh_runtime.api_agent_chat_transport import ChatCompletionsTransport
from dsh_runtime.api_agent_connections import Connection, ConnectionCatalog
from dsh_runtime.api_agent_contract import ApiAgentConfig, ApiRole
from dsh_runtime.api_agent_loop import ModelTransport, run_api_agent
from dsh_runtime.api_agent_read_tools import WorkspaceReadBroker
from dsh_runtime.observability.logger import record
from dsh_runtime.runtime.plugin import ExecutionContext, PluginResult


class _AuditedReadBroker:
    def __init__(self, broker: WorkspaceReadBroker, ctx: ExecutionContext) -> None:
        self.broker = broker
        self.ctx = ctx

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        try:
            result = await self.broker.execute(name, arguments)
        except Exception:
            record(
                "api_agent_tool_settled", task_id=self.ctx.task_id,
                workspace_id=self.ctx.workspace_id, tool=name, outcome="failed",
            )
            raise
        record(
            "api_agent_tool_settled", task_id=self.ctx.task_id,
            workspace_id=self.ctx.workspace_id, tool=name, outcome="completed",
            result_chars=len(result),
        )
        return result


class ApiAgentPlugin:
    name = "api_agent"

    def __init__(
        self, connections: ConnectionCatalog,
        *, transport_factory: Callable[[Connection], ModelTransport] = ChatCompletionsTransport,
    ) -> None:
        self.connections = connections
        self.transport_factory = transport_factory

    async def execute(self, ctx: ExecutionContext, params: dict[str, Any]) -> PluginResult:
        expected = {
            "prompt", "role_name", "provider", "model", "connection_ref",
            "max_requests", "max_tool_calls", "max_output_tokens",
        }
        role_name = params.get("role_name")
        if (set(params) != expected or not isinstance(role_name, str)
            or role_name not in {"reviewer", "inspector"}):
            return PluginResult(False, error="api_agent read-only role is required")
        if ctx.allow_workspace_write or not ctx.cwd:
            return PluginResult(False, error="api_agent requires a read-only workspace")
        try:
            role_payload = {key: params[key] for key in expected - {"prompt", "role_name"}}
            role_payload["adapter"] = "api_agent"
            parsed = ApiAgentConfig.from_document({
                "schema_version": 2,
                "roles": {
                    "worker": {"adapter": "codebuddy", "model": None},
                    "reviewer": role_payload,
                    "inspector": role_payload,
                },
            })
            config = getattr(parsed, role_name)
            assert isinstance(config, ApiRole)
            connection = self.connections.get(config.connection_ref, config.provider)
            broker = _AuditedReadBroker(WorkspaceReadBroker(Path(ctx.cwd)), ctx)
            transport = self.transport_factory(connection)
        except (ValueError, OSError, TypeError):
            return PluginResult(False, error="api_agent preflight failed")
        outcome = await run_api_agent(
            config, params["prompt"], transport, broker,
            role_name=params["role_name"], allow_workspace_write=False,
        )
        record(
            "api_agent_settled",
            task_id=ctx.task_id,
            workspace_id=ctx.workspace_id,
            role_name=role_name,
            provider=config.provider,
            requested_model=outcome.requested_model,
            observed_model=outcome.observed_model,
            requests=outcome.requests,
            tool_calls=outcome.tool_calls,
            outcome="completed" if outcome.success else outcome.error_code,
        )
        if outcome.success:
            return PluginResult(True, output=outcome.text)
        return PluginResult(False, error=f"api_agent {outcome.error_code}")
