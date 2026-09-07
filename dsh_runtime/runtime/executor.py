"""Bounded plugin execution with an explicit timeout boundary."""

import asyncio
import time
from dataclasses import replace
from typing import Any

from ..observability.logger import record
from .plugin import (
    INVALID_PLUGIN_RESULT_ERROR,
    PLUGIN_TIMEOUT_ERROR,
    ExecutionContext,
    PluginResult,
    StopReason,
)
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
        invocation: asyncio.Task[PluginResult] | None = None
        record(
            "plugin_started",
            task_id=ctx.task_id,
            workspace_id=ctx.workspace_id,
            plugin=plugin_name,
        )
        try:
            plugin = self.registry.get(plugin_name)
            invocation = asyncio.create_task(plugin.execute(ctx, params))
            try:
                # Shield keeps timeout intent separate from the task's cleanup.
                # Executor then cancels and awaits the invocation explicitly.
                result = await asyncio.wait_for(
                    asyncio.shield(invocation), timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                cleanup_error = await self._cancel_and_settle(invocation)
                duration_ms = int((time.perf_counter() - started) * 1000)
                record(
                    "plugin_timed_out",
                    task_id=ctx.task_id,
                    workspace_id=ctx.workspace_id,
                    plugin=plugin_name,
                    duration_ms=duration_ms,
                    error=PLUGIN_TIMEOUT_ERROR,
                    cleanup_error=cleanup_error,
                    stop_reason=StopReason.TIMED_OUT.value,
                )
                return PluginResult(
                    success=False,
                    error=PLUGIN_TIMEOUT_ERROR,
                    stop_reason=StopReason.TIMED_OUT,
                    cleanup_error=cleanup_error,
                )
            except asyncio.CancelledError:
                # Preserve caller cancellation, but do not abandon Plugin cleanup.
                cleanup_error = await self._cancel_and_settle(invocation)
                if cleanup_error is not None:
                    record(
                        "plugin_cleanup_failed",
                        task_id=ctx.task_id,
                        workspace_id=ctx.workspace_id,
                        plugin=plugin_name,
                        cleanup_error=cleanup_error,
                    )
                raise

            result = self._normalize_result(result)
            duration_ms = int((time.perf_counter() - started) * 1000)
            record(
                "plugin_completed",
                task_id=ctx.task_id,
                workspace_id=ctx.workspace_id,
                plugin=plugin_name,
                duration_ms=duration_ms,
                stop_reason=result.stop_reason.value,
                cleanup_error=result.cleanup_error,
            )
            return result
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
                stop_reason=StopReason.FAILED.value,
            )
            return PluginResult(
                success=False,
                error=error,
                stop_reason=StopReason.FAILED,
            )

    async def _cancel_and_settle(
        self, invocation: asyncio.Task[PluginResult]
    ) -> str | None:
        """Cancel one invocation and observe its cleanup before returning."""

        if not invocation.done():
            invocation.cancel()
        try:
            await invocation
        except asyncio.CancelledError:
            return None
        except Exception as exc:
            return f"{type(exc).__name__}: {exc}"
        return None

    @staticmethod
    def _normalize_result(result: Any) -> PluginResult:
        if not isinstance(result, PluginResult):
            return PluginResult(
                success=False,
                error=INVALID_PLUGIN_RESULT_ERROR,
                stop_reason=StopReason.FAILED,
            )
        return replace(
            result,
            stop_reason=(
                StopReason.COMPLETED if result.success else StopReason.FAILED
            ),
        )
