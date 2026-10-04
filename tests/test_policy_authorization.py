"""Deterministic tests for the pure policy authorization evaluator."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, dataclass, replace
import inspect
import json

import pytest

import dsh_runtime.policy_authorization as authorization_module
from dsh_runtime.gate_contract import (
    GateRequestStructure,
    GateTrustedContext,
    SelectionProposal,
)
from dsh_runtime.policy_artifact_loader import (
    LoadedPolicyArtifact,
    PolicyArtifactIdentity,
    load_policy_artifact,
)
from dsh_runtime.policy_authorization import (
    PolicyAuthorizationDecision,
    PolicyAuthorizationOutcome,
    PolicyAuthorizationReasonCode,
    PolicyAuthorizationValidationError,
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
    task_kind: str = "repository_inspection",
    reason_code: str = "caller_proposed",
) -> SelectionProposal:
    return SelectionProposal(
        task_kind=task_kind,
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
    session_pin = create_session_policy_pin("session-A", loaded_artifact)
    loaded_policy = parse_selection_policy_semantics(loaded_artifact)
    trusted_context = GateTrustedContext(
        policy_identity=loaded_artifact.identity,
        session_id="session-A",
        caller_id="trusted-host",
        enabled_workloads=enabled_workloads,
    )
    return session_pin, loaded_policy, trusted_context, _proposal()


def _evaluate(
    facts: tuple[
        SessionPolicyPin,
        LoadedSelectionPolicy,
        GateTrustedContext,
        SelectionProposal,
    ],
) -> PolicyAuthorizationDecision:
    return evaluate_policy_authorization(*facts)


def _different_identity(
    identity: PolicyArtifactIdentity,
    **overrides: str,
) -> PolicyArtifactIdentity:
    return replace(identity, **overrides)


def test_policy_allow_and_deployment_enable_returns_allow() -> None:
    decision = _evaluate(_facts())

    assert decision.outcome is PolicyAuthorizationOutcome.ALLOW
    assert decision.reason_code is PolicyAuthorizationReasonCode.AUTHORIZED


def test_policy_allow_and_deployment_disable_returns_deny() -> None:
    decision = _evaluate(_facts(enabled_workloads=()))

    assert decision.outcome is PolicyAuthorizationOutcome.DENY
    assert decision.reason_code is (
        PolicyAuthorizationReasonCode.WORKLOAD_NOT_ENABLED_BY_DEPLOYMENT
    )


def test_policy_deny_and_deployment_enable_returns_deny() -> None:
    decision = _evaluate(_facts(policy_workloads=[]))

    assert decision.outcome is PolicyAuthorizationOutcome.DENY
    assert decision.reason_code is (
        PolicyAuthorizationReasonCode.WORKLOAD_NOT_AUTHORIZED_BY_POLICY
    )


def test_policy_deny_and_deployment_disable_returns_policy_deny_first() -> None:
    decision = _evaluate(_facts(policy_workloads=[], enabled_workloads=()))

    assert decision.outcome is PolicyAuthorizationOutcome.DENY
    assert decision.reason_code is (
        PolicyAuthorizationReasonCode.WORKLOAD_NOT_AUTHORIZED_BY_POLICY
    )


def test_empty_policy_workloads_naturally_returns_deny() -> None:
    decision = _evaluate(_facts(policy_workloads=[]))

    assert decision.reason_code is (
        PolicyAuthorizationReasonCode.WORKLOAD_NOT_AUTHORIZED_BY_POLICY
    )


def test_empty_deployment_workloads_returns_deny() -> None:
    decision = _evaluate(_facts(enabled_workloads=()))

    assert decision.reason_code is (
        PolicyAuthorizationReasonCode.WORKLOAD_NOT_ENABLED_BY_DEPLOYMENT
    )


def test_session_mismatch_returns_deny() -> None:
    pin, loaded_policy, context, proposal = _facts()
    context = replace(context, session_id="session-B")

    decision = evaluate_policy_authorization(
        pin, loaded_policy, context, proposal
    )

    assert decision.reason_code is PolicyAuthorizationReasonCode.SESSION_MISMATCH


def test_trusted_context_policy_identity_mismatch_returns_deny() -> None:
    pin, loaded_policy, context, proposal = _facts()
    context = replace(
        context,
        policy_identity=_different_identity(
            context.policy_identity,
            policy_version="different-version",
        ),
    )

    decision = evaluate_policy_authorization(
        pin, loaded_policy, context, proposal
    )

    assert decision.reason_code is (
        PolicyAuthorizationReasonCode.TRUSTED_POLICY_IDENTITY_MISMATCH
    )


def test_loaded_policy_identity_mismatch_returns_deny() -> None:
    pin, loaded_policy, context, proposal = _facts()
    loaded_policy = replace(
        loaded_policy,
        policy_identity=_different_identity(
            loaded_policy.policy_identity,
            artifact_schema_version="different-schema",
        ),
    )

    decision = evaluate_policy_authorization(
        pin, loaded_policy, context, proposal
    )

    assert decision.reason_code is (
        PolicyAuthorizationReasonCode.LOADED_POLICY_IDENTITY_MISMATCH
    )


def test_same_id_version_schema_but_different_hash_returns_deny() -> None:
    pin, loaded_policy, context, proposal = _facts()
    loaded_policy = replace(
        loaded_policy,
        policy_identity=_different_identity(
            loaded_policy.policy_identity,
            policy_hash="f" * 64,
        ),
    )

    decision = evaluate_policy_authorization(
        pin, loaded_policy, context, proposal
    )

    assert decision.reason_code is (
        PolicyAuthorizationReasonCode.LOADED_POLICY_IDENTITY_MISMATCH
    )


def test_same_hash_but_different_policy_id_returns_deny() -> None:
    pin, loaded_policy, context, proposal = _facts()
    loaded_policy = replace(
        loaded_policy,
        policy_identity=_different_identity(
            loaded_policy.policy_identity,
            policy_id="different-policy",
        ),
    )

    assert (
        loaded_policy.policy_identity.policy_hash
        == pin.policy_identity.policy_hash
    )
    decision = evaluate_policy_authorization(
        pin, loaded_policy, context, proposal
    )

    assert decision.reason_code is (
        PolicyAuthorizationReasonCode.LOADED_POLICY_IDENTITY_MISMATCH
    )


def test_decision_precedence_starts_with_session_then_trusted_identity() -> None:
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

    session_decision = evaluate_policy_authorization(
        pin, loaded_policy, context, proposal
    )
    trusted_decision = evaluate_policy_authorization(
        pin,
        loaded_policy,
        replace(context, session_id=pin.session_id),
        proposal,
    )

    assert session_decision.reason_code is (
        PolicyAuthorizationReasonCode.SESSION_MISMATCH
    )
    assert trusted_decision.reason_code is (
        PolicyAuthorizationReasonCode.TRUSTED_POLICY_IDENTITY_MISMATCH
    )


def test_identical_input_produces_exact_same_decision() -> None:
    facts = _facts()

    assert _evaluate(facts) == _evaluate(facts)


def test_proposal_is_preserved_without_task_kind_rewrite() -> None:
    pin, loaded_policy, context, proposal = _facts()

    decision = evaluate_policy_authorization(
        pin, loaded_policy, context, proposal
    )

    assert decision.proposal is proposal
    assert decision.proposal.task_kind == "repository_inspection"


def test_proposal_reason_code_does_not_affect_authorization() -> None:
    pin, loaded_policy, context, proposal = _facts()
    other_proposal = replace(proposal, reason_code="different_metadata")

    first = evaluate_policy_authorization(
        pin, loaded_policy, context, proposal
    )
    second = evaluate_policy_authorization(
        pin, loaded_policy, context, other_proposal
    )

    assert (first.outcome, first.reason_code) == (
        second.outcome,
        second.reason_code,
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
def test_malformed_input_raises_typed_validation_error(
    position: int,
    message: str,
) -> None:
    inputs = list(_facts())
    inputs[position] = object()

    with pytest.raises(PolicyAuthorizationValidationError, match=message):
        evaluate_policy_authorization(*inputs)  # type: ignore[arg-type]


def test_authorization_decision_is_immutable() -> None:
    decision = _evaluate(_facts())

    with pytest.raises(FrozenInstanceError):
        decision.outcome = PolicyAuthorizationOutcome.DENY  # type: ignore[misc]


def test_evaluator_api_has_only_the_four_contract_inputs() -> None:
    signature = inspect.signature(evaluate_policy_authorization)

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


def test_authorization_module_has_no_runtime_provider_or_entrypoint_dependency() -> None:
    tree = ast.parse(inspect.getsource(authorization_module))
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
