"""Deterministic tests for the pure gate contract foundation."""

from __future__ import annotations

from inspect import signature

import pytest

from dsh_runtime.gate_contract import (
    GateDecision,
    GateDecisionOutcome,
    GateProposalValidationError,
    GateRequestStructure,
    GateTrustedContext,
    GateTrustedContextValidationError,
    SelectionProposal,
    evaluate_gate_contract,
)
from dsh_runtime.policy_artifact_loader import PolicyArtifactIdentity


def _identity(**overrides: object) -> PolicyArtifactIdentity:
    values: dict[str, object] = {
        "policy_id": "selection-policy",
        "policy_version": "candidate-2",
        "artifact_schema_version": "1",
        "policy_hash": "a" * 64,
    }
    values.update(overrides)
    return PolicyArtifactIdentity(**values)


def _context(**overrides: object) -> GateTrustedContext:
    values: dict[str, object] = {
        "policy_identity": _identity(),
        "session_id": "session-1",
        "caller_id": "caller-1",
        "enabled_workloads": ["repository_inspection"],
    }
    values.update(overrides)
    return GateTrustedContext(**values)


def _structure() -> GateRequestStructure:
    return GateRequestStructure(
        request_type="repository_request",
        required_fields=["request_id", "workspace"],
    )


def _proposal(**overrides: object) -> SelectionProposal:
    values: dict[str, object] = {
        "task_kind": "repository_inspection",
        "reason_code": "caller_selected",
        "request_structure": _structure(),
    }
    values.update(overrides)
    return SelectionProposal(**values)


def test_valid_trusted_context_can_be_constructed() -> None:
    context = _context()

    assert context.policy_identity == _identity()
    assert context.session_id == "session-1"
    assert context.caller_id == "caller-1"
    assert context.enabled_workloads == frozenset({"repository_inspection"})


def test_trusted_context_detaches_from_mutable_workloads() -> None:
    workloads = ["repository_inspection"]
    context = _context(enabled_workloads=workloads)

    workloads.append("later-workload")

    assert context.enabled_workloads == frozenset({"repository_inspection"})


@pytest.mark.parametrize("session_id", [None, "", "   "])
def test_invalid_session_identity_is_rejected(session_id: object) -> None:
    with pytest.raises(
        GateTrustedContextValidationError,
        match="session_id",
    ):
        _context(session_id=session_id)


@pytest.mark.parametrize("caller_id", [None, "", "   "])
def test_invalid_caller_identity_is_rejected(caller_id: object) -> None:
    with pytest.raises(
        GateTrustedContextValidationError,
        match="caller_id",
    ):
        _context(caller_id=caller_id)


def test_missing_policy_identity_is_rejected() -> None:
    with pytest.raises(
        GateTrustedContextValidationError,
        match="policy_identity",
    ):
        _context(policy_identity=None)


@pytest.mark.parametrize("enabled_workloads", [None, "repository_inspection", {}])
def test_invalid_enabled_workloads_representation_is_rejected(
    enabled_workloads: object,
) -> None:
    with pytest.raises(
        GateTrustedContextValidationError,
        match="enabled_workloads",
    ):
        _context(enabled_workloads=enabled_workloads)


def test_valid_selection_proposal_can_be_constructed() -> None:
    proposal = _proposal()

    assert proposal.task_kind == "repository_inspection"
    assert proposal.reason_code == "caller_selected"
    assert proposal.request_structure.required_fields == frozenset(
        {"request_id", "workspace"}
    )


@pytest.mark.parametrize("task_kind", [None, "", "   "])
def test_missing_or_empty_task_kind_is_rejected(task_kind: object) -> None:
    with pytest.raises(GateProposalValidationError, match="task_kind"):
        _proposal(task_kind=task_kind)


@pytest.mark.parametrize("reason_code", [None, "", "   "])
def test_missing_or_empty_reason_code_is_rejected(reason_code: object) -> None:
    with pytest.raises(GateProposalValidationError, match="reason_code"):
        _proposal(reason_code=reason_code)


def test_invalid_request_structure_is_rejected() -> None:
    with pytest.raises(
        GateProposalValidationError,
        match="request_structure",
    ):
        _proposal(request_structure=None)


def test_valid_contract_inputs_produce_deterministic_structural_allow() -> None:
    context = _context()
    proposal = _proposal()

    first = evaluate_gate_contract(context, proposal)
    second = evaluate_gate_contract(context, proposal)

    assert first == second
    assert first.outcome is GateDecisionOutcome.ALLOW
    assert first.reason_code == "contract_structure_valid"
    assert first.policy_identity == context.policy_identity


def test_malformed_evaluator_input_is_a_validation_failure() -> None:
    with pytest.raises(GateProposalValidationError, match="proposal"):
        evaluate_gate_contract(_context(), None)


def test_gate_records_workload_without_rewriting_it() -> None:
    proposal = _proposal(task_kind="repository_inspection")

    decision = evaluate_gate_contract(_context(), proposal)

    assert decision.proposal.task_kind == "repository_inspection"
    assert decision.proposal is proposal


def test_gate_api_has_no_semantic_input_or_external_dependency_parameter() -> None:
    parameters = signature(evaluate_gate_contract).parameters

    assert tuple(parameters) == ("trusted_context", "proposal")


def test_decision_contract_supports_inspectable_deny_outcome() -> None:
    decision = GateDecision(
        outcome=GateDecisionOutcome.DENY,
        reason_code="contract_rejected",
        policy_identity=_identity(),
        proposal=_proposal(),
    )

    assert decision.outcome.value == "DENY"
