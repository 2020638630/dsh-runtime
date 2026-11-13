"""Opt-in observation channel. No output text, disk history, or task authority."""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator
from uuid import uuid4
from .observation_pipe import write_observation_frame

STREAM_ENV = "DSH_RUNTIME_ACTIVITY_STREAM"
PREFIX = "DSH_RUNTIME_ACTIVITY_V1 "
_UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
_TOOLS = {
    "codex": {"commandExecution", "fileChange"},
    "codebuddy": {"Read", "Edit", "Write", "Bash"},
    "api_agent": {"list_files", "read_file", "search_text"},
}
_ROLES = {("worker", "codex"), ("worker", "codebuddy"),
          ("reviewer", "codex"), ("reviewer", "api_agent"),
          ("inspector", "codex"), ("inspector", "api_agent")}


class ActivityWriter:
    def __init__(self, run_id: str, stream_id: str, workspace_id: str) -> None:
        self.run_id, self.stream_id, self.workspace_id = run_id, stream_id, workspace_id
        self.seq = 0
        self.dropped = 0
        self.closed = False
        self.transport_lock = threading.Lock()
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        self.queue: deque[str | None] = deque()
        self.queued_bytes = 0
        # Capture the Runtime pipe, never a native CLI's stdout/stderr.
        self.pipe = sys.stderr
        try:
            self.fd = self.pipe.fileno()
        except (AttributeError, OSError, ValueError):
            self.fd = None
        self.sender = threading.Thread(target=self._pump, daemon=True, name="dsh-safe-activity")
        with self.lock:
            self._enqueue({"v": 1, "type": "begin", "runId": self.run_id,
                           "workspaceId": self.workspace_id, "streamId": self.stream_id})
        self.sender.start()

    def _enqueue(self, value: dict) -> None:
        line = PREFIX + json.dumps(value, ensure_ascii=True, separators=(",", ":")) + "\n"
        size = len(line.encode("ascii"))
        # Reserve one slot / 2 KiB for the closing marker; never wait on the pipe.
        if size > 2048 or len(self.queue) >= 63 or self.queued_bytes + size > 30 * 1024:
            self.dropped += 1
            return
        self.queue.append(line)
        self.queued_bytes += size
        self.condition.notify()

    def _pump(self) -> None:
        while True:
            with self.condition:
                while not self.queue:
                    self.condition.wait()
                line = self.queue.popleft()
                ending = line is None
                if ending:
                    # Include drops from earlier I/O failures, not just enqueue time.
                    value = {"v": 1, "type": "end", "runId": self.run_id,
                             "workspaceId": self.workspace_id, "streamId": self.stream_id,
                             "lastSeq": self.seq, "dropped": self.dropped}
                    line = PREFIX + json.dumps(value, separators=(",", ":")) + "\n"
                else:
                    self.queued_bytes -= len(line.encode("ascii"))
            try:
                # Raw fd writes avoid a daemon owning Python's buffered stderr lock
                # during interpreter shutdown when the Host stops draining the pipe.
                write_observation_frame(self.pipe, self.fd, line, self.transport_lock)
            except Exception:
                with self.lock:
                    self.dropped += 1
            if ending:
                return

    def emit(self, scope: Invocation, kind: str, status: str, tool: str | None) -> None:
        with self.lock:
            if self.closed:
                return
            if scope.closed:
                self.dropped += 1
                return
            self.seq += 1
            self._enqueue({"v": 1, "type": "event", "runId": self.run_id,
                         "workspaceId": self.workspace_id, "streamId": self.stream_id,
                         "seq": self.seq, "invocationId": scope.id,
                         "invocationIndex": scope.index, "role": scope.role,
                         "adapter": scope.adapter, "atMs": time.time_ns() // 1_000_000,
                         "kind": kind, "status": status, **({"tool": tool} if tool else {})})

    def close(self) -> None:
        with self.lock:
            if self.closed:
                return
            self.closed = True
            self.queue.append(None)
            self.condition.notify()
        # A blocked observer is abandoned; Runtime settlement must remain bounded.
        self.sender.join(timeout=0.2)


@dataclass
class Invocation:
    writer: ActivityWriter
    id: str
    index: int
    role: str
    adapter: str
    closed: bool = False


_writer: ContextVar[ActivityWriter | None] = ContextVar("activity_writer", default=None)
_invocation: ContextVar[Invocation | None] = ContextVar("activity_invocation", default=None)


@contextmanager
def activity_stream(workspace_id: str) -> Iterator[None]:
    # Consume the Host-only stream identity before any external CLI is spawned.
    stream_id = os.environ.pop(STREAM_ENV, "")
    run_id = os.environ.get("DSH_RUNTIME_RUN_ID", "")
    if (not _UUID.fullmatch(stream_id) or not run_id.startswith("dsh-runtime-")
        or not _UUID.fullmatch(run_id[12:]) or not 0 < len(workspace_id) <= 128):
        yield
        return
    try:
        writer = ActivityWriter(run_id, stream_id, workspace_id)
    except Exception:
        yield
        return
    token = _writer.set(writer)
    try:
        yield
    finally:
        # Outside asyncio.run: its cancelled child tasks have finished cleanup.
        writer.close()
        _writer.reset(token)


@contextmanager
def invocation_activity(workspace_id: str, role: str | None, adapter: str,
                        index: int) -> Iterator[None]:
    writer = _writer.get()
    if writer is None or writer.workspace_id != workspace_id or (role, adapter) not in _ROLES:
        yield
        return
    scope = Invocation(writer, str(uuid4()), index, role, adapter)
    token = _invocation.set(scope)
    writer.emit(scope, "phase", "dispatched", None)
    try:
        yield
    except BaseException:
        writer.emit(scope, "invocation", "interrupted", None)
        raise
    else:
        writer.emit(scope, "invocation", "returned", None)
    finally:
        # A copied ContextVar in a child task still sees this same closed object.
        with writer.lock:
            scope.closed = True
        _invocation.reset(token)


def record_activity(adapter: str, kind: str, status: str, tool: str | None = None) -> None:
    if (not all(isinstance(value, str) for value in (adapter, kind, status))
        or (tool is not None and not isinstance(tool, str))):
        return
    scope = _invocation.get()
    if scope is None or adapter != scope.adapter:
        return
    allowed = (kind == "tool" and status in {"called", "completed", "failed", "observed"}
               and tool in _TOOLS.get(adapter, set())) or (
                   kind == "message" and status == "observed" and tool is None)
    if allowed:
        scope.writer.emit(scope, kind, status, tool)
