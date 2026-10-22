"""Non-streaming Chat Completions transport prototype for two pinned gateways."""

from __future__ import annotations

import json
from typing import Any

from dsh_runtime.api_agent_connections import Connection
from dsh_runtime.api_agent_loop import ModelReply, ToolCall, TransportFailure


_TOOL_DESCRIPTIONS = {
    "list_files": ("List one workspace directory", {"path": {"type": "string"}}),
    "read_file": ("Read a bounded UTF-8 workspace file", {"path": {"type": "string"}}),
    "search_text": ("Search literal text in bounded workspace files", {
        "path": {"type": "string"}, "query": {"type": "string"},
    }),
    "apply_patch": ("Apply a checked workspace patch", {
        "path": {"type": "string"}, "old_text": {"type": "string"},
        "new_text": {"type": "string"}, "expected_sha256": {"type": "string"},
    }),
}
_MAX_RESPONSE_BYTES = 1_000_000


def _tool_definition(name: str) -> dict[str, Any]:
    description, properties = _TOOL_DESCRIPTIONS[name]
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties,
                       "required": list(properties), "additionalProperties": False},
    }}


def _wire_messages(messages: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for message in messages:
        if message.get("role") == "assistant" and "tool_calls" in message:
            converted.append({"role": "assistant", "content": None, "tool_calls": [
                {"id": call["id"], "type": "function", "function": {
                    "name": call["name"],
                    "arguments": json.dumps(call["arguments"], ensure_ascii=False),
                }} for call in message["tool_calls"]
            ]})
        else:
            converted.append(message)
    return converted


class ChatCompletionsTransport:
    """One HTTP request per complete() call; retries and redirects are disabled."""

    def __init__(
        self, connection: Connection, *, client: Any = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        expected = {
            "openrouter": "https://openrouter.ai/api/v1",
            "siliconflow": "https://api.siliconflow.cn/v1",
        }
        if connection.provider not in expected or connection.base_url != expected[connection.provider]:
            raise ValueError("provider endpoint is not allowlisted")
        if not isinstance(timeout_seconds, (int, float)) or not 5 <= timeout_seconds <= 120:
            raise ValueError("provider timeout is out of bounds")
        self.connection = connection
        self.client = client
        self.timeout_seconds = float(timeout_seconds)

    async def complete(
        self, *, model: str, messages: tuple[dict[str, Any], ...],
        allowed_tools: frozenset[str], max_output_tokens: int,
    ) -> ModelReply:
        try:
            import httpx
        except ImportError:
            raise TransportFailure("http_client_unavailable") from None
        if not allowed_tools.issubset(_TOOL_DESCRIPTIONS):
            raise TransportFailure("unsupported_tool_schema")
        body: dict[str, Any] = {
            "model": model,
            "messages": _wire_messages(messages),
            "stream": False,
            "max_tokens": max_output_tokens,
        }
        if allowed_tools:
            body["tools"] = [_tool_definition(name) for name in sorted(allowed_tools)]
            body["tool_choice"] = "auto"
        if self.connection.provider == "openrouter":
            body["provider"] = {
                "allow_fallbacks": False,
                "require_parameters": True,
            }
        url = self.connection.base_url + "/chat/completions"
        headers = {"Authorization": "Bearer " + self.connection.api_key,
                   "Content-Type": "application/json"}
        try:
            if self.client is None:
                async with httpx.AsyncClient(
                    timeout=self.timeout_seconds, follow_redirects=False, trust_env=False,
                ) as client:
                    response = await client.post(url, headers=headers, json=body)
            else:
                response = await self.client.post(url, headers=headers, json=body)
        except httpx.TimeoutException:
            raise TransportFailure("provider_timeout") from None
        except httpx.HTTPError:
            raise TransportFailure("provider_network_error") from None
        if response.status_code in {401, 403}:
            raise TransportFailure("provider_auth_error")
        if response.status_code == 429:
            raise TransportFailure("provider_rate_limited")
        if response.status_code < 200 or response.status_code >= 300:
            raise TransportFailure("provider_http_error")
        if len(response.content) > _MAX_RESPONSE_BYTES:
            raise TransportFailure("provider_response_too_large")
        try:
            document = response.json()
            if not isinstance(document, dict):
                raise ValueError
            choices = document["choices"]
            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError
            choice = choices[0]
            finish_reason = choice["finish_reason"]
            message = choice["message"]
            if not isinstance(message, dict):
                raise ValueError
            usage = document["usage"]
            if not isinstance(usage, dict):
                raise ValueError
            output_tokens = usage["completion_tokens"]
            if type(output_tokens) is not int or output_tokens < 0:
                raise ValueError
            observed_model = document.get("model")
            if observed_model is not None and not isinstance(observed_model, str):
                raise ValueError
            raw_calls = message.get("tool_calls") or []
            if not isinstance(raw_calls, list):
                raise ValueError
            if finish_reason != ("tool_calls" if raw_calls else "stop"):
                raise ValueError
            calls = tuple(ToolCall(
                call["id"], call["function"]["name"],
                call["function"]["arguments"],
            ) for call in raw_calls)
            content = message.get("content")
            if content is not None and not isinstance(content, str):
                raise ValueError
            return ModelReply(content, calls, observed_model, output_tokens)
        except (KeyError, TypeError, ValueError, IndexError):
            raise TransportFailure("provider_response_invalid") from None
