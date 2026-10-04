import asyncio
import logging
from pathlib import Path
from unittest.mock import patch

from dsh_runtime.bootstrap import build_controller, build_repository_change_task
from dsh_runtime.codex_runtime_home import CodexRuntimeHome
from dsh_runtime.plugins.codebuddy import CodeBuddyPlugin
from dsh_runtime.plugins.codex import CodexPlugin
from dsh_runtime.runtime.plugin import PluginResult
from dsh_runtime.state import TaskStatus
from dsh_runtime.workspace.manager import Workspace, WorkspaceManager


class _DeterministicReadyRuntimeHome(CodexRuntimeHome):
    """Keep legacy workflow tests on the pre-existing fake Codex seam."""

    def require_execution_ready(self):
        return self


def _controller_for(workspace: Path):
    manager = WorkspaceManager(
        {"workspace.m5": Workspace("workspace.m5", workspace)}
    )
    runtime_home = _DeterministicReadyRuntimeHome(workspace / ".dsh-state")
    runtime_home.prepare()
    return build_controller(
        workspace_manager=manager,
        codex_runtime_home=runtime_home,
    )


def test_golden_repository_change_runs_codebuddy_then_codex_in_same_workspace(
    tmp_path: Path,
) -> None:
    goal = "change the repository target"
    target = tmp_path / "target.txt"
    target.write_text("before", encoding="utf-8")
    events: list[str] = []
    builder_observations: list[tuple[str | None, bool, dict]] = []
    verifier_observations: list[tuple[str | None, bool, str]] = []

    async def fake_codebuddy(self, ctx, params):
        events.append("codebuddy")
        builder_observations.append((ctx.cwd, ctx.allow_workspace_write, params))
        Path(ctx.cwd, "target.txt").write_text("changed", encoding="utf-8")
        return PluginResult(success=True, output="CodeBuddy changed target.txt")

    async def fake_codex(self, ctx, params):
        events.append("codex")
        observed = Path(ctx.cwd, "target.txt").read_text(encoding="utf-8")
        verifier_observations.append((ctx.cwd, ctx.allow_workspace_write, observed))
        return PluginResult(
            success=True,
            output=f"observed {observed}\nDSH_VERIFICATION: PASS",
        )

    controller = _controller_for(tmp_path)
    task = build_repository_change_task(goal, "workspace.m5")
    planner_decisions = []
    original_next_action = controller.planner.next_action

    def observe_planner(task_state):
        decision = original_next_action(task_state)
        planner_decisions.append((task_state.iteration, decision))
        return decision

    with (
        patch.object(CodeBuddyPlugin, "execute", new=fake_codebuddy),
        patch.object(CodexPlugin, "execute", new=fake_codex),
        patch.object(controller.planner, "next_action", side_effect=observe_planner),
    ):
        result = asyncio.run(controller.run(task))

    assert events == ["codebuddy", "codex"]
    assert builder_observations == [
        (str(tmp_path.resolve()), True, {"prompt": goal})
    ]
    assert verifier_observations == [
        (str(tmp_path.resolve()), False, "changed")
    ]
    assert planner_decisions[0][0] == 0
    assert planner_decisions[0][1].plugin == "codebuddy"
    assert planner_decisions[0][1].params == {"prompt": goal}
    assert planner_decisions[1][0] == 1
    assert planner_decisions[1][1].plugin == "codex"
    assert planner_decisions[2][0] == 2
    assert planner_decisions[2][1].is_terminal
    assert result is task
    assert task.iteration == 2
    assert task.status is TaskStatus.COMPLETED
    assert task.last_invocation_result == "observed changed\nDSH_VERIFICATION: PASS"
    assert task.result == task.last_invocation_result


