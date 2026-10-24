"""Bounded, content-free evidence for one Codex worker invocation."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


SAFE_EVENT_TRACE_DIR_ENV = "DSH_CODEX_SAFE_EVENT_TRACE_DIR"
RUNTIME_RUN_ID_ENV = "DSH_RUNTIME_RUN_ID"
_RUN_ID = re.compile(r"dsh-runtime-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
_TOOLS = frozenset({"commandExecution", "fileChange"})
_STATUSES = frozenset({"completed", "failed"})
_TERMINALS = frozenset({"completed", "failed", "cancelled"})
MAX_TRACE_BYTES = 65_536
MAX_TRACE_EVENTS = 256
_TERMINAL_RESERVE = 1_024


class CodexSafeTraceError(Exception):
    """A content-free Codex trace could not be opened or completed."""


class CodexSafeTrace:
    def __init__(self, directory: Path, *, run_id: str) -> None:
        if (not directory.is_absolute() or directory.is_symlink()
            or _RUN_ID.fullmatch(run_id) is None):
            raise CodexSafeTraceError("Codex safe trace configuration is invalid")
        self.run_id = run_id
        self.trace_id = uuid4().hex
        self.path = directory / f"codex-safe-worker-{self.trace_id}.jsonl"
        self._count = 0
        self._bytes = 0
        self._closed = False
        self._complete = True
        self._stream = None
        try:
            directory.mkdir(parents=True, exist_ok=True)
            self._stream = self.path.open("x", encoding="utf-8", newline="\n")
            self._emit("started")
        except (OSError, ValueError, CodexSafeTraceError):
            if self._stream is not None:
                self._stream.close()
            raise CodexSafeTraceError("Codex safe trace could not start") from None

    def _emit(
        self, event_type: str, *, tool_name: str | None = None,
        tool_status: str | None = None, terminal_reason: str | None = None,
        native_status: str | None = None,
    ) -> None:
        if self._closed or self._stream is None:
            raise CodexSafeTraceError("Codex safe trace is closed")
        record = {
            "schema_version": 1,
            "trace_id": self.trace_id,
            "event_seq": self._count,
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "tool_name": tool_name,
            "tool_status": tool_status,
            "native_status": native_status,
            "terminal_reason": terminal_reason,
            "trace_complete": self._complete,
        }
        line = json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n"
        size = len(line.encode("utf-8"))
        limit = MAX_TRACE_BYTES if event_type == "terminal" else MAX_TRACE_BYTES - _TERMINAL_RESERVE
        count_limit = MAX_TRACE_EVENTS if event_type == "terminal" else MAX_TRACE_EVENTS - 1
        if self._count + 1 > count_limit or self._bytes + size > limit:
            self._complete = False
            raise CodexSafeTraceError("Codex safe trace quota exhausted")
        try:
            self._stream.write(line)
            self._stream.flush()
        except OSError:
            self._complete = False
            raise CodexSafeTraceError("Codex safe trace write failed") from None
        self._count += 1
        self._bytes += size

    def tool(self, name: str, status: str) -> None:
        if name not in _TOOLS or status not in _STATUSES:
            raise CodexSafeTraceError("Codex safe trace tool event is invalid")
        self._emit("tool_call", tool_name=name, tool_status=status)

    def native_terminal(self, status: str) -> None:
        if status not in _STATUSES:
            raise CodexSafeTraceError("Codex native terminal is invalid")
        self._emit("native_terminal", native_status=status)

    def finish(self, reason: str) -> None:
        if reason not in _TERMINALS:
            raise CodexSafeTraceError("Codex safe trace terminal is invalid")
        try:
            self._emit("terminal", terminal_reason=reason)
            self._stream.close()
            self._closed = True
            marker_path = self.path.with_name(self.path.name + ".closed")
            with marker_path.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump({
                    "schema_version": 1, "run_id": self.run_id,
                    "trace_id": self.trace_id, "final_bytes": self.path.stat().st_size,
                }, stream, separators=(",", ":"))
                stream.write("\n")
        except (OSError, CodexSafeTraceError):
            self._complete = False
            if self._stream is not None and not self._closed:
                self._stream.close()
            raise CodexSafeTraceError("Codex safe trace could not close") from None
