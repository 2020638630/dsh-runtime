"""Canonical identity foundation for future selection-policy artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from types import MappingProxyType
from typing import TypeAlias, cast


SUPPORTED_ARTIFACT_SCHEMA_VERSIONS = frozenset({"1"})

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | tuple["JsonValue", ...] | Mapping[str, "JsonValue"]

_ARTIFACT_FIELDS = frozenset(
    {
        "policy_id",
        "policy_version",
        "artifact_schema_version",
        "policy_content",
    }
)


class PolicyArtifactValidationError(ValueError):
    """A canonical policy artifact has an invalid identity or representation."""


def _validate_identity(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PolicyArtifactValidationError(f"{name} must be a non-empty string")
    return value


def _freeze_json(value: object, path: str) -> JsonValue:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PolicyArtifactValidationError(
                f"{path} must not contain non-finite numbers"
            )
        return value
    if isinstance(value, list):
        return tuple(
            _freeze_json(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        )
    if isinstance(value, Mapping):
        frozen: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise PolicyArtifactValidationError(
                    f"{path} must contain only string keys"
                )
            frozen[key] = _freeze_json(item, f"{path}.{key}")
        return MappingProxyType(frozen)
    raise PolicyArtifactValidationError(
        f"{path} must contain only JSON-compatible values"
    )


def _mutable_json(value: JsonValue) -> object:
    if isinstance(value, Mapping):
        return {key: _mutable_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_mutable_json(item) for item in value]
    return value


@dataclass(frozen=True)
class CanonicalPolicyArtifact:
    """Validated, immutable identity and opaque content for a future policy."""

    policy_id: str
    policy_version: str
    artifact_schema_version: str
    policy_content: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        _validate_identity("policy_id", self.policy_id)
        _validate_identity("policy_version", self.policy_version)
        schema_version = _validate_identity(
            "artifact_schema_version", self.artifact_schema_version
        )
        if schema_version not in SUPPORTED_ARTIFACT_SCHEMA_VERSIONS:
            raise PolicyArtifactValidationError(
                "unsupported artifact_schema_version: "
                f"{schema_version!r}"
            )
        if not isinstance(self.policy_content, Mapping):
            raise PolicyArtifactValidationError(
                "policy_content must be a JSON object"
            )
        frozen_content = _freeze_json(self.policy_content, "policy_content")
        object.__setattr__(
            self,
            "policy_content",
            cast(Mapping[str, JsonValue], frozen_content),
        )


def validate_policy_artifact(value: object) -> CanonicalPolicyArtifact:
    """Validate untrusted artifact data and return its immutable representation."""

    if isinstance(value, CanonicalPolicyArtifact):
        return value
    if not isinstance(value, Mapping):
        raise PolicyArtifactValidationError("policy artifact must be an object")

    keys = set(value.keys())
    if any(not isinstance(key, str) for key in keys):
        raise PolicyArtifactValidationError(
            "policy artifact must contain only string keys"
        )
    missing = sorted(_ARTIFACT_FIELDS - keys)
    if missing:
        raise PolicyArtifactValidationError(
            f"missing required policy artifact field(s): {', '.join(missing)}"
        )
    unexpected = sorted(keys - _ARTIFACT_FIELDS)
    if unexpected:
        raise PolicyArtifactValidationError(
            f"unexpected policy artifact field(s): {', '.join(unexpected)}"
        )

    return CanonicalPolicyArtifact(
        policy_id=value["policy_id"],
        policy_version=value["policy_version"],
        artifact_schema_version=value["artifact_schema_version"],
        policy_content=value["policy_content"],
    )


def canonical_policy_bytes(value: object) -> bytes:
    """Serialize one validated artifact to deterministic canonical UTF-8 JSON."""

    artifact = validate_policy_artifact(value)
    serializable = {
        "policy_id": artifact.policy_id,
        "policy_version": artifact.policy_version,
        "artifact_schema_version": artifact.artifact_schema_version,
        "policy_content": _mutable_json(artifact.policy_content),
    }
    return json.dumps(
        serializable,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def compute_policy_hash(value: object) -> str:
    """Return the lowercase SHA-256 hex digest of the canonical artifact."""

    return sha256(canonical_policy_bytes(value)).hexdigest()
