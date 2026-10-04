"""Deterministic tests for the audit persistence boundary."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, dataclass, fields
import inspect
import json

import pytest

import dsh_runtime.audit_persistence as persistence_module
from dsh_runtime.audit_persistence import (
    AuditPersistenceOutcome,
    AuditPersistenceReasonCode,
    AuditPersistenceResult,
    AuditPersistenceValidationError,
    persist_pre_start_audit,
)
from dsh_runtime.gate_authorization import (
    AuthorizedGateOutcome,
    evaluate_authorized_gate,
)
from dsh_runtime.gate_contract import (
    GateRequestStructure,
    GateTrustedContext,
    SelectionProposal,
)
from dsh_runtime.policy_artifact_loader import load_policy_artifact
from dsh_runtime.pre_start_audit import (
    PreStartAuditRecord,
    build_pre_start_audit_record,
)
from dsh_runtime.selection_policy_schema import parse_selection_policy_semantics
from dsh_runtime.session_policy_pin import create_session_policy_pin


@dataclass(frozen=True)
class InMemoryPolicyArtifactSource:
    document: str

    def read_text(self) -> str:
        return self.document


class RecordingAuditSink:
    def __init__(self, outcome: AuditPersistenceOutcome) -> None:
        self.outcome = outcome
        self.records: list[PreStartAuditRecord] = []

    def persist(
        self,
        record: PreStartAuditRecord,
    ) -> AuditPersistenceOutcome:
        self.records.append(record)
        return self.outcome


class ExceptionAuditSink:
    def __init__(self) -> None:
        self.records: list[PreStartAuditRecord] = []

    def persist(
        self,
        record: PreStartAuditRecord,
    ) -> AuditPersistenceOutcome:
        self.records.append(record)
        raise RuntimeError("test sink failure")


class InvalidOutcomeAuditSink:
    def persist(self, record: PreStartAuditRecord) -> object:
        return object()


def _audit_record(
    *,
    authorized_workloads: list[str] | None = None,
) -> PreStartAuditRecord:
    workloads = (
        ["repository_inspection"]
        if authorized_workloads is None
        else authorized_workloads
    )
    document = json.dumps(
        {
            "policy_id": "selection-policy-candidate",
            "policy_version": "candidate-1",
            "artifact_schema_version": "1",
            "policy_content": {"authorized_workloads": workloads},
        }
    )
    loaded_artifact = load_policy_artifact(
        InMemoryPolicyArtifactSource(document)
    )
    pin = create_session_policy_pin("session-A", loaded_artifact)
    loaded_policy = parse_selection_policy_semantics(loaded_artifact)
    context = GateTrustedContext(
        policy_identity=loaded_artifact.identity,
        session_id="session-A",
        caller_id="trusted-host",
        enabled_workloads=("repository_inspection",),
    )
    proposal = SelectionProposal(
        task_kind="repository_inspection",
        reason_code="caller_proposed",
        request_structure=GateRequestStructure(
            request_type="repository_task",
            required_fields=("repository",),
        ),
    )
    gate_decision = evaluate_authorized_gate(
        pin,
        loaded_policy,
        context,
        proposal,
    )
    return build_pre_start_audit_record(context, gate_decision)


def test_success_sink_returns_success_and_persisted_reason() -> None:
    record = _audit_record()
    sink = RecordingAuditSink(AuditPersistenceOutcome.SUCCESS)

    result = persist_pre_start_audit(sink, record)

    assert result.outcome is AuditPersistenceOutcome.SUCCESS
    assert result.reason_code is AuditPersistenceReasonCode.PERSISTED


def test_success_sink_and_result_preserve_exact_original_record() -> None:
    record = _audit_record()
    sink = RecordingAuditSink(AuditPersistenceOutcome.SUCCESS)

    result = persist_pre_start_audit(sink, record)

    assert sink.records == [record]
    assert sink.records[0] is record
    assert result.record is record


def test_gate_allow_record_can_be_persisted() -> None:
    record = _audit_record()

    result = persist_pre_start_audit(
        RecordingAuditSink(AuditPersistenceOutcome.SUCCESS),
        record,
    )

    assert record.gate_decision.outcome is AuthorizedGateOutcome.ALLOW
    assert result.outcome is AuditPersistenceOutcome.SUCCESS


def test_gate_deny_record_can_be_persisted() -> None:
    record = _audit_record(authorized_workloads=[])

    result = persist_pre_start_audit(
        RecordingAuditSink(AuditPersistenceOutcome.SUCCESS),
        record,
    )

    assert record.gate_decision.outcome is AuthorizedGateOutcome.DENY
    assert result.outcome is AuditPersistenceOutcome.SUCCESS


def test_explicit_sink_failure_returns_failure_and_sink_failure_reason() -> None:
    record = _audit_record()

    result = persist_pre_start_audit(
        RecordingAuditSink(AuditPersistenceOutcome.FAILURE),
        record,
    )

    assert result.outcome is AuditPersistenceOutcome.FAILURE
    assert result.reason_code is AuditPersistenceReasonCode.SINK_FAILURE
    assert result.record is record
    assert result.failure_cause is None


def test_sink_exception_becomes_failure_with_diagnostic_cause() -> None:
    record = _audit_record()
    sink = ExceptionAuditSink()

    result = persist_pre_start_audit(sink, record)

    assert result.outcome is AuditPersistenceOutcome.FAILURE
    assert result.reason_code is AuditPersistenceReasonCode.SINK_FAILURE
    assert result.record is record
    assert isinstance(result.failure_cause, RuntimeError)
    assert sink.records == [record]


def test_malformed_sink_is_typed_validation_failure() -> None:
    with pytest.raises(AuditPersistenceValidationError, match="sink"):
        persist_pre_start_audit(None, _audit_record())  # type: ignore[arg-type]


def test_malformed_record_is_typed_validation_failure() -> None:
    sink = RecordingAuditSink(AuditPersistenceOutcome.SUCCESS)

    with pytest.raises(AuditPersistenceValidationError, match="record"):
        persist_pre_start_audit(sink, {})  # type: ignore[arg-type]

    assert sink.records == []


def test_invalid_sink_outcome_is_typed_protocol_failure() -> None:
    with pytest.raises(AuditPersistenceValidationError, match="return"):
        persist_pre_start_audit(InvalidOutcomeAuditSink(), _audit_record())


def test_deterministic_success_inputs_produce_equivalent_results() -> None:
    record = _audit_record()
    sink = RecordingAuditSink(AuditPersistenceOutcome.SUCCESS)

    first = persist_pre_start_audit(sink, record)
    second = persist_pre_start_audit(sink, record)

    assert first == second
    assert sink.records == [record, record]


def test_deterministic_failure_inputs_produce_equivalent_results() -> None:
    record = _audit_record()
    sink = RecordingAuditSink(AuditPersistenceOutcome.FAILURE)

    first = persist_pre_start_audit(sink, record)
    second = persist_pre_start_audit(sink, record)

    assert first == second
    assert sink.records == [record, record]


@pytest.mark.parametrize(
    "outcome",
    [AuditPersistenceOutcome.SUCCESS, AuditPersistenceOutcome.FAILURE],
)
def test_one_boundary_call_makes_exactly_one_sink_attempt(
    outcome: AuditPersistenceOutcome,
) -> None:
    record = _audit_record()
    sink = RecordingAuditSink(outcome)

    persist_pre_start_audit(sink, record)

    assert sink.records == [record]


def test_sink_exception_is_not_retried() -> None:
    record = _audit_record()
    sink = ExceptionAuditSink()

    persist_pre_start_audit(sink, record)

    assert sink.records == [record]


def test_failure_does_not_mutate_or_destroy_access_to_record() -> None:
    record = _audit_record()
    before = record

    result = persist_pre_start_audit(
        ExceptionAuditSink(),
        record,
    )

    assert record == before
    assert result.record is record


@pytest.mark.parametrize(
    "field",
    ["outcome", "reason_code", "record", "failure_cause"],
)
def test_persistence_result_is_immutable(field: str) -> None:
    result = persist_pre_start_audit(
        RecordingAuditSink(AuditPersistenceOutcome.SUCCESS),
        _audit_record(),
    )

    with pytest.raises(FrozenInstanceError):
        setattr(result, field, None)


def test_persistence_api_has_only_sink_and_record_inputs() -> None:
    signature = inspect.signature(persist_pre_start_audit)

    assert tuple(signature.parameters) == ("sink", "record")
    assert not {
        "goal",
        "proposal",
        "trusted_context",
        "runtime",
        "provider",
        "loaded_policy",
        "session_pin",
    }.intersection(signature.parameters)


def test_persistence_module_does_not_reevaluate_governance() -> None:
    tree = ast.parse(inspect.getsource(persistence_module))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert imported_modules == {
        "__future__",
        "dataclasses",
        "enum",
        "typing",
        "pre_start_audit",
    }


def test_persistence_module_has_no_production_adapter_or_execution_surface() -> None:
    source = inspect.getsource(persistence_module).lower()
    result_fields = {field.name for field in fields(AuditPersistenceResult)}

    assert not {
        "timestamp",
        "created_at",
        "recorded_at",
        "audit_id",
        "event_id",
    }.intersection(result_fields)
    assert not {
        "controller",
        "planner",
        "entrypoint",
        "provider",
        "subagentruntime",
        "sqlite",
        "jsonl",
        "http",
        "socket",
        "uuid",
    }.intersection(source)
