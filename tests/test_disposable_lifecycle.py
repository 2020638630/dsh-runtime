"""Disposable lifecycle evidence for Milestone 2-C.2a.

These tests intentionally use local doubles and a short-lived helper process.
They do not change the runtime contract or production implementation.
"""

import asyncio
import sys
import time

import pytest

from dsh_runtime.plugins.echo import EchoPlugin
from dsh_runtime.runtime.executor import Executor
from dsh_runtime.runtime.plugin import ExecutionContext, PluginResult
from dsh_runtime.runtime.registry import PluginRegistry


CTX = ExecutionContext(task_id="lifecycle-task", workspace_id="logical.test", goal="probe")


def executor_with(plugin) -> Executor:
    registry = PluginRegistry()
    registry.register(plugin)
    return Executor(registry)


class CleanupProbe:
    name = "probe"

    def __init__(self, cleanup_error: Exception | None = None) -> None:
        self.events: list[str] = []
        self.cleanup_done = asyncio.Event()
        self.cleanup_error = cleanup_error

    async def execute(self, ctx, params) -> PluginResult:
        try:
            self.events.append("running")
            await asyncio.Event().wait()
            return PluginResult(success=True, output="unexpected")
        except asyncio.CancelledError:
            self.events.append("cancelled")
            raise
        finally:
            self.events.append("cleanup_started")
            await asyncio.sleep(0.02)
            if self.cleanup_error is not None:
                self.events.append("cleanup_failed")
                self.cleanup_done.set()
                raise self.cleanup_error
            self.events.append("cleanup_finished")
            self.cleanup_done.set()


class SuppressingProbe:
    name = "probe"

    def __init__(self) -> None:
        self.events: list[str] = []

    async def execute(self, ctx, params) -> PluginResult:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.events.append("cancelled_suppressed")
            await asyncio.sleep(0.03)
            self.events.append("continued_after_cancel")
            return PluginResult(success=True, output="suppressed")


class OuterCancellationProbe(CleanupProbe):
    pass


class FakeProcessLifecycle:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.quiescent = False

    async def graceful_interrupt(self) -> None:
        self.events.append("graceful_attempt")
        raise RuntimeError("graceful interrupt unavailable")

    async def force_terminate(self) -> None:
        self.events.append("force_terminate")
        await asyncio.sleep(0.005)

    async def wait_quiescence(self) -> None:
        await asyncio.sleep(0.005)
        self.quiescent = True
        self.events.append("quiescent")


class SimulatedProcessPlugin:
    name = "probe"

    def __init__(self) -> None:
        self.process = FakeProcessLifecycle()

    async def execute(self, ctx, params) -> PluginResult:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.process.events.append("cancelled")
            raise
        finally:
            try:
                await self.process.graceful_interrupt()
            except RuntimeError:
                self.process.events.append("graceful_failed")
                await self.process.force_terminate()
            await self.process.wait_quiescence()


class SubprocessPlugin:
    """A process-backed double whose child must be gone before execute returns."""

    name = "probe"

    def __init__(self) -> None:
        self.process = None
        self.events: list[str] = []

    async def execute(self, ctx, params) -> PluginResult:
        self.process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import time; time.sleep(60)",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            self.events.append("started")
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.events.append("cancelled")
            raise
        finally:
            self.events.append("terminate_requested")
            if self.process.returncode is None:
                self.process.terminate()
            await self.process.wait()
            self.events.append("process_exited")


def test_timeout_delivers_cancel_and_waits_for_async_cleanup() -> None:
    async def scenario():
        plugin = CleanupProbe()
        started = time.perf_counter()
        result = await executor_with(plugin).execute("probe", CTX, {}, 0.005)
        elapsed = time.perf_counter() - started
        return plugin, result, elapsed

    plugin, result, elapsed = asyncio.run(scenario())

    assert result.success is False
    assert result.error == "plugin execution timed out"
    assert plugin.events == ["running", "cancelled", "cleanup_started", "cleanup_finished"]
    assert plugin.cleanup_done.is_set()
    assert elapsed >= 0.02


