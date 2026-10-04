"""Pure composition of structural Gate validation and policy authorization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .gate_contract import (
    GateDecision,
    GateDecisionOutcome,
    GateTrustedContext,
    SelectionProposal,
    evaluate_gate_contract,
)
from .policy_artifact_loader import PolicyArtifactIdentity
from .policy_authorization import (
    PolicyAuthorizationDecision,
    PolicyAuthorizationOutcome,
    PolicyAuthorizationReasonCode,
    evaluate_policy_authorization,
)
from .selection_policy_schema import LoadedSelectionPolicy
from .session_policy_pin import SessionPolicyPin


class GateAuthorizationCompositionError(ValueError):
    """Base error for malformed authorized Gate composition data."""


class GateAuthorizationCompositionValidationError(
    GateAuthorizationCompositionError
):
    """A composition input or final decision representation is malformed."""


class AuthorizedGateOutcome(str, Enum):
    """Final outcomes after structural validation and authorization."""

    ALLOW = "ALLOW"
    DENY = "DENY"


@dataclass(frozen=True)
class AuthorizedGateDecision:
    """An immutable final Gate decision preserving both component decisions."""

    outcome: AuthorizedGateOutcome
    reason_code: PolicyAuthorizationReasonCode
    policy_identity: PolicyArtifactIdentity
    session_id: str
    proposal: SelectionProposal
    structural_decision: GateDecision
    authorization_decision: PolicyAuthorizationDecision

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, AuthorizedGateOutcome):
            raise GateAuthorizationCompositionValidationError(
                "outcome must be an AuthorizedGateOutcome"
            )
        if not isinstance(self.reason_code, PolicyAuthorizationReasonCode):
            raise GateAuthorizationCompositionValidationError(
                "reason_code must be a PolicyAuthorizationReasonCode"
            )
        if not isinstance(self.policy_identity, PolicyArtifactIdentity):
            raise GateAuthorizationCompositionValidationError(
                "policy_identity must be a PolicyArtifactIdentity"
            )
        if not isinstance(self.session_id, str) or not self.session_id.strip():
            raise GateAuthorizationCompositionValidationError(
                "session_id must be a non-empty string"
            )
        if not isinstance(self.proposal, SelectionProposal):
            raise GateAuthorizationCompositionValidationError(
                "proposal must be a SelectionProposal"
            )
        if not isinstance(self.structural_decision, GateDecision):
            raise GateAuthorizationCompositionValidationError(
                "structural_decision must be a GateDecision"
            )
        if self.structural_decision.outcome is not GateDecisionOutcome.ALLOW:
            raise GateAuthorizationCompositionValidationError(
                "structural_decision must be structural ALLOW"
            )
        if not isinstance(
            self.authorization_decision,
            PolicyAuthorizationDecision,
        ):
            raise GateAuthorizationCompositionValidationError(
                "authorization_decision must be a PolicyAuthorizationDecision"
            )

        expected_outcome = AuthorizedGateOutcome(
            self.authorization_decision.outcome.value
        )
        if self.outcome is not expected_outcome:
            raise GateAuthorizationCompositionValidationError(
                "final outcome must match the authorization outcome"
            )
        if self.reason_code is not self.authorization_decision.reason_code:
            raise GateAuthorizationCompositionValidationError(
                "final reason_code must preserve the authorization reason"
            )
        if self.policy_identity is not self.authorization_decision.policy_identity:
            raise GateAuthorizationCompositionValidationError(
                "final policy_identity must preserve the authorization identity"
            )
        if self.session_id != self.authorization_decision.session_id:
            raise GateAuthorizationCompositionValidationError(
                "final session_id must match the authorization session"
            )
        if self.proposal is not self.structural_decision.proposal:
            raise GateAuthorizationCompositionValidationError(
                "structural decision must preserve the original proposal"
            )
        if self.proposal is not self.authorization_decision.proposal:
            raise GateAuthorizationCompositionValidationError(
                "authorization decision must preserve the original proposal"
            )


def evaluate_authorized_gate(
    session_pin: SessionPolicyPin,
    loaded_policy: LoadedSelectionPolicy,
    trusted_context: GateTrustedContext,
    proposal: SelectionProposal,
) -> AuthorizedGateDecision:
    """Compose structural validation and pure authorization into one decision."""

    if not isinstance(session_pin, SessionPolicyPin):
        raise GateAuthorizationCompositionValidationError(
            "session_pin must be a SessionPolicyPin"
        )
    if not isinstance(loaded_policy, LoadedSelectionPolicy):
        raise GateAuthorizationCompositionValidationError(
            "loaded_policy must be a LoadedSelectionPolicy"
        )
    if not isinstance(trusted_context, GateTrustedContext):
        raise GateAuthorizationCompositionValidationError(
            "trusted_context must be a GateTrustedContext"
        )
    if not isinstance(proposal, SelectionProposal):
        raise GateAuthorizationCompositionValidationError(
            "proposal must be a SelectionProposal"
        )

    structural_decision = evaluate_gate_contract(trusted_context, proposal)
    if structural_decision.outcome is not GateDecisionOutcome.ALLOW:
        raise GateAuthorizationCompositionValidationError(
            "structural Gate evaluation did not produce structural ALLOW"
        )

    authorization_decision = evaluate_policy_authorization(
        session_pin,
        loaded_policy,
        trusted_context,
        proposal,
    )

    return AuthorizedGateDecision(
        outcome=AuthorizedGateOutcome(authorization_decision.outcome.value),
        reason_code=authorization_decision.reason_code,
        policy_identity=session_pin.policy_identity,
        session_id=session_pin.session_id,
        proposal=proposal,
        structural_decision=structural_decision,
        authorization_decision=authorization_decision,
    )
