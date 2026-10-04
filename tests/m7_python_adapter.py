"""One-shot JSON adapter for the deterministic M7-B1 harness bridge.

This module is test support only.  It delegates task semantics and workflow
ownership to the existing production bootstrap and controller.
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

# Running a file path (rather than ``python -m``) puts only ``tests/`` on
# sys.path.  Make the repository root explicit so the adapter remains a
# self-contained one-shot child process.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dsh_runtime.bootstrap import build_controller, build_repository_change_task
from dsh_runtime.observability.logger import logger as runtime_logger
from dsh_runtime.plugins.codebuddy import CodeBuddyPlugin
from dsh_runtime.plugins.codex import CodexPlugin
from dsh_runtime.runtime.plugin import ExecutionContext, PluginResult
from dsh_runtime.state import TaskState
from dsh_runtime.workspace.manager import Workspace, WorkspaceManager


_MUTATION_NAME = "m7_full_flow.txt"
_MUTATION_CONTENT = "DSH_M7_DETERMINISTIC_FULL_FLOW"
_OBSERVATIONS: dict[str, Any] = {}


def _observation_payload() -> dict[str, Any]:
    return {
        "kind": "m7_b1_test_observation",
        **_OBSERVATIONS,
    }


def _persist_observation() -> None:
    path = os.environ.get("M7_B1_OBSERVATION_PATH")
    if path is None:
        return
    Path(path).write_text(
        json.dumps(_observation_payload(), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _workspace_snapshot(cwd: str) -> list[str]:
    return sorted(path.name for path in Path(cwd).iterdir())


class _ExecutionTraceHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload = json.loads(record.getMessage())
        except (TypeError, json.JSONDecodeError):
            return
        if isinstance(payload, dict):
            self.events.append(payload)


def _append_external_invocation(
    plugin: str,
    ctx: ExecutionContext,
    **facts: Any,
) -> None:
    invocations = _OBSERVATIONS.setdefault("external_invocations", [])
    invocations.append({
        "plugin": plugin,
        "invocation_index": len(invocations) + 1,
        "cwd": ctx.cwd,
        **facts,
    })


async def _codebuddy_double(
    self: CodeBuddyPlugin,
    ctx: ExecutionContext,
    params: dict[str, Any],
) -> PluginResult:
    del self
    if ctx.cwd is None or not ctx.allow_workspace_write:
        return PluginResult(
            success=False,
            error="deterministic CodeBuddy double requires workspace write authority",
        )
    _OBSERVATIONS.setdefault("codebuddy_invocations", 0)
    _OBSERVATIONS["codebuddy_invocations"] += 1
    _OBSERVATIONS["codebuddy"] = {
        "cwd": ctx.cwd,
        "allow_workspace_write": ctx.allow_workspace_write,
        "prompt": params.get("prompt"),
    }
    _append_external_invocation(
        "codebuddy",
        ctx,
        allow_workspace_write=ctx.allow_workspace_write,
        prompt=params.get("prompt"),
    )
    Path(ctx.cwd, _MUTATION_NAME).write_text(_MUTATION_CONTENT, encoding="utf-8")
    _OBSERVATIONS["workspace_after_codebuddy"] = _workspace_snapshot(ctx.cwd)
    _persist_observation()
    return PluginResult(success=True, output="deterministic CodeBuddy double completed")


async def _codex_double(
    self: CodexPlugin,
    ctx: ExecutionContext,
    params: dict[str, Any],
) -> PluginResult:
    del self, params
    if ctx.cwd is None:
        return PluginResult(success=False, error="deterministic Codex double has no cwd")
    if ctx.allow_workspace_write:
        return PluginResult(success=False, error="deterministic Codex double received write authority")
    _OBSERVATIONS.setdefault("codex_invocations", 0)
    _OBSERVATIONS["codex_invocations"] += 1
    _append_external_invocation(
        "codex",
        ctx,
        allow_workspace_write=ctx.allow_workspace_write,
    )
    _OBSERVATIONS["workspace_before_codex"] = _workspace_snapshot(ctx.cwd)
    mutation = Path(ctx.cwd, _MUTATION_NAME)
    if not mutation.is_file():
        return PluginResult(success=False, error="deterministic Codex double did not find mutation")
    observed = mutation.read_text(encoding="utf-8")
    if observed != _MUTATION_CONTENT:
        return PluginResult(success=False, error="deterministic Codex double observed unexpected mutation")
    _OBSERVATIONS["codex"] = {
        "cwd": ctx.cwd,
        "allow_workspace_write": ctx.allow_workspace_write,
        "observed_mutation": observed,
    }
    _OBSERVATIONS["workspace_after_codex"] = _workspace_snapshot(ctx.cwd)
    _persist_observation()
    return PluginResult(
        success=True,
        output=f"observed {_MUTATION_NAME}: {observed}\nDSH_VERIFICATION: PASS",
    )


def _run_with_doubles(request: dict[str, Any]) -> TaskState:
    _OBSERVATIONS.clear()
    goal = request.get("goal")
    workspace_id = request.get("workspace_id")
    workspace_path = request.get("workspace_path")
    if not all(isinstance(value, str) and value.strip() for value in (
        goal,
        workspace_id,
        workspace_path,
    )):
        raise ValueError("goal, workspace_id, and workspace_path must be non-empty strings")

    workspace = Path(workspace_path)
    manager = WorkspaceManager({
        workspace_id: Workspace(workspace_id, workspace),
    })
    original_codebuddy = CodeBuddyPlugin.execute
    original_codex = CodexPlugin.execute
    CodeBuddyPlugin.execute = _codebuddy_double
    CodexPlugin.execute = _codex_double
    trace_handler = _ExecutionTraceHandler()
    previous_log_level = runtime_logger.level
    runtime_logger.setLevel(logging.INFO)
    runtime_logger.addHandler(trace_handler)
    try:
        controller = build_controller(workspace_manager=manager)
        task = build_repository_change_task(goal, workspace_id)
        result = asyncio.run(controller.run(task))
        _OBSERVATIONS["runtime_events"] = trace_handler.events
        return result
    finally:
        runtime_logger.removeHandler(trace_handler)
        runtime_logger.setLevel(previous_log_level)
        CodeBuddyPlugin.execute = original_codebuddy
        CodexPlugin.execute = original_codex


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
    sys.stderr.write(f"m7 python adapter transport failure: {message}\n")
    return 2


def main() -> int:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("request must be a JSON object")
        captured_stdout = io.StringIO()
        with redirect_stdout(captured_stdout):
            task = _run_with_doubles(request)
        if captured_stdout.getvalue():
            raise RuntimeError("unexpected adapter output reached captured stdout")
        response = json.dumps(
            _serialize_task(task),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        _persist_observation()
        sys.stdout.write(response)
        sys.stdout.write("\n")
        sys.stdout.flush()
        return 0
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return _transport_failure(str(exc))
    except Exception as exc:  # pragma: no cover - transport safety net
        return _transport_failure(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
