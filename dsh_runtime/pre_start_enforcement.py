"""Pure composition of final Gate and audit persistence facts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .audit_persistence import AuditPersistenceOutcome, AuditPersistenceResult
from .gate_authorization import AuthorizedGateDecision, AuthorizedGateOutcome


class PreStartEnforcementError(ValueError):
    """Base error for malformed pre-start enforcement contract data."""


class PreStartEnforcementValidationError(PreStartEnforcementError):
    """Enforcement inputs or decision representation are malformed."""


class PreStartEnforcementOutcome(str, Enum):
    """Whether established governance facts permit entering execution."""

    EXECUTION_ELIGIBLE = "EXECUTION_ELIGIBLE"
    BLOCKED = "BLOCKED"


class PreStartEnforcementReasonCode(str, Enum):
    """Stable machine-inspectable enforcement composition reasons."""

    EXECUTION_ELIGIBLE = "execution_eligible"
    GATE_DENIED = "gate_denied"
    AUDIT_PERSISTENCE_FAILED = "audit_persistence_failed"


@dataclass(frozen=True)
class PreStartEnforcementDecision:
    """Immutable eligibility decision retaining its exact source facts."""

    outcome: PreStartEnforcementOutcome
    reason_code: PreStartEnforcementReasonCode
    gate_decision: AuthorizedGateDecision
    audit_result: AuditPersistenceResult

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, PreStartEnforcementOutcome):
            raise PreStartEnforcementValidationError(
                "outcome must be a PreStartEnforcementOutcome"
            )
        if not isinstance(self.reason_code, PreStartEnforcementReasonCode):
            raise PreStartEnforcementValidationError(
                "reason_code must be a PreStartEnforcementReasonCode"
            )
        if not isinstance(self.gate_decision, AuthorizedGateDecision):
            raise PreStartEnforcementValidationError(
                "gate_decision must be an AuthorizedGateDecision"
            )
        if not isinstance(self.audit_result, AuditPersistenceResult):
            raise PreStartEnforcementValidationError(
                "audit_result must be an AuditPersistenceResult"
            )
        if self.audit_result.record.gate_decision is not self.gate_decision:
            raise PreStartEnforcementValidationError(
                "audit_result must belong to the exact Gate decision"
            )

        if self.gate_decision.outcome is AuthorizedGateOutcome.DENY:
            expected_outcome = PreStartEnforcementOutcome.BLOCKED
            expected_reason = PreStartEnforcementReasonCode.GATE_DENIED
        elif self.audit_result.outcome is AuditPersistenceOutcome.FAILURE:
            expected_outcome = PreStartEnforcementOutcome.BLOCKED
            expected_reason = (
                PreStartEnforcementReasonCode.AUDIT_PERSISTENCE_FAILED
            )
        else:
            expected_outcome = PreStartEnforcementOutcome.EXECUTION_ELIGIBLE
            expected_reason = PreStartEnforcementReasonCode.EXECUTION_ELIGIBLE

        if self.outcome is not expected_outcome:
            raise PreStartEnforcementValidationError(
                "outcome does not match the Gate and audit facts"
            )
        if self.reason_code is not expected_reason:
            raise PreStartEnforcementValidationError(
                "reason_code does not match enforcement precedence"
            )


def evaluate_pre_start_enforcement(
    gate_decision: AuthorizedGateDecision,
    audit_result: AuditPersistenceResult,
) -> PreStartEnforcementDecision:
    """Derive execution eligibility without re-running governance or execution."""

    if not isinstance(gate_decision, AuthorizedGateDecision):
        raise PreStartEnforcementValidationError(
            "gate_decision must be an AuthorizedGateDecision"
        )
    if not isinstance(audit_result, AuditPersistenceResult):
        raise PreStartEnforcementValidationError(
            "audit_result must be an AuditPersistenceResult"
        )
    if audit_result.record.gate_decision is not gate_decision:
        raise PreStartEnforcementValidationError(
            "audit_result must belong to the exact Gate decision"
        )

    if gate_decision.outcome is AuthorizedGateOutcome.DENY:
        outcome = PreStartEnforcementOutcome.BLOCKED
        reason_code = PreStartEnforcementReasonCode.GATE_DENIED
    elif audit_result.outcome is AuditPersistenceOutcome.FAILURE:
        outcome = PreStartEnforcementOutcome.BLOCKED
        reason_code = PreStartEnforcementReasonCode.AUDIT_PERSISTENCE_FAILED
    else:
        outcome = PreStartEnforcementOutcome.EXECUTION_ELIGIBLE
        reason_code = PreStartEnforcementReasonCode.EXECUTION_ELIGIBLE

    return PreStartEnforcementDecision(
        outcome=outcome,
        reason_code=reason_code,
        gate_decision=gate_decision,
        audit_result=audit_result,
    )
