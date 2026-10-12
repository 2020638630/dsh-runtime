import asyncio
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import dsh_runtime.entrypoint as entrypoint
from dsh_runtime.bootstrap import (
    build_repository_change_task,
    build_repository_inspection_task,
)
from dsh_runtime.state import TaskStatus


def _invoke(monkeypatch, payload: object) -> tuple[int, str, str]:
    stdin = io.StringIO(
        payload if isinstance(payload, str) else json.dumps(payload)
    )
    stdout = io.StringIO()
    stderr = io.StringIO()
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    code = entrypoint.main()
    return code, stdout.getvalue(), stderr.getvalue()


class _FakeController:
    def __init__(self, settle):
        self._settle = settle

    async def run(self, task):
        return self._settle(task)


def _request(workspace: Path, *, goal: str = "change the repository") -> dict[str, str]:
    return {
        "goal": goal,
        "workspace_id": "workspace.product",
        "workspace_path": str(workspace.resolve()),
    }


def test_valid_request_binds_explicit_workspace_and_serializes_completed_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed: dict[str, object] = {}

    def fake_build_controller(*, workspace_manager):
        observed["cwd"] = workspace_manager.resolve_cwd("workspace.product")

        def settle(task):
            task.iteration = 2
            task.last_invocation_result = "completed result"
            task.apply_success("completed result")
            return task

        return _FakeController(settle)

    monkeypatch.setattr(entrypoint, "build_controller", fake_build_controller)
    code, stdout, stderr = _invoke(monkeypatch, _request(tmp_path))

    assert code == 0
    assert stderr == ""
    assert observed["cwd"] == tmp_path.resolve()
    records = stdout.strip().splitlines()
    assert len(records) == 1
    assert json.loads(records[0]) == {
        "task_id": pytest.approx("", abs=0),
    } if False else json.loads(records[0])
    task = json.loads(records[0])
    assert isinstance(task["task_id"], str)
    assert task == {
        "task_id": task["task_id"],
        "task_kind": "repository_change",
        "workspace_id": "workspace.product",
        "status": "completed",
        "iteration": 2,
        "result": "completed result",
        "error": None,
        "last_invocation_result": "completed result",
    }


def test_binary_stdio_uses_utf8_and_escapes_surrogate_task_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _request(tmp_path, goal="review 中文")
    stdin_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    stdout_bytes = io.BytesIO()
    observed_goal: list[str] = []

    def fake_build_controller(*, workspace_manager):
        def settle(task):
            observed_goal.append(task.goal)
            task.apply_success("结果" + chr(0xDC94))
            return task

        return _FakeController(settle)

    monkeypatch.setattr(entrypoint, "build_controller", fake_build_controller)
    monkeypatch.setattr(
        entrypoint.sys,
        "stdin",
        SimpleNamespace(buffer=io.BytesIO(stdin_bytes)),
    )
    monkeypatch.setattr(
        entrypoint.sys,
        "stdout",
        SimpleNamespace(buffer=stdout_bytes),
    )
    stderr = io.StringIO()
    monkeypatch.setattr(entrypoint.sys, "stderr", stderr)

    assert entrypoint.main() == 0

    raw_output = stdout_bytes.getvalue()
    task = json.loads(raw_output.decode("utf-8"))
    assert observed_goal == [payload["goal"]]
    assert task["result"] == "结果" + chr(0xDC94)
    assert b"\\udc94" in raw_output
    assert stderr.getvalue() == ""


def test_failed_task_is_settled_successfully_at_process_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_build_controller(*, workspace_manager):
        def settle(task):
            task.iteration = 2
            task.last_invocation_result = "DSH_VERIFICATION: FAIL"
            task.apply_failure("Codex verification reported FAIL")
            return task

        return _FakeController(settle)

    monkeypatch.setattr(entrypoint, "build_controller", fake_build_controller)
    code, stdout, stderr = _invoke(monkeypatch, _request(tmp_path))

    assert code == 0
    assert stderr == ""
    task = json.loads(stdout)
    assert task["status"] == TaskStatus.FAILED.value
    assert task["iteration"] == 2
    assert task["result"] is None
    assert task["error"] == "Codex verification reported FAIL"
    assert task["last_invocation_result"] == "DSH_VERIFICATION: FAIL"


def test_wrapper_does_not_reinterpret_task_status_or_build_a_replacement_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed: dict[str, object] = {}

    def fake_build_controller(*, workspace_manager):
        def settle(task):
            observed["task"] = task
            task.apply_success("native task result")
            return task

        return _FakeController(settle)

    monkeypatch.setattr(entrypoint, "build_controller", fake_build_controller)
    code, stdout, stderr = _invoke(monkeypatch, _request(tmp_path))

    assert code == 0
    assert stderr == ""
    task = observed["task"]
    assert task is not None
    assert task.task_kind.value == "repository_change"
    assert task.allow_workspace_write is True
    assert task.max_iterations == 2
    assert task.timeout_seconds == 900.0
    assert json.loads(stdout)["result"] == "native task result"


def test_malformed_json_is_a_transport_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    code, stdout, stderr = _invoke(monkeypatch, "not-json")

    assert code != 0
    assert stdout == ""
    assert "transport failure" in stderr


