"""Deterministic tests for session policy identity pinning."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass
import json

import pytest

from dsh_runtime.policy_artifact_loader import (
    LoadedPolicyArtifact,
    PolicyArtifactIdentity,
    load_policy_artifact,
)
from dsh_runtime.session_policy_pin import (
    SessionPolicyHashMismatchError,
    SessionPolicyIdMismatchError,
    SessionPolicyPin,
    SessionPolicyPinError,
    SessionPolicyPinValidationError,
    SessionPolicySchemaVersionMismatchError,
    SessionPolicySessionMismatchError,
    SessionPolicyVersionMismatchError,
    create_session_policy_pin,
    verify_session_policy_pin,
)


@dataclass(frozen=True)
class InMemoryPolicyArtifactSource:
    document: str

    def read_text(self) -> str:
        return self.document


def _loaded_artifact(
    *,
    policy_id: str = "selection-policy",
    policy_version: str = "v1",
    artifact_schema_version: str = "1",
    policy_content: object = None,
) -> LoadedPolicyArtifact:
    content = {"marker": "stable"} if policy_content is None else policy_content
    document = json.dumps(
        {
            "policy_id": policy_id,
            "policy_version": policy_version,
            "artifact_schema_version": artifact_schema_version,
            "policy_content": content,
        }
    )
    return load_policy_artifact(InMemoryPolicyArtifactSource(document))


def _loaded_with_identity(**overrides: str) -> LoadedPolicyArtifact:
    loaded = _loaded_artifact()
    values = {
        "policy_id": loaded.identity.policy_id,
        "policy_version": loaded.identity.policy_version,
        "artifact_schema_version": loaded.identity.artifact_schema_version,
        "policy_hash": loaded.identity.policy_hash,
    }
    values.update(overrides)
    return LoadedPolicyArtifact(
        artifact=loaded.artifact,
        identity=PolicyArtifactIdentity(**values),
    )


def test_create_pin_from_valid_loaded_policy() -> None:
    loaded = _loaded_artifact()

    pin = create_session_policy_pin("session-A", loaded)

    assert pin == SessionPolicyPin(
        session_id="session-A",
        policy_identity=loaded.identity,
    )


@pytest.mark.parametrize("session_id", [None, "", "   "])
def test_invalid_session_identity_is_rejected(session_id: object) -> None:
    with pytest.raises(SessionPolicyPinValidationError, match="session_id"):
        create_session_policy_pin(session_id, _loaded_artifact())  # type: ignore[arg-type]


def test_pin_is_immutable() -> None:
    pin = create_session_policy_pin("session-A", _loaded_artifact())

    with pytest.raises(FrozenInstanceError):
        pin.session_id = "session-B"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        pin.policy_identity = _loaded_artifact().identity  # type: ignore[misc]


def test_same_session_and_exact_identity_verifies() -> None:
    loaded = _loaded_artifact()
    pin = create_session_policy_pin("session-A", loaded)

    verified = verify_session_policy_pin(pin, "session-A", loaded)

    assert verified is pin


def test_different_session_is_rejected() -> None:
    pin = create_session_policy_pin("session-A", _loaded_artifact())

    with pytest.raises(SessionPolicySessionMismatchError):
        verify_session_policy_pin(pin, "session-B", _loaded_artifact())


def test_policy_id_mismatch_is_rejected() -> None:
    pin = create_session_policy_pin("session-A", _loaded_artifact())
    candidate = _loaded_with_identity(policy_id="different-policy")

    with pytest.raises(SessionPolicyIdMismatchError):
        verify_session_policy_pin(pin, "session-A", candidate)


def test_policy_version_mismatch_is_rejected() -> None:
    pin = create_session_policy_pin("session-A", _loaded_artifact())
    candidate = _loaded_with_identity(policy_version="v2")

    with pytest.raises(SessionPolicyVersionMismatchError):
        verify_session_policy_pin(pin, "session-A", candidate)


def test_schema_version_mismatch_is_rejected() -> None:
    pin = create_session_policy_pin("session-A", _loaded_artifact())
    candidate = _loaded_with_identity(artifact_schema_version="2")

    with pytest.raises(SessionPolicySchemaVersionMismatchError):
        verify_session_policy_pin(pin, "session-A", candidate)


def test_hash_mismatch_is_rejected_even_when_other_identity_fields_match() -> None:
    pin = create_session_policy_pin("session-A", _loaded_artifact())
    candidate = _loaded_artifact(policy_content={"marker": "changed"})

    with pytest.raises(SessionPolicyHashMismatchError):
        verify_session_policy_pin(pin, "session-A", candidate)


def test_newer_policy_version_is_not_an_automatic_upgrade() -> None:
    pin = create_session_policy_pin("session-A", _loaded_artifact())
    newer = _loaded_artifact(policy_version="v2")

    with pytest.raises(SessionPolicyVersionMismatchError):
        verify_session_policy_pin(pin, "session-A", newer)


def test_same_hash_does_not_bypass_policy_id_match() -> None:
    pin = create_session_policy_pin("session-A", _loaded_artifact())
    candidate = _loaded_with_identity(policy_id="different-policy")

    assert candidate.identity.policy_hash == pin.policy_identity.policy_hash
    with pytest.raises(SessionPolicyIdMismatchError):
        verify_session_policy_pin(pin, "session-A", candidate)


def test_mutating_source_data_does_not_change_pin() -> None:
    source_content = {"items": ["one", "two"]}
    loaded = _loaded_artifact(policy_content=source_content)
    pin = create_session_policy_pin("session-A", loaded)
    pinned_identity = pin.policy_identity

    source_content["items"].append("three")

    assert pin.policy_identity is pinned_identity
    assert loaded.artifact.policy_content["items"] == ("one", "two")


def test_malformed_pin_and_loaded_artifact_inputs_are_validation_failures() -> None:
    loaded = _loaded_artifact()

    with pytest.raises(SessionPolicyPinError):
        create_session_policy_pin("session-A", object())  # type: ignore[arg-type]
    with pytest.raises(SessionPolicyPinValidationError):
        verify_session_policy_pin(object(), "session-A", loaded)  # type: ignore[arg-type]
