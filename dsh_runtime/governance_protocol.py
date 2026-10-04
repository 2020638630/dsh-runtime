"""Strict JSONL wire contract for the isolated governance worker."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .gate_contract import GateRequestStructure
from .policy_artifact_loader import PolicyArtifactIdentity


PROTOCOL_VERSION = "1"


class GovernanceProtocolError(ValueError):
    """A governance protocol message is malformed or unsupported."""


def _object(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(
        not isinstance(key, str) for key in value
    ):
        raise GovernanceProtocolError("message must be a JSON object")
    return value


def _fields(
    value: Mapping[str, Any], required: set[str], optional: set[str] | None = None
) -> None:
    optional = optional or set()
    present = set(value)
    missing = sorted(required - present)
    extra = sorted(present - required - optional)
    if missing:
        raise GovernanceProtocolError(
            f"missing required field(s): {', '.join(missing)}"
        )
    if extra:
        raise GovernanceProtocolError(
            f"unexpected field(s): {', '.join(extra)}"
        )


def _text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GovernanceProtocolError(f"{name} must be a non-empty string")
    return value


def _text_array(name: str, value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise GovernanceProtocolError(f"{name} must be an array")
    result = tuple(_text(name, item) for item in value)
    if len(set(result)) != len(result):
        raise GovernanceProtocolError(f"{name} must not contain duplicates")
    return result


@dataclass(frozen=True)
class InitializeRequest:
    """Trusted deployment inputs supplied once at worker startup."""

    policy_source: str
    expected_policy_hash: str
    enabled_workloads: tuple[str, ...]
    audit_path: str


@dataclass(frozen=True)
class BindSessionRequest:
    """Create or resume one exact session policy pin."""

    request_id: str
    session_id: str
    mode: str
    pinned_policy_identity: PolicyArtifactIdentity | None


@dataclass(frozen=True)
class EvaluatePreStartRequest:
    """Trusted facts needed for one pre-start governance evaluation."""

    request_id: str
    session_id: str
    caller_id: str
    pinned_policy_identity: PolicyArtifactIdentity
    task_kind: str
    reason_code: str
    request_structure: GateRequestStructure


OperationalRequest = BindSessionRequest | EvaluatePreStartRequest


def parse_identity(value: object) -> PolicyArtifactIdentity:
    """Parse an exact policy identity object with no extension fields."""

    message = _object(value)
    required = {
        "policy_id",
        "policy_version",
        "artifact_schema_version",
        "policy_hash",
    }
    _fields(message, required)
    identity = PolicyArtifactIdentity(
        policy_id=_text("policy_id", message["policy_id"]),
        policy_version=_text("policy_version", message["policy_version"]),
        artifact_schema_version=_text(
            "artifact_schema_version", message["artifact_schema_version"]
        ),
        policy_hash=_text("policy_hash", message["policy_hash"]),
    )
    if len(identity.policy_hash) != 64 or any(
        character not in "0123456789abcdef"
        for character in identity.policy_hash
    ):
        raise GovernanceProtocolError(
            "policy_hash must be a lowercase SHA-256 hex digest"
        )
    return identity


def serialize_identity(identity: PolicyArtifactIdentity) -> dict[str, str]:
    """Serialize a loader-established policy identity."""

    if not isinstance(identity, PolicyArtifactIdentity):
        raise GovernanceProtocolError(
            "policy_identity must be a PolicyArtifactIdentity"
        )
    return {
        "policy_id": identity.policy_id,
        "policy_version": identity.policy_version,
        "artifact_schema_version": identity.artifact_schema_version,
        "policy_hash": identity.policy_hash,
    }


def parse_initialize(value: object) -> InitializeRequest:
    """Parse the first and only INITIALIZE request."""

    message = _object(value)
    required = {
        "kind",
        "protocol_version",
        "policy_source",
        "expected_policy_hash",
        "enabled_workloads",
        "audit_path",
    }
    _fields(message, required)
    if message["kind"] != "INITIALIZE":
        raise GovernanceProtocolError("first message must be INITIALIZE")
    if message["protocol_version"] != PROTOCOL_VERSION:
        raise GovernanceProtocolError("unsupported protocol_version")
    return InitializeRequest(
        policy_source=_text("policy_source", message["policy_source"]),
        expected_policy_hash=_text(
            "expected_policy_hash", message["expected_policy_hash"]
        ),
        enabled_workloads=_text_array(
            "enabled_workloads", message["enabled_workloads"]
        ),
        audit_path=_text("audit_path", message["audit_path"]),
    )


def parse_operational(value: object) -> OperationalRequest:
    """Parse one post-initialization operation with strict discrimination."""

    message = _object(value)
    kind = message.get("kind")
    if kind == "BIND_SESSION":
        base = {"kind", "request_id", "session_id", "mode"}
        mode = message.get("mode")
        if mode == "create":
            _fields(message, base)
            identity = None
        elif mode == "resume":
            _fields(message, base | {"pinned_policy_identity"})
            identity = parse_identity(message["pinned_policy_identity"])
        else:
            raise GovernanceProtocolError("mode must be create or resume")
        return BindSessionRequest(
            request_id=_text("request_id", message["request_id"]),
            session_id=_text("session_id", message["session_id"]),
            mode=mode,
            pinned_policy_identity=identity,
        )
    if kind == "EVALUATE_PRE_START":
        required = {
            "kind",
            "request_id",
            "session_id",
            "caller_id",
            "pinned_policy_identity",
            "task_kind",
            "reason_code",
            "request_structure",
        }
        _fields(message, required)
        structure = _object(message["request_structure"])
        _fields(structure, {"request_type", "required_fields"})
        return EvaluatePreStartRequest(
            request_id=_text("request_id", message["request_id"]),
            session_id=_text("session_id", message["session_id"]),
            caller_id=_text("caller_id", message["caller_id"]),
            pinned_policy_identity=parse_identity(
                message["pinned_policy_identity"]
            ),
            task_kind=_text("task_kind", message["task_kind"]),
            reason_code=_text("reason_code", message["reason_code"]),
            request_structure=GateRequestStructure(
                request_type=_text("request_type", structure["request_type"]),
                required_fields=_text_array(
                    "required_fields", structure["required_fields"]
                ),
            ),
        )
    raise GovernanceProtocolError("unknown operational message kind")


def recover_request_id(value: object) -> str | None:
    """Return a usable correlation id from a malformed object, if present."""

    if isinstance(value, Mapping):
        candidate = value.get("request_id")
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    return None
