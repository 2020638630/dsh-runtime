"""Audit persistence port and deterministic success/failure contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

from .pre_start_audit import PreStartAuditRecord


class AuditPersistenceError(ValueError):
    """Base error for malformed audit persistence contract data."""


class AuditPersistenceValidationError(AuditPersistenceError):
    """A persistence input, sink response, or result is malformed."""


class AuditPersistenceOutcome(str, Enum):
    """Whether the trusted sink accepted the exact audit record."""

    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


class AuditPersistenceReasonCode(str, Enum):
    """Stable machine-inspectable persistence result reasons."""

    PERSISTED = "persisted"
    SINK_FAILURE = "sink_failure"


@runtime_checkable
class AuditSink(Protocol):
    """Effect port for exactly one attempt to persist an existing record."""

    def persist(
        self,
        record: PreStartAuditRecord,
    ) -> AuditPersistenceOutcome:
        """Return whether this sink accepted the exact record."""


@dataclass(frozen=True)
class AuditPersistenceResult:
    """Immutable fact describing one audit persistence attempt."""

    outcome: AuditPersistenceOutcome
    reason_code: AuditPersistenceReasonCode
    record: PreStartAuditRecord
    failure_cause: Exception | None = field(
        default=None,
        compare=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, AuditPersistenceOutcome):
            raise AuditPersistenceValidationError(
                "outcome must be an AuditPersistenceOutcome"
            )
        if not isinstance(self.reason_code, AuditPersistenceReasonCode):
            raise AuditPersistenceValidationError(
                "reason_code must be an AuditPersistenceReasonCode"
            )
        if not isinstance(self.record, PreStartAuditRecord):
            raise AuditPersistenceValidationError(
                "record must be a PreStartAuditRecord"
            )
        if self.failure_cause is not None and not isinstance(
            self.failure_cause,
            Exception,
        ):
            raise AuditPersistenceValidationError(
                "failure_cause must be an Exception or None"
            )

        succeeded = self.outcome is AuditPersistenceOutcome.SUCCESS
        persisted = self.reason_code is AuditPersistenceReasonCode.PERSISTED
        if succeeded != persisted:
            raise AuditPersistenceValidationError(
                "SUCCESS must use persisted and FAILURE must use sink_failure"
            )
        if succeeded and self.failure_cause is not None:
            raise AuditPersistenceValidationError(
                "successful persistence cannot have a failure_cause"
            )


def persist_pre_start_audit(
    sink: AuditSink,
    record: PreStartAuditRecord,
) -> AuditPersistenceResult:
    """Make exactly one sink attempt and normalize its persistence result."""

    if not isinstance(sink, AuditSink) or not callable(
        getattr(sink, "persist", None)
    ):
        raise AuditPersistenceValidationError(
            "sink must implement the AuditSink protocol"
        )
    if not isinstance(record, PreStartAuditRecord):
        raise AuditPersistenceValidationError(
            "record must be a PreStartAuditRecord"
        )

    try:
        sink_outcome = sink.persist(record)
    except Exception as exc:
        return AuditPersistenceResult(
            outcome=AuditPersistenceOutcome.FAILURE,
            reason_code=AuditPersistenceReasonCode.SINK_FAILURE,
            record=record,
            failure_cause=exc,
        )

    if not isinstance(sink_outcome, AuditPersistenceOutcome):
        raise AuditPersistenceValidationError(
            "sink.persist must return an AuditPersistenceOutcome"
        )
    if sink_outcome is AuditPersistenceOutcome.SUCCESS:
        return AuditPersistenceResult(
            outcome=AuditPersistenceOutcome.SUCCESS,
            reason_code=AuditPersistenceReasonCode.PERSISTED,
            record=record,
        )
    return AuditPersistenceResult(
        outcome=AuditPersistenceOutcome.FAILURE,
        reason_code=AuditPersistenceReasonCode.SINK_FAILURE,
        record=record,
    )
