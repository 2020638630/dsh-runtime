"""Deterministic tests for pure Gate authorization composition."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, dataclass, replace
import inspect
import json

import pytest

import dsh_runtime.gate_authorization as composition_module
from dsh_runtime.gate_authorization import (
    AuthorizedGateDecision,
    AuthorizedGateOutcome,
    GateAuthorizationCompositionValidationError,
    evaluate_authorized_gate,
)
from dsh_runtime.gate_contract import (
    GateDecisionOutcome,
    GateRequestStructure,
    GateTrustedContext,
    SelectionProposal,
    evaluate_gate_contract,
)
from dsh_runtime.policy_artifact_loader import (
    LoadedPolicyArtifact,
    PolicyArtifactIdentity,
    load_policy_artifact,
)
from dsh_runtime.policy_authorization import (
    PolicyAuthorizationOutcome,
    PolicyAuthorizationReasonCode,
    evaluate_policy_authorization,
)
from dsh_runtime.selection_policy_schema import (
    LoadedSelectionPolicy,
    parse_selection_policy_semantics,
)
from dsh_runtime.session_policy_pin import (
    SessionPolicyPin,
    create_session_policy_pin,
)


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


def _proposal(
    reason_code: str = "caller_proposed",
) -> SelectionProposal:
    return SelectionProposal(
        task_kind="repository_inspection",
        reason_code=reason_code,
        request_structure=GateRequestStructure(
            request_type="repository_task",
            required_fields=("repository",),
        ),
    )


def _facts(
    *,
    policy_workloads: list[str] | None = None,
    enabled_workloads: tuple[str, ...] = ("repository_inspection",),
) -> tuple[
    SessionPolicyPin,
    LoadedSelectionPolicy,
    GateTrustedContext,
    SelectionProposal,
]:
    loaded_artifact = _loaded_artifact(
        ["repository_inspection"]
        if policy_workloads is None
        else policy_workloads
    )
    pin = create_session_policy_pin("session-A", loaded_artifact)
    loaded_policy = parse_selection_policy_semantics(loaded_artifact)
    context = GateTrustedContext(
        policy_identity=loaded_artifact.identity,
        session_id="session-A",
        caller_id="trusted-host",
        enabled_workloads=enabled_workloads,
    )
    return pin, loaded_policy, context, _proposal()


def _different_identity(
    identity: PolicyArtifactIdentity,
    **overrides: str,
) -> PolicyArtifactIdentity:
    return replace(identity, **overrides)


def test_structural_valid_and_authorization_allow_returns_final_allow() -> None:
    decision = evaluate_authorized_gate(*_facts())

    assert decision.outcome is AuthorizedGateOutcome.ALLOW
    assert decision.reason_code is PolicyAuthorizationReasonCode.AUTHORIZED
    assert decision.structural_decision.outcome is GateDecisionOutcome.ALLOW
    assert decision.authorization_decision.outcome is (
        PolicyAuthorizationOutcome.ALLOW
    )


def test_structural_valid_and_policy_deny_returns_final_deny() -> None:
    decision = evaluate_authorized_gate(*_facts(policy_workloads=[]))

    assert decision.outcome is AuthorizedGateOutcome.DENY
    assert decision.reason_code is (
        PolicyAuthorizationReasonCode.WORKLOAD_NOT_AUTHORIZED_BY_POLICY
    )


def test_structural_valid_and_deployment_deny_returns_final_deny() -> None:
    decision = evaluate_authorized_gate(*_facts(enabled_workloads=()))

    assert decision.outcome is AuthorizedGateOutcome.DENY
    assert decision.reason_code is (
        PolicyAuthorizationReasonCode.WORKLOAD_NOT_ENABLED_BY_DEPLOYMENT
    )


def test_session_mismatch_maps_to_final_deny() -> None:
    pin, loaded_policy, context, proposal = _facts()
    context = replace(context, session_id="session-B")

    decision = evaluate_authorized_gate(pin, loaded_policy, context, proposal)

    assert decision.reason_code is PolicyAuthorizationReasonCode.SESSION_MISMATCH


def test_trusted_identity_mismatch_maps_to_final_deny() -> None:
    pin, loaded_policy, context, proposal = _facts()
    context = replace(
        context,
        policy_identity=_different_identity(
            context.policy_identity,
            policy_version="different-version",
        ),
    )

    decision = evaluate_authorized_gate(pin, loaded_policy, context, proposal)

    assert decision.reason_code is (
        PolicyAuthorizationReasonCode.TRUSTED_POLICY_IDENTITY_MISMATCH
    )


def test_loaded_policy_identity_mismatch_maps_to_final_deny() -> None:
    pin, loaded_policy, context, proposal = _facts()
    loaded_policy = replace(
        loaded_policy,
        policy_identity=_different_identity(
            loaded_policy.policy_identity,
            policy_hash="f" * 64,
        ),
    )

    decision = evaluate_authorized_gate(pin, loaded_policy, context, proposal)

    assert decision.reason_code is (
        PolicyAuthorizationReasonCode.LOADED_POLICY_IDENTITY_MISMATCH
    )


@pytest.mark.parametrize(
    ("position", "message"),
    [
        (0, "session_pin"),
        (1, "loaded_policy"),
        (2, "trusted_context"),
        (3, "proposal"),
    ],
)
def test_malformed_composition_input_raises_typed_validation_error(
    position: int,
    message: str,
) -> None:
    inputs = list(_facts())
    inputs[position] = None

    with pytest.raises(
        GateAuthorizationCompositionValidationError,
        match=message,
    ):
        evaluate_authorized_gate(*inputs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field",
    ["outcome", "reason_code", "proposal", "policy_identity"],
)
def test_final_decision_is_immutable(field: str) -> None:
    decision = evaluate_authorized_gate(*_facts())

    with pytest.raises(FrozenInstanceError):
        setattr(decision, field, None)


def test_final_and_nested_decisions_preserve_original_proposal() -> None:
    pin, loaded_policy, context, proposal = _facts()

    decision = evaluate_authorized_gate(pin, loaded_policy, context, proposal)

    assert decision.proposal is proposal
    assert decision.structural_decision.proposal is proposal
    assert decision.authorization_decision.proposal is proposal


def test_nested_decisions_equal_direct_component_evaluation() -> None:
    pin, loaded_policy, context, proposal = _facts()

    decision = evaluate_authorized_gate(pin, loaded_policy, context, proposal)

    assert decision.structural_decision == evaluate_gate_contract(
        context,
        proposal,
    )
    assert decision.authorization_decision == evaluate_policy_authorization(
        pin,
        loaded_policy,
        context,
        proposal,
    )


def test_final_identity_and_session_are_anchored_to_pin() -> None:
    pin, loaded_policy, context, proposal = _facts()

    decision = evaluate_authorized_gate(pin, loaded_policy, context, proposal)

    assert decision.policy_identity is pin.policy_identity
    assert decision.session_id == pin.session_id


def test_identical_inputs_produce_exact_same_final_decision() -> None:
    facts = _facts()

    assert evaluate_authorized_gate(*facts) == evaluate_authorized_gate(*facts)


def test_authorization_precedence_is_preserved_through_composition() -> None:
    pin, loaded_policy, context, proposal = _facts(
        policy_workloads=[],
        enabled_workloads=(),
    )
    loaded_policy = replace(
        loaded_policy,
        policy_identity=_different_identity(
            loaded_policy.policy_identity,
            policy_id="different-loaded-policy",
        ),
    )
    context = replace(
        context,
        session_id="session-B",
        policy_identity=_different_identity(
            context.policy_identity,
            policy_id="different-trusted-policy",
        ),
    )

    decision = evaluate_authorized_gate(pin, loaded_policy, context, proposal)

    assert decision.reason_code is PolicyAuthorizationReasonCode.SESSION_MISMATCH


def test_task_kind_is_not_rewritten() -> None:
    decision = evaluate_authorized_gate(*_facts())

    assert decision.proposal.task_kind == "repository_inspection"


def test_proposal_reason_code_does_not_change_gate_authority() -> None:
    pin, loaded_policy, context, proposal = _facts()
    other_proposal = replace(proposal, reason_code="different_metadata")

    first = evaluate_authorized_gate(pin, loaded_policy, context, proposal)
    second = evaluate_authorized_gate(
        pin,
        loaded_policy,
        context,
        other_proposal,
    )

    assert (first.outcome, first.reason_code) == (
        second.outcome,
        second.reason_code,
    )


def test_composition_api_has_only_the_four_contract_inputs() -> None:
    signature = inspect.signature(evaluate_authorized_gate)

    assert tuple(signature.parameters) == (
        "session_pin",
        "loaded_policy",
        "trusted_context",
        "proposal",
    )
    assert not {
        "goal",
        "workspace",
        "runtime",
        "provider",
        "prompt",
    }.intersection(signature.parameters)


def test_composition_module_has_no_production_execution_dependency() -> None:
    tree = ast.parse(inspect.getsource(composition_module))
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
        "deepseek_harness",
    }.intersection(imported_modules)
