"""Bounded plugin execution with an explicit timeout boundary."""

import asyncio
import time
from typing import Any

from ..observability.logger import record
from .plugin import ExecutionContext, PluginResult, PLUGIN_TIMEOUT_ERROR
from .registry import PluginRegistry


class Executor:
    def __init__(self, registry: PluginRegistry) -> None:
        self.registry = registry

    async def execute(
        self,
        plugin_name: str,
        ctx: ExecutionContext,
        params: dict[str, Any],
        timeout_seconds: float,
    ) -> PluginResult:
        started = time.perf_counter()
        record(
            "plugin_started",
            task_id=ctx.task_id,
            workspace_id=ctx.workspace_id,
            plugin=plugin_name,
        )
        try:
            plugin = self.registry.get(plugin_name)
            result = await asyncio.wait_for(
                plugin.execute(ctx, params), timeout=timeout_seconds
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            record(
                "plugin_completed",
                task_id=ctx.task_id,
                workspace_id=ctx.workspace_id,
                plugin=plugin_name,
                duration_ms=duration_ms,
            )
            return result
        except asyncio.TimeoutError:
            duration_ms = int((time.perf_counter() - started) * 1000)
            record(
                "plugin_timed_out",
                task_id=ctx.task_id,
                workspace_id=ctx.workspace_id,
                plugin=plugin_name,
                duration_ms=duration_ms,
                error=PLUGIN_TIMEOUT_ERROR,
            )
            return PluginResult(success=False, error=PLUGIN_TIMEOUT_ERROR)
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            error = f"{type(exc).__name__}: {exc}"
            record(
                "plugin_failed",
                task_id=ctx.task_id,
                workspace_id=ctx.workspace_id,
                plugin=plugin_name,
                duration_ms=duration_ms,
                error=error,
            )
            return PluginResult(success=False, error=error)
