"""Persistent single-policy governance worker over strict JSONL stdio."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterable
from typing import Any, TextIO

from .audit_jsonl_sink import AppendOnlyJsonlAuditSink
from .audit_persistence import AuditSink, persist_pre_start_audit
from .gate_authorization import evaluate_authorized_gate
from .gate_contract import GateTrustedContext, SelectionProposal
from .governance_protocol import (
    BindSessionRequest,
    EvaluatePreStartRequest,
    GovernanceProtocolError,
    InitializeRequest,
    PROTOCOL_VERSION,
    parse_initialize,
    parse_operational,
    recover_request_id,
    serialize_identity,
)
from .policy_artifact_loader import (
    FilePolicyArtifactSource,
    LoadedPolicyArtifact,
    load_policy_artifact,
)
from .pre_start_audit import build_pre_start_audit_record
from .pre_start_enforcement import evaluate_pre_start_enforcement
from .selection_policy_schema import (
    LoadedSelectionPolicy,
    parse_selection_policy_semantics,
)
from .session_policy_pin import (
    SessionPolicyPin,
    create_session_policy_pin,
    verify_session_policy_pin,
)


JsonObject = dict[str, Any]


class GovernanceWorker:
    """One initialized policy, sink, and validated live-pin cache."""

    def __init__(
        self,
        request: InitializeRequest,
        *,
        load: Callable[..., LoadedPolicyArtifact] = load_policy_artifact,
        sink_factory: Callable[[str], AuditSink] = AppendOnlyJsonlAuditSink,
    ) -> None:
        self.loaded_artifact = load(
            FilePolicyArtifactSource(request.policy_source),
            expected_policy_hash=request.expected_policy_hash,
        )
        self.loaded_policy: LoadedSelectionPolicy = (
            parse_selection_policy_semantics(self.loaded_artifact)
        )
        self.enabled_workloads = request.enabled_workloads
        self.audit_sink = sink_factory(request.audit_path)
        self._pins: dict[str, SessionPolicyPin] = {}

    @property
    def ready_response(self) -> JsonObject:
        """Return the exact identity fixed for this worker lifecycle."""

        return {
            "kind": "READY",
            "protocol_version": PROTOCOL_VERSION,
            "policy_identity": serialize_identity(self.loaded_artifact.identity),
        }

    def handle(self, request: BindSessionRequest | EvaluatePreStartRequest) -> JsonObject:
        """Perform exactly one sequential governance operation."""

        if isinstance(request, BindSessionRequest):
            return self._bind(request)
        return self._evaluate(request)

    def _bind(self, request: BindSessionRequest) -> JsonObject:
        existing = self._pins.get(request.session_id)
        if request.mode == "create":
            candidate = create_session_policy_pin(
                request.session_id, self.loaded_artifact
            )
        else:
            assert request.pinned_policy_identity is not None
            candidate = SessionPolicyPin(
                session_id=request.session_id,
                policy_identity=request.pinned_policy_identity,
            )
            verify_session_policy_pin(
                candidate, request.session_id, self.loaded_artifact
            )
        if existing is not None and existing.policy_identity != candidate.policy_identity:
            raise ValueError("session already has a different policy identity")
        self._pins[request.session_id] = existing or candidate
        return {
            "kind": "SESSION_BOUND",
            "request_id": request.request_id,
            "session_id": request.session_id,
            "policy_identity": serialize_identity(candidate.policy_identity),
        }

    def _evaluate(self, request: EvaluatePreStartRequest) -> JsonObject:
        cached = self._pins.get(request.session_id)
        if cached is None:
            raise ValueError("session must be bound before evaluation")
        presented = SessionPolicyPin(
            session_id=request.session_id,
            policy_identity=request.pinned_policy_identity,
        )
        verify_session_policy_pin(
            presented, request.session_id, self.loaded_artifact
        )
        if presented.policy_identity != cached.policy_identity:
            raise ValueError("presented identity differs from the live pin")
        trusted_context = GateTrustedContext(
            policy_identity=self.loaded_artifact.identity,
            session_id=request.session_id,
            caller_id=request.caller_id,
            enabled_workloads=self.enabled_workloads,
        )
        proposal = SelectionProposal(
            task_kind=request.task_kind,
            reason_code=request.reason_code,
            request_structure=request.request_structure,
        )
        gate = evaluate_authorized_gate(
            cached, self.loaded_policy, trusted_context, proposal
        )
        record = build_pre_start_audit_record(trusted_context, gate)
        audit = persist_pre_start_audit(self.audit_sink, record)
        enforcement = evaluate_pre_start_enforcement(gate, audit)
        response: JsonObject = {
            "kind": enforcement.outcome.value,
            "request_id": request.request_id,
            "session_id": request.session_id,
            "policy_identity": serialize_identity(gate.policy_identity),
            "task_kind": request.task_kind,
            "reason_code": enforcement.reason_code.value,
        }
        if enforcement.outcome.value == "BLOCKED":
            response["gate_reason_code"] = gate.reason_code.value
        return response


def _failure(request_id: str | None, reason_code: str, diagnostic: str) -> JsonObject:
    return {
        "kind": "FAILURE",
        "request_id": request_id,
        "reason_code": reason_code,
        "diagnostic": diagnostic,
    }


def _write(output: TextIO, response: JsonObject) -> None:
    output.write(
        json.dumps(response, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    )
    output.flush()


def serve(input_lines: Iterable[str], output: TextIO) -> int:
    """Serve one worker lifecycle; initialization failure never enters service."""

    iterator = iter(input_lines)
    try:
        first_line = next(iterator)
    except StopIteration:
        return 1
    try:
        initialization_value = json.loads(first_line)
        initialization = parse_initialize(initialization_value)
        worker = GovernanceWorker(initialization)
    except Exception:
        _write(
            output,
            _failure(None, "initialization_failed", "worker initialization failed"),
        )
        return 1
    _write(output, worker.ready_response)

    for line in iterator:
        value: object = None
        try:
            value = json.loads(line)
            request = parse_operational(value)
            response = worker.handle(request)
        except (json.JSONDecodeError, GovernanceProtocolError):
            response = _failure(
                recover_request_id(value),
                "protocol_error",
                "malformed governance request",
            )
        except Exception:
            response = _failure(
                recover_request_id(value),
                "governance_failure",
                "governance operation failed",
            )
        _write(output, response)
    return 0


def main() -> int:
    """Run the separate governance worker entrypoint."""

    return serve(sys.stdin, sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
