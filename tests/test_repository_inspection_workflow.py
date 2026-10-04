import asyncio
from pathlib import Path

from dsh_runtime.bootstrap import build_repository_inspection_task
from dsh_runtime.controller import DSHController
from dsh_runtime.planner import SimplePlanner
from dsh_runtime.runtime.plugin import PluginResult
from dsh_runtime.runtime.registry import PluginRegistry
from dsh_runtime.state import TaskKind, TaskStatus
from dsh_runtime.workspace.manager import Workspace, WorkspaceManager


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


class RecordingPlugin:
    def __init__(
        self,
        name: str,
        *,
        output: str | None = None,
        error: str | None = None,
    ):
        self.name = name
        self.output = output
        self.error = error
        self.calls = 0
        self.contexts = []
        self.params = []

    async def execute(self, ctx, params):
        self.calls += 1
        self.contexts.append(ctx)
        self.params.append(params)
        if self.error is not None:
            return PluginResult(success=False, error=self.error)
        return PluginResult(success=True, output=self.output)


class RecordingPlanner(SimplePlanner):
    def __init__(self):
        self.calls = []

    def next_action(self, task):
        decision = super().next_action(task)
        self.calls.append((task.iteration, decision.plugin, decision.is_terminal))
        return decision


def _controller_for(workspace: Path, planner: RecordingPlanner, *plugins):
    registry = PluginRegistry()
    for plugin in plugins:
        registry.register(plugin)
    manager = WorkspaceManager(
        {"workspace.inspection": Workspace("workspace.inspection", workspace)}
    )
    return DSHController(registry, planner=planner, workspace_manager=manager)


def test_repository_inspection_is_one_codex_read_only_action_without_mutation(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "runtime.py").write_text("controller", encoding="utf-8")
    (tmp_path / "README.md").write_text("runtime notes", encoding="utf-8")
    before = _snapshot(tmp_path)
    report = "The runtime loop is owned by the controller. Evidence: src/runtime.py."
    codex = RecordingPlugin("codex", output=report)
    codebuddy = RecordingPlugin("codebuddy", output="unexpected")
    planner = RecordingPlanner()
    task = build_repository_inspection_task(
        "Trace the runtime loop and report the relevant evidence.",
        "workspace.inspection",
    )

    result = asyncio.run(
        _controller_for(tmp_path, planner, codex, codebuddy).run(task)
    )

    assert result is task
    assert task.task_kind is TaskKind.REPOSITORY_INSPECTION
    assert task.allow_workspace_write is False
    assert task.max_iterations == 1
    assert task.timeout_seconds == 900.0
    assert codex.calls == 1
    assert codebuddy.calls == 0
    assert codex.contexts[0].cwd == str(tmp_path.resolve())
    assert codex.contexts[0].allow_workspace_write is False
    assert codex.params[0]["prompt"].startswith(
        "Inspect the current logical workspace/repository"
    )
    assert task.goal in codex.params[0]["prompt"]
    assert "DSH_VERIFICATION" not in codex.params[0]["prompt"]
    assert planner.calls == [(0, "codex", False), (1, None, True)]
    assert task.iteration == 1
    assert task.status is TaskStatus.COMPLETED
    assert task.result == report
    assert task.last_invocation_result == report
    assert task.error is None
    assert _snapshot(tmp_path) == before


def test_repository_inspection_codex_failure_does_not_fallback_or_retry(
    tmp_path: Path,
) -> None:
    (tmp_path / "existing.txt").write_text("stable", encoding="utf-8")
    before = _snapshot(tmp_path)
    codex = RecordingPlugin("codex", error="bounded inspection failure")
    codebuddy = RecordingPlugin("codebuddy", output="unexpected")
    planner = RecordingPlanner()
    task = build_repository_inspection_task(
        "Inspect the repository and report the relevant evidence.",
        "workspace.inspection",
    )

    asyncio.run(_controller_for(tmp_path, planner, codex, codebuddy).run(task))

    assert codex.calls == 1
    assert codebuddy.calls == 0
    assert planner.calls == [(0, "codex", False)]
    assert task.iteration == 1
    assert task.status is TaskStatus.FAILED
    assert task.result is None
    assert task.last_invocation_result is None
    assert task.error == "bounded inspection failure"
    assert _snapshot(tmp_path) == before
