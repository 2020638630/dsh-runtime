import json
from pathlib import Path

import pytest

from dsh_runtime.api_agent_safe_trace import ApiAgentSafeTrace, ApiAgentTraceError


RUN_ID = "dsh-runtime-00000000-0000-4000-8000-000000000001"


def test_trace_is_metadata_only_and_closed_marker_binds_final_size(tmp_path):
    sink = ApiAgentSafeTrace(tmp_path / "evidence", run_id=RUN_ID, role_name="inspector")
    sink.tool("read_file", "completed")
    sink.finish("completed")
    trace_bytes = sink.path.read_bytes()
    events = [json.loads(line) for line in trace_bytes.splitlines()]
    assert [event["event_type"] for event in events] == [
        "started", "tool_call", "terminal",
    ]
    assert [event["event_seq"] for event in events] == [0, 1, 2]
    assert events[1]["tool_name"] == "read_file"
    assert events[2]["terminal_reason"] == "completed"
    assert all(set(event) == {
        "schema_version", "trace_id", "event_seq", "captured_at_utc",
        "event_type", "role_name", "tool_name", "tool_status", "terminal_reason",
    } for event in events)
    marker = json.loads(Path(str(sink.path) + ".closed").read_text(encoding="utf-8"))
    assert marker == {
        "schema_version": 1, "run_id": RUN_ID,
        "trace_id": sink.trace_id, "final_bytes": len(trace_bytes),
    }


def test_trace_rejects_unlisted_metadata(tmp_path):
    sink = ApiAgentSafeTrace(tmp_path / "evidence", run_id=RUN_ID, role_name="reviewer")
    with pytest.raises(ApiAgentTraceError):
        sink.tool("Bash", "completed")
    with pytest.raises(ApiAgentTraceError):
        sink.tool("read_file", "private-model-response")
    sink.finish("failed")


def test_failed_marker_records_only_whitelisted_diagnostic_code(tmp_path):
    sink = ApiAgentSafeTrace(tmp_path / "evidence", run_id=RUN_ID, role_name="reviewer")
    with pytest.raises(ApiAgentTraceError):
        sink.finish("failed", failure_code="private-model-response")
    with pytest.raises(ApiAgentTraceError):
        sink.finish("completed", failure_code="request_budget_exhausted")
    sink.finish("failed", failure_code="request_budget_exhausted")
    marker = json.loads(Path(str(sink.path) + ".closed").read_text(encoding="utf-8"))
    assert marker["failure_code"] == "request_budget_exhausted"
    assert set(marker) == {"schema_version", "run_id", "trace_id", "final_bytes", "failure_code"}


def test_trace_requires_bounded_run_identity(tmp_path):
    with pytest.raises(ApiAgentTraceError):
        ApiAgentSafeTrace(tmp_path / "evidence", run_id="arbitrary", role_name="inspector")
    assert not (tmp_path / "evidence").exists()
