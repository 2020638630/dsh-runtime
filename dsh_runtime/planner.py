"""Simple deterministic planner for the first runtime milestone."""

from dataclasses import dataclass, field
from typing import Any

from .state import TaskState


@dataclass(frozen=True)
class Decision:
    plugin: str
    params: dict[str, Any] = field(default_factory=dict)


class SimplePlanner:
    def next_action(self, task: TaskState) -> Decision:
        return Decision(plugin="echo", params={"text": task.goal})
