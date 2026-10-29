"""Fail-closed, credential-free contract for an opt-in model API agent.

This module is intentionally separate from the active CLI role configuration.
Parsing it never enables an API call or changes a production role.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping


_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}\Z")
_REFERENCE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
_ROLES = frozenset({"worker", "reviewer", "inspector"})
_PROVIDERS = frozenset({"openrouter", "siliconflow"})
_MAX_DOCUMENT_CHARS = 16_384


def _no_duplicate_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate API agent configuration field")
        result[key] = value
    return result


@dataclass(frozen=True)
class ApiRole:
    provider: str
    model: str
    connection_ref: str
    max_requests: int
    max_tool_calls: int
    max_output_tokens: int


@dataclass(frozen=True)
class CliRole:
    adapter: str
    model: str | None


@dataclass(frozen=True)
class ApiAgentConfig:
    worker: ApiRole | CliRole
    reviewer: ApiRole | CliRole
    inspector: ApiRole | CliRole

    @classmethod
    def from_json(cls, raw: str) -> "ApiAgentConfig":
        if not raw or len(raw) > _MAX_DOCUMENT_CHARS:
            raise ValueError("API agent configuration must be non-empty and bounded")
        try:
            document = json.loads(raw, object_pairs_hook=_no_duplicate_fields)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError("API agent configuration must be valid JSON") from exc
        return cls.from_document(document)

    @classmethod
    def from_document(cls, document: Any) -> "ApiAgentConfig":
        if not isinstance(document, dict) or set(document) != {"schema_version", "roles"}:
            raise ValueError("API agent configuration requires schema_version and roles")
        if type(document["schema_version"]) is not int or document["schema_version"] != 2:
            raise ValueError("API agent configuration schema_version must be 2")
        roles = document["roles"]
        if not isinstance(roles, dict) or set(roles) != _ROLES:
            raise ValueError("API agent configuration requires worker, reviewer and inspector")
        return cls(**{name: _parse_role(name, roles[name]) for name in _ROLES})


def _bounded_integer(value: Any, label: str, maximum: int) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{label} must be an integer from 1 to {maximum}")
    return value


def _parse_role(name: str, value: Any) -> ApiRole | CliRole:
    adapter = value.get("adapter") if isinstance(value, Mapping) else None
    if isinstance(adapter, str) and adapter in {"codebuddy", "codex"}:
        if set(value) != {"adapter", "model"}:
            raise ValueError(f"{name} CLI role fields are invalid")
        if name != "worker" and value["adapter"] != "codex":
            raise ValueError(f"{name} CLI adapter is unsupported")
        model = value["model"]
        if model is not None and (not isinstance(model, str) or not _IDENTIFIER.fullmatch(model)):
            raise ValueError(f"{name} CLI model ID is invalid")
        return CliRole(value["adapter"], model)
    required = {
        "adapter", "provider", "model", "connection_ref",
        "max_requests", "max_tool_calls", "max_output_tokens",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise ValueError(f"{name} API role fields are invalid")
    if value["adapter"] != "api_agent":
        raise ValueError(f"{name} adapter must be api_agent")
    if not isinstance(value["provider"], str) or value["provider"] not in _PROVIDERS:
        raise ValueError(f"{name} provider is unsupported")
    if not isinstance(value["model"], str) or not _IDENTIFIER.fullmatch(value["model"]):
        raise ValueError(f"{name} model ID is invalid")
    if not isinstance(value["connection_ref"], str) or not _REFERENCE.fullmatch(value["connection_ref"]):
        raise ValueError(f"{name} connection_ref is invalid")
    return ApiRole(
        provider=value["provider"],
        model=value["model"],
        connection_ref=value["connection_ref"],
        max_requests=_bounded_integer(value["max_requests"], "max_requests", 12),
        max_tool_calls=_bounded_integer(value["max_tool_calls"], "max_tool_calls", 40),
        max_output_tokens=_bounded_integer(value["max_output_tokens"], "max_output_tokens", 8192),
    )
