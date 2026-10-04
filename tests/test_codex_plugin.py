"""Deterministic and local-process tests for the first Codex-backed Plugin."""

import asyncio
import json
import os
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from dsh_runtime.controller import DSHController
from dsh_runtime.plugins.codex import CodexPlugin
from dsh_runtime.planner import Decision, SimplePlanner
from dsh_runtime.runtime.executor import Executor
from dsh_runtime.runtime.plugin import ExecutionContext, StopReason
from dsh_runtime.runtime.registry import PluginRegistry
from dsh_runtime.state import TaskKind, TaskState, TaskStatus
from dsh_runtime.workspace.manager import Workspace, WorkspaceManager


ROOT = Path(__file__).resolve().parent
STUB = ROOT / "codex_app_server_stub.mjs"


def stub_command() -> tuple[str, str]:
    return (shutil.which("node") or "node", str(STUB))


def plugin(*, trace_dir: Path | None = None) -> CodexPlugin:
    overlay = {
        key: os.environ[key]
        for key in (
            "DSH_CODEX_STUB_CAPTURE",
            "DSH_CODEX_STUB_MODE",
            "DSH_CODEX_STUB_STDERR",
            "DSH_CODEX_STUB_EXIT_CODE",
        )
        if key in os.environ
    }
    return CodexPlugin(
        command=stub_command(),
        environment=overlay,
        cleanup_grace_seconds=1.0,
        qualification_trace_dir=trace_dir,
    )


def executor_with(codex: CodexPlugin) -> Executor:
    registry = PluginRegistry()
    registry.register(codex)
    return Executor(registry)


def context(cwd: Path, *, allow_workspace_write: bool = False) -> ExecutionContext:
    return ExecutionContext(
        task_id="codex-test",
        workspace_id="logical.test",
        goal="fallback goal",
        cwd=str(cwd),
        allow_workspace_write=allow_workspace_write,
    )


def test_codex_success_uses_one_bounded_protocol_path(tmp_path: Path, monkeypatch) -> None:
    capture = tmp_path / "thread-start.json"
    monkeypatch.setenv("DSH_CODEX_STUB_CAPTURE", str(capture))

    async def scenario():
        return await executor_with(plugin()).execute(
            "codex", context(tmp_path), {"prompt": "hello"}, 1.0
        )

    result = asyncio.run(scenario())

    assert result.success is True
    assert result.stop_reason is StopReason.COMPLETED
    assert "stub answer: hello" in result.output
    assert f"cwd={tmp_path.resolve()}" in result.output
    params = json.loads(capture.read_text(encoding="utf-8"))
    assert params["cwd"] == str(tmp_path.resolve())
    assert params["ephemeral"] is True
    assert params["approvalPolicy"] == "never"
    assert params["sandbox"] == "read-only"


def test_qualification_trace_is_opt_in(tmp_path: Path) -> None:
    async def scenario():
        return await executor_with(plugin()).execute(
            "codex", context(tmp_path), {"prompt": "no trace"}, 1.0
        )

    result = asyncio.run(scenario())

    assert result.success is True
    assert not (tmp_path / "trace").exists()


