"""Simple deterministic planner for the first runtime milestone."""

from dataclasses import dataclass, field
from typing import Any

from .role_config import RoleConfig, RoleSelection
from .state import TaskKind, TaskState


@dataclass(frozen=True)
class Decision:
    plugin: str | None
    params: dict[str, Any] = field(default_factory=dict)
    terminal_success: bool = True
    terminal_error: str | None = None
    allow_workspace_write: bool | None = None

    @property
    def is_terminal(self) -> bool:
        return self.plugin is None


class SimplePlanner:
    def __init__(self, roles: RoleConfig | None = None) -> None:
        self.roles = roles or RoleConfig.defaults()

    @staticmethod
    def _role_decision(role: RoleSelection, prompt: str, *, role_name: str, allow_write: bool) -> Decision:
        return Decision(
            plugin=role.adapter,
            params=role.params(prompt, role_name=role_name),
            allow_workspace_write=allow_write,
        )

    def next_action(self, task: TaskState) -> Decision:
        if task.task_kind is TaskKind.REPOSITORY_CHANGE:
            if task.iteration == 0:
                return self._role_decision(self.roles.worker, task.goal, role_name="worker", allow_write=True)
            if task.iteration == 1:
                return self._role_decision(
                    self.roles.reviewer, _verification_prompt(task), role_name="reviewer", allow_write=False
                )
            return _verification_decision(task.last_invocation_result)
        if (
            task.task_kind is TaskKind.REPOSITORY_INSPECTION
            and task.iteration == 0
        ):
            return self._role_decision(
                self.roles.inspector, _inspection_prompt(task), role_name="inspector", allow_write=False
            )
        if task.iteration > 0:
            return Decision(plugin=None)
        if task.task_kind is TaskKind.REPOSITORY_ANALYSIS:
            return Decision(plugin="codex", params={"prompt": task.goal})
        return Decision(plugin="echo", params={"text": task.goal})


def _inspection_prompt(task: TaskState) -> str:
    return (
        "Inspect the current logical workspace/repository to answer the "
        "delegated repository question.\n"
        f"Repository question:\n{task.goal}\n\n"
        "Remain read-only: do not create, modify, or delete files, and do not "
        "perform repository mutations. Stay within the current workspace. "
        "Return a final textual inspection report that clearly states the "
        "answer and the relevant evidence."
    )


def _verification_prompt(task: TaskState) -> str:
    return (
        "Original task goal:\n"
        f"{task.goal}\n\n"
        "Inspect the current workspace and independently verify whether the "
        "requested repository change is correct. Do not modify any file or "
        "run a mutating command. The workspace may have contained modified or "
        "untracked files before this task. A dirty Git status alone does not "
        "prove this task changed those files; do not require a clean working "
        "tree unless the original goal explicitly requires it. State any "
        "uncertainty about when unrelated files changed, and do not claim they "
        "were unchanged without before-and-after evidence. Report the evidence "
        "you used. Finish your "
        "response with exactly one final non-empty verdict line: either "
        "DSH_VERIFICATION: PASS or DSH_VERIFICATION: FAIL."
    )


def _verification_decision(result: Any) -> Decision:
    if not isinstance(result, str):
        return Decision(
            plugin=None,
            terminal_success=False,
            terminal_error="invalid verifier result",
        )

    non_empty_lines = [line.strip() for line in result.splitlines() if line.strip()]
    verdict = non_empty_lines[-1] if non_empty_lines else None
    if verdict == "DSH_VERIFICATION: PASS":
        return Decision(plugin=None)
    if verdict == "DSH_VERIFICATION: FAIL":
        return Decision(
            plugin=None,
            terminal_success=False,
            terminal_error="Codex verification reported FAIL",
        )
    return Decision(
        plugin=None,
        terminal_success=False,
        terminal_error="invalid verifier result",
    )
