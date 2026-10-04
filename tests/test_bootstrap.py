import pytest

from dsh_runtime.bootstrap import (
    CODEX_QUALIFICATION_TRACE_DIR_ENV,
    build_controller,
    build_repository_change_task,
    build_repository_inspection_task,
)
from dsh_runtime.bootstrap import CODEBUDDY_QUALIFICATION_TRACE_DIR_ENV
from dsh_runtime.codex_runtime_home import CodexRuntimeHome
from dsh_runtime.controller import DSHController
from dsh_runtime.plugins.codebuddy import CodeBuddyPlugin
from dsh_runtime.plugins.codebuddy import SAFE_EVENT_TRACE_DIR_ENV
from dsh_runtime.plugins.codex import CodexPlugin
from dsh_runtime.plugins.echo import EchoPlugin
from dsh_runtime.runtime.registry import PluginRegistry
from dsh_runtime.state import TaskKind, TaskState


def test_production_composition_registers_builtin_capabilities() -> None:
    controller = build_controller()
    registry = controller.executor.registry

    assert isinstance(controller, DSHController)
    assert isinstance(registry.get("echo"), EchoPlugin)
    assert isinstance(registry.get("codex"), CodexPlugin)
    assert isinstance(registry.get("codebuddy"), CodeBuddyPlugin)


def test_production_composition_keeps_trace_disabled_without_explicit_environment(
    monkeypatch,
) -> None:
    monkeypatch.delenv(CODEBUDDY_QUALIFICATION_TRACE_DIR_ENV, raising=False)
    monkeypatch.delenv(SAFE_EVENT_TRACE_DIR_ENV, raising=False)

    controller = build_controller()

    codebuddy = controller.executor.registry.get("codebuddy")
    assert isinstance(codebuddy, CodeBuddyPlugin)
    assert codebuddy.qualification_trace_dir is None
    assert codebuddy.safe_event_trace_dir is None
    assert controller.executor.registry.get("codex").qualification_trace_dir is None


def test_explicit_safe_codebuddy_trace_path_reaches_codebuddy_plugin(
    monkeypatch, tmp_path
) -> None:
    trace_dir = tmp_path / "safe-codebuddy-events"
    monkeypatch.setenv(SAFE_EVENT_TRACE_DIR_ENV, str(trace_dir))

    controller = build_controller()

    codebuddy = controller.executor.registry.get("codebuddy")
    assert isinstance(codebuddy, CodeBuddyPlugin)
    assert codebuddy.safe_event_trace_dir == trace_dir
    assert codebuddy.max_turns == 12


def test_explicit_codex_trace_path_reaches_codex_plugin(monkeypatch, tmp_path) -> None:
    trace_dir = tmp_path / "capture" / "codex"
    monkeypatch.setenv(CODEX_QUALIFICATION_TRACE_DIR_ENV, str(trace_dir))

    controller = build_controller()

    codex = controller.executor.registry.get("codex")
    assert isinstance(codex, CodexPlugin)
    assert codex.qualification_trace_dir == trace_dir


def test_bootstrap_injects_managed_codex_home_environment(tmp_path) -> None:
    runtime_home = CodexRuntimeHome(tmp_path / "dsh-state")

    controller = build_controller(codex_runtime_home=runtime_home)

    codex = controller.executor.registry.get("codex")
    assert isinstance(codex, CodexPlugin)
    assert codex._environment_overlay == runtime_home.environment_overlay
    assert codex._environment_overlay["CODEX_HOME"] == str(
        runtime_home.codex_home
    )
    assert codex._environment_overlay["CODEX_SQLITE_HOME"] == str(
        runtime_home.codex_sqlite_home
    )


def test_relative_codex_trace_path_is_rejected_before_worker_execution(monkeypatch) -> None:
    monkeypatch.setenv(CODEX_QUALIFICATION_TRACE_DIR_ENV, "relative-trace")

    with pytest.raises(ValueError, match="must be an absolute path"):
        build_controller()


def test_explicit_absolute_trace_path_reaches_codebuddy_plugin(
    monkeypatch, tmp_path
) -> None:
    trace_dir = tmp_path / "capture" / "codebuddy"
    monkeypatch.setenv(CODEBUDDY_QUALIFICATION_TRACE_DIR_ENV, str(trace_dir))

    controller = build_controller()

    codebuddy = controller.executor.registry.get("codebuddy")
    assert isinstance(codebuddy, CodeBuddyPlugin)
    assert codebuddy.qualification_trace_dir == trace_dir
    assert codebuddy.max_turns == 12


def test_relative_trace_path_is_rejected_before_worker_execution(monkeypatch) -> None:
    monkeypatch.setenv(CODEBUDDY_QUALIFICATION_TRACE_DIR_ENV, "relative-trace")

    with pytest.raises(ValueError, match="must be an absolute path"):
        build_controller()


def test_composition_preserves_registry_duplicate_error_semantics() -> None:
    registry = PluginRegistry()
    registry.register(EchoPlugin())

    try:
        registry.register(EchoPlugin())
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("duplicate registration should fail fast")


def test_repository_change_caller_builds_existing_task_state() -> None:
    goal = "replace the old implementation"
    workspace = "workspace.project"

    task = build_repository_change_task(goal, workspace)

    assert isinstance(task, TaskState)
    assert task.goal == goal
    assert task.workspace_id == workspace
    assert task.task_kind is TaskKind.REPOSITORY_CHANGE
    assert task.allow_workspace_write is True
    assert task.max_iterations == 2
    assert task.timeout_seconds == 900.0


def test_repository_inspection_caller_uses_real_worker_timeout_read_only() -> None:
    task = build_repository_inspection_task(
        "inspect the runtime",
        "workspace.project",
    )

    assert task.task_kind is TaskKind.REPOSITORY_INSPECTION
    assert task.allow_workspace_write is False
    assert task.max_iterations == 1
    assert task.timeout_seconds == 900.0


def test_unrelated_task_state_keeps_global_timeout_default() -> None:
    task = TaskState(goal="inspect the runtime")

    assert task.task_kind is TaskKind.DEFAULT
    assert task.timeout_seconds == 30.0
