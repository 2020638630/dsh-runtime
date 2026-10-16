"""Product-facing one-shot process entry for a Runtime task.

The entrypoint owns only the external JSON/process boundary. Workflow
sequencing, authority calculation, provider selection, and terminal business
semantics remain in the existing DSH-Runtime production components. An
explicit call-trace path enables privacy-limited lifecycle records for direct
provider launches; the MCP adapter owns tracing when it launches this module.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import sys
import time
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

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
from dsh_runtime.json_stdio import read_json_document, write_json_line
from dsh_runtime.call_trace import (
    CALL_TRACE_PATH_ENV,
    append_call_trace,
    resolve_call_trace_path,
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


def _trace_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _trace_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _append_call_started(path: Path, call_id: str) -> None:
    append_call_trace(
        path,
        {
            "schema_version": "1",
            "event": "call_started",
            "call_id": call_id,
            "timestamp": _trace_timestamp(),
            "state": "started",
            "invocation_count": 1,
        },
    )


def _append_call_terminal(
    path: Path,
    *,
    call_id: str,
    started: float,
    state: str,
    returncode: int,
    stdout: bytes,
    stderr: bytes,
    task_status: str | None = None,
    result_sha256: str | None = None,
    error_type: str | None = None,
) -> None:
    append_call_trace(
        path,
        {
            "schema_version": "1",
            "event": "call_terminal",
            "call_id": call_id,
            "timestamp": _trace_timestamp(),
            "state": state,
            "duration_ms": max(0, int((time.perf_counter() - started) * 1000)),
            "runtime_exit_code": returncode,
            "stdout_bytes": len(stdout),
            "stdout_sha256": _trace_hash(stdout),
            "stderr_bytes": len(stderr),
            "stderr_sha256": _trace_hash(stderr),
            "task_status": task_status,
            "result_sha256": result_sha256,
            "error_code": None,
            "error_type": error_type,
        },
    )


def _json_line_bytes(value: Any) -> bytes:
    payload = json.dumps(
        value, ensure_ascii=False, separators=(",", ":")
    )
    return payload.encode("utf-8", errors="backslashreplace") + b"\n"


def _canonical_result_hash(value: dict[str, Any]) -> str:
    payload = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return _trace_hash(payload)


def _transport_diagnostic(message: str) -> bytes:
    safe_message = message.encode("ascii", errors="backslashreplace").decode("ascii")
    return f"dsh runtime entrypoint transport failure: {safe_message}\n".encode("ascii")


def _transport_failure(message: str) -> int:
    sys.stderr.write(_transport_diagnostic(message).decode("ascii"))
    return 2


def main() -> int:
    """Process one JSON request and return a process exit code."""

    configured_trace_path = os.environ.get(CALL_TRACE_PATH_ENV)
    trace_path: Path | None = None
    call_id = str(uuid4())
    started = time.perf_counter()
    if configured_trace_path:
        try:
            trace_path = resolve_call_trace_path()
            _append_call_started(trace_path, call_id)
        except Exception:
            return _transport_failure("call start trace could not be persisted")

    try:
        request = read_json_document(sys.stdin)
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

        task_payload = _serialize_task(task)
        stdout_payload = _json_line_bytes(task_payload)
        write_json_line(sys.stdout, task_payload)
        if trace_path is not None:
            try:
                _append_call_terminal(
                    trace_path,
                    call_id=call_id,
                    started=started,
                    state="returned",
                    returncode=0,
                    stdout=stdout_payload,
                    stderr=b"",
                    task_status=task.status.value,
                    result_sha256=_canonical_result_hash(task_payload),
                )
            except Exception:
                return _transport_failure("call terminal trace could not be persisted")
        return 0
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        if trace_path is not None:
            diagnostic = _transport_diagnostic(str(exc))
            try:
                _append_call_terminal(
                    trace_path,
                    call_id=call_id,
                    started=started,
                    state="process_error",
                    returncode=2,
                    stdout=b"",
                    stderr=diagnostic,
                    error_type=type(exc).__name__,
                )
            except Exception:
                return _transport_failure("call terminal trace could not be persisted")
        return _transport_failure(str(exc))
    except Exception as exc:  # pragma: no cover - process boundary safety net
        if trace_path is not None:
            diagnostic = _transport_diagnostic(f"{type(exc).__name__}: {exc}")
            try:
                _append_call_terminal(
                    trace_path,
                    call_id=call_id,
                    started=started,
                    state="process_error",
                    returncode=2,
                    stdout=b"",
                    stderr=diagnostic,
                    error_type=type(exc).__name__,
                )
            except Exception:
                return _transport_failure("call terminal trace could not be persisted")
        return _transport_failure(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
