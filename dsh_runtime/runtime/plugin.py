"""Minimal plugin protocol and execution context."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


PLUGIN_TIMEOUT_ERROR = "plugin execution timed out"
INVALID_PLUGIN_RESULT_ERROR = "plugin returned an invalid result"


class StopReason(str, Enum):
    """The governing terminal reason for one bounded plugin invocation."""

    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True)
class ExecutionContext:
    task_id: str
    workspace_id: str
    goal: str
    cwd: str | None = None
    allow_workspace_write: bool = False


@dataclass(frozen=True)
class PluginResult:
    success: bool
    output: Any = None
    error: str | None = None
    stop_reason: StopReason | None = None
    cleanup_error: str | None = None


class Plugin(Protocol):
    name: str

    async def execute(self, ctx: ExecutionContext, params: dict[str, Any]) -> PluginResult:
        """Execute one bounded action and return a result."""
