"""Role selection is frozen and fails closed before any worker launch."""

import json

import pytest

from dsh_runtime.bootstrap import build_controller
from dsh_runtime.planner import SimplePlanner
from dsh_runtime.role_config import ROLE_CONFIG_ENV, RoleConfig
from dsh_runtime.state import TaskKind, TaskState


def _document() -> dict:
    return {
        "schema_version": 1,
        "roles": {
            "worker": {"adapter": "codex", "model": "gpt-worker"},
            "reviewer": {"adapter": "codex", "model": "gpt-reviewer"},
            "inspector": {"adapter": "codex", "model": "gpt-inspector"},
        },
    }


def test_role_config_routes_distinct_models_without_changing_authority() -> None:
    planner = SimplePlanner(RoleConfig.from_document(_document()))
    change = TaskState(
        goal="make a change",
        task_kind=TaskKind.REPOSITORY_CHANGE,
        allow_workspace_write=True,
        max_iterations=2,
    )
    worker = planner.next_action(change)
    assert (worker.plugin, worker.params, worker.allow_workspace_write) == (
        "codex", {"prompt": "make a change", "model": "gpt-worker"}, True
    )

    change.iteration = 1
    reviewer = planner.next_action(change)
    assert reviewer.plugin == "codex"
    assert reviewer.params["model"] == "gpt-reviewer"
    assert reviewer.allow_workspace_write is False
    assert "DSH_VERIFICATION: PASS" in reviewer.params["prompt"]

    inspection = TaskState(goal="inspect", task_kind=TaskKind.REPOSITORY_INSPECTION)
    inspector = planner.next_action(inspection)
    assert inspector.plugin == "codex"
    assert inspector.params["model"] == "gpt-inspector"
    assert inspector.allow_workspace_write is False


def test_default_roles_preserve_existing_worker_and_read_only_stages() -> None:
    roles = RoleConfig.from_environment({})
    assert roles == RoleConfig.defaults()
    assert roles.worker.adapter == "codebuddy"
    assert roles.reviewer.adapter == roles.inspector.adapter == "codex"
    assert roles.worker.params("goal") == {"prompt": "goal"}


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda doc: doc.update(schema_version=True), "schema_version"),
        (lambda doc: doc["roles"].pop("inspector"), "requires worker"),
        (lambda doc: doc["roles"]["reviewer"].update(adapter="codebuddy"), "reviewer adapter"),
        (lambda doc: doc["roles"]["worker"].update(model="bad model"), "bounded model ID"),
        (lambda doc: doc["roles"]["worker"].update(model="gpt-worker", extra="x"), "requires adapter and model"),
        (lambda doc: doc["roles"]["reviewer"].update(reasoning="high"), "requires adapter and model"),
    ],
)
def test_invalid_role_config_is_rejected(mutate, message: str) -> None:
    document = _document()
    mutate(document)
    with pytest.raises(ValueError, match=message):
        RoleConfig.from_document(document)


def test_duplicate_json_field_is_rejected() -> None:
    raw = json.dumps(_document()).replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1')
    with pytest.raises(ValueError, match="duplicate role config field"):
        RoleConfig.from_environment({ROLE_CONFIG_ENV: raw})


def test_codebuddy_worker_model_is_selected_without_changing_write_authority() -> None:
    document = _document()
    document["roles"]["worker"] = {"adapter": "codebuddy", "model": "glm-5.3-flash"}
    decision = SimplePlanner(RoleConfig.from_document(document)).next_action(
        TaskState(
            goal="make a change",
            task_kind=TaskKind.REPOSITORY_CHANGE,
            allow_workspace_write=True,
            max_iterations=2,
        )
    )
    assert decision.plugin == "codebuddy"
    assert decision.params == {"prompt": "make a change", "model": "glm-5.3-flash"}
    assert decision.allow_workspace_write is True


def test_api_reviewer_is_read_only_and_fail_verdict_has_correct_attribution() -> None:
    document = {
        "schema_version": 2,
        "roles": {
            "worker": {"adapter": "codebuddy", "model": None},
            "reviewer": {
                "adapter": "api_agent", "provider": "siliconflow",
                "model": "Qwen/Qwen3-Coder-30B-A3B-Instruct",
                "connection_ref": "trial_siliconflow", "max_requests": 3,
                "max_tool_calls": 3, "max_output_tokens": 512,
            },
            "inspector": {"adapter": "codex", "model": None},
        },
    }
    planner = SimplePlanner(RoleConfig.from_document(document))
    task = TaskState(
        goal="change repository", task_kind=TaskKind.REPOSITORY_CHANGE,
        allow_workspace_write=True, max_iterations=2, iteration=1,
    )
    decision = planner.next_action(task)
    assert decision.plugin == "api_agent"
    assert decision.params["role_name"] == "reviewer"
    assert decision.allow_workspace_write is False
    task.iteration = 2
    task.last_invocation_result = "Issue found.\nDSH_VERIFICATION: FAIL"
    terminal = planner.next_action(task)
    assert terminal.terminal_error == "API reviewer verification reported FAIL"


def test_controller_freezes_roles_at_construction(monkeypatch) -> None:
    document = _document()
    monkeypatch.setenv(ROLE_CONFIG_ENV, json.dumps(document))
    controller = build_controller()
    document["roles"]["inspector"]["model"] = "changed-later"
    monkeypatch.setenv(ROLE_CONFIG_ENV, json.dumps(document))
    decision = controller.planner.next_action(
        TaskState(goal="inspect", task_kind=TaskKind.REPOSITORY_INSPECTION)
    )
    assert decision.params["model"] == "gpt-inspector"


def test_invalid_environment_fails_before_plugin_construction(monkeypatch) -> None:
    monkeypatch.setenv(ROLE_CONFIG_ENV, "not json")
    monkeypatch.setattr(
        "dsh_runtime.plugins.codebuddy._default_command",
        lambda: pytest.fail("CodeBuddy must not be constructed"),
    )
    with pytest.raises(ValueError, match=ROLE_CONFIG_ENV):
        build_controller()
