"""Semantic schema foundation for an already-loaded selection policy artifact."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from .policy_artifact import CanonicalPolicyArtifact
from .policy_artifact_loader import LoadedPolicyArtifact, PolicyArtifactIdentity


_SEMANTIC_FIELDS = frozenset({"authorized_workloads"})


class SelectionPolicySchemaError(Exception):
    """A loaded artifact cannot be represented as selection-policy semantics."""


class SelectionPolicyContentValidationError(SelectionPolicySchemaError):
    """The artifact policy_content has an invalid semantic object shape."""


class SelectionPolicyWorkloadValidationError(SelectionPolicySchemaError):
    """The authorized workload collection or an identifier is invalid."""


def _freeze_workload_identifiers(value: object) -> frozenset[str]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise SelectionPolicyWorkloadValidationError(
            "authorized_workloads must be an array"
        )

    identifiers: set[str] = set()
    for identifier in value:
        if not isinstance(identifier, str) or not identifier.strip():
            raise SelectionPolicyWorkloadValidationError(
                "authorized_workloads must contain only non-empty strings"
            )
        if identifier in identifiers:
            raise SelectionPolicyWorkloadValidationError(
                f"duplicate authorized workload: {identifier!r}"
            )
        identifiers.add(identifier)
    return frozenset(identifiers)


@dataclass(frozen=True)
class ValidatedSelectionPolicySemantics:
    """Minimal immutable facts expressed by selection-policy content."""

    authorized_workloads: Collection[str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "authorized_workloads",
            _freeze_workload_identifiers(self.authorized_workloads),
        )


@dataclass(frozen=True)
class LoadedSelectionPolicy:
    """Validated semantics associated with the loader-established identity."""

    policy_identity: PolicyArtifactIdentity
    semantics: ValidatedSelectionPolicySemantics

    def __post_init__(self) -> None:
        if not isinstance(self.policy_identity, PolicyArtifactIdentity):
            raise SelectionPolicyContentValidationError(
                "policy_identity must be a PolicyArtifactIdentity"
            )
        if not isinstance(self.semantics, ValidatedSelectionPolicySemantics):
            raise SelectionPolicyContentValidationError(
                "semantics must be ValidatedSelectionPolicySemantics"
            )


def parse_selection_policy_semantics(
    loaded_artifact: LoadedPolicyArtifact,
) -> LoadedSelectionPolicy:
    """Parse one loaded artifact's opaque content without authorizing workloads."""

    if not isinstance(loaded_artifact, LoadedPolicyArtifact):
        raise SelectionPolicyContentValidationError(
            "loaded_artifact must be a LoadedPolicyArtifact"
        )
    if not isinstance(loaded_artifact.artifact, CanonicalPolicyArtifact):
        raise SelectionPolicyContentValidationError(
            "loaded_artifact.artifact must be a CanonicalPolicyArtifact"
        )
    if not isinstance(loaded_artifact.identity, PolicyArtifactIdentity):
        raise SelectionPolicyContentValidationError(
            "loaded_artifact.identity must be a PolicyArtifactIdentity"
        )

    content = loaded_artifact.artifact.policy_content
    fields = set(content)
    missing = sorted(_SEMANTIC_FIELDS - fields)
    if missing:
        raise SelectionPolicyContentValidationError(
            f"missing selection policy semantic field(s): {', '.join(missing)}"
        )
    unexpected = sorted(fields - _SEMANTIC_FIELDS)
    if unexpected:
        raise SelectionPolicyContentValidationError(
            f"unexpected selection policy semantic field(s): {', '.join(unexpected)}"
        )

    authorized_workloads = content["authorized_workloads"]
    if not isinstance(authorized_workloads, tuple):
        raise SelectionPolicyWorkloadValidationError(
            "authorized_workloads must be a JSON array"
        )

    return LoadedSelectionPolicy(
        policy_identity=loaded_artifact.identity,
        semantics=ValidatedSelectionPolicySemantics(authorized_workloads),
    )
