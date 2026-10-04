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


def test_repository_inspection_defaults_to_one_read_only_iteration() -> None:
    task = TaskState(
        goal="inspect repository",
        task_kind=TaskKind.REPOSITORY_INSPECTION,
    )

    assert task.allow_workspace_write is False
    assert task.max_iterations == 1


def test_write_enabled_repository_inspection_is_rejected() -> None:
    with pytest.raises(ValueError, match="must be read-only"):
        TaskState(
            goal="inspect repository",
            task_kind=TaskKind.REPOSITORY_INSPECTION,
            allow_workspace_write=True,
        )


@pytest.mark.parametrize("max_iterations", [0, 2])
def test_repository_inspection_requires_exactly_one_iteration(
    max_iterations: int,
) -> None:
    with pytest.raises(ValueError, match="exactly 1 iteration"):
        TaskState(
            goal="inspect repository",
            task_kind=TaskKind.REPOSITORY_INSPECTION,
            max_iterations=max_iterations,
        )


def test_repository_change_requires_write_authority_and_two_iterations() -> None:
    task = TaskState(
        goal="change repository",
        task_kind=TaskKind.REPOSITORY_CHANGE,
        allow_workspace_write=True,
        max_iterations=2,
    )

    assert task.task_kind is TaskKind.REPOSITORY_CHANGE


def test_repository_change_without_write_authority_is_rejected() -> None:
    with pytest.raises(ValueError, match="require workspace write authority"):
        TaskState(
            goal="change repository",
            task_kind=TaskKind.REPOSITORY_CHANGE,
            max_iterations=2,
        )


def test_repository_change_with_one_iteration_is_rejected() -> None:
    with pytest.raises(ValueError, match="require at least 2 iterations"):
        TaskState(
            goal="change repository",
            task_kind=TaskKind.REPOSITORY_CHANGE,
            allow_workspace_write=True,
            max_iterations=1,
        )


def test_simple_planner_routes_repository_analysis_then_terminates() -> None:
    planner = SimplePlanner()
    task = TaskState(goal="inspect repository", task_kind=TaskKind.REPOSITORY_ANALYSIS)

    initial = planner.next_action(task)
    assert initial == Decision(plugin="codex", params={"prompt": task.goal})

    task.iteration = 1
    task.last_invocation_result = "bounded answer"
    assert planner.next_action(task).is_terminal


def test_simple_planner_routes_repository_change_to_codebuddy_then_codex() -> None:
    planner = SimplePlanner()
    task = TaskState(
        goal="replace the old implementation",
        task_kind=TaskKind.REPOSITORY_CHANGE,
        allow_workspace_write=True,
        max_iterations=2,
    )

    initial = planner.next_action(task)
    assert initial == Decision(
        plugin="codebuddy",
        params={"prompt": task.goal},
        allow_workspace_write=True,
    )

    task.iteration = 1
    task.last_invocation_result = "builder settled"
    verification = planner.next_action(task)
    assert verification.plugin == "codex"
    assert task.goal in verification.params["prompt"]
    assert "current workspace" in verification.params["prompt"]
    assert "Do not modify" in verification.params["prompt"]
    assert "independently verify" in verification.params["prompt"]

    task.iteration = 2
    task.last_invocation_result = "review\nDSH_VERIFICATION: PASS"
    terminal = planner.next_action(task)
    assert terminal.is_terminal
    assert terminal.terminal_success is True


def test_invocation_authority_can_narrow_but_cannot_escalate() -> None:
    class AuthorityPlugin:
        name = "authority"

        def __init__(self):
            self.authorities = []

        async def execute(self, ctx, params):
            self.authorities.append(ctx.allow_workspace_write)
            return PluginResult(success=True, output="done")

    def run_with(task, requested_authority):
        plugin = AuthorityPlugin()
        planner = ScriptedPlanner(
            [
                Decision(
                    plugin="authority",
                    allow_workspace_write=requested_authority,
                ),
                Decision(plugin=None),
            ]
        )
        registry = PluginRegistry()
        registry.register(plugin)
        result = asyncio.run(DSHController(registry, planner=planner).run(task))
        return result, plugin

    narrowed, narrowed_plugin = run_with(
        TaskState(
            goal="read after write",
            task_kind=TaskKind.REPOSITORY_CHANGE,
            allow_workspace_write=True,
            max_iterations=2,
        ),
        False,
    )
    inherited, inherited_plugin = run_with(
        TaskState(
            goal="inherit write authority",
            task_kind=TaskKind.REPOSITORY_CHANGE,
            allow_workspace_write=True,
            max_iterations=2,
        ),
        None,
    )
    ceiling, ceiling_plugin = run_with(TaskState(goal="read-only"), True)

    assert narrowed.status is TaskStatus.COMPLETED
    assert narrowed_plugin.authorities == [False]
    assert inherited.status is TaskStatus.COMPLETED
    assert inherited_plugin.authorities == [True]
    assert ceiling.status is TaskStatus.COMPLETED
    assert ceiling_plugin.authorities == [False]


