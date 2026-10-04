"""One-shot real-host adapter for the M7-B2 DeepSeekHarness qualification.

This module is test support only.  It binds the caller-supplied disposable
workspace to the existing production bootstrap and serializes the real
terminal TaskState.  It deliberately does not replace, wrap, or route either
production provider plugin.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dsh_runtime.bootstrap import build_controller, build_repository_change_task
from dsh_runtime.observability.logger import logger as runtime_logger
from dsh_runtime.plugins.codebuddy import CodeBuddyPlugin
from dsh_runtime.plugins.codex import CodexPlugin
from dsh_runtime.runtime.plugin import ExecutionContext
from dsh_runtime.state import TaskState
from dsh_runtime.workspace.manager import Workspace, WorkspaceManager


_OBSERVATION_ENV = "M7_B2_OBSERVATION_PATH"
_OBSERVATIONS: dict[str, Any] = {}
_PROFILED_FRAMES: set[tuple[str, int]] = set()


def _observation_payload() -> dict[str, Any]:
    return {
        "kind": "m7_b2_real_host_observation",
        **_OBSERVATIONS,
    }


def _persist_observation() -> None:
    path = os.environ.get(_OBSERVATION_ENV)
    if path is None:
        return
    Path(path).write_text(
        json.dumps(_observation_payload(), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _workspace_snapshot(cwd: str) -> list[str]:
    return sorted(path.name for path in Path(cwd).iterdir())


class _ExecutionTraceHandler(logging.Handler):
    """Capture existing runtime JSON events without changing production logging."""

    def __init__(self, workspace_path: Path) -> None:
        super().__init__()
        self.workspace_path = workspace_path
        self.events: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload = json.loads(record.getMessage())
        except (TypeError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        self.events.append(payload)
        event = payload.get("event")
        plugin = payload.get("plugin")
        if event == "plugin_started" and plugin == "codex":
            _OBSERVATIONS["workspace_before_codex"] = _workspace_snapshot(
                str(self.workspace_path)
            )
        elif event == "plugin_completed" and plugin == "codebuddy":
            _OBSERVATIONS["workspace_after_codebuddy"] = _workspace_snapshot(
                str(self.workspace_path)
            )
        elif event == "plugin_completed" and plugin == "codex":
            _OBSERVATIONS["workspace_after_codex"] = _workspace_snapshot(
                str(self.workspace_path)
            )


def _command_basename(plugin: object) -> list[str]:
    command = getattr(plugin, "_command", ())
    if not isinstance(command, tuple):
        return []
    return [Path(str(part)).name for part in command]


def _implementation_evidence(plugin: object) -> dict[str, Any]:
    execute = getattr(type(plugin), "execute")
    return {
        "class": f"{type(plugin).__module__}.{type(plugin).__qualname__}",
        "execute": f"{execute.__module__}.{execute.__qualname__}",
        "command_basename": _command_basename(plugin),
    }


def _profile_real_contexts(frame: Any, event: str, arg: Any) -> None:
    del arg
    if event != "call" or frame.f_code.co_name != "execute":
        return
    source = Path(frame.f_code.co_filename).name
    plugin = {
        "codebuddy.py": "codebuddy",
        "codex.py": "codex",
    }.get(source)
    if plugin is None:
        return
    ctx = frame.f_locals.get("ctx")
    if not isinstance(ctx, ExecutionContext):
        return
    frame_key = (plugin, id(frame))
    if frame_key in _PROFILED_FRAMES:
        return
    _PROFILED_FRAMES.add(frame_key)
    contexts = _OBSERVATIONS.setdefault("real_plugin_contexts", [])
    contexts.append(
        {
            "plugin": plugin,
            "cwd": ctx.cwd,
            "goal": ctx.goal,
            "allow_workspace_write": ctx.allow_workspace_write,
        }
    )


def _run_real_host(request: dict[str, Any]) -> TaskState:
    _OBSERVATIONS.clear()
    _PROFILED_FRAMES.clear()
    goal = request.get("goal")
    workspace_id = request.get("workspace_id")
    workspace_path = request.get("workspace_path")
    if not all(
        isinstance(value, str) and value.strip()
        for value in (goal, workspace_id, workspace_path)
    ):
        raise ValueError("goal, workspace_id, and workspace_path must be non-empty strings")

    workspace = Path(workspace_path).resolve()
    if not workspace.exists() or not workspace.is_dir():
        raise ValueError("workspace_path must be an existing directory")
    _OBSERVATIONS["workspace_before"] = _workspace_snapshot(str(workspace))

    manager = WorkspaceManager({workspace_id: Workspace(workspace_id, workspace)})
    controller = build_controller(workspace_manager=manager)
    registry = controller.executor.registry
    codebuddy = registry.get("codebuddy")
    codex = registry.get("codex")
    _OBSERVATIONS["implementations"] = {
        "codebuddy": _implementation_evidence(codebuddy),
        "codex": _implementation_evidence(codex),
    }

    task = build_repository_change_task(goal, workspace_id)
    _OBSERVATIONS["caller_contract"] = {
        "task_kind": task.task_kind.value,
        "allow_workspace_write": task.allow_workspace_write,
        "max_iterations": task.max_iterations,
        "timeout_seconds": task.timeout_seconds,
    }
    trace_handler = _ExecutionTraceHandler(workspace)
    previous_log_level = runtime_logger.level
    runtime_logger.setLevel(logging.INFO)
    runtime_logger.addHandler(trace_handler)
    previous_profile = sys.getprofile()
    sys.setprofile(_profile_real_contexts)
    try:
        terminal = asyncio.run(controller.run(task))
        _OBSERVATIONS["runtime_events"] = trace_handler.events
        return terminal
    finally:
        sys.setprofile(previous_profile)
        runtime_logger.removeHandler(trace_handler)
        runtime_logger.setLevel(previous_log_level)


def _serialize_task(task: TaskState) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "task_kind": task.task_kind.value,
        "workspace_id": task.workspace_id,
        "status": task.status.value,
        "iteration": task.iteration,
        "result": task.result,
        "error": task.error,
        "last_invocation_result": task.last_invocation_result,
    }


def _transport_failure(message: str) -> int:
    sys.stderr.write(f"m7 python real-host adapter transport failure: {message}\n")
    return 2


def main() -> int:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("request must be a JSON object")
        captured_stdout = io.StringIO()
        with redirect_stdout(captured_stdout):
            terminal = _run_real_host(request)
        if captured_stdout.getvalue():
            raise RuntimeError("unexpected adapter output reached captured stdout")
        _persist_observation()
        sys.stdout.write(
            json.dumps(_serialize_task(terminal), ensure_ascii=False, separators=(",", ":"))
        )
        sys.stdout.write("\n")
        sys.stdout.flush()
        return 0
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return _transport_failure(str(exc))
    except Exception as exc:  # pragma: no cover - transport safety net
        return _transport_failure(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
