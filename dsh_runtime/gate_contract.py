"""Pure structural contracts for the future policy gate boundary."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import Enum
from typing import TypeVar

from .policy_artifact_loader import PolicyArtifactIdentity


_SHA256_HEX_DIGITS = frozenset("0123456789abcdef")
_STRUCTURE_VALID_REASON = "contract_structure_valid"


class GateContractError(ValueError):
    """Base error for malformed gate contract data."""


class GateTrustedContextValidationError(GateContractError):
    """Trusted context data is structurally invalid."""


class GateProposalValidationError(GateContractError):
    """Selection proposal data is structurally invalid."""


class GateDecisionValidationError(GateContractError):
    """Gate decision data is structurally invalid."""


_ContractError = TypeVar("_ContractError", bound=GateContractError)


def _require_non_empty_string(
    name: str,
    value: object,
    error_type: type[_ContractError],
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise error_type(f"{name} must be a non-empty string")
    return value


def _freeze_identifiers(
    name: str,
    value: object,
    error_type: type[_ContractError],
) -> frozenset[str]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise error_type(f"{name} must be a list, tuple, set, or frozenset")
    frozen: set[str] = set()
    for identifier in value:
        frozen.add(_require_non_empty_string(name, identifier, error_type))
    return frozenset(frozen)


def _validate_policy_identity(
    value: object,
    error_type: type[_ContractError],
) -> PolicyArtifactIdentity:
    if not isinstance(value, PolicyArtifactIdentity):
        raise error_type("policy_identity must be a PolicyArtifactIdentity")
    _require_non_empty_string("policy_id", value.policy_id, error_type)
    _require_non_empty_string("policy_version", value.policy_version, error_type)
    _require_non_empty_string(
        "artifact_schema_version",
        value.artifact_schema_version,
        error_type,
    )
    valid_hash = (
        isinstance(value.policy_hash, str)
        and len(value.policy_hash) == 64
        and all(character in _SHA256_HEX_DIGITS for character in value.policy_hash)
    )
    if not valid_hash:
        raise error_type("policy_hash must be a lowercase SHA-256 hex digest")
    return value


@dataclass(frozen=True)
class GateTrustedContext:
    """Validated trusted identities and deployment workload configuration."""

    policy_identity: PolicyArtifactIdentity
    session_id: str
    caller_id: str
    enabled_workloads: Collection[str]

    def __post_init__(self) -> None:
        _validate_policy_identity(
            self.policy_identity,
            GateTrustedContextValidationError,
        )
        _require_non_empty_string(
            "session_id",
            self.session_id,
            GateTrustedContextValidationError,
        )
        _require_non_empty_string(
            "caller_id",
            self.caller_id,
            GateTrustedContextValidationError,
        )
        frozen_workloads = _freeze_identifiers(
            "enabled_workloads",
            self.enabled_workloads,
            GateTrustedContextValidationError,
        )
        object.__setattr__(self, "enabled_workloads", frozen_workloads)


@dataclass(frozen=True)
class GateRequestStructure:
    """Minimal request-shape metadata carried by a selection proposal."""

    request_type: str
    required_fields: Collection[str]

    def __post_init__(self) -> None:
        _require_non_empty_string(
            "request_type",
            self.request_type,
            GateProposalValidationError,
        )
        frozen_fields = _freeze_identifiers(
            "required_fields",
            self.required_fields,
            GateProposalValidationError,
        )
        object.__setattr__(self, "required_fields", frozen_fields)


@dataclass(frozen=True)
class SelectionProposal:
    """A caller-supplied workload proposal without classification behavior."""

    task_kind: str
    reason_code: str
    request_structure: GateRequestStructure

    def __post_init__(self) -> None:
        _require_non_empty_string(
            "task_kind",
            self.task_kind,
            GateProposalValidationError,
        )
        _require_non_empty_string(
            "reason_code",
            self.reason_code,
            GateProposalValidationError,
        )
        if not isinstance(self.request_structure, GateRequestStructure):
            raise GateProposalValidationError(
                "request_structure must be a GateRequestStructure"
            )


class GateDecisionOutcome(str, Enum):
    """Inspectable outcomes supported by the gate decision contract."""

    ALLOW = "ALLOW"
    DENY = "DENY"


@dataclass(frozen=True)
class GateDecision:
    """An inspectable gate outcome tied to its exact structural inputs."""

    outcome: GateDecisionOutcome
    reason_code: str
    policy_identity: PolicyArtifactIdentity
    proposal: SelectionProposal

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, GateDecisionOutcome):
            raise GateDecisionValidationError(
                "outcome must be a GateDecisionOutcome"
            )
        _require_non_empty_string(
            "reason_code",
            self.reason_code,
            GateDecisionValidationError,
        )
        _validate_policy_identity(
            self.policy_identity,
            GateDecisionValidationError,
        )
        if not isinstance(self.proposal, SelectionProposal):
            raise GateDecisionValidationError(
                "proposal must be a SelectionProposal"
            )


def evaluate_gate_contract(
    trusted_context: GateTrustedContext,
    proposal: SelectionProposal,
) -> GateDecision:
    """Accept valid structural inputs without evaluating workload policy."""

    if not isinstance(trusted_context, GateTrustedContext):
        raise GateTrustedContextValidationError(
            "trusted_context must be a GateTrustedContext"
        )
    if not isinstance(proposal, SelectionProposal):
        raise GateProposalValidationError(
            "proposal must be a SelectionProposal"
        )
    return GateDecision(
        outcome=GateDecisionOutcome.ALLOW,
        reason_code=_STRUCTURE_VALID_REASON,
        policy_identity=trusted_context.policy_identity,
        proposal=proposal,
    )
