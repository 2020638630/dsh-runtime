"""Deterministic qualification for the Selection Policy v2 artifact boundary."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path

import pytest

from dsh_runtime.audit_persistence import (
    AuditPersistenceOutcome,
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
from dsh_runtime.governance_protocol import (
    BindSessionRequest,
    EvaluatePreStartRequest,
    InitializeRequest,
)
from dsh_runtime.governance_worker import GovernanceWorker
from dsh_runtime.policy_artifact import compute_policy_hash
from dsh_runtime.policy_artifact_loader import (
    FilePolicyArtifactSource,
    LoadedPolicyArtifact,
    load_policy_artifact,
)
from dsh_runtime.pre_start_audit import build_pre_start_audit_record
from dsh_runtime.pre_start_enforcement import (
    PreStartEnforcementOutcome,
    evaluate_pre_start_enforcement,
)
from dsh_runtime.policy_authorization import PolicyAuthorizationReasonCode
from dsh_runtime.selection_policy_schema import parse_selection_policy_semantics
from dsh_runtime.session_policy_pin import (
    SessionPolicyHashMismatchError,
    SessionPolicyIdMismatchError,
    create_session_policy_pin,
)


V2_ARTIFACT_PATH = (
    Path(__file__).parents[1]
    / "dsh_runtime"
    / "resources"
    / "selection_policy"
    / "selection-v2.json"
)
V2_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "selection-policy-v2.json"
V2_WORKLOADS = ("repository_change", "repository_inspection")


@dataclass(frozen=True)
class InMemoryPolicyArtifactSource:
    document: str

    def read_text(self) -> str:
        return self.document


@dataclass
class CountingAuditSink:
    outcome: AuditPersistenceOutcome
    attempts: int = 0

    def persist(self, record: object) -> AuditPersistenceOutcome:
        self.attempts += 1
        return self.outcome


def _load_document(document: dict[str, object]) -> LoadedPolicyArtifact:
    return load_policy_artifact(
        InMemoryPolicyArtifactSource(json.dumps(document))
    )


def _load_v2() -> LoadedPolicyArtifact:
    return load_policy_artifact(FilePolicyArtifactSource(V2_ARTIFACT_PATH))


def _v1_document() -> dict[str, object]:
    return {
        "policy_id": "selection-v1",
        "policy_version": "1",
        "artifact_schema_version": "1",
        "policy_content": {
            "authorized_workloads": ["repository_change"],
        },
    }


def _proposal(task_kind: str) -> SelectionProposal:
    return SelectionProposal(
        task_kind=task_kind,
        reason_code=(
            "host_v1_repository_change"
            if task_kind == "repository_change"
            else "host_v2_repository_inspection"
        ),
        request_structure=GateRequestStructure(
            request_type="subagent_one_shot_start",
            required_fields=("parent", "prompt", "signal"),
        ),
    )


def _gate_facts(
    *,
    task_kind: str,
    policy_workloads: tuple[str, ...] = V2_WORKLOADS,
    enabled_workloads: tuple[str, ...] = V2_WORKLOADS,
) -> tuple[LoadedPolicyArtifact, object, object, SelectionProposal]:
    artifact = _load_v2()
    policy = _load_document({
        "policy_id": artifact.identity.policy_id,
        "policy_version": artifact.identity.policy_version,
        "artifact_schema_version": artifact.identity.artifact_schema_version,
        "policy_content": {"authorized_workloads": list(policy_workloads)},
    })
    pin = create_session_policy_pin("session-A", policy)
    loaded_policy = parse_selection_policy_semantics(policy)
    context = GateTrustedContext(
        policy_identity=policy.identity,
        session_id="session-A",
        caller_id="trusted-host",
        enabled_workloads=enabled_workloads,
    )
    return policy, pin, context, _proposal(task_kind)


def _worker(tmp_path: Path, enabled_workloads: tuple[str, ...] = V2_WORKLOADS) -> GovernanceWorker:
    loaded = _load_v2()
    return GovernanceWorker(InitializeRequest(
        policy_source=str(V2_ARTIFACT_PATH),
        expected_policy_hash=loaded.identity.policy_hash,
        enabled_workloads=enabled_workloads,
        audit_path=str(tmp_path / "audit.jsonl"),
    ))


def _evaluate_worker(
    worker: GovernanceWorker,
    identity: object,
    task_kind: str,
    request_id: str,
) -> dict[str, object]:
    return worker.handle(EvaluatePreStartRequest(
        request_id=request_id,
        session_id="session-A",
        caller_id="trusted-host",
        pinned_policy_identity=identity,  # type: ignore[arg-type]
        task_kind=task_kind,
        reason_code=(
            "host_v1_repository_change"
            if task_kind == "repository_change"
            else "host_v2_repository_inspection"
        ),
        request_structure=GateRequestStructure(
            request_type="subagent_one_shot_start",
            required_fields=("parent", "prompt", "signal"),
        ),
    ))


def test_v2_production_resource_is_valid_and_keeps_artifact_schema_v1() -> None:
    loaded = _load_v2()
    parsed = parse_selection_policy_semantics(loaded)

    assert loaded.artifact.policy_id == "selection-v2"
    assert loaded.artifact.policy_version == "2"
    assert loaded.identity.policy_hash == (
        "c1cb7d4350a94e9353dd445de41a741a66f01b2be88b8f073613dd548adad463"
    )
    assert loaded.artifact.artifact_schema_version == "1"
    assert parsed.semantics.authorized_workloads == frozenset(V2_WORKLOADS)


def test_v2_fixture_matches_production_identity_but_is_not_the_runtime_source() -> None:
    production = load_policy_artifact(FilePolicyArtifactSource(V2_ARTIFACT_PATH))
    fixture = load_policy_artifact(FilePolicyArtifactSource(V2_FIXTURE_PATH))

    assert production.identity == fixture.identity
    assert "tests" not in str(V2_ARTIFACT_PATH)


def test_v2_identity_is_distinct_from_the_existing_v1_identity() -> None:
    v1 = _load_document(_v1_document())
    v2 = _load_v2()

    assert v1.artifact.policy_id == "selection-v1"
    assert v1.artifact.policy_version == "1"
    assert v1.artifact.artifact_schema_version == "1"
    assert v1.identity.policy_id != v2.identity.policy_id
    assert v1.identity.policy_version != v2.identity.policy_version
    assert v1.identity.policy_hash != v2.identity.policy_hash


@pytest.mark.parametrize(
    ("task_kind", "policy_workloads", "enabled_workloads", "outcome", "reason"),
    [
        (
            "repository_change",
            V2_WORKLOADS,
            V2_WORKLOADS,
            AuthorizedGateOutcome.ALLOW,
            PolicyAuthorizationReasonCode.AUTHORIZED,
        ),
        (
            "repository_inspection",
            V2_WORKLOADS,
            V2_WORKLOADS,
            AuthorizedGateOutcome.ALLOW,
            PolicyAuthorizationReasonCode.AUTHORIZED,
        ),
        (
            "repository_inspection",
            V2_WORKLOADS,
            ("repository_change",),
            AuthorizedGateOutcome.DENY,
            PolicyAuthorizationReasonCode.WORKLOAD_NOT_ENABLED_BY_DEPLOYMENT,
        ),
        (
            "repository_inspection",
            ("repository_change",),
            V2_WORKLOADS,
            AuthorizedGateOutcome.DENY,
            PolicyAuthorizationReasonCode.WORKLOAD_NOT_AUTHORIZED_BY_POLICY,
        ),
    ],
)
def test_v2_policy_and_deployment_authorization_is_intersection(
    task_kind: str,
    policy_workloads: tuple[str, ...],
    enabled_workloads: tuple[str, ...],
    outcome: AuthorizedGateOutcome,
    reason: PolicyAuthorizationReasonCode,
) -> None:
    policy_artifact, pin, context, proposal = _gate_facts(
        task_kind=task_kind,
        policy_workloads=policy_workloads,
        enabled_workloads=enabled_workloads,
    )
    loaded_policy = parse_selection_policy_semantics(policy_artifact)

    decision = evaluate_authorized_gate(pin, loaded_policy, context, proposal)

    assert decision.outcome is outcome
    assert decision.reason_code is reason


def test_inspection_allow_requires_audit_success_for_execution_eligibility() -> None:
    artifact, pin, context, proposal = _gate_facts(
        task_kind="repository_inspection"
    )
    loaded_policy = parse_selection_policy_semantics(artifact)
    gate = evaluate_authorized_gate(pin, loaded_policy, context, proposal)
    sink = CountingAuditSink(AuditPersistenceOutcome.SUCCESS)
    audit = persist_pre_start_audit(
        sink,
        build_pre_start_audit_record(context, gate),
    )

    enforcement = evaluate_pre_start_enforcement(gate, audit)

    assert gate.outcome is AuthorizedGateOutcome.ALLOW
    assert enforcement.outcome is PreStartEnforcementOutcome.EXECUTION_ELIGIBLE
    assert sink.attempts == 1


def test_inspection_deny_is_audited_and_blocked() -> None:
    artifact, pin, context, proposal = _gate_facts(
        task_kind="repository_inspection",
        enabled_workloads=("repository_change",),
    )
    loaded_policy = parse_selection_policy_semantics(artifact)
    gate = evaluate_authorized_gate(pin, loaded_policy, context, proposal)
    sink = CountingAuditSink(AuditPersistenceOutcome.SUCCESS)
    audit = persist_pre_start_audit(
        sink,
        build_pre_start_audit_record(context, gate),
    )

    enforcement = evaluate_pre_start_enforcement(gate, audit)

    assert gate.outcome is AuthorizedGateOutcome.DENY
    assert enforcement.outcome is PreStartEnforcementOutcome.BLOCKED
    assert sink.attempts == 1


def test_v2_worker_create_resume_and_same_pin_support_both_workloads(
    tmp_path: Path,
) -> None:
    worker = _worker(tmp_path)
    created = worker.handle(BindSessionRequest(
        request_id="bind-create",
        session_id="session-A",
        mode="create",
        pinned_policy_identity=None,
    ))
    identity = worker.loaded_artifact.identity
    resumed = worker.handle(BindSessionRequest(
        request_id="bind-resume",
        session_id="session-A",
        mode="resume",
        pinned_policy_identity=identity,
    ))

    change = _evaluate_worker(worker, identity, "repository_change", "change")
    inspection = _evaluate_worker(
        worker,
        identity,
        "repository_inspection",
        "inspection",
    )

    assert created["policy_identity"] == resumed["policy_identity"]
    assert change["kind"] == "EXECUTION_ELIGIBLE"
    assert inspection["kind"] == "EXECUTION_ELIGIBLE"
    assert change["policy_identity"] == inspection["policy_identity"]
    assert len((tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_v1_pinned_session_cannot_resume_against_v2_worker(tmp_path: Path) -> None:
    worker = _worker(tmp_path)
    v1 = _load_document(_v1_document())

    with pytest.raises(SessionPolicyIdMismatchError):
        worker.handle(BindSessionRequest(
            request_id="resume-v1",
            session_id="session-A",
            mode="resume",
            pinned_policy_identity=v1.identity,
        ))

    assert worker._pins == {}


def test_v2_resume_rejects_wrong_hash_and_keeps_existing_pin(tmp_path: Path) -> None:
    worker = _worker(tmp_path)
    worker.handle(BindSessionRequest(
        request_id="bind-create",
        session_id="session-A",
        mode="create",
        pinned_policy_identity=None,
    ))
    identity = worker.loaded_artifact.identity
    wrong_hash = replace(identity, policy_hash="0" * 64)

    with pytest.raises(SessionPolicyHashMismatchError):
        worker.handle(BindSessionRequest(
            request_id="resume-wrong-hash",
            session_id="session-A",
            mode="resume",
            pinned_policy_identity=wrong_hash,
        ))

    assert worker._pins["session-A"].policy_identity is identity
