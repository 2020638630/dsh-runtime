"""Minimal plugin protocol and execution context."""

from dataclasses import dataclass
from typing import Any, Protocol


PLUGIN_TIMEOUT_ERROR = "plugin execution timed out"


@dataclass(frozen=True)
class ExecutionContext:
    task_id: str
    workspace_id: str
    goal: str


@dataclass(frozen=True)
class PluginResult:
    success: bool
    output: Any = None
    error: str | None = None


class Plugin(Protocol):
    name: str

    async def execute(self, ctx: ExecutionContext, params: dict[str, Any]) -> PluginResult:
        """Execute one bounded action and return a result."""
