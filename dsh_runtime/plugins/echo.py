"""Small deterministic plugin used to prove the runtime lifecycle."""

from typing import Any

from ..runtime.plugin import ExecutionContext, PluginResult


class EchoPlugin:
    name = "echo"

    async def execute(self, ctx: ExecutionContext, params: dict[str, Any]) -> PluginResult:
        text = params.get("text", ctx.goal)
        return PluginResult(success=True, output=str(text))
