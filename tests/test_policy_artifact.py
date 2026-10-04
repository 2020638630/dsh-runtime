"""Deterministic identity tests for canonical policy artifacts."""

import pytest

from dsh_runtime.policy_artifact import (
    CanonicalPolicyArtifact,
    PolicyArtifactValidationError,
    canonical_policy_bytes,
    compute_policy_hash,
    validate_policy_artifact,
)


def _artifact(**overrides: object) -> dict[str, object]:
    artifact: dict[str, object] = {
        "policy_id": "selection-policy",
        "policy_version": "candidate-2",
        "artifact_schema_version": "1",
        "policy_content": {"alpha": 1, "nested": {"left": True, "right": None}},
    }
    artifact.update(overrides)
    return artifact


def test_same_artifact_has_same_hash() -> None:
    first = _artifact()
    second = _artifact()

    assert compute_policy_hash(first) == compute_policy_hash(second)


def test_field_order_does_not_change_hash() -> None:
    first = {
        "policy_id": "selection-policy",
        "policy_version": "candidate-2",
        "artifact_schema_version": "1",
        "policy_content": {"a": 1, "b": {"x": 2, "y": 3}},
    }
    second = {
        "policy_content": {"b": {"y": 3, "x": 2}, "a": 1},
        "artifact_schema_version": "1",
        "policy_version": "candidate-2",
        "policy_id": "selection-policy",
    }

    assert canonical_policy_bytes(first) == canonical_policy_bytes(second)
    assert compute_policy_hash(first) == compute_policy_hash(second)


def test_policy_content_mutation_changes_hash() -> None:
    first = _artifact(policy_content={"value": "before"})
    second = _artifact(policy_content={"value": "after"})

    assert compute_policy_hash(first) != compute_policy_hash(second)


def test_missing_policy_identity_is_rejected() -> None:
    artifact = _artifact()
    del artifact["policy_id"]

    with pytest.raises(PolicyArtifactValidationError, match="policy_id"):
        validate_policy_artifact(artifact)


def test_unsupported_artifact_schema_version_is_rejected() -> None:
    with pytest.raises(
        PolicyArtifactValidationError,
        match="unsupported artifact_schema_version",
    ):
        validate_policy_artifact(_artifact(artifact_schema_version="unknown"))


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        (field, invalid_value)
        for field in ("policy_id", "policy_version", "artifact_schema_version")
        for invalid_value in (None, "", "   ")
    ],
)
def test_identity_fields_reject_null_empty_and_whitespace(
    field: str, invalid_value: object
) -> None:
    artifact = _artifact()
    artifact[field] = invalid_value

    with pytest.raises(PolicyArtifactValidationError, match=field):
        validate_policy_artifact(artifact)


def test_policy_content_must_be_a_json_object() -> None:
    with pytest.raises(PolicyArtifactValidationError, match="JSON object"):
        validate_policy_artifact(_artifact(policy_content=None))


def test_policy_content_rejects_non_json_values() -> None:
    with pytest.raises(PolicyArtifactValidationError, match="JSON-compatible"):
        validate_policy_artifact(_artifact(policy_content={"bad": object()}))


def test_validated_artifact_is_detached_from_mutable_input() -> None:
    content = {"items": ["one"]}
    artifact = validate_policy_artifact(_artifact(policy_content=content))
    before = compute_policy_hash(artifact)

    content["items"].append("two")

    assert isinstance(artifact, CanonicalPolicyArtifact)
    assert compute_policy_hash(artifact) == before