def test_codebuddy_success_then_codex_fail_is_terminal_without_repair(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target.txt"
    target.write_text("before", encoding="utf-8")
    events: list[str] = []
    verifier_observations: list[tuple[str | None, bool, str]] = []

    async def fake_codebuddy(self, ctx, params):
        events.append("codebuddy")
        Path(ctx.cwd, "target.txt").write_text("changed", encoding="utf-8")
        return PluginResult(success=True, output="builder settled")

    async def fake_codex(self, ctx, params):
        events.append("codex")
        observed = Path(ctx.cwd, "target.txt").read_text(encoding="utf-8")
        verifier_observations.append((ctx.cwd, ctx.allow_workspace_write, observed))
        return PluginResult(
            success=True,
            output=f"observed {observed}\nDSH_VERIFICATION: FAIL",
        )

    controller = _controller_for(tmp_path)
    task = build_repository_change_task("change target", "workspace.m5")

    with (
        patch.object(CodeBuddyPlugin, "execute", new=fake_codebuddy),
        patch.object(CodexPlugin, "execute", new=fake_codex),
    ):
        asyncio.run(controller.run(task))

    assert events == ["codebuddy", "codex"]
    assert verifier_observations == [
        (str(tmp_path.resolve()), False, "changed")
    ]
    assert task.iteration == 2
    assert task.status is TaskStatus.FAILED
    assert task.result is None
    assert task.error == "Codex verification reported FAIL"


def test_codebuddy_failure_short_circuits_before_codex(tmp_path: Path) -> None:
    events: list[str] = []

    async def fake_codebuddy(self, ctx, params):
        events.append("codebuddy")
        return PluginResult(success=False, error="native tool failed")

    async def unexpected_codex(self, ctx, params):
        events.append("codex")
        raise AssertionError("Codex must not run after CodeBuddy failure")

    controller = _controller_for(tmp_path)
    task = build_repository_change_task("fail the builder", "workspace.m5")

    with (
        patch.object(CodeBuddyPlugin, "execute", new=fake_codebuddy),
        patch.object(CodexPlugin, "execute", new=unexpected_codex),
    ):
        asyncio.run(controller.run(task))

    assert events == ["codebuddy"]
    assert task.iteration == 1
    assert task.status is TaskStatus.FAILED
    assert task.result is None
    assert task.error == "native tool failed"


def test_codebuddy_timeout_does_not_continue_to_codex(tmp_path: Path) -> None:
    events: list[str] = []

    async def slow_codebuddy(self, ctx, params):
        events.append("codebuddy")
        await asyncio.sleep(0.2)
        return PluginResult(success=True, output="too late")

    async def unexpected_codex(self, ctx, params):
        events.append("codex")
        raise AssertionError("Codex must not run after timeout")

    controller = _controller_for(tmp_path)
    task = build_repository_change_task("timeout the builder", "workspace.m5")
    task.timeout_seconds = 0.05

    with (
        patch.object(CodeBuddyPlugin, "execute", new=slow_codebuddy),
        patch.object(CodexPlugin, "execute", new=unexpected_codex),
    ):
        asyncio.run(controller.run(task))

    assert events == ["codebuddy"]
    assert task.iteration == 1
    assert task.status is TaskStatus.TIMED_OUT
    assert task.error == "plugin execution timed out"
    assert task.result is None


def test_codebuddy_timeout_cleanup_error_remains_observable(
    tmp_path: Path, caplog
) -> None:
    events: list[str] = []
    caplog.set_level(logging.INFO, logger="dsh_runtime")

    async def codebuddy_with_cleanup_failure(self, ctx, params):
        events.append("codebuddy")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise RuntimeError("deterministic cleanup failure")

    async def unexpected_codex(self, ctx, params):
        events.append("codex")
        raise AssertionError("Codex must not run after timeout cleanup")

    controller = _controller_for(tmp_path)
    task = build_repository_change_task(
        "observe timeout cleanup", "workspace.m5"
    )
    task.timeout_seconds = 0.05

    with (
        patch.object(
            CodeBuddyPlugin,
            "execute",
            new=codebuddy_with_cleanup_failure,
        ),
        patch.object(CodexPlugin, "execute", new=unexpected_codex),
    ):
        asyncio.run(controller.run(task))

    assert events == ["codebuddy"]
    assert task.iteration == 1
    assert task.status is TaskStatus.TIMED_OUT
    assert task.result is None
    assert any(
        "cleanup_error" in record.getMessage()
        and "deterministic cleanup failure" in record.getMessage()
        for record in caplog.records
    )
