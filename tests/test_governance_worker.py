"""Focused qualification for the persistent governance worker boundary."""

from __future__ import annotations

from dataclasses import dataclass, replace
from io import StringIO
import json
from pathlib import Path

import pytest

from dsh_runtime.audit_persistence import AuditPersistenceOutcome
from dsh_runtime.governance_protocol import (
    BindSessionRequest,
    EvaluatePreStartRequest,
    GovernanceProtocolError,
    InitializeRequest,
    parse_initialize,
    parse_operational,
)
from dsh_runtime.governance_worker import GovernanceWorker, serve
from dsh_runtime.gate_contract import GateRequestStructure
from dsh_runtime.policy_artifact import compute_policy_hash
from dsh_runtime.policy_artifact_loader import load_policy_artifact
from dsh_runtime.audit_jsonl_sink import AppendOnlyJsonlAuditSink


def _artifact(workloads: list[str]) -> dict[str, object]:
    return {
        "policy_id": "selection-v1",
        "policy_version": "1",
        "artifact_schema_version": "1",
        "policy_content": {"authorized_workloads": workloads},
    }


def _init(tmp_path: Path, workloads: list[str]) -> InitializeRequest:
    document = _artifact(workloads)
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(document), encoding="utf-8")
    return InitializeRequest(
        policy_source=str(policy),
        expected_policy_hash=compute_policy_hash(document),
        enabled_workloads=("repository_change",),
        audit_path=str(tmp_path / "audit.jsonl"),
    )


def _bind(worker: GovernanceWorker, session: str = "session-A") -> dict[str, object]:
    return worker.handle(BindSessionRequest("bind-1", session, "create", None))


def _evaluate(worker: GovernanceWorker, identity: object, request_id: str = "eval-1") -> dict[str, object]:
    return worker.handle(EvaluatePreStartRequest(
        request_id=request_id,
        session_id="session-A",
        caller_id="trusted-host",
        pinned_policy_identity=identity,  # type: ignore[arg-type]
        task_kind="repository_change",
        reason_code="host_v1_repository_change",
        request_structure=GateRequestStructure(
            request_type="subagent_one_shot_start",
            required_fields=("parent", "prompt", "signal"),
        ),
    ))


def test_initialization_loads_once_constructs_one_sink_and_returns_exact_identity(tmp_path: Path) -> None:
    request = _init(tmp_path, ["repository_change"])
    counts = {"load": 0, "sink": 0}

    def counted_load(source: object, **kwargs: object):
        counts["load"] += 1
        return load_policy_artifact(source, **kwargs)  # type: ignore[arg-type]

    def counted_sink(path: str):
        counts["sink"] += 1
        return AppendOnlyJsonlAuditSink(path)

    worker = GovernanceWorker(request, load=counted_load, sink_factory=counted_sink)
    assert worker.ready_response["policy_identity"]["policy_hash"] == request.expected_policy_hash  # type: ignore[index]
    assert counts == {"load": 1, "sink": 1}


@pytest.mark.parametrize("change", ["version", "missing", "extra"])
def test_initialize_protocol_is_strict(change: str) -> None:
    value: dict[str, object] = {
        "kind": "INITIALIZE", "protocol_version": "1", "policy_source": "p",
        "expected_policy_hash": "a" * 64, "enabled_workloads": [], "audit_path": "a",
    }
    if change == "version": value["protocol_version"] = "2"
    elif change == "missing": del value["audit_path"]
    else: value["extra"] = True
    with pytest.raises(GovernanceProtocolError):
        parse_initialize(value)


@pytest.mark.parametrize("line", ["not-json\n", '{"kind":"UNKNOWN","request_id":"r"}\n'])
def test_protocol_failure_is_deterministic_after_ready(tmp_path: Path, line: str) -> None:
    request = _init(tmp_path, ["repository_change"])
    init = json.dumps({"kind": "INITIALIZE", "protocol_version": "1", "policy_source": request.policy_source, "expected_policy_hash": request.expected_policy_hash, "enabled_workloads": list(request.enabled_workloads), "audit_path": request.audit_path}) + "\n"
    output = StringIO()
    assert serve([init, line], output) == 0
    responses = [json.loads(item) for item in output.getvalue().splitlines()]
    assert responses[0]["kind"] == "READY"
    assert responses[1]["kind"] == "FAILURE"
    assert responses[1]["reason_code"] == "protocol_error"


