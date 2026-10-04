"""Deterministic tests for the policy artifact loading boundary."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import pytest

from dsh_runtime.policy_artifact import CanonicalPolicyArtifact
from dsh_runtime.policy_artifact_loader import (
    FilePolicyArtifactSource,
    PolicyArtifactHashMismatchError,
    PolicyArtifactLoadError,
    PolicyArtifactLoadValidationError,
    PolicyArtifactParseError,
    PolicyArtifactSourceError,
    load_policy_artifact,
)


def _artifact(**overrides: object) -> dict[str, object]:
    artifact: dict[str, object] = {
        "policy_id": "selection-policy",
        "policy_version": "candidate-2",
        "artifact_schema_version": "1",
        "policy_content": {"alpha": 1, "nested": {"enabled": True}},
    }
    artifact.update(overrides)
    return artifact


@dataclass(frozen=True)
class InMemoryPolicyArtifactSource:
    document: str

    def read_text(self) -> str:
        return self.document


def _source(artifact: dict[str, object]) -> InMemoryPolicyArtifactSource:
    return InMemoryPolicyArtifactSource(json.dumps(artifact))


def test_load_valid_artifact_exposes_identity() -> None:
    loaded = load_policy_artifact(_source(_artifact()))

    assert isinstance(loaded.artifact, CanonicalPolicyArtifact)
    assert loaded.identity.policy_id == "selection-policy"
    assert loaded.identity.policy_version == "candidate-2"
    assert loaded.identity.artifact_schema_version == "1"
    assert len(loaded.identity.policy_hash) == 64


def test_same_artifact_loaded_twice_has_same_identity() -> None:
    source = _source(_artifact())

    first = load_policy_artifact(source)
    second = load_policy_artifact(source)

    assert first.identity == second.identity


def test_modified_artifact_fails_expected_hash_verification() -> None:
    original = load_policy_artifact(
        _source(_artifact(policy_content={"value": "before"}))
    )
    modified = _source(_artifact(policy_content={"value": "after"}))

    with pytest.raises(PolicyArtifactHashMismatchError):
        load_policy_artifact(
            modified,
            expected_policy_hash=original.identity.policy_hash,
        )


def test_missing_filesystem_source_is_rejected(tmp_path: Path) -> None:
    source = FilePolicyArtifactSource(tmp_path / "missing-policy.json")

    with pytest.raises(PolicyArtifactSourceError) as caught:
        load_policy_artifact(source)

    assert isinstance(caught.value, PolicyArtifactLoadError)
    assert isinstance(caught.value.__cause__, FileNotFoundError)


def test_invalid_json_is_rejected() -> None:
    source = InMemoryPolicyArtifactSource('{"policy_id":')

    with pytest.raises(PolicyArtifactParseError):
        load_policy_artifact(source)


def test_invalid_artifact_is_rejected_as_validation_failure() -> None:
    artifact = _artifact()
    del artifact["policy_version"]

    with pytest.raises(
        PolicyArtifactLoadValidationError,
        match="policy_version",
    ):
        load_policy_artifact(_source(artifact))


def test_loader_does_not_mutate_in_memory_artifact() -> None:
    artifact = _artifact(policy_content={"items": ["one", "two"]})
    before = json.loads(json.dumps(artifact))

    load_policy_artifact(_source(artifact))

    assert artifact == before


def test_filesystem_source_loads_utf8_json(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    artifact = _artifact(policy_content={"label": "策略"})
    path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")

    loaded = load_policy_artifact(FilePolicyArtifactSource(path))

    assert loaded.artifact.policy_content["label"] == "策略"
