"""Frozen, versioned role selection for one Runtime controller.

The host may pass this small JSON object through an owned environment value.
It contains no credentials. Unsupported adapter/model combinations fail before
the first worker process is started.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Mapping


ROLE_CONFIG_ENV = "DSH_RUNTIME_ROLE_CONFIG_JSON"
_MAX_CONFIG_CHARS = 16_384
_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}\Z")
_ROLE_NAMES = frozenset({"worker", "reviewer", "inspector"})


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate role config field: {key}")
        result[key] = value
    return result


@dataclass(frozen=True)
class RoleSelection:
    adapter: str
    model: str | None = None

    def params(self, prompt: str) -> dict[str, str]:
        result = {"prompt": prompt}
        if self.model is not None:
            result["model"] = self.model
        return result


@dataclass(frozen=True)
class RoleConfig:
    worker: RoleSelection
    reviewer: RoleSelection
    inspector: RoleSelection

    @classmethod
    def defaults(cls) -> "RoleConfig":
        return cls(
            worker=RoleSelection("codebuddy"),
            reviewer=RoleSelection("codex"),
            inspector=RoleSelection("codex"),
        )

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "RoleConfig":
        env = os.environ if environment is None else environment
        raw = env.get(ROLE_CONFIG_ENV)
        if raw is None:
            return cls.defaults()
        if not raw or len(raw) > _MAX_CONFIG_CHARS:
            raise ValueError(f"{ROLE_CONFIG_ENV} must be non-empty and bounded")
        try:
            document = json.loads(raw, object_pairs_hook=_object_without_duplicates)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError(f"{ROLE_CONFIG_ENV} must contain valid JSON") from exc
        return cls.from_document(document)

    @classmethod
    def from_document(cls, document: Any) -> "RoleConfig":
        if not isinstance(document, dict) or set(document) != {"schema_version", "roles"}:
            raise ValueError("role config requires only schema_version and roles")
        if type(document["schema_version"]) is not int or document["schema_version"] != 1:
            raise ValueError("role config schema_version must be 1")
        roles = document["roles"]
        if not isinstance(roles, dict) or set(roles) != _ROLE_NAMES:
            raise ValueError("role config requires worker, reviewer and inspector")
        return cls(**{role: _selection(role, roles[role]) for role in _ROLE_NAMES})


def _selection(role: str, value: Any) -> RoleSelection:
    if not isinstance(value, dict) or set(value) != {"adapter", "model"}:
        raise ValueError(f"{role} requires adapter and model")
    adapter = value["adapter"]
    permitted = {"codebuddy", "codex"} if role == "worker" else {"codex"}
    if not isinstance(adapter, str) or adapter not in permitted:
        raise ValueError(f"{role} adapter is unsupported")
    model = value["model"]
    if model is not None and (not isinstance(model, str) or not _MODEL_ID.fullmatch(model)):
        raise ValueError(f"{role} model must be a bounded model ID or null")
    if adapter == "codebuddy" and model is not None:
        raise ValueError("CodeBuddy model overrides are not yet verified")
    return RoleSelection(adapter=adapter, model=model)
