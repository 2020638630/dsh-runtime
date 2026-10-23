"""Bounded model/tool loop; transport and tools are injected and own no secrets here."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from dsh_runtime.api_agent_contract import ApiRole


# Directory names cannot be safely enumerated by the current path-based broker
# under concurrent junction/rename swaps. Keep the API tool surface explicit.
READ_TOOLS = frozenset({"read_file"})
# No API worker write tool is qualified for the model-facing surface yet.
WRITE_TOOLS: frozenset[str] = frozenset()
MAX_TOOL_ARGUMENT_CHARS = 16_384
# A 32 KiB file can expand when JSON-escaped with verified byte metadata.
MAX_TOOL_RESULT_CHARS = 65_536
MAX_TOOL_COMPANION_CHARS = 4_096
MAX_FINAL_CHARS = 100_000


class TransportFailure(Exception):
    """Safe, predetermined provider failure category without response contents."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments_json: str


@dataclass(frozen=True)
class ModelReply:
    text: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    observed_model: str | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class AgentOutcome:
    success: bool
    text: str | None
    error_code: str | None
    requested_model: str
    observed_model: str | None
    requests: int
    tool_calls: int


class ModelTransport(Protocol):
    async def complete(
        self, *, model: str, messages: tuple[dict[str, Any], ...],
        allowed_tools: frozenset[str], max_output_tokens: int,
    ) -> ModelReply: ...


class ToolBroker(Protocol):
    async def execute(self, name: str, arguments: dict[str, Any]) -> str: ...


