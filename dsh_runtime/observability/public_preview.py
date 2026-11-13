"""Opt-in C1 public commentary preview. Not redacted, persisted, or authoritative."""

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

from .activity import _invocation, _writer as _activity_writer
from .observation_pipe import write_observation_frame

STREAM_ENV = "DSH_RUNTIME_PUBLIC_PREVIEW_STREAM"
PREFIX = "DSH_RUNTIME_PUBLIC_PREVIEW_V1 "
MAX_TEXT_BYTES = 1024
MAX_SOURCE_ITEMS = 128
_UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
_ITEM = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")
_writer = ContextVar("public_preview_writer", default=None)


class PreviewWriter:
    def __init__(self, run_id, stream_id, workspace_id):
        self.identity = {"v": 1, "runId": run_id, "workspaceId": workspace_id, "streamId": stream_id}
        activity = _activity_writer.get()
        self.transport_lock = activity.transport_lock if activity is not None else threading.Lock()
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        self.queue = deque()
        self.queued_bytes = 0
        self.seq = 0
        self.dropped = 0
        self.closed = False
        self.seen = set()
        self.pipe = sys.stderr
        try:
            self.fd = self.pipe.fileno()
        except (AttributeError, OSError, ValueError):
            self.fd = None
        self.sender = threading.Thread(target=self._pump, daemon=True, name="dsh-public-preview")
        with self.lock:
            self._enqueue({"type": "begin"})
        self.sender.start()

    def _line(self, value):
        return PREFIX + json.dumps({**self.identity, **value}, ensure_ascii=True, separators=(",", ":")) + "\n"

    def _enqueue(self, value):
        line = self._line(value)
        size = len(line.encode("ascii"))
        if size > 4096 or len(self.queue) >= 8 or self.queued_bytes + size > 32 * 1024:
            self.dropped += 1
            return
        self.queue.append(line)
        self.queued_bytes += size
        self.condition.notify()

    def _pump(self):
        while True:
            with self.condition:
                while not self.queue:
                    self.condition.wait()
                line = self.queue.popleft()
                ending = line is None
                if ending:
                    line = self._line({"type": "end", "lastSeq": self.seq, "dropped": self.dropped})
                else:
                    self.queued_bytes -= len(line.encode("ascii"))
            try:
                write_observation_frame(self.pipe, self.fd, line, self.transport_lock)
            except Exception:
                with self.lock:
                    self.dropped += 1
            if ending:
                return

    def emit(self, scope, item_id, text):
        with self.lock:
            if self.closed or item_id in self.seen:
                return
            if len(self.seen) >= MAX_SOURCE_ITEMS:
                self.dropped += 1
                return
            self.seen.add(item_id)
            self.seq += 1
            raw = text.encode("utf-8", errors="replace")
            bounded = raw[:MAX_TEXT_BYTES].decode("utf-8", errors="ignore")
            value = {"type": "message", "seq": self.seq, "invocationId": scope.id,
                     "invocationIndex": 1, "role": "worker", "adapter": "codex",
                     "itemId": item_id, "phase": "commentary", "atMs": time.time_ns() // 1_000_000,
                     "text": bounded, "truncated": len(raw) > len(bounded.encode("utf-8"))}
            # JSON escapes and identity metadata also count against the frame.
            while len(self._line(value).encode("ascii")) > 4096 and value["text"]:
                value["text"] = value["text"][:len(value["text"]) // 2]
                value["truncated"] = True
            self._enqueue(value)

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            self.queue.append(None)
            self.condition.notify()
        self.sender.join(timeout=0.2)


@contextmanager
def public_preview_stream(workspace_id):
    stream_id = os.environ.pop(STREAM_ENV, "")
    run_id = os.environ.get("DSH_RUNTIME_RUN_ID", "")
    if (not _UUID.fullmatch(stream_id) or not run_id.startswith("dsh-runtime-")
        or not _UUID.fullmatch(run_id[12:]) or not isinstance(workspace_id, str)
        or not 0 < len(workspace_id) <= 128):
        yield
        return
    try:
        writer = PreviewWriter(run_id, stream_id, workspace_id)
    except Exception:
        yield
        return
    token = _writer.set(writer)
    try:
        yield
    finally:
        writer.close()
        _writer.reset(token)


def record_public_commentary(item_id, text):
    """Called only after the adapter validates a completed matching-turn item."""
    try:
        writer, scope = _writer.get(), _invocation.get()
        if (writer is None or scope is None or scope.role != "worker" or scope.adapter != "codex"
            or scope.index != 1 or scope.writer.run_id != writer.identity["runId"]
            or scope.writer.workspace_id != writer.identity["workspaceId"]
            or not isinstance(item_id, str) or not _ITEM.fullmatch(item_id)
            or not isinstance(text, str)):
            return
        # Copied async contexts retain this same closed flag after Worker returns.
        with scope.writer.lock:
            if not scope.closed:
                writer.emit(scope, item_id, text)
    except Exception:
        pass  # Optional display must never change task execution or settlement.
