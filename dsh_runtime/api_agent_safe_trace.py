"""Opt-in, bounded API Agent evidence containing metadata only."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


SAFE_EVENT_TRACE_DIR_ENV = "DSH_API_AGENT_SAFE_EVENT_TRACE_DIR"
RUNTIME_RUN_ID_ENV = "DSH_RUNTIME_RUN_ID"
_RUN_ID = re.compile(
    r"dsh-runtime-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z"
)
_ROLES = frozenset({"inspector", "reviewer"})
_TOOLS = frozenset({"list_files", "read_file", "search_text"})
_STATUSES = frozenset({"completed", "failed"})
_TERMINALS = frozenset({"completed", "failed", "cancelled"})
_FAILURE_CODES = frozenset({
    "execution_error", "http_client_unavailable", "unsupported_tool_schema",
    "provider_timeout", "provider_network_error", "provider_auth_error",
    "provider_rate_limited", "provider_http_error", "provider_response_too_large",
    "provider_response_invalid", "provider_error", "invalid_role", "invalid_prompt",
    "token_budget_exhausted", "invalid_model_reply", "invalid_observed_model",
    "model_changed", "model_mismatch", "missing_or_invalid_token_count",
    "invalid_tool_companion_text", "tool_budget_exhausted", "invalid_tool_call",
    "invalid_tool_arguments", "tool_error", "invalid_tool_result",
    "invalid_final_text", "reviewer_no_file_read", "request_budget_exhausted",
})
MAX_TRACE_BYTES = 65_536
MAX_TRACE_EVENTS = 128
_TERMINAL_RESERVE = 1_024


class ApiAgentTraceError(Exception):
    """A configured safe trace could not be written or closed."""


class ApiAgentSafeTrace:
    def __init__(self, directory: Path, *, run_id: str, role_name: str) -> None:
        if (not directory.is_absolute() or directory.is_symlink()
            or _RUN_ID.fullmatch(run_id) is None or role_name not in _ROLES):
            raise ApiAgentTraceError("api_agent trace configuration is invalid")
        self.run_id = run_id
        self.role_name = role_name
        self.trace_id = uuid4().hex
        self.path = directory / f"api-agent-safe-role-{self.trace_id}.jsonl"
        self._count = 0
        self._bytes = 0
        self._closed = False
        self._stream = None
        try:
            directory.mkdir(parents=True, exist_ok=True)
            self._stream = self.path.open("x", encoding="utf-8", newline="\n")
            self._emit("started")
        except (OSError, ValueError, ApiAgentTraceError):
            if self._stream is not None:
                self._stream.close()
            raise ApiAgentTraceError("api_agent trace could not start") from None

    def _emit(
        self, event_type: str, *, tool_name: str | None = None,
        tool_status: str | None = None, terminal_reason: str | None = None,
    ) -> None:
        if self._closed:
            raise ApiAgentTraceError("api_agent trace is closed")
        record = {
            "schema_version": 1,
            "trace_id": self.trace_id,
            "event_seq": self._count,
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "role_name": self.role_name,
            "tool_name": tool_name,
            "tool_status": tool_status,
            "terminal_reason": terminal_reason,
        }
        line = json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n"
        size = len(line.encode("utf-8"))
        limit = MAX_TRACE_BYTES if event_type == "terminal" else MAX_TRACE_BYTES - _TERMINAL_RESERVE
        count_limit = MAX_TRACE_EVENTS if event_type == "terminal" else MAX_TRACE_EVENTS - 1
        if self._count + 1 > count_limit or self._bytes + size > limit:
            raise ApiAgentTraceError("api_agent trace quota exhausted")
        try:
            self._stream.write(line)
            self._stream.flush()
        except OSError:
            raise ApiAgentTraceError("api_agent trace write failed") from None
        self._count += 1
        self._bytes += size

    def tool(self, name: str, status: str) -> None:
        if name not in _TOOLS or status not in _STATUSES:
            raise ApiAgentTraceError("api_agent trace tool event is invalid")
        self._emit("tool_call", tool_name=name, tool_status=status)

    def finish(self, reason: str, *, failure_code: str | None = None) -> None:
        if (reason not in _TERMINALS
            or (failure_code is not None
                and (reason != "failed" or failure_code not in _FAILURE_CODES))):
            raise ApiAgentTraceError("api_agent trace terminal reason is invalid")
        self._emit("terminal", terminal_reason=reason)
        try:
            self._stream.close()
            self._closed = True
            marker = self.path.with_name(self.path.name + ".closed")
            with marker.open("x", encoding="utf-8", newline="\n") as stream:
                marker = {
                    "schema_version": 1, "run_id": self.run_id,
                    "trace_id": self.trace_id, "final_bytes": self.path.stat().st_size,
                }
                if failure_code is not None:
                    marker["failure_code"] = failure_code
                json.dump(marker, stream, separators=(",", ":"))
                stream.write("\n")
        except OSError:
            raise ApiAgentTraceError("api_agent trace could not close") from None
