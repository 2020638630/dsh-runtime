"""Production-facing semantic hardening tests for Milestone 2-C.2b."""

import asyncio

import pytest

from dsh_runtime.controller import DSHController
from dsh_runtime.plugins.echo import EchoPlugin
from dsh_runtime.runtime.executor import Executor
from dsh_runtime.runtime.plugin import (
    PLUGIN_TIMEOUT_ERROR,
    ExecutionContext,
    PluginResult,
    StopReason,
)
from dsh_runtime.runtime.registry import PluginRegistry
from dsh_runtime.state import TaskState, TaskStatus


CTX = ExecutionContext(task_id="semantic-task", workspace_id="logical.test", goal="probe")


def executor_with(plugin) -> Executor:
    registry = PluginRegistry()
    registry.register(plugin)
    return Executor(registry)


def test_normal_success_gets_completed_stop_reason() -> None:
    async def scenario():
        return await executor_with(EchoPlugin()).execute(
            "echo", CTX, {"text": "hello"}, 0.1
        )

    result = asyncio.run(scenario())

    assert result.success is True
    assert result.output == "hello"
    assert result.stop_reason is StopReason.COMPLETED
    assert result.cleanup_error is None


def test_ordinary_plugin_exception_gets_failed_stop_reason() -> None:
    class BrokenPlugin:
        name = "broken"

        async def execute(self, ctx, params):
            raise RuntimeError("boom")

    async def scenario():
        return await executor_with(BrokenPlugin()).execute("broken", CTX, {}, 0.1)

    result = asyncio.run(scenario())

    assert result.success is False
    assert result.stop_reason is StopReason.FAILED
    assert "RuntimeError: boom" == result.error
    assert result.cleanup_error is None


def test_plugin_cannot_forge_timed_out_stop_reason_on_success() -> None:
    class ForgingPlugin:
        name = "forging-success"

        async def execute(self, ctx, params):
            return PluginResult(
                success=True,
                output="done",
                stop_reason=StopReason.TIMED_OUT,
            )

    async def scenario():
        return await executor_with(ForgingPlugin()).execute(
            "forging-success", CTX, {}, 0.1
        )

    result = asyncio.run(scenario())

    assert result.success is True
    assert result.output == "done"
    assert result.stop_reason is StopReason.COMPLETED


def test_plugin_cannot_forge_timed_out_stop_reason_on_failure() -> None:
    class ForgingPlugin:
        name = "forging-failure"

        async def execute(self, ctx, params):
            return PluginResult(
                success=False,
                error="product failure",
                stop_reason=StopReason.TIMED_OUT,
            )

    async def scenario():
        return await executor_with(ForgingPlugin()).execute(
            "forging-failure", CTX, {}, 0.1
        )

    result = asyncio.run(scenario())

    assert result.success is False
    assert result.error == "product failure"
    assert result.stop_reason is StopReason.FAILED


def test_plain_timeout_maps_controller_without_error_string_matching() -> None:
    class SlowPlugin:
        name = "slow"

        async def execute(self, ctx, params):
            await asyncio.sleep(0.05)
            return PluginResult(success=True, output="late")

    async def scenario():
        registry = PluginRegistry()
        registry.register(SlowPlugin())

        class Planner:
            def next_action(self, task):
                from dsh_runtime.planner import Decision

                return Decision(plugin="slow", params={})

        return await DSHController(registry, planner=Planner()).run(
            TaskState(goal="timeout", timeout_seconds=0.005)
        )

    task = asyncio.run(scenario())

    assert task.status is TaskStatus.TIMED_OUT
    assert task.error == PLUGIN_TIMEOUT_ERROR


def test_failure_with_timeout_text_is_not_mistaken_for_timeout() -> None:
    class MisleadingFailurePlugin:
        name = "misleading"

        async def execute(self, ctx, params):
            return PluginResult(success=False, error=PLUGIN_TIMEOUT_ERROR)

    async def scenario():
        registry = PluginRegistry()
        registry.register(MisleadingFailurePlugin())

        class Planner:
            def next_action(self, task):
                from dsh_runtime.planner import Decision

                return Decision(plugin="misleading", params={})

        return await DSHController(registry, planner=Planner()).run(TaskState(goal="x"))

    task = asyncio.run(scenario())

    assert task.status is TaskStatus.FAILED
    assert task.error == PLUGIN_TIMEOUT_ERROR


def test_timeout_and_cleanup_failure_preserve_both_facts() -> None:
    class CleanupFailurePlugin:
        name = "cleanup-failure"

        async def execute(self, ctx, params):
            try:
                await asyncio.Event().wait()
            finally:
                raise RuntimeError("cleanup boom")

    async def scenario():
        return await executor_with(CleanupFailurePlugin()).execute(
            "cleanup-failure", CTX, {}, 0.005
        )

    result = asyncio.run(scenario())

    assert result.success is False
    assert result.stop_reason is StopReason.TIMED_OUT
    assert result.error == PLUGIN_TIMEOUT_ERROR
    assert result.cleanup_error == "RuntimeError: cleanup boom"


def test_timeout_result_is_returned_only_after_cleanup_finishes() -> None:
    class CleanupPlugin:
        name = "cleanup"

        def __init__(self):
            self.cleaned = False

        async def execute(self, ctx, params):
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0.01)
                self.cleaned = True

    async def scenario():
        plugin = CleanupPlugin()
        result = await executor_with(plugin).execute("cleanup", CTX, {}, 0.001)
        return plugin, result

    plugin, result = asyncio.run(scenario())

    assert plugin.cleaned is True
    assert result.stop_reason is StopReason.TIMED_OUT


def test_outer_cancellation_still_propagates() -> None:
    class BlockingPlugin:
        name = "blocking"

        def __init__(self):
            self.cleaned = False

        async def execute(self, ctx, params):
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0.005)
                self.cleaned = True

    async def scenario():
        plugin = BlockingPlugin()
        task = asyncio.create_task(
            executor_with(plugin).execute("blocking", CTX, {}, 1.0)
        )
        await asyncio.sleep(0.001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return plugin

    plugin = asyncio.run(scenario())

    assert plugin.cleaned is True


def test_invalid_plugin_result_is_not_blank_success() -> None:
    class InvalidPlugin:
        name = "invalid"

        async def execute(self, ctx, params):
            return {"success": True, "output": "not a PluginResult"}

    async def scenario():
        return await executor_with(InvalidPlugin()).execute("invalid", CTX, {}, 0.1)

    result = asyncio.run(scenario())

    assert result.success is False
    assert result.stop_reason is StopReason.FAILED
    assert result.error == "plugin returned an invalid result"


def test_echo_does_not_need_process_metadata() -> None:
    async def scenario():
        return await executor_with(EchoPlugin()).execute(
            "echo", CTX, {"text": "no pid"}, 0.1
        )

    result = asyncio.run(scenario())

    assert result.success is True
    assert result.cleanup_error is None
