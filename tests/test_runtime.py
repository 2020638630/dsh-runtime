import asyncio

from dsh_runtime.controller import DSHController
from dsh_runtime.plugins.echo import EchoPlugin
from dsh_runtime.runtime.plugin import PluginResult
from dsh_runtime.planner import Decision
from dsh_runtime.runtime.registry import PluginRegistry
from dsh_runtime.state import TaskState, TaskStatus


def registry_with(plugin) -> PluginRegistry:
    registry = PluginRegistry()
    registry.register(plugin)
    return registry


def test_echo_completes_task() -> None:
    task = asyncio.run(DSHController(registry_with(EchoPlugin())).run(TaskState(goal="hello")))
    assert task.status is TaskStatus.COMPLETED
    assert task.result == "hello"
    assert task.iteration == 1


def test_plugin_error_stays_inside_runtime() -> None:
    class BrokenPlugin:
        name = "echo"

        async def execute(self, ctx, params):
            raise RuntimeError("boom")

    task = asyncio.run(DSHController(registry_with(BrokenPlugin())).run(TaskState(goal="x")))
    assert task.status is TaskStatus.FAILED
    assert "RuntimeError" in task.error


def test_plugin_timeout_is_bounded() -> None:
    class SlowPlugin:
        name = "echo"

        async def execute(self, ctx, params):
            await asyncio.sleep(0.05)
            return PluginResult(success=True, output="late")

    task = asyncio.run(DSHController(registry_with(SlowPlugin())).run(
        TaskState(goal="x", timeout_seconds=0.001)
    ))
    assert task.status is TaskStatus.TIMED_OUT
    assert task.iteration == 1
    assert task.error == "plugin execution timed out"


def test_zero_max_iterations_does_not_execute_plugin() -> None:
    task = asyncio.run(
        DSHController(registry_with(EchoPlugin())).run(
            TaskState(goal="x", max_iterations=0)
        )
    )
    assert task.status is TaskStatus.MAX_ITERATIONS
    assert task.iteration == 0


def test_unknown_plugin_is_converted_to_task_failure() -> None:
    class UnknownPlanner:
        def next_action(self, task):
            return Decision(plugin="missing", params={})

    task = asyncio.run(
        DSHController(registry_with(EchoPlugin()), planner=UnknownPlanner()).run(
            TaskState(goal="x")
        )
    )
    assert task.status is TaskStatus.FAILED
    assert "plugin not found" in task.error


def test_duplicate_plugin_registration_fails_fast() -> None:
    registry = PluginRegistry()
    registry.register(EchoPlugin())
    try:
        registry.register(EchoPlugin())
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("duplicate registration should fail fast")