def test_cleanup_exception_is_observable_and_replaces_timeout_result() -> None:
    async def scenario():
        plugin = CleanupProbe(RuntimeError("cleanup boom"))
        result = await executor_with(plugin).execute("probe", CTX, {}, 0.005)
        return plugin, result

    plugin, result = asyncio.run(scenario())

    assert plugin.events == ["running", "cancelled", "cleanup_started", "cleanup_failed"]
    assert result.success is False
    assert result.error == "plugin execution timed out"
    assert result.cleanup_error == "RuntimeError: cleanup boom"


def test_cancelled_error_suppression_can_extend_wait_for_beyond_timeout() -> None:
    async def scenario():
        plugin = SuppressingProbe()
        started = time.perf_counter()
        result = await executor_with(plugin).execute("probe", CTX, {}, 0.005)
        return plugin, result, time.perf_counter() - started

    plugin, result, elapsed = asyncio.run(scenario())

    assert result.success is False
    assert result.error == "plugin execution timed out"
    assert plugin.events == ["cancelled_suppressed", "continued_after_cancel"]
    # The probe sleeps for 30ms after cancellation, but scheduler overhead and
    # timer resolution make an exact 30ms wall-clock lower bound flaky. The
    # 20ms bound still proves wait_for did not return at the 5ms deadline.
    assert elapsed >= 0.02


def test_outer_executor_cancellation_propagates_after_plugin_cleanup() -> None:
    async def scenario():
        plugin = OuterCancellationProbe()
        task = asyncio.create_task(
            executor_with(plugin).execute("probe", CTX, {}, 1.0)
        )
        await asyncio.sleep(0.005)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return plugin

    plugin = asyncio.run(scenario())

    assert plugin.events == ["running", "cancelled", "cleanup_started", "cleanup_finished"]
    assert plugin.cleanup_done.is_set()


def test_simulated_graceful_failure_escalates_to_force_and_quiescence() -> None:
    async def scenario():
        plugin = SimulatedProcessPlugin()
        result = await executor_with(plugin).execute("probe", CTX, {}, 0.005)
        return plugin, result

    plugin, result = asyncio.run(scenario())

    assert result.error == "plugin execution timed out"
    assert plugin.process.quiescent is True
    assert plugin.process.events == [
        "cancelled",
        "graceful_attempt",
        "graceful_failed",
        "force_terminate",
        "quiescent",
    ]


def test_real_helper_process_is_exited_before_executor_returns() -> None:
    async def scenario():
        plugin = SubprocessPlugin()
        result = await executor_with(plugin).execute("probe", CTX, {}, 0.05)
        return plugin, result

    plugin, result = asyncio.run(scenario())

    assert result.error == "plugin execution timed out"
    assert plugin.process is not None
    assert plugin.process.returncode is not None
    assert plugin.events == ["started", "cancelled", "terminate_requested", "process_exited"]


def test_quiescence_failure_can_be_reported_by_plugin_cleanup() -> None:
    class QuiescenceFailurePlugin:
        name = "probe"

        async def execute(self, ctx, params):
            try:
                await asyncio.Event().wait()
            finally:
                try:
                    await asyncio.wait_for(asyncio.Event().wait(), timeout=0.005)
                except asyncio.TimeoutError as exc:
                    raise RuntimeError("quiescence deadline exceeded") from exc

    result = asyncio.run(
        executor_with(QuiescenceFailurePlugin()).execute("probe", CTX, {}, 0.005)
    )

    assert result.success is False
    assert result.error == "plugin execution timed out"
    assert result.cleanup_error == "RuntimeError: quiescence deadline exceeded"


def test_echo_plugin_remains_non_process_and_unchanged() -> None:
    async def scenario():
        return await executor_with(EchoPlugin()).execute(
            "echo", CTX, {"text": "unchanged"}, 0.1
        )

    result = asyncio.run(scenario())

    assert result.success is True
    assert result.output == "unchanged"
