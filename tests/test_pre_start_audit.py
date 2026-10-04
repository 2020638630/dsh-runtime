"""Deterministic tests for the pre-start audit record contract."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, dataclass, fields, replace
import inspect
import json

import pytest

import dsh_runtime.pre_start_audit as audit_module
from dsh_runtime.gate_authorization import (
    AuthorizedGateDecision,
    AuthorizedGateOutcome,
    evaluate_authorized_gate,
)
from dsh_runtime.gate_contract import (
    GateDecisionOutcome,
    GateRequestStructure,
    GateTrustedContext,
    SelectionProposal,
)
from dsh_runtime.policy_artifact_loader import (
    LoadedPolicyArtifact,
    load_policy_artifact,
)
from dsh_runtime.policy_authorization import (
    PolicyAuthorizationOutcome,
    PolicyAuthorizationReasonCode,
)
from dsh_runtime.pre_start_audit import (
    PreStartAuditRecord,
    PreStartAuditValidationError,
    build_pre_start_audit_record,
)
from dsh_runtime.selection_policy_schema import parse_selection_policy_semantics
from dsh_runtime.session_policy_pin import create_session_policy_pin


@dataclass(frozen=True)
class InMemoryPolicyArtifactSource:
    document: str

    def read_text(self) -> str:
        return self.document


def _loaded_artifact(
    authorized_workloads: list[str],
) -> LoadedPolicyArtifact:
    document = json.dumps(
        {
            "policy_id": "selection-policy-candidate",
            "policy_version": "candidate-1",
            "artifact_schema_version": "1",
            "policy_content": {
                "authorized_workloads": authorized_workloads,
            },
        }
    )
    return load_policy_artifact(InMemoryPolicyArtifactSource(document))


def _gate_facts(
    *,
    authorized_workloads: list[str] | None = None,
) -> tuple[GateTrustedContext, SelectionProposal, AuthorizedGateDecision]:
    loaded_artifact = _loaded_artifact(
        ["repository_inspection"]
        if authorized_workloads is None
        else authorized_workloads
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
    decision = evaluate_authorized_gate(
        pin,
        loaded_policy,
        context,
        proposal,
    )
    return context, proposal, decision


def test_gate_allow_builds_complete_audit_record() -> None:
    context, proposal, decision = _gate_facts()

    record = build_pre_start_audit_record(context, decision)

    assert record.caller_id == context.caller_id
    assert record.session_id == context.session_id == decision.session_id
    assert record.policy_identity is decision.policy_identity
    assert record.gate_decision is decision
    assert record.gate_decision.proposal is proposal
    assert record.gate_decision.outcome is AuthorizedGateOutcome.ALLOW


def test_gate_deny_builds_valid_audit_record() -> None:
    context, _, decision = _gate_facts(authorized_workloads=[])

    record = build_pre_start_audit_record(context, decision)

    assert record.gate_decision.outcome is AuthorizedGateOutcome.DENY
    assert record.gate_decision.reason_code is (
        PolicyAuthorizationReasonCode.WORKLOAD_NOT_AUTHORIZED_BY_POLICY
    )


@pytest.mark.parametrize(
    "field",
    ["caller_id", "session_id", "policy_identity", "gate_decision"],
)
def test_audit_record_is_immutable(field: str) -> None:
    context, _, decision = _gate_facts()
    record = build_pre_start_audit_record(context, decision)

    with pytest.raises(FrozenInstanceError):
        setattr(record, field, None)


def test_record_preserves_original_gate_decision_and_proposal() -> None:
    context, proposal, decision = _gate_facts()

    record = build_pre_start_audit_record(context, decision)

    assert record.gate_decision is decision
    assert record.gate_decision.proposal is proposal


def test_record_preserves_policy_identity_without_reconstruction() -> None:
    context, _, decision = _gate_facts()

    record = build_pre_start_audit_record(context, decision)

    assert record.policy_identity is decision.policy_identity


def test_record_caller_identity_comes_from_trusted_context() -> None:
    context, _, decision = _gate_facts()

    record = build_pre_start_audit_record(context, decision)

    assert record.caller_id == "trusted-host"


def test_cross_context_session_mismatch_is_validation_failure() -> None:
    context, _, decision = _gate_facts()
    wrong_context = replace(context, session_id="session-B")

    with pytest.raises(PreStartAuditValidationError, match="session_id"):
        build_pre_start_audit_record(wrong_context, decision)


def test_cross_context_policy_identity_mismatch_is_validation_failure() -> None:
    context, _, decision = _gate_facts()
    wrong_context = replace(
        context,
        policy_identity=replace(
            context.policy_identity,
            policy_hash="f" * 64,
        ),
    )

    with pytest.raises(PreStartAuditValidationError, match="policy_identity"):
        build_pre_start_audit_record(wrong_context, decision)


@pytest.mark.parametrize(
    ("trusted_context", "gate_decision", "message"),
    [
        (None, "valid", "trusted_context"),
        ("valid", None, "gate_decision"),
    ],
)
def test_malformed_input_is_typed_validation_failure(
    trusted_context: object,
    gate_decision: object,
    message: str,
) -> None:
    valid_context, _, valid_decision = _gate_facts()
    actual_context = (
        valid_context if trusted_context == "valid" else trusted_context
    )
    actual_decision = (
        valid_decision if gate_decision == "valid" else gate_decision
    )

    with pytest.raises(PreStartAuditValidationError, match=message):
        build_pre_start_audit_record(  # type: ignore[arg-type]
            actual_context,
            actual_decision,
        )


def test_gate_deny_reason_is_preserved_without_translation() -> None:
    context, _, decision = _gate_facts(authorized_workloads=[])

    record = build_pre_start_audit_record(context, decision)

    assert record.gate_decision.reason_code is decision.reason_code
    assert record.gate_decision.reason_code is (
        PolicyAuthorizationReasonCode.WORKLOAD_NOT_AUTHORIZED_BY_POLICY
    )


def test_structural_and_authorization_decisions_remain_traceable() -> None:
    context, _, decision = _gate_facts()

    record = build_pre_start_audit_record(context, decision)

    assert record.gate_decision.structural_decision is (
        decision.structural_decision
    )
    assert record.gate_decision.structural_decision.outcome is (
        GateDecisionOutcome.ALLOW
    )
    assert record.gate_decision.authorization_decision is (
        decision.authorization_decision
    )
    assert record.gate_decision.authorization_decision.outcome is (
        PolicyAuthorizationOutcome.ALLOW
    )


def test_identical_inputs_produce_value_equal_audit_records() -> None:
    context, _, decision = _gate_facts()

    first = build_pre_start_audit_record(context, decision)
    second = build_pre_start_audit_record(context, decision)

    assert first == second


def test_builder_api_accepts_only_context_and_final_gate_decision() -> None:
    signature = inspect.signature(build_pre_start_audit_record)

    assert tuple(signature.parameters) == (
        "trusted_context",
        "gate_decision",
    )
    assert not {
        "goal",
        "workspace",
        "runtime",
        "provider",
        "policy_content",
        "session_pin",
        "loaded_policy",
    }.intersection(signature.parameters)


def test_audit_module_has_no_production_execution_dependency() -> None:
    tree = ast.parse(inspect.getsource(audit_module))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert not {
        "controller",
        "planner",
        "entrypoint",
        "runtime",
        "provider",
    }.intersection(imported_modules)


def test_audit_record_has_no_timestamp_random_id_or_persistence_result() -> None:
    record_fields = {field.name for field in fields(PreStartAuditRecord)}
    source = inspect.getsource(audit_module).lower()

    assert not {
        "timestamp",
        "created_at",
        "recorded_at",
        "audit_id",
        "event_id",
        "audit_success",
    }.intersection(record_fields)
    assert "uuid" not in source
    assert "random" not in source
