"""Deterministic qualification tests for the production JSONL audit adapter."""

from __future__ import annotations

from dataclasses import dataclass
import inspect
import json
import os
from pathlib import Path

import pytest

import dsh_runtime.audit_jsonl_sink as adapter_module
from dsh_runtime.audit_jsonl_sink import (
    AppendOnlyJsonlAuditSink,
    AuditJsonlPathValidationError,
    IncompleteAuditTailError,
    serialize_pre_start_audit_record,
)
from dsh_runtime.audit_persistence import (
    AuditPersistenceOutcome,
    AuditPersistenceReasonCode,
    AuditPersistenceResult,
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


class CountingAuditSink:
    def __init__(self, sink: AppendOnlyJsonlAuditSink) -> None:
        self.sink = sink
        self.attempts = 0
        self.records: list[PreStartAuditRecord] = []

    def persist(
        self,
        record: PreStartAuditRecord,
    ) -> AuditPersistenceOutcome:
        self.attempts += 1
        self.records.append(record)
        return self.sink.persist(record)


def _audit_record(
    *,
    policy_allows: bool = True,
    caller_id: str = "可信调用者",
    proposal_reason: str = "caller_proposed",
) -> PreStartAuditRecord:
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
        caller_id=caller_id,
        enabled_workloads=("repository_inspection",),
    )
    proposal = SelectionProposal(
        task_kind="repository_inspection",
        reason_code=proposal_reason,
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
    return build_pre_start_audit_record(context, decision)


def _persist(
    path: Path,
    record: PreStartAuditRecord,
) -> AuditPersistenceResult:
    return persist_pre_start_audit(AppendOnlyJsonlAuditSink(path), record)


def test_absolute_path_is_explicitly_accepted(tmp_path: Path) -> None:
    sink = AppendOnlyJsonlAuditSink(tmp_path / "audit.jsonl")

    assert Path(sink.audit_path).is_absolute()


def test_relative_path_is_rejected() -> None:
    with pytest.raises(AuditJsonlPathValidationError, match="absolute"):
        AppendOnlyJsonlAuditSink(Path("relative") / "audit.jsonl")


def test_constructor_has_no_implicit_default_path() -> None:
    with pytest.raises(TypeError):
        AppendOnlyJsonlAuditSink()  # type: ignore[call-arg]


def test_missing_parent_fails_without_creating_directories(tmp_path: Path) -> None:
    path = tmp_path / "missing" / "audit.jsonl"

    result = _persist(path, _audit_record())

    assert result.outcome is AuditPersistenceOutcome.FAILURE
    assert result.reason_code is AuditPersistenceReasonCode.SINK_FAILURE
    assert not path.parent.exists()


def test_parent_must_be_a_directory(tmp_path: Path) -> None:
    parent_file = tmp_path / "not-a-directory"
    parent_file.write_bytes(b"unchanged")
    path = parent_file / "audit.jsonl"

    result = _persist(path, _audit_record())

    assert result.outcome is AuditPersistenceOutcome.FAILURE
    assert parent_file.read_bytes() == b"unchanged"


def test_record_contents_cannot_change_configured_target(tmp_path: Path) -> None:
    configured_path = tmp_path / "configured.jsonl"
    attacker_path = tmp_path / "record-derived.jsonl"
    record = _audit_record(caller_id=str(attacker_path))

    result = _persist(configured_path, record)

    assert result.outcome is AuditPersistenceOutcome.SUCCESS
    assert configured_path.is_file()
    assert not attacker_path.exists()


def test_serialization_is_deterministic_canonical_utf8_jsonl() -> None:
    record = _audit_record(
        caller_id="可信调用者",
        proposal_reason="请求检查",
    )

    first = serialize_pre_start_audit_record(record)
    second = serialize_pre_start_audit_record(record)
    decoded = first.decode("utf-8")

    assert first == second
    assert "可信调用者" in decoded
    assert "请求检查" in decoded
    assert first.endswith(b"\n")
    assert not first.endswith(b"\n\n")
    assert b'": "' not in first
    assert decoded.startswith('{"record":')


def test_storage_envelope_has_only_version_and_existing_record() -> None:
    envelope = json.loads(serialize_pre_start_audit_record(_audit_record()))

    assert set(envelope) == {"storage_schema_version", "record"}
    assert envelope["storage_schema_version"] == "1"
    assert set(envelope["record"]) == {
        "caller_id",
        "gate_decision",
        "policy_identity",
        "session_id",
    }
    assert "gate_outcome" not in envelope
    assert "gate_reason_code" not in envelope
    assert "proposal" not in envelope


def test_first_append_creates_exactly_one_valid_line(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    record = _audit_record()

    outcome = AppendOnlyJsonlAuditSink(path).persist(record)

    assert outcome is AuditPersistenceOutcome.SUCCESS
    assert path.read_bytes() == serialize_pre_start_audit_record(record)
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_repeated_append_preserves_first_line_and_adds_second(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    first_record = _audit_record(proposal_reason="first")
    second_record = _audit_record(proposal_reason="second")
    sink = AppendOnlyJsonlAuditSink(path)

    sink.persist(first_record)
    first_bytes = path.read_bytes()
    sink.persist(second_record)
    final_bytes = path.read_bytes()

    assert first_bytes == serialize_pre_start_audit_record(first_record)
    assert final_bytes.startswith(first_bytes)
    assert final_bytes == (
        first_bytes + serialize_pre_start_audit_record(second_record)
    )
    assert len(final_bytes.splitlines()) == 2


def test_existing_lf_terminated_content_is_preserved_before_append(
    tmp_path: Path,
) -> None:
    path = tmp_path / "audit.jsonl"
    existing = b'{"legacy":"outside-history-validation"}\n'
    path.write_bytes(existing)
    record = _audit_record()

    outcome = AppendOnlyJsonlAuditSink(path).persist(record)

    assert outcome is AuditPersistenceOutcome.SUCCESS
    assert path.read_bytes() == existing + serialize_pre_start_audit_record(record)


def test_incomplete_existing_tail_fails_closed_without_repair(
    tmp_path: Path,
) -> None:
    path = tmp_path / "audit.jsonl"
    incomplete = b'{"incomplete":true}'
    path.write_bytes(incomplete)
    sink = CountingAuditSink(AppendOnlyJsonlAuditSink(path))

    result = persist_pre_start_audit(sink, _audit_record())

    assert result.outcome is AuditPersistenceOutcome.FAILURE
    assert result.reason_code is AuditPersistenceReasonCode.SINK_FAILURE
    assert isinstance(result.failure_cause, IncompleteAuditTailError)
    assert sink.attempts == 1
    assert path.read_bytes() == incomplete


def test_serialization_failure_has_no_retry_fallback_or_new_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "audit.jsonl"
    sink = CountingAuditSink(AppendOnlyJsonlAuditSink(path))

    def fail_serialization(record: PreStartAuditRecord) -> bytes:
        raise ValueError("injected serialization failure")

    monkeypatch.setattr(
        adapter_module,
        "serialize_pre_start_audit_record",
        fail_serialization,
    )

    result = persist_pre_start_audit(sink, _audit_record())

    assert result.outcome is AuditPersistenceOutcome.FAILURE
    assert result.reason_code is AuditPersistenceReasonCode.SINK_FAILURE
    assert sink.attempts == 1
    assert not path.exists()


def test_write_failure_has_no_retry_or_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "audit.jsonl"
    sink = CountingAuditSink(AppendOnlyJsonlAuditSink(path))

    def fail_write(file_descriptor: int, payload: object) -> int:
        raise OSError("injected write failure")

    monkeypatch.setattr(adapter_module.os, "write", fail_write)

    result = persist_pre_start_audit(sink, _audit_record())

    assert result.outcome is AuditPersistenceOutcome.FAILURE
    assert result.reason_code is AuditPersistenceReasonCode.SINK_FAILURE
    assert sink.attempts == 1
    assert path.read_bytes() == b""


def test_partial_low_level_writes_emit_one_complete_logical_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "audit.jsonl"
    record = _audit_record()
    expected = serialize_pre_start_audit_record(record)
    real_write = os.write
    writes = 0

    def partial_write(file_descriptor: int, payload: object) -> int:
        nonlocal writes
        writes += 1
        chunk = bytes(memoryview(payload)[:17])
        return real_write(file_descriptor, chunk)

    monkeypatch.setattr(adapter_module.os, "write", partial_write)

    outcome = AppendOnlyJsonlAuditSink(path).persist(record)

    assert outcome is AuditPersistenceOutcome.SUCCESS
    assert writes > 1
    assert path.read_bytes() == expected


def test_fsync_failure_is_failure_even_when_line_is_physically_visible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "audit.jsonl"
    record = _audit_record()
    sink = CountingAuditSink(AppendOnlyJsonlAuditSink(path))

    def fail_fsync(file_descriptor: int) -> None:
        raise OSError("injected fsync failure")

    monkeypatch.setattr(adapter_module.os, "fsync", fail_fsync)

    result = persist_pre_start_audit(sink, record)

    assert result.outcome is AuditPersistenceOutcome.FAILURE
    assert result.reason_code is AuditPersistenceReasonCode.SINK_FAILURE
    assert sink.attempts == 1
    assert path.read_bytes() == serialize_pre_start_audit_record(record)


@pytest.mark.parametrize("policy_allows", [True, False])
def test_sink_persists_allow_and_deny_records_without_gate_semantics(
    tmp_path: Path,
    policy_allows: bool,
) -> None:
    path = tmp_path / f"audit-{policy_allows}.jsonl"
    record = _audit_record(policy_allows=policy_allows)

    result = _persist(path, record)

    assert result.outcome is AuditPersistenceOutcome.SUCCESS
    expected_gate_outcome = (
        AuthorizedGateOutcome.ALLOW
        if policy_allows
        else AuthorizedGateOutcome.DENY
    )
    assert record.gate_decision.outcome is expected_gate_outcome


def test_sink_constructor_accepts_only_explicit_audit_path() -> None:
    signature = inspect.signature(AppendOnlyJsonlAuditSink)

    assert tuple(signature.parameters) == ("audit_path",)


def test_production_adapter_documents_single_writer_qualification() -> None:
    documentation = (
        inspect.getdoc(adapter_module).lower()
        + " "
        + inspect.getdoc(AppendOnlyJsonlAuditSink).lower()
    )

    assert "single-writer" in documentation