def test_qualification_trace_captures_identity_protocol_stderr_and_authority(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSH_CODEX_STUB_STDERR", "stub qualification stderr\n")
    trace_dir = tmp_path / "trace"

    async def scenario():
        return await executor_with(plugin(trace_dir=trace_dir)).execute(
            "codex",
            context(tmp_path),
            {"prompt": "traced", "model": "trace-model", "reasoning": "xhigh"},
            1.0,
        )

    result = asyncio.run(scenario())
    trace = json.loads(next(trace_dir.glob("codex-worker-*.json")).read_text())

    assert result.success is True
    assert isinstance(trace["pid"], int)
    assert trace["executable"] == (shutil.which("node") or "node")
    assert trace["argv"][-1] == str(STUB)
    assert trace["cwd"] == str(tmp_path.resolve())
    assert trace["model"] == "trace-model"
    assert trace["reasoning"] == "xhigh"
    assert trace["allow_workspace_write"] is False
    assert trace["stderr"] == "stub qualification stderr\n"
    assert trace["turn_completed_observed"] is True

    frames = trace["protocol_frames"]
    methods = [
        frame["message"].get("method")
        for frame in frames
        if frame["message"] is not None and frame["message"].get("method") is not None
    ]
    assert methods[:4] == ["initialize", "initialized", "thread/start", "turn/start"]
    assert "turn/completed" in methods
    assert all(frame["parse_error"] is None for frame in frames if frame["direction"] == "inbound")
    assert trace["events"][0]["event"] == "process_spawned"


def test_qualification_trace_records_eof_and_child_return_code(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSH_CODEX_STUB_MODE", "eof")
    trace_dir = tmp_path / "trace"

    async def scenario():
        return await executor_with(plugin(trace_dir=trace_dir)).execute(
            "codex", context(tmp_path), {"prompt": "eof"}, 1.0
        )

    result = asyncio.run(scenario())
    trace = json.loads(next(trace_dir.glob("codex-worker-*.json")).read_text())

    assert result.success is False
    assert result.error == "Codex bounded invocation failed: app-server stream ended"
    assert any(event["event"] == "stdout_eof" for event in trace["events"])
    assert trace["terminal"]["returncode"] == 17
    assert trace["turn_completed_observed"] is False
    assert "id" in trace["last_valid_inbound_frame"]["message"]
    assert "method" not in trace["last_valid_inbound_frame"]["message"]


def test_qualification_trace_sink_failure_is_explicit(tmp_path: Path) -> None:
    trace_sink = tmp_path / "trace-file"
    trace_sink.write_text("not a directory", encoding="utf-8")

    async def scenario():
        return await executor_with(plugin(trace_dir=trace_sink)).execute(
            "codex", context(tmp_path), {"prompt": "must not start"}, 1.0
        )

    result = asyncio.run(scenario())

    assert result.success is False
    assert result.error is not None
    assert result.error.startswith("QUALIFICATION OBSERVABILITY FAILURE:")


def test_qualification_trace_preserves_timeout_and_records_cancellation(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DSH_CODEX_STUB_MODE", "hold")
    trace_dir = tmp_path / "trace"

    async def scenario():
        return await executor_with(plugin(trace_dir=trace_dir)).execute(
            "codex", context(tmp_path), {"prompt": "hold"}, 0.05
        )

    result = asyncio.run(scenario())
    trace = json.loads(next(trace_dir.glob("codex-worker-*.json")).read_text())

    assert result.success is False
    assert result.stop_reason is StopReason.TIMED_OUT
    assert result.error == "plugin execution timed out"
    assert any(event["event"] == "plugin_cancelled" for event in trace["events"])
    assert trace["terminal"]["cancelled"] is True


def test_workspace_write_authority_is_dsh_owned_and_mapped_natively(
    tmp_path: Path, monkeypatch
) -> None:
    capture = tmp_path / "thread-start.json"
    monkeypatch.setenv("DSH_CODEX_STUB_CAPTURE", str(capture))

    async def scenario():
        return await executor_with(plugin()).execute(
            "codex",
            context(tmp_path, allow_workspace_write=True),
            {"prompt": "write", "allow_workspace_write": False},
            1.0,
        )

    result = asyncio.run(scenario())
    params = json.loads(capture.read_text(encoding="utf-8"))

    assert result.success is True
    assert params["approvalPolicy"] == "on-request"
    assert params["approvalsReviewer"] == "auto_review"
    assert params["sandbox"] == "workspace-write"


def test_read_only_authority_maps_to_explicit_read_only_sandbox(
    tmp_path: Path, monkeypatch
) -> None:
    capture = tmp_path / "thread-start-read-only.json"
    monkeypatch.setenv("DSH_CODEX_STUB_CAPTURE", str(capture))

    async def scenario():
        return await executor_with(plugin()).execute(
            "codex",
            context(tmp_path, allow_workspace_write=False),
            {"prompt": "inspect"},
            1.0,
        )

    result = asyncio.run(scenario())
    params = json.loads(capture.read_text(encoding="utf-8"))

    assert result.success is True
    assert params["approvalPolicy"] == "never"
    assert params["sandbox"] == "read-only"
    assert "approvalsReviewer" not in params


def test_controller_resolves_logical_workspace_before_plugin_start(tmp_path: Path) -> None:
    class Planner:
        def next_action(self, task):
            if task.iteration > 0:
                return Decision(plugin=None)
            return Decision(plugin="codex", params={"prompt": "workspace"})

    manager = WorkspaceManager({"logical.test": Workspace("logical.test", tmp_path)})
    registry = PluginRegistry()
    registry.register(plugin())
    task = asyncio.run(
        DSHController(registry, Planner(), manager).run(
            TaskState(goal="ignored", workspace_id="logical.test")
        )
    )

    assert task.status is TaskStatus.COMPLETED
    assert f"cwd={tmp_path.resolve()}" in task.result


def test_repository_analysis_uses_production_planner_and_completes_normally(
    tmp_path: Path, monkeypatch
) -> None:
    capture = tmp_path / "repository-analysis-thread-start.json"
    monkeypatch.setenv("DSH_CODEX_STUB_CAPTURE", str(capture))
    goal = "Inspect the repository and summarize its runtime boundaries."
    manager = WorkspaceManager({"logical.test": Workspace("logical.test", tmp_path)})
    registry = PluginRegistry()
    codex = plugin()
    registry.register(codex)
    planner = SimplePlanner()

    with patch.object(planner, "next_action", wraps=planner.next_action) as next_action:
        task = asyncio.run(
            DSHController(registry, planner=planner, workspace_manager=manager).run(
                TaskState(
                    goal=goal,
                    task_kind=TaskKind.REPOSITORY_ANALYSIS,
                    workspace_id="logical.test",
                )
            )
        )

    params = json.loads(capture.read_text(encoding="utf-8"))
    assert params["cwd"] == str(tmp_path.resolve())
    assert params["ephemeral"] is True
    assert params["approvalPolicy"] == "never"
    assert params["sandbox"] == "read-only"
    assert next_action.call_count == 2
    assert task.iteration == 1
    assert task.last_invocation_result == task.result
    assert goal in task.last_invocation_result
    assert task.status is TaskStatus.COMPLETED


def test_invalid_workspace_fails_before_codex_start(tmp_path: Path) -> None:
    class Planner:
        def next_action(self, task):
            return Decision(plugin="codex", params={"prompt": "never starts"})

    manager = WorkspaceManager({"logical.test": Workspace("logical.test", tmp_path / "gone")})
    registry = PluginRegistry()
    registry.register(plugin())
    task = asyncio.run(
        DSHController(registry, Planner(), manager).run(
            TaskState(goal="ignored", workspace_id="logical.test")
        )
    )

    assert task.status is TaskStatus.FAILED
    assert "workspace resolution failed" in (task.error or "")
    assert task.iteration == 0


def test_protocol_failure_is_safe_and_not_raw_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DSH_CODEX_STUB_MODE", "protocol-fail")

    async def scenario():
        return await executor_with(plugin()).execute(
            "codex", context(tmp_path), {"prompt": "fail"}, 1.0
        )

    result = asyncio.run(scenario())

    assert result.success is False
    assert result.stop_reason is StopReason.FAILED
    assert (result.error or "").startswith("Codex bounded invocation failed:")
    assert "jsonrpc" not in (result.error or "")


def test_missing_codex_executable_is_bounded_failure(tmp_path: Path) -> None:
    async def scenario():
        missing = CodexPlugin(command=(str(tmp_path / "missing-codex"),))
        return await executor_with(missing).execute(
            "codex", context(tmp_path), {"prompt": "fail"}, 1.0
        )

    result = asyncio.run(scenario())

    assert result.success is False
    assert result.stop_reason is StopReason.FAILED
    assert result.error == "Codex bounded invocation failed: Codex app-server startup failed"


def test_executor_timeout_cleans_up_codex_process(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DSH_CODEX_STUB_MODE", "hold")

    async def scenario():
        return await executor_with(plugin()).execute(
            "codex", context(tmp_path), {"prompt": "hold"}, 0.05
        )

    result = asyncio.run(scenario())

    assert result.success is False
    assert result.stop_reason is StopReason.TIMED_OUT
    assert result.cleanup_error is None


def test_outer_cancellation_repropagates_after_codex_cleanup(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DSH_CODEX_STUB_MODE", "hold")

    async def scenario():
        task = asyncio.create_task(
            executor_with(plugin()).execute(
                "codex", context(tmp_path), {"prompt": "cancel"}, 2.0
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
