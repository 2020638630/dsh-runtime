"""Simple deterministic planner for the first runtime milestone."""

from dataclasses import dataclass, field
from typing import Any

from .state import TaskKind, TaskState


@dataclass(frozen=True)
class Decision:
    plugin: str | None
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        return self.plugin is None


class SimplePlanner:
    def next_action(self, task: TaskState) -> Decision:
        if task.iteration > 0:
            return Decision(plugin=None)
        if task.task_kind is TaskKind.REPOSITORY_ANALYSIS:
            return Decision(plugin="codex", params={"prompt": task.goal})
        return Decision(plugin="echo", params={"text": task.goal})
