"""Product-facing one-shot process entry for a repository-change task.

The entrypoint owns only the external JSON/process boundary. Workflow
sequencing, authority calculation, provider selection, and terminal business
semantics remain in the existing DSH-Runtime production components.
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

# Support both ``python -m dsh_runtime.entrypoint`` and direct execution as a
# file path without using the process cwd to locate the Runtime package.
if __package__ in {None, ""}:
    _REPO_ROOT = Path(__file__).resolve().parents[1]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

from dsh_runtime.bootstrap import (
    build_controller,
    build_repository_change_task,
    build_repository_inspection_task,
)
from dsh_runtime.state import TaskState
from dsh_runtime.workspace.manager import Workspace, WorkspaceManager


_REQUIRED_FIELDS = ("goal", "workspace_id", "workspace_path")
_TASK_KIND_REPOSITORY_CHANGE = "repository_change"
_TASK_KIND_REPOSITORY_INSPECTION = "repository_inspection"


def _request_value(request: dict[str, Any], field: str) -> str:
    value = request.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _request_task_kind(request: dict[str, Any]) -> str:
    if "task_kind" not in request:
        return _TASK_KIND_REPOSITORY_CHANGE

    value = request["task_kind"]
    if (
        not isinstance(value, str)
        or value not in {
            _TASK_KIND_REPOSITORY_CHANGE,
            _TASK_KIND_REPOSITORY_INSPECTION,
        }
    ):
        raise ValueError(
            "task_kind must be one of: repository_change, repository_inspection"
        )
    return value

def _workspace_manager(workspace_id: str, workspace_path: str) -> WorkspaceManager:
    path = Path(workspace_path)
    if not path.is_absolute():
        raise ValueError("workspace_path must be an absolute path")
    if not path.exists() or not path.is_dir():
        raise ValueError("workspace_path must be an existing directory")
    return WorkspaceManager({
        workspace_id: Workspace(workspace_id, path),
    })


async def _run_request(request: dict[str, Any]) -> TaskState:
    goal = _request_value(request, "goal")
    workspace_id = _request_value(request, "workspace_id")
    workspace_path = _request_value(request, "workspace_path")
    task_kind = _request_task_kind(request)
    manager = _workspace_manager(workspace_id, workspace_path)
    controller = build_controller(workspace_manager=manager)
    if task_kind == _TASK_KIND_REPOSITORY_INSPECTION:
        task = build_repository_inspection_task(goal, workspace_id)
    else:
        task = build_repository_change_task(goal, workspace_id)
    return await controller.run(task)


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
    sys.stderr.write(f"dsh runtime entrypoint transport failure: {message}\n")
    return 2


def main() -> int:
    """Process one JSON request and return a process exit code."""

    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("request must be a JSON object")
        missing = [field for field in _REQUIRED_FIELDS if field not in request]
        if missing:
            raise ValueError(f"missing required field(s): {', '.join(missing)}")

        captured_stdout = io.StringIO()
        with redirect_stdout(captured_stdout):
            task = asyncio.run(_run_request(request))
        if captured_stdout.getvalue():
            raise RuntimeError("unexpected wrapper or workflow output reached stdout")

        sys.stdout.write(
            json.dumps(_serialize_task(task), ensure_ascii=False, separators=(",", ":"))
        )
        sys.stdout.write("\n")
        sys.stdout.flush()
        return 0
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return _transport_failure(str(exc))
    except Exception as exc:  # pragma: no cover - process boundary safety net
        return _transport_failure(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
