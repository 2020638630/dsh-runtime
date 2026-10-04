"""Pure pre-start audit record construction for final Gate decisions."""

from __future__ import annotations

from dataclasses import dataclass

from .gate_authorization import AuthorizedGateDecision
from .gate_contract import GateTrustedContext
from .policy_artifact_loader import PolicyArtifactIdentity


class PreStartAuditError(ValueError):
    """Base error for malformed pre-start audit contract data."""


class PreStartAuditValidationError(PreStartAuditError):
    """Audit inputs or record facts are malformed or cross-context inconsistent."""


@dataclass(frozen=True)
class PreStartAuditRecord:
    """Immutable representation of an already-established final Gate fact."""

    caller_id: str
    session_id: str
    policy_identity: PolicyArtifactIdentity
    gate_decision: AuthorizedGateDecision

    def __post_init__(self) -> None:
        if not isinstance(self.caller_id, str) or not self.caller_id.strip():
            raise PreStartAuditValidationError(
                "caller_id must be a non-empty string"
            )
        if not isinstance(self.session_id, str) or not self.session_id.strip():
            raise PreStartAuditValidationError(
                "session_id must be a non-empty string"
            )
        if not isinstance(self.policy_identity, PolicyArtifactIdentity):
            raise PreStartAuditValidationError(
                "policy_identity must be a PolicyArtifactIdentity"
            )
        if not isinstance(self.gate_decision, AuthorizedGateDecision):
            raise PreStartAuditValidationError(
                "gate_decision must be an AuthorizedGateDecision"
            )
        if self.session_id != self.gate_decision.session_id:
            raise PreStartAuditValidationError(
                "record session_id must match the Gate decision session_id"
            )
        if self.policy_identity is not self.gate_decision.policy_identity:
            raise PreStartAuditValidationError(
                "record policy_identity must preserve the Gate decision identity"
            )


def build_pre_start_audit_record(
    trusted_context: GateTrustedContext,
    gate_decision: AuthorizedGateDecision,
) -> PreStartAuditRecord:
    """Build an audit fact without persisting it or re-evaluating authority."""

    if not isinstance(trusted_context, GateTrustedContext):
        raise PreStartAuditValidationError(
            "trusted_context must be a GateTrustedContext"
        )
    if not isinstance(gate_decision, AuthorizedGateDecision):
        raise PreStartAuditValidationError(
            "gate_decision must be an AuthorizedGateDecision"
        )
    if trusted_context.session_id != gate_decision.session_id:
        raise PreStartAuditValidationError(
            "trusted_context session_id does not match the Gate decision"
        )
    if trusted_context.policy_identity != gate_decision.policy_identity:
        raise PreStartAuditValidationError(
            "trusted_context policy_identity does not match the Gate decision"
        )

    return PreStartAuditRecord(
        caller_id=trusted_context.caller_id,
        session_id=gate_decision.session_id,
        policy_identity=gate_decision.policy_identity,
        gate_decision=gate_decision,
    )