async def run_api_agent(
    role: ApiRole, prompt: str, transport: ModelTransport, broker: ToolBroker,
    *, role_name: str, allow_workspace_write: bool,
) -> AgentOutcome:
    """Run one stage. Any uncertain model/tool state fails closed without replay."""
    allowed = READ_TOOLS | (
        WRITE_TOOLS if role_name == "worker" and allow_workspace_write else frozenset()
    )
    messages: list[dict[str, Any]] = []
    if role_name == "reviewer":
        messages.append({"role": "system", "content": (
            "You are an independent read-only repository reviewer. Use the "
            "provider's native read_file function call to inspect relevant "
            "workspace files before giving a verdict. Pass a workspace-relative "
            "filename in the path field, never an absolute path; inspect the "
            "requested changed file when it is named. Its JSON response "
            "contains verified byte_length, sha256, and UTF-8 content from "
            "one opened file; use those fields for exact byte claims. Do not "
            "invent file metadata or claim bytes not supported by the tool. "
            "A generic unavailable result means that read did not succeed; "
            "retry with a valid relative filename within the tool budget. "
            "Writing a tool call "
            "as text or XML does not execute it. Never modify files. End "
            "with exactly one verdict line: DSH_VERIFICATION: PASS or "
            "DSH_VERIFICATION: FAIL. If file evidence is unavailable, FAIL."
        )})
    messages.append({"role": "user", "content": prompt})
    observed: str | None = None
    calls_used = 0
    successful_reads = 0
    output_tokens_used = 0

    def outcome(error: str | None, text: str | None, requests: int) -> AgentOutcome:
        return AgentOutcome(error is None, text, error, role.model, observed, requests, calls_used)

    if role_name not in {"worker", "reviewer", "inspector"}:
        return outcome("invalid_role", None, 0)
    if not isinstance(prompt, str) or not prompt or len(prompt) > 100_000:
        return outcome("invalid_prompt", None, 0)
    for request_number in range(1, role.max_requests + 1):
        if output_tokens_used >= role.max_output_tokens:
            return outcome("token_budget_exhausted", None, request_number - 1)
        try:
            reply = await transport.complete(
                model=role.model, messages=tuple(messages), allowed_tools=allowed,
                max_output_tokens=role.max_output_tokens - output_tokens_used,
            )
        except TransportFailure as exc:
            return outcome(exc.code, None, request_number)
        except Exception:
            # Transport exceptions can contain URLs, headers, or provider payloads.
            return outcome("provider_error", None, request_number)
        if not isinstance(reply, ModelReply):
            return outcome("invalid_model_reply", None, request_number)
        if reply.observed_model is not None:
            if not isinstance(reply.observed_model, str) or len(reply.observed_model) > 128:
                return outcome("invalid_observed_model", None, request_number)
            if observed is not None and observed != reply.observed_model:
                return outcome("model_changed", None, request_number)
            observed = reply.observed_model
            if observed != role.model:
                return outcome("model_mismatch", None, request_number)
        if type(reply.output_tokens) is not int or reply.output_tokens < 0:
            return outcome("missing_or_invalid_token_count", None, request_number)
        output_tokens_used += reply.output_tokens
        if output_tokens_used > role.max_output_tokens:
            return outcome("token_budget_exhausted", None, request_number)
        if reply.tool_calls:
            # Some gateways attach explanatory text to a native tool call.
            # It is not a final answer or tool argument; discard it after a
            # strict bound and execute only the validated native calls.
            if reply.text is not None and (
                not isinstance(reply.text, str)
                or len(reply.text) > MAX_TOOL_COMPANION_CHARS
            ):
                return outcome("invalid_tool_companion_text", None, request_number)
            if calls_used + len(reply.tool_calls) > role.max_tool_calls:
                return outcome("tool_budget_exhausted", None, request_number)
            ids: set[str] = set()
            parsed: list[tuple[ToolCall, dict[str, Any]]] = []
            # Validate the entire batch before allowing a single side effect.
            for call in reply.tool_calls:
                if (not isinstance(call, ToolCall) or not isinstance(call.call_id, str)
                    or not call.call_id or len(call.call_id) > 128 or call.call_id in ids
                    or call.name not in allowed or not isinstance(call.arguments_json, str)
                    or len(call.arguments_json) > MAX_TOOL_ARGUMENT_CHARS):
                    return outcome("invalid_tool_call", None, request_number)
                ids.add(call.call_id)
                try:
                    arguments = json.loads(call.arguments_json, object_pairs_hook=_unique_fields)
                except (json.JSONDecodeError, ValueError):
                    return outcome("invalid_tool_arguments", None, request_number)
                if not isinstance(arguments, dict):
                    return outcome("invalid_tool_arguments", None, request_number)
                parsed.append((call, arguments))
            messages.append({"role": "assistant", "tool_calls": [
                {"id": call.call_id, "name": call.name, "arguments": arguments}
                for call, arguments in parsed
            ]})
            for call, arguments in parsed:
                try:
                    result = await broker.execute(call.name, arguments)
                except ValueError:
                    # Only the advertised read tool is available. A rejected
                    # path/content is a safe, bounded model-correctable error;
                    # neither the attempted path nor exception text is echoed.
                    calls_used += 1
                    messages.append({
                        "role": "tool", "tool_call_id": call.call_id,
                        "content": "read_file unavailable for that path",
                    })
                    continue
                except Exception:
                    return outcome("tool_error", None, request_number)
                calls_used += 1
                if not isinstance(result, str) or len(result) > MAX_TOOL_RESULT_CHARS:
                    return outcome("invalid_tool_result", None, request_number)
                if call.name == "read_file":
                    successful_reads += 1
                messages.append({"role": "tool", "tool_call_id": call.call_id, "content": result})
            continue
        if not isinstance(reply.text, str) or not reply.text or len(reply.text) > MAX_FINAL_CHARS:
            return outcome("invalid_final_text", None, request_number)
        if role_name == "reviewer" and successful_reads == 0:
            return outcome("reviewer_no_file_read", None, request_number)
        return outcome(None, reply.text, request_number)
    return outcome("request_budget_exhausted", None, role.max_requests)


def _unique_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate argument field")
        result[key] = value
    return result
