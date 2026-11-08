import asyncio
import hashlib
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from dsh_runtime.bootstrap import build_controller, build_repository_change_task
from dsh_runtime.codex_runtime_home import CodexRuntimeHome
from dsh_runtime.entrypoint import _serialize_task
from dsh_runtime.plugins.codebuddy import CodeBuddyPlugin
from dsh_runtime.plugins.codex import CodexPlugin
from dsh_runtime.role_config import RoleConfig, RoleSelection
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
    with patch(
        "dsh_runtime.plugins.codebuddy._default_command",
        return_value=("test-only-codebuddy",),
    ):
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
    monkeypatch,
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
    monkeypatch.setenv("DSH_RUNTIME_RUN_ID", "dsh-runtime-fixture")
    monkeypatch.delenv("DSH_RUNTIME_INVOCATION_EVIDENCE", raising=False)
    assert "invocation_evidence" not in _serialize_task(task)
    monkeypatch.setenv("DSH_RUNTIME_INVOCATION_EVIDENCE", "1")
    output = b"observed changed\nDSH_VERIFICATION: FAIL"
    assert _serialize_task(task)["invocation_evidence"] == {
        "version": 1,
        "run_id": "dsh-runtime-fixture",
        "task_id": task.task_id,
        "workspace_id": task.workspace_id,
        "role": "reviewer",
        "adapter": "codex",
        "invocation_index": 2,
        "allow_workspace_write": False,
        "stop_reason": "completed",
        "success": True,
        "cleanup_ok": True,
        "output_bytes": len(output),
        "output_sha256": hashlib.sha256(output).hexdigest(),
    }


@pytest.mark.parametrize("timeout", [False, True])
def test_failed_reviewer_does_not_bind_the_previous_worker_output(
    tmp_path: Path, timeout: bool,
) -> None:
    worker_output = "worker finished\nDSH_VERIFICATION: PASS"

    async def fake_codebuddy(self, ctx, params):
        return PluginResult(success=True, output=worker_output)

    async def fake_codex(self, ctx, params):
        if timeout:
            await asyncio.Event().wait()
        return PluginResult(success=False, error="reviewer unavailable")

    controller = _controller_for(tmp_path)
    task = build_repository_change_task("review target", "workspace.m5")
    task.timeout_seconds = 0.05
    with (
        patch.object(CodeBuddyPlugin, "execute", new=fake_codebuddy),
        patch.object(CodexPlugin, "execute", new=fake_codex),
    ):
        asyncio.run(controller.run(task))

    assert task.status is (TaskStatus.TIMED_OUT if timeout else TaskStatus.FAILED)
    assert task.last_invocation_result == worker_output
    evidence = task.invocation_evidence
    assert evidence is not None
    assert evidence.role == "reviewer"
    assert evidence.invocation_index == 2
    assert evidence.stop_reason == ("timed_out" if timeout else "failed")
    assert evidence.output_bytes is None
    assert evidence.output_sha256 is None
    assert task.model_observations == []


def test_codex_model_observations_keep_both_phases(tmp_path: Path, monkeypatch) -> None:
    async def fake_codex(self, ctx, params):
        if ctx.allow_workspace_write:
            assert params["model"] == "worker-request"
            return PluginResult(True, "worker settled", reported_model="worker-return")
        assert "model" not in params
        return PluginResult(True, "DSH_VERIFICATION: PASS", reported_model="review-return")

    controller = _controller_for(tmp_path)
    controller.planner.roles = RoleConfig(
        worker=RoleSelection("codex", "worker-request"),
        reviewer=RoleSelection("codex"),
        inspector=RoleSelection("codex"),
    )
    task = build_repository_change_task("review target", "workspace.m5")
    with patch.object(CodexPlugin, "execute", new=fake_codex):
        asyncio.run(controller.run(task))
    monkeypatch.setenv("DSH_RUNTIME_RUN_ID", "dsh-runtime-fixture")
    monkeypatch.delenv("DSH_RUNTIME_INVOCATION_EVIDENCE", raising=False)
    assert "model_observations" not in _serialize_task(task)
    monkeypatch.setenv("DSH_RUNTIME_INVOCATION_EVIDENCE", "1")
    assert task.status is TaskStatus.COMPLETED
    assert _serialize_task(task)["model_observations"] == {
        "version": 1, "run_id": "dsh-runtime-fixture",
        "task_id": task.task_id, "workspace_id": task.workspace_id,
        "entries": [
            {"role": "worker", "adapter": "codex", "invocation_index": 1,
             "requested_model": "worker-request", "reported_model": "worker-return"},
            {"role": "reviewer", "adapter": "codex", "invocation_index": 2,
             "requested_model": None, "reported_model": "review-return"},
        ],
    }


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
