"""Deterministic tests for Gate plus audit enforcement composition."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, dataclass
import inspect
import json

import pytest

import dsh_runtime.pre_start_enforcement as enforcement_module
from dsh_runtime.audit_persistence import (
    AuditPersistenceOutcome,
    AuditPersistenceReasonCode,
    AuditPersistenceResult,
    persist_pre_start_audit,
)
from dsh_runtime.gate_authorization import (
    AuthorizedGateDecision,
    AuthorizedGateOutcome,
    evaluate_authorized_gate,
)
from dsh_runtime.gate_contract import (
    GateRequestStructure,
    GateTrustedContext,
    SelectionProposal,
)
from dsh_runtime.policy_artifact_loader import load_policy_artifact
from dsh_runtime.policy_authorization import PolicyAuthorizationReasonCode
from dsh_runtime.pre_start_audit import build_pre_start_audit_record
from dsh_runtime.pre_start_enforcement import (
    PreStartEnforcementDecision,
    PreStartEnforcementOutcome,
    PreStartEnforcementReasonCode,
    PreStartEnforcementValidationError,
    evaluate_pre_start_enforcement,
)
from dsh_runtime.selection_policy_schema import parse_selection_policy_semantics
from dsh_runtime.session_policy_pin import create_session_policy_pin


@dataclass(frozen=True)
class InMemoryPolicyArtifactSource:
    document: str

    def read_text(self) -> str:
        return self.document


class FixedAuditSink:
    def __init__(self, outcome: AuditPersistenceOutcome) -> None:
        self.outcome = outcome

    def persist(self, record: object) -> AuditPersistenceOutcome:
        return self.outcome


class ExceptionAuditSink:
    def persist(self, record: object) -> AuditPersistenceOutcome:
        raise RuntimeError("test sink failure")


def _gate_decision(*, policy_allows: bool) -> AuthorizedGateDecision:
    workloads = ["repository_inspection"] if policy_allows else []
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
    return evaluate_authorized_gate(
        pin,
        loaded_policy,
        context,
        proposal,
    )


def _audit_result(
    gate_decision: AuthorizedGateDecision,
    outcome: AuditPersistenceOutcome,
) -> AuditPersistenceResult:
    context = GateTrustedContext(
        policy_identity=gate_decision.policy_identity,
        session_id=gate_decision.session_id,
        caller_id="trusted-host",
        enabled_workloads=("repository_inspection",),
    )
    record = build_pre_start_audit_record(context, gate_decision)
    return persist_pre_start_audit(FixedAuditSink(outcome), record)


@pytest.mark.parametrize(
    (
        "policy_allows",
        "audit_outcome",
        "expected_outcome",
        "expected_reason",
    ),
    [
        (
            True,
            AuditPersistenceOutcome.SUCCESS,
            PreStartEnforcementOutcome.EXECUTION_ELIGIBLE,
            PreStartEnforcementReasonCode.EXECUTION_ELIGIBLE,
        ),
        (
            True,
            AuditPersistenceOutcome.FAILURE,
            PreStartEnforcementOutcome.BLOCKED,
            PreStartEnforcementReasonCode.AUDIT_PERSISTENCE_FAILED,
        ),
        (
            False,
            AuditPersistenceOutcome.SUCCESS,
            PreStartEnforcementOutcome.BLOCKED,
            PreStartEnforcementReasonCode.GATE_DENIED,
        ),
        (
            False,
            AuditPersistenceOutcome.FAILURE,
            PreStartEnforcementOutcome.BLOCKED,
            PreStartEnforcementReasonCode.GATE_DENIED,
        ),
    ],
)
def test_enforcement_matrix(
    policy_allows: bool,
    audit_outcome: AuditPersistenceOutcome,
    expected_outcome: PreStartEnforcementOutcome,
    expected_reason: PreStartEnforcementReasonCode,
) -> None:
    gate_decision = _gate_decision(policy_allows=policy_allows)
    audit_result = _audit_result(gate_decision, audit_outcome)

    decision = evaluate_pre_start_enforcement(gate_decision, audit_result)

    assert decision.outcome is expected_outcome
    assert decision.reason_code is expected_reason


def test_gate_deny_precedes_simultaneous_audit_failure() -> None:
    gate_decision = _gate_decision(policy_allows=False)
    audit_result = _audit_result(
        gate_decision,
        AuditPersistenceOutcome.FAILURE,
    )

    decision = evaluate_pre_start_enforcement(gate_decision, audit_result)

    assert decision.reason_code is PreStartEnforcementReasonCode.GATE_DENIED


@pytest.mark.parametrize(
    ("policy_allows", "audit_outcome"),
    [
        (True, AuditPersistenceOutcome.SUCCESS),
        (True, AuditPersistenceOutcome.FAILURE),
        (False, AuditPersistenceOutcome.SUCCESS),
    ],
)
def test_enforcement_decision_is_immutable(
    policy_allows: bool,
    audit_outcome: AuditPersistenceOutcome,
) -> None:
    gate_decision = _gate_decision(policy_allows=policy_allows)
    audit_result = _audit_result(gate_decision, audit_outcome)
    decision = evaluate_pre_start_enforcement(gate_decision, audit_result)

    with pytest.raises(FrozenInstanceError):
        decision.outcome = PreStartEnforcementOutcome.BLOCKED  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        decision.reason_code = (  # type: ignore[misc]
            PreStartEnforcementReasonCode.GATE_DENIED
        )


def test_decision_preserves_exact_gate_and_audit_objects() -> None:
    gate_decision = _gate_decision(policy_allows=True)
    audit_result = _audit_result(
        gate_decision,
        AuditPersistenceOutcome.SUCCESS,
    )

    decision = evaluate_pre_start_enforcement(gate_decision, audit_result)

    assert decision.gate_decision is gate_decision
    assert decision.audit_result is audit_result


def test_cross_decision_mixing_is_typed_validation_failure() -> None:
    gate_decision_a = _gate_decision(policy_allows=True)
    gate_decision_b = _gate_decision(policy_allows=True)
    audit_result_b = _audit_result(
        gate_decision_b,
        AuditPersistenceOutcome.SUCCESS,
    )

    assert gate_decision_a == gate_decision_b
    assert gate_decision_a is not gate_decision_b
    with pytest.raises(
        PreStartEnforcementValidationError,
        match="exact Gate decision",
    ):
        evaluate_pre_start_enforcement(gate_decision_a, audit_result_b)


@pytest.mark.parametrize(
    ("gate_decision", "audit_result", "message"),
    [
        (None, "valid", "gate_decision"),
        ("valid", None, "audit_result"),
    ],
)
def test_malformed_input_is_typed_validation_failure(
    gate_decision: object,
    audit_result: object,
    message: str,
) -> None:
    valid_gate = _gate_decision(policy_allows=True)
    valid_audit = _audit_result(valid_gate, AuditPersistenceOutcome.SUCCESS)
    actual_gate = valid_gate if gate_decision == "valid" else gate_decision
    actual_audit = valid_audit if audit_result == "valid" else audit_result

    with pytest.raises(PreStartEnforcementValidationError, match=message):
        evaluate_pre_start_enforcement(  # type: ignore[arg-type]
            actual_gate,
            actual_audit,
        )


def test_identical_inputs_produce_exact_same_value_decision() -> None:
    gate_decision = _gate_decision(policy_allows=True)
    audit_result = _audit_result(
        gate_decision,
        AuditPersistenceOutcome.SUCCESS,
    )

    first = evaluate_pre_start_enforcement(gate_decision, audit_result)
    second = evaluate_pre_start_enforcement(gate_decision, audit_result)

    assert first == second


def test_nested_gate_reason_remains_available() -> None:
    gate_decision = _gate_decision(policy_allows=False)
    audit_result = _audit_result(
        gate_decision,
        AuditPersistenceOutcome.SUCCESS,
    )

    decision = evaluate_pre_start_enforcement(gate_decision, audit_result)

    assert decision.gate_decision.reason_code is (
        PolicyAuthorizationReasonCode.WORKLOAD_NOT_AUTHORIZED_BY_POLICY
    )


def test_nested_audit_failure_cause_remains_available() -> None:
    gate_decision = _gate_decision(policy_allows=True)
    context = GateTrustedContext(
        policy_identity=gate_decision.policy_identity,
        session_id=gate_decision.session_id,
        caller_id="trusted-host",
        enabled_workloads=("repository_inspection",),
    )
    record = build_pre_start_audit_record(context, gate_decision)
    audit_result = persist_pre_start_audit(ExceptionAuditSink(), record)

    decision = evaluate_pre_start_enforcement(gate_decision, audit_result)

    assert decision.reason_code is (
        PreStartEnforcementReasonCode.AUDIT_PERSISTENCE_FAILED
    )
    assert isinstance(decision.audit_result.failure_cause, RuntimeError)


def test_only_allow_plus_success_is_execution_eligible() -> None:
    combinations = []
    for policy_allows in (True, False):
        gate_decision = _gate_decision(policy_allows=policy_allows)
        for audit_outcome in (
            AuditPersistenceOutcome.SUCCESS,
            AuditPersistenceOutcome.FAILURE,
        ):
            audit_result = _audit_result(gate_decision, audit_outcome)
            decision = evaluate_pre_start_enforcement(
                gate_decision,
                audit_result,
            )
            combinations.append(
                (
                    gate_decision.outcome,
                    audit_result.outcome,
                    decision.outcome,
                )
            )

    eligible = [item for item in combinations if item[2] is PreStartEnforcementOutcome.EXECUTION_ELIGIBLE]
    assert eligible == [
        (
            AuthorizedGateOutcome.ALLOW,
            AuditPersistenceOutcome.SUCCESS,
            PreStartEnforcementOutcome.EXECUTION_ELIGIBLE,
        )
    ]


def test_enforcement_api_accepts_only_established_result_objects() -> None:
    signature = inspect.signature(evaluate_pre_start_enforcement)

    assert tuple(signature.parameters) == ("gate_decision", "audit_result")
    assert not {
        "goal",
        "proposal",
        "trusted_context",
        "session_pin",
        "policy",
        "runtime",
        "provider",
        "sink",
    }.intersection(signature.parameters)


def test_enforcement_module_has_no_reevaluation_or_execution_dependency() -> None:
    tree = ast.parse(inspect.getsource(enforcement_module))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert imported_modules == {
        "__future__",
        "dataclasses",
        "enum",
        "audit_persistence",
        "gate_authorization",
    }


def test_enforcement_module_calls_no_governance_or_persistence_function() -> None:
    tree = ast.parse(inspect.getsource(enforcement_module))
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert not {
        "evaluate_gate_contract",
        "evaluate_policy_authorization",
        "evaluate_authorized_gate",
        "build_pre_start_audit_record",
        "persist_pre_start_audit",
    }.intersection(called_names)
