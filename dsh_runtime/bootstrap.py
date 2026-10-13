"""Minimal production composition and caller seams for DSH Runtime."""

from __future__ import annotations

import os
from pathlib import Path

from dsh_runtime.codex_runtime_home import CodexRuntimeHome, ManagedCodexPlugin
from dsh_runtime.controller import DSHController
from dsh_runtime.planner import SimplePlanner
from dsh_runtime.plugins.codebuddy import (
    CodeBuddyPlugin,
    MAX_STREAM_CHARS_ENV,
    MAX_STREAM_CHARS_HARD_LIMIT,
)
from dsh_runtime.plugins.echo import EchoPlugin
from dsh_runtime.runtime.registry import PluginRegistry
from dsh_runtime.state import TaskKind, TaskState
from dsh_runtime.workspace.manager import WorkspaceManager


CODEBUDDY_QUALIFICATION_TRACE_DIR_ENV = "DSH_CODEBUDDY_QUALIFICATION_TRACE_DIR"
CODEBUDDY_MAX_STREAM_CHARS_ENV = MAX_STREAM_CHARS_ENV
CODEX_QUALIFICATION_TRACE_DIR_ENV = "DSH_CODEX_QUALIFICATION_TRACE_DIR"


def _qualification_trace_dir_from_environment(environment_name: str) -> Path | None:
    """Resolve the explicit, opt-in worker trace sink for this process."""

    raw_path = os.environ.get(environment_name)
    if raw_path in (None, ""):
        return None
    path = Path(raw_path)
    if not path.is_absolute():
        raise ValueError(
            f"{environment_name} must be an absolute path"
        )
    return path


def _codebuddy_max_stream_chars_from_environment() -> int | None:
    """Read an opt-in bounded CodeBuddy stream limit without widening final output."""

    raw_limit = os.environ.get(CODEBUDDY_MAX_STREAM_CHARS_ENV)
    if raw_limit in (None, ""):
        return None
    if not raw_limit.isascii() or not raw_limit.isdecimal():
        raise ValueError(f"{CODEBUDDY_MAX_STREAM_CHARS_ENV} must be a positive integer")
    limit = int(raw_limit)
    if not 1 <= limit <= MAX_STREAM_CHARS_HARD_LIMIT:
        raise ValueError(
            f"{CODEBUDDY_MAX_STREAM_CHARS_ENV} must be between "
            f"1 and {MAX_STREAM_CHARS_HARD_LIMIT}"
        )
    return limit


def build_controller(
    *,
    workspace_manager: WorkspaceManager | None = None,
    codex_runtime_home: CodexRuntimeHome | None = None,
) -> DSHController:
    """Assemble Runtime owners and the opt-in qualification trace capability."""

    runtime_home = codex_runtime_home or CodexRuntimeHome.from_environment()
    registry = PluginRegistry()
    registry.register(EchoPlugin())
    registry.register(
        ManagedCodexPlugin(
            runtime_home,
            qualification_trace_dir=_qualification_trace_dir_from_environment(
                CODEX_QUALIFICATION_TRACE_DIR_ENV
            )
        )
    )
    registry.register(
        CodeBuddyPlugin(
            max_stream_chars=_codebuddy_max_stream_chars_from_environment(),
            qualification_trace_dir=_qualification_trace_dir_from_environment(
                CODEBUDDY_QUALIFICATION_TRACE_DIR_ENV
            )
        )
    )
    return DSHController(
        registry,
        planner=SimplePlanner(),
        workspace_manager=workspace_manager or WorkspaceManager(),
    )


def build_repository_change_task(goal: str, workspace: str) -> TaskState:
    """Construct the approved caller intent for an M5 repository change."""

    return TaskState(
        goal=goal,
        workspace_id=workspace,
        task_kind=TaskKind.REPOSITORY_CHANGE,
        allow_workspace_write=True,
        max_iterations=2,
        timeout_seconds=900.0,
    )


def build_repository_inspection_task(goal: str, workspace: str) -> TaskState:
    """Construct the bounded read-only repository inspection task."""

    return TaskState(
        goal=goal,
        workspace_id=workspace,
        task_kind=TaskKind.REPOSITORY_INSPECTION,
        allow_workspace_write=False,
        max_iterations=1,
        timeout_seconds=900.0,
    )
