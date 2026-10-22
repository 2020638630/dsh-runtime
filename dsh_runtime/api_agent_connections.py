"""Local-only API credentials. Never serialize Connection to evidence or logs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_ENDPOINTS = {
    "openrouter": "https://openrouter.ai/api/v1",
    "siliconflow": "https://api.siliconflow.cn/v1",
}
_MAX_FILE_BYTES = 32_768


def _unique_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("duplicate connection field")
        result[name] = value
    return result


@dataclass(frozen=True)
class Connection:
    provider: str
    base_url: str
    api_key: str = field(repr=False)


class ConnectionCatalog:
    def __init__(self, connections: dict[str, Connection]) -> None:
        self._connections = connections

    def get(self, reference: str, provider: str) -> Connection:
        connection = self._connections.get(reference)
        if connection is None or connection.provider != provider:
            raise ValueError("connection_ref is missing or provider does not match")
        return connection

    @classmethod
    def from_file(cls, path: Path) -> "ConnectionCatalog":
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            raise ValueError("connection file must be an existing absolute regular file")
        if any((parent / ".git").exists() for parent in path.parents):
            raise ValueError("connection file must be outside a Git worktree")
        # The caller supplies this path out of band. It is never model input.
        if path.stat().st_size > _MAX_FILE_BYTES:
            raise ValueError("connection file is too large")
        try:
            raw = path.read_bytes()
            if len(raw) > _MAX_FILE_BYTES:
                raise ValueError("connection file is too large")
            document = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_fields)
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise ValueError("connection file is unreadable or invalid JSON") from None
        if (not isinstance(document, dict) or set(document) != {"schema_version", "connections"}
            or type(document["schema_version"]) is not int or document["schema_version"] != 1
            or not isinstance(document["connections"], dict)):
            raise ValueError("connection file schema is invalid")
        connections: dict[str, Connection] = {}
        for reference, entry in document["connections"].items():
            if (not isinstance(reference, str) or not reference.isascii()
                or not reference.replace("_", "").replace("-", "").isalnum()
                or not reference[0].isalpha() or len(reference) > 64):
                raise ValueError("connection reference is invalid")
            if not isinstance(entry, dict) or set(entry) != {"provider", "base_url", "api_key"}:
                raise ValueError("connection entry fields are invalid")
            provider = entry["provider"]
            if not isinstance(provider, str) or provider not in _ENDPOINTS:
                raise ValueError("connection provider is unsupported")
            if entry["base_url"] != _ENDPOINTS[provider]:
                raise ValueError("connection endpoint is not allowlisted")
            key = entry["api_key"]
            if (not isinstance(key, str) or not 8 <= len(key) <= 512
                or key.startswith("REPLACE_") or any(c.isspace() for c in key)):
                raise ValueError("connection API key is invalid")
            connections[reference] = Connection(provider, _ENDPOINTS[provider], key)
        if not connections:
            raise ValueError("connection file must contain at least one connection")
        return cls(connections)