@pytest.mark.parametrize(
    "verifier_output",
    [
        "DSH_VERIFICATION: PASS\nVerification actually failed.",
        "The report quotes DSH_VERIFICATION: PASS\nNo valid verdict supplied.",
        "Report\nDSH_VERIFICATION: PASS\nextra text after the verdict",
        "",
        None,
    ],
)
def test_verifier_requires_exact_final_non_empty_verdict_line(verifier_output) -> None:
    planner = SimplePlanner()
    task = TaskState(
        goal="change repository",
        task_kind=TaskKind.REPOSITORY_CHANGE,
        allow_workspace_write=True,
        max_iterations=2,
        iteration=2,
        last_invocation_result=verifier_output,
    )

    decision = planner.next_action(task)

    assert decision.is_terminal
    assert decision.terminal_success is False
    assert decision.terminal_error == "invalid verifier result"


def test_verifier_fail_marker_is_terminal_failure() -> None:
    planner = SimplePlanner()
    task = TaskState(
        goal="change repository",
        task_kind=TaskKind.REPOSITORY_CHANGE,
        allow_workspace_write=True,
        max_iterations=2,
        iteration=2,
        last_invocation_result="Issue found.\nDSH_VERIFICATION: FAIL",
    )

    decision = planner.next_action(task)

    assert decision.is_terminal
    assert decision.terminal_success is False
    assert decision.terminal_error == "Codex verification reported FAIL"


def test_verifier_pass_requires_only_final_non_empty_line_exact_match() -> None:
    planner = SimplePlanner()
    task = TaskState(
        goal="change repository",
        task_kind=TaskKind.REPOSITORY_CHANGE,
        allow_workspace_write=True,
        max_iterations=2,
        iteration=2,
        last_invocation_result="Report\n  DSH_VERIFICATION: PASS  \n",
    )

    decision = planner.next_action(task)

    assert decision == Decision(plugin=None)


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


def test_repository_change_completes_only_after_codex_verification_pass() -> None:
    codebuddy = RecordingPlugin("codebuddy", output="builder settled")
    codex = RecordingPlugin(
        "codex", output="workspace verified\nDSH_VERIFICATION: PASS"
    )
    registry = PluginRegistry()
    registry.register(codebuddy)
    registry.register(codex)

    task = asyncio.run(
        DSHController(registry).run(
            TaskState(
                goal="change repository",
                task_kind=TaskKind.REPOSITORY_CHANGE,
                allow_workspace_write=True,
                max_iterations=2,
            )
        )
    )

    assert codebuddy.calls == 1
    assert codex.calls == 1
    assert task.iteration == 2
    assert task.status is TaskStatus.COMPLETED
    assert task.result == "workspace verified\nDSH_VERIFICATION: PASS"


def test_repository_change_verifier_fail_becomes_terminal_task_failure() -> None:
    codebuddy = RecordingPlugin("codebuddy", output="builder settled")
    codex = RecordingPlugin("codex", output="issue\nDSH_VERIFICATION: FAIL")
    registry = PluginRegistry()
    registry.register(codebuddy)
    registry.register(codex)

    task = asyncio.run(
        DSHController(registry).run(
            TaskState(
                goal="change repository",
                task_kind=TaskKind.REPOSITORY_CHANGE,
                allow_workspace_write=True,
                max_iterations=2,
            )
        )
    )

    assert codebuddy.calls == 1
    assert codex.calls == 1
    assert task.iteration == 2
    assert task.status is TaskStatus.FAILED
    assert task.result is None
    assert task.error == "Codex verification reported FAIL"


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