def test_initialization_failure_exits_without_ready(tmp_path: Path) -> None:
    request = _init(tmp_path, ["repository_change"])
    line = json.dumps({"kind": "INITIALIZE", "protocol_version": "1", "policy_source": request.policy_source, "expected_policy_hash": "f" * 64, "enabled_workloads": [], "audit_path": request.audit_path}) + "\n"
    output = StringIO()
    assert serve([line], output) == 1
    assert [json.loads(item)["kind"] for item in output.getvalue().splitlines()] == ["FAILURE"]


def test_policy_source_load_failure_exits_without_ready(tmp_path: Path) -> None:
    request = _init(tmp_path, ["repository_change"])
    line = json.dumps({
        "kind": "INITIALIZE",
        "protocol_version": "1",
        "policy_source": str(tmp_path / "missing-policy.json"),
        "expected_policy_hash": request.expected_policy_hash,
        "enabled_workloads": [],
        "audit_path": request.audit_path,
    }) + "\n"
    output = StringIO()

    assert serve([line], output) == 1
    assert json.loads(output.getvalue())["reason_code"] == "initialization_failed"


def test_relative_audit_path_fails_initialization(tmp_path: Path) -> None:
    request = _init(tmp_path, ["repository_change"])
    line = json.dumps({
        "kind": "INITIALIZE",
        "protocol_version": "1",
        "policy_source": request.policy_source,
        "expected_policy_hash": request.expected_policy_hash,
        "enabled_workloads": [],
        "audit_path": "relative-audit.jsonl",
    }) + "\n"
    output = StringIO()

    assert serve([line], output) == 1
    assert json.loads(output.getvalue())["reason_code"] == "initialization_failed"

def test_create_and_exact_resume_return_same_worker_identity(tmp_path: Path) -> None:
    worker = GovernanceWorker(_init(tmp_path, ["repository_change"]))
    created = _bind(worker)
    identity = worker.loaded_artifact.identity
    resumed = worker.handle(BindSessionRequest("bind-2", "session-A", "resume", identity))
    assert created["policy_identity"] == resumed["policy_identity"]


def test_resume_mismatch_and_repin_fail_closed(tmp_path: Path) -> None:
    worker = GovernanceWorker(_init(tmp_path, ["repository_change"]))
    _bind(worker)
    wrong = replace(worker.loaded_artifact.identity, policy_version="2")
    with pytest.raises(Exception):
        worker.handle(BindSessionRequest("bind-2", "session-A", "resume", wrong))
    assert worker._pins["session-A"].policy_identity == worker.loaded_artifact.identity


@dataclass
class CountingSink:
    outcome: AuditPersistenceOutcome
    attempts: int = 0

    def persist(self, record: object) -> AuditPersistenceOutcome:
        self.attempts += 1
        return self.outcome


@pytest.mark.parametrize(
    ("policy_workloads", "sink_outcome", "expected"),
    [
        (["repository_change"], AuditPersistenceOutcome.SUCCESS, "EXECUTION_ELIGIBLE"),
        ([], AuditPersistenceOutcome.SUCCESS, "BLOCKED"),
        (["repository_change"], AuditPersistenceOutcome.FAILURE, "BLOCKED"),
        ([], AuditPersistenceOutcome.FAILURE, "BLOCKED"),
    ],
)
def test_evaluation_composes_gate_audit_once_and_enforcement(
    tmp_path: Path,
    policy_workloads: list[str],
    sink_outcome: AuditPersistenceOutcome,
    expected: str,
) -> None:
    sink = CountingSink(sink_outcome)
    worker = GovernanceWorker(_init(tmp_path, policy_workloads), sink_factory=lambda _: sink)
    _bind(worker)
    response = _evaluate(worker, worker.loaded_artifact.identity)
    assert response["kind"] == expected
    assert sink.attempts == 1


@pytest.mark.parametrize(
    "value",
    [
        {"kind": "UNKNOWN", "request_id": "r"},
        {"kind": "BIND_SESSION", "request_id": "r", "session_id": "s", "mode": "create", "extra": 1},
        {"kind": "BIND_SESSION", "request_id": "", "session_id": "s", "mode": "create"},
        {"kind": "BIND_SESSION", "request_id": "r", "mode": "create"},
    ],
)
def test_operational_protocol_rejects_unknown_extra_missing_and_bad_id(value: object) -> None:
    with pytest.raises(GovernanceProtocolError):
        parse_operational(value)


def test_real_jsonl_sink_persists_one_physical_line(tmp_path: Path) -> None:
    worker = GovernanceWorker(_init(tmp_path, ["repository_change"]))
    _bind(worker)
    response = _evaluate(worker, worker.loaded_artifact.identity)
    assert response["kind"] == "EXECUTION_ELIGIBLE"
    assert len((tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()) == 1
