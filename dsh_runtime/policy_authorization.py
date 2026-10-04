"""Pure authorization decisions over validated selection-policy contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .gate_contract import GateTrustedContext, SelectionProposal
from .policy_artifact_loader import PolicyArtifactIdentity
from .selection_policy_schema import LoadedSelectionPolicy
from .session_policy_pin import SessionPolicyPin


class PolicyAuthorizationError(ValueError):
    """Base error for malformed policy authorization contract data."""


class PolicyAuthorizationValidationError(PolicyAuthorizationError):
    """An authorization input or decision representation is malformed."""


class PolicyAuthorizationOutcome(str, Enum):
    """Possible outcomes of pure workload authorization."""

    ALLOW = "ALLOW"
    DENY = "DENY"


class PolicyAuthorizationReasonCode(str, Enum):
    """Stable machine-inspectable reasons for authorization outcomes."""

    AUTHORIZED = "authorized"
    SESSION_MISMATCH = "session_mismatch"
    TRUSTED_POLICY_IDENTITY_MISMATCH = "trusted_policy_identity_mismatch"
    LOADED_POLICY_IDENTITY_MISMATCH = "loaded_policy_identity_mismatch"
    WORKLOAD_NOT_AUTHORIZED_BY_POLICY = "workload_not_authorized_by_policy"
    WORKLOAD_NOT_ENABLED_BY_DEPLOYMENT = "workload_not_enabled_by_deployment"


@dataclass(frozen=True)
class PolicyAuthorizationDecision:
    """An immutable authorization result anchored to the pinned session."""

    outcome: PolicyAuthorizationOutcome
    reason_code: PolicyAuthorizationReasonCode
    policy_identity: PolicyArtifactIdentity
    session_id: str
    proposal: SelectionProposal

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, PolicyAuthorizationOutcome):
            raise PolicyAuthorizationValidationError(
                "outcome must be a PolicyAuthorizationOutcome"
            )
        if not isinstance(self.reason_code, PolicyAuthorizationReasonCode):
            raise PolicyAuthorizationValidationError(
                "reason_code must be a PolicyAuthorizationReasonCode"
            )
        if not isinstance(self.policy_identity, PolicyArtifactIdentity):
            raise PolicyAuthorizationValidationError(
                "policy_identity must be a PolicyArtifactIdentity"
            )
        if not isinstance(self.session_id, str) or not self.session_id.strip():
            raise PolicyAuthorizationValidationError(
                "session_id must be a non-empty string"
            )
        if not isinstance(self.proposal, SelectionProposal):
            raise PolicyAuthorizationValidationError(
                "proposal must be a SelectionProposal"
            )

        is_authorized = (
            self.reason_code is PolicyAuthorizationReasonCode.AUTHORIZED
        )
        if is_authorized != (
            self.outcome is PolicyAuthorizationOutcome.ALLOW
        ):
            raise PolicyAuthorizationValidationError(
                "ALLOW must use authorized and DENY must use a denial reason"
            )


def evaluate_policy_authorization(
    session_pin: SessionPolicyPin,
    loaded_policy: LoadedSelectionPolicy,
    trusted_context: GateTrustedContext,
    proposal: SelectionProposal,
) -> PolicyAuthorizationDecision:
    """Authorize the proposed workload under pinned policy and deployment facts."""

    if not isinstance(session_pin, SessionPolicyPin):
        raise PolicyAuthorizationValidationError(
            "session_pin must be a SessionPolicyPin"
        )
    if not isinstance(loaded_policy, LoadedSelectionPolicy):
        raise PolicyAuthorizationValidationError(
            "loaded_policy must be a LoadedSelectionPolicy"
        )
    if not isinstance(trusted_context, GateTrustedContext):
        raise PolicyAuthorizationValidationError(
            "trusted_context must be a GateTrustedContext"
        )
    if not isinstance(proposal, SelectionProposal):
        raise PolicyAuthorizationValidationError(
            "proposal must be a SelectionProposal"
        )

    outcome = PolicyAuthorizationOutcome.DENY
    if trusted_context.session_id != session_pin.session_id:
        reason_code = PolicyAuthorizationReasonCode.SESSION_MISMATCH
    elif trusted_context.policy_identity != session_pin.policy_identity:
        reason_code = (
            PolicyAuthorizationReasonCode.TRUSTED_POLICY_IDENTITY_MISMATCH
        )
    elif loaded_policy.policy_identity != session_pin.policy_identity:
        reason_code = (
            PolicyAuthorizationReasonCode.LOADED_POLICY_IDENTITY_MISMATCH
        )
    elif (
        proposal.task_kind
        not in loaded_policy.semantics.authorized_workloads
    ):
        reason_code = (
            PolicyAuthorizationReasonCode.WORKLOAD_NOT_AUTHORIZED_BY_POLICY
        )
    elif proposal.task_kind not in trusted_context.enabled_workloads:
        reason_code = (
            PolicyAuthorizationReasonCode.WORKLOAD_NOT_ENABLED_BY_DEPLOYMENT
        )
    else:
        outcome = PolicyAuthorizationOutcome.ALLOW
        reason_code = PolicyAuthorizationReasonCode.AUTHORIZED

    return PolicyAuthorizationDecision(
        outcome=outcome,
        reason_code=reason_code,
        policy_identity=session_pin.policy_identity,
        session_id=session_pin.session_id,
        proposal=proposal,
    )
