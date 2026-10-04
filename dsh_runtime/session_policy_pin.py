"""Pure session-to-policy identity pinning contracts."""

from __future__ import annotations

from dataclasses import dataclass
import hmac

from .policy_artifact_loader import LoadedPolicyArtifact, PolicyArtifactIdentity


class SessionPolicyPinError(Exception):
    """A session policy pin could not be created or verified."""


class SessionPolicyPinValidationError(SessionPolicyPinError):
    """Pin input is malformed or did not come from the loading boundary."""


class SessionPolicySessionMismatchError(SessionPolicyPinError):
    """A resume attempt targeted a different session."""


class SessionPolicyIdentityMismatchError(SessionPolicyPinError):
    """A resume attempt supplied a different policy identity."""


class SessionPolicyIdMismatchError(SessionPolicyIdentityMismatchError):
    """The candidate policy id differs from the pinned policy id."""


class SessionPolicyVersionMismatchError(SessionPolicyIdentityMismatchError):
    """The candidate policy version differs from the pinned version."""


class SessionPolicySchemaVersionMismatchError(SessionPolicyIdentityMismatchError):
    """The candidate artifact schema version differs from the pinned version."""


class SessionPolicyHashMismatchError(SessionPolicyIdentityMismatchError):
    """The candidate canonical policy hash differs from the pinned hash."""


def _require_session_id(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SessionPolicyPinValidationError(
            "session_id must be a non-empty string"
        )
    return value


def _require_loaded_artifact(value: object) -> LoadedPolicyArtifact:
    if not isinstance(value, LoadedPolicyArtifact):
        raise SessionPolicyPinValidationError(
            "loaded_artifact must be a LoadedPolicyArtifact"
        )
    if not isinstance(value.identity, PolicyArtifactIdentity):
        raise SessionPolicyPinValidationError(
            "loaded_artifact.identity must be a PolicyArtifactIdentity"
        )
    return value


@dataclass(frozen=True)
class SessionPolicyPin:
    """An immutable binding between one session and one exact policy identity."""

    session_id: str
    policy_identity: PolicyArtifactIdentity

    def __post_init__(self) -> None:
        _require_session_id(self.session_id)
        if not isinstance(self.policy_identity, PolicyArtifactIdentity):
            raise SessionPolicyPinValidationError(
                "policy_identity must be a PolicyArtifactIdentity"
            )


def create_session_policy_pin(
    session_id: str,
    loaded_artifact: LoadedPolicyArtifact,
) -> SessionPolicyPin:
    """Pin a session to the verified identity produced by the artifact loader."""

    validated_session_id = _require_session_id(session_id)
    validated_artifact = _require_loaded_artifact(loaded_artifact)
    return SessionPolicyPin(
        session_id=validated_session_id,
        policy_identity=validated_artifact.identity,
    )


def verify_session_policy_pin(
    pin: SessionPolicyPin,
    session_id: str,
    candidate_artifact: LoadedPolicyArtifact,
) -> SessionPolicyPin:
    """Require the same session and exact loaded policy identity as the pin."""

    if not isinstance(pin, SessionPolicyPin):
        raise SessionPolicyPinValidationError(
            "pin must be a SessionPolicyPin"
        )
    validated_session_id = _require_session_id(session_id)
    candidate = _require_loaded_artifact(candidate_artifact).identity
    pinned = pin.policy_identity

    if validated_session_id != pin.session_id:
        raise SessionPolicySessionMismatchError(
            "session_id does not match the pinned session"
        )
    if candidate.policy_id != pinned.policy_id:
        raise SessionPolicyIdMismatchError(
            "candidate policy_id does not match the pinned policy_id"
        )
    if candidate.policy_version != pinned.policy_version:
        raise SessionPolicyVersionMismatchError(
            "candidate policy_version does not match the pinned policy_version"
        )
    if candidate.artifact_schema_version != pinned.artifact_schema_version:
        raise SessionPolicySchemaVersionMismatchError(
            "candidate artifact_schema_version does not match the pinned version"
        )
    if not hmac.compare_digest(candidate.policy_hash, pinned.policy_hash):
        raise SessionPolicyHashMismatchError(
            "candidate policy_hash does not match the pinned policy_hash"
        )

    return pin
