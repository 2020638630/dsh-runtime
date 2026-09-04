"""Task state owned by the DSH controller."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    MAX_ITERATIONS = "max_iterations"


@dataclass
class TaskState:
    goal: str
    workspace_id: str = "dsh.main"
    max_iterations: int = 1
    timeout_seconds: float = 30.0
    task_id: str = field(default_factory=lambda: str(uuid4()))
    status: TaskStatus = TaskStatus.PENDING
    iteration: int = 0
    result: Any = None
    error: str | None = None
    artifacts: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def apply_success(self, result: Any) -> None:
        self.result = result
        self.status = TaskStatus.COMPLETED

    def apply_failure(self, error: str) -> None:
        self.error = error
        self.status = TaskStatus.FAILED