def test_transport_failure_backslash_escapes_surrogates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stderr = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr)

    assert entrypoint._transport_failure("invalid " + chr(0xDC94)) == 2
    assert stderr.getvalue() == (
        r"dsh runtime entrypoint transport failure: invalid \udc94" + "\n"
    )


def test_missing_required_request_field_is_a_transport_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _request(tmp_path)
    del payload["workspace_path"]
    code, stdout, stderr = _invoke(monkeypatch, payload)

    assert code != 0
    assert stdout == ""
    assert "workspace_path" in stderr


def test_invalid_workspace_binding_is_a_transport_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _request(tmp_path / "does-not-exist")
    code, stdout, stderr = _invoke(monkeypatch, payload)

    assert code != 0
    assert stdout == ""
    assert "existing directory" in stderr


def test_unexpected_workflow_stdout_is_not_emitted_as_protocol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_build_controller(*, workspace_manager):
        async def noisy_run(task):
            print("progress")
            task.apply_success("result")
            return task

        controller = type("NoisyController", (), {"run": noisy_run})()
        return controller

    monkeypatch.setattr(entrypoint, "build_controller", fake_build_controller)
    code, stdout, stderr = _invoke(monkeypatch, _request(tmp_path))

    assert code != 0
    assert stdout == ""
    assert "unexpected" in stderr


@pytest.mark.parametrize(
    "task_kind",
    [None, "repository_change"],
    ids=["omitted", "explicit-repository-change"],
)
def test_task_kind_omission_and_explicit_change_use_repository_change_builder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, task_kind: str | None
) -> None:
    observed: dict[str, object] = {}

    def fake_change(goal: str, workspace: str):
        observed["builder"] = ("change", goal, workspace)
        return build_repository_change_task(goal, workspace)

    def unexpected_inspection(goal: str, workspace: str):
        pytest.fail("repository inspection builder must not be used")

    def fake_build_controller(*, workspace_manager):
        def settle(task):
            observed["task"] = task
            task.apply_success("change result")
            return task

        return _FakeController(settle)

    monkeypatch.setattr(entrypoint, "build_repository_change_task", fake_change)
    monkeypatch.setattr(
        entrypoint,
        "build_repository_inspection_task",
        unexpected_inspection,
    )
    monkeypatch.setattr(entrypoint, "build_controller", fake_build_controller)

    payload = _request(tmp_path)
    if task_kind is not None:
        payload["task_kind"] = task_kind
    code, stdout, stderr = _invoke(monkeypatch, payload)

    assert code == 0
    assert stderr == ""
    assert observed["builder"] == (
        "change",
        payload["goal"],
        payload["workspace_id"],
    )
    task = observed["task"]
    assert task.task_kind.value == "repository_change"
    assert task.allow_workspace_write is True
    assert task.max_iterations == 2
    assert json.loads(stdout)["task_kind"] == "repository_change"


def test_explicit_repository_inspection_uses_inspection_builder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed: dict[str, object] = {}

    def unexpected_change(goal: str, workspace: str):
        pytest.fail("repository change builder must not be used")

    def fake_inspection(goal: str, workspace: str):
        observed["builder"] = ("inspection", goal, workspace)
        return build_repository_inspection_task(goal, workspace)

    def fake_build_controller(*, workspace_manager):
        def settle(task):
            observed["task"] = task
            task.apply_success("inspection result")
            return task

        return _FakeController(settle)

    monkeypatch.setattr(
        entrypoint,
        "build_repository_change_task",
        unexpected_change,
    )
    monkeypatch.setattr(
        entrypoint,
        "build_repository_inspection_task",
        fake_inspection,
    )
    monkeypatch.setattr(entrypoint, "build_controller", fake_build_controller)

    payload = _request(tmp_path, goal="inspect configuration loading")
    payload["task_kind"] = "repository_inspection"
    code, stdout, stderr = _invoke(monkeypatch, payload)

    assert code == 0
    assert stderr == ""
    assert observed["builder"] == (
        "inspection",
        payload["goal"],
        payload["workspace_id"],
    )
    task = observed["task"]
    assert task.task_kind.value == "repository_inspection"
    assert task.allow_workspace_write is False
    assert task.max_iterations == 1
    assert task.timeout_seconds == 900.0
    assert json.loads(stdout)["task_kind"] == "repository_inspection"


@pytest.mark.parametrize(
    "task_kind",
    ["unknown", "", 123],
    ids=["unknown-string", "empty-string", "non-string"],
)
def test_invalid_explicit_task_kind_is_a_transport_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, task_kind: object
) -> None:
    def unexpected_builder(goal: str, workspace: str):
        pytest.fail("invalid task_kind must not dispatch a builder")

    monkeypatch.setattr(entrypoint, "build_repository_change_task", unexpected_builder)
    monkeypatch.setattr(
        entrypoint,
        "build_repository_inspection_task",
        unexpected_builder,
    )

    payload = _request(tmp_path)
    payload["task_kind"] = task_kind  # type: ignore[assignment]
    code, stdout, stderr = _invoke(monkeypatch, payload)

    assert code != 0
    assert stdout == ""
    assert "task_kind" in stderr
    assert "repository_change" in stderr
