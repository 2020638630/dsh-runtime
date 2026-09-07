import asyncio

import pytest

from dsh_runtime.controller import DSHController
from dsh_runtime.plugins.echo import EchoPlugin
from dsh_runtime.runtime.plugin import PluginResult
from dsh_runtime.planner import Decision, SimplePlanner
from dsh_runtime.runtime.registry import PluginRegistry
from dsh_runtime.state import TaskKind, TaskState, TaskStatus


def registry_with(plugin) -> PluginRegistry:
    registry = PluginRegistry()
    registry.register(plugin)
    return registry


def test_echo_completes_task() -> None:
    task = asyncio.run(DSHController(registry_with(EchoPlugin())).run(TaskState(goal="hello")))
    assert task.status is TaskStatus.COMPLETED
    assert task.result == "hello"
    assert task.iteration == 1


def test_raw_task_kind_is_rejected() -> None:
    with pytest.raises(TypeError, match="task_kind must be a TaskKind"):
        TaskState(goal="analyze", task_kind="repository_analysis")


def test_write_enabled_repository_analysis_is_rejected() -> None:
    with pytest.raises(ValueError, match="must be read-only"):
        TaskState(
            goal="analyze",
            task_kind=TaskKind.REPOSITORY_ANALYSIS,
            allow_workspace_write=True,
        )


def test_repository_analysis_defaults_to_read_only() -> None:
    task = TaskState(goal="analyze", task_kind=TaskKind.REPOSITORY_ANALYSIS)

    assert task.allow_workspace_write is False


def test_simple_planner_routes_repository_analysis_then_terminates() -> None:
    planner = SimplePlanner()
    task = TaskState(goal="inspect repository", task_kind=TaskKind.REPOSITORY_ANALYSIS)

    initial = planner.next_action(task)
    assert initial == Decision(plugin="codex", params={"prompt": task.goal})

    task.iteration = 1
    task.last_invocation_result = "bounded answer"
    assert planner.next_action(task).is_terminal


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


class ScriptedPlanner:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = []

    def next_action(self, task):
        self.calls.append((task.iteration, task.last_invocation_result))
        return self.decisions.pop(0)


class RecordingPlugin:
    def __init__(self, name, output=None, error=None):
        self.name = name
        self.output = output
        self.error = error
        self.calls = 0

    async def execute(self, ctx, params):
        self.calls += 1
        if self.error is not None:
            return PluginResult(success=False, error=self.error)
        return PluginResult(success=True, output=self.output)


def test_two_step_continuation_observes_latest_result() -> None:
    first = RecordingPlugin("first", output="A")
    second = RecordingPlugin("second", output="B")
    planner = ScriptedPlanner(
        [
            Decision(plugin="first"),
            Decision(plugin="second"),
            Decision(plugin=None),
        ]
    )
    registry = PluginRegistry()
    registry.register(first)
    registry.register(second)

    task = asyncio.run(
        DSHController(registry, planner=planner).run(
            TaskState(goal="two steps", max_iterations=2)
        )
    )

    assert first.calls == 1
    assert second.calls == 1
    assert planner.calls == [(0, None), (1, "A"), (2, "B")]
    assert task.iteration == 2
    assert task.status is TaskStatus.COMPLETED
    assert task.result == "B"
    assert task.last_invocation_result == "B"


def test_failure_stops_continuation_before_next_planner_decision() -> None:
    failing = RecordingPlugin("failing", error="failed A")
    second = RecordingPlugin("second", output="B")
    planner = ScriptedPlanner([Decision(plugin="failing"), Decision(plugin="second")])
    registry = PluginRegistry()
    registry.register(failing)
    registry.register(second)

    task = asyncio.run(
        DSHController(registry, planner=planner).run(TaskState(goal="failure"))
    )

    assert failing.calls == 1
    assert second.calls == 0
    assert len(planner.calls) == 1
    assert task.iteration == 1
    assert task.status is TaskStatus.FAILED


def test_timeout_stops_continuation_before_next_planner_decision() -> None:
    class SlowPlugin:
        name = "slow"

        async def execute(self, ctx, params):
            await asyncio.sleep(0.05)
            return PluginResult(success=True, output="late")

    second = RecordingPlugin("second", output="B")
    planner = ScriptedPlanner([Decision(plugin="slow"), Decision(plugin="second")])
    registry = PluginRegistry()
    registry.register(SlowPlugin())
    registry.register(second)

    task = asyncio.run(
        DSHController(
            registry,
            planner=planner,
        ).run(TaskState(goal="timeout", timeout_seconds=0.001))
    )

    assert second.calls == 0
    assert len(planner.calls) == 1
    assert task.iteration == 1
    assert task.status is TaskStatus.TIMED_OUT


def test_budget_exhaustion_does_not_execute_next_action_or_commit_result() -> None:
    first = RecordingPlugin("first", output="A")
    second = RecordingPlugin("second", output="B")
    third = RecordingPlugin("third", output="C")
    planner = ScriptedPlanner(
        [Decision(plugin="first"), Decision(plugin="second"), Decision(plugin="third")]
    )
    registry = PluginRegistry()
    for plugin in (first, second, third):
        registry.register(plugin)

    task = asyncio.run(
        DSHController(registry, planner=planner).run(
            TaskState(goal="budget", max_iterations=2)
        )
    )

    assert first.calls == 1
    assert second.calls == 1
    assert third.calls == 0
    assert task.iteration == 2
    assert task.status is TaskStatus.MAX_ITERATIONS
    assert task.result is None
    assert task.last_invocation_result == "B"


def test_terminal_decision_at_budget_boundary_completes_task() -> None:
    first = RecordingPlugin("first", output="A")
    second = RecordingPlugin("second", output="B")
    planner = ScriptedPlanner(
        [Decision(plugin="first"), Decision(plugin="second"), Decision(plugin=None)]
    )
    registry = PluginRegistry()
    registry.register(first)
    registry.register(second)

    task = asyncio.run(
        DSHController(registry, planner=planner).run(
            TaskState(goal="boundary", max_iterations=2)
        )
    )

    assert task.iteration == 2
    assert task.status is TaskStatus.COMPLETED
    assert task.result == "B"


def test_successful_none_output_is_not_used_as_no_invocation_signal() -> None:
    plugin = RecordingPlugin("none", output=None)
    planner = ScriptedPlanner([Decision(plugin="none"), Decision(plugin=None)])
    registry = PluginRegistry()
    registry.register(plugin)

    task = asyncio.run(
        DSHController(registry, planner=planner).run(TaskState(goal="none"))
    )

    assert plugin.calls == 1
    assert planner.calls == [(0, None), (1, None)]
    assert task.iteration == 1
    assert task.status is TaskStatus.COMPLETED
    assert task.result is None


def test_zero_budget_skips_initial_planner_evaluation() -> None:
    planner = ScriptedPlanner([])
    task = asyncio.run(
        DSHController(PluginRegistry(), planner=planner).run(
            TaskState(goal="zero", max_iterations=0)
        )
    )

    assert planner.calls == []
    assert task.iteration == 0
    assert task.status is TaskStatus.MAX_ITERATIONS


def test_initial_terminal_decision_is_safe_task_failure() -> None:
    planner = ScriptedPlanner([Decision(plugin=None)])
    task = asyncio.run(
        DSHController(PluginRegistry(), planner=planner).run(TaskState(goal="terminal"))
    )

    assert planner.calls == [(0, None)]
    assert task.iteration == 0
    assert task.status is TaskStatus.FAILED
    assert task.result is None
