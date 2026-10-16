"""One-shot bounded CodeBuddy CLI capability.

CodeBuddy's CLI and JSON event details intentionally stay private to this
module. The Runtime only sees the existing Plugin/PluginResult boundary.
"""

from __future__ import annotations

import asyncio
import base64
import codecs
import ctypes
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..runtime.plugin import ExecutionContext, PluginResult


_SETTINGS = {
    "permissions": {
        "defaultMode": "dontAsk",
        "allow": ["Read", "Edit", "Write", "Bash(python:*)"],
    }
}
_DEFAULT_MAX_TURNS = 12
_DEFAULT_MAX_OUTPUT_CHARS = 100_000
_DEFAULT_MAX_DIAGNOSTIC_CHARS = 1_000
MAX_STREAM_CHARS_ENV = "DSH_CODEBUDDY_MAX_STREAM_CHARS"
MAX_STREAM_CHARS_HARD_LIMIT = 1_000_000
_QUALIFICATION_OBSERVABILITY_FAILURE = "QUALIFICATION OBSERVABILITY FAILURE"
SAFE_EVENT_TRACE_DIR_ENV = "DSH_CODEBUDDY_SAFE_EVENT_TRACE_DIR"
RUNTIME_RUN_ID_ENV = "DSH_RUNTIME_RUN_ID"
_RUNTIME_RUN_ID_PATTERN = re.compile(
    r"^dsh-runtime-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
SAFE_STREAM_JSON_ENV = "DSH_CODEBUDDY_SAFE_STREAM_JSON"
_STREAM_JSON_READ_CHUNK = 16_384
_STREAM_JSON_MAX_TOOL_CORRELATIONS = 256
_STREAM_JSON_MAX_EVENTS_PER_FEED = 128
_STREAM_JSON_MAX_TOOL_BLOCKS_PER_EVENT = 256
_SAFE_TRACE_MAX_BYTES = 1_048_576
_SAFE_TRACE_MAX_EVENTS = 2_048
_SAFE_TRACE_TERMINAL_RESERVE_BYTES = 2_048
_SAFE_OBSERVER_MAX_EVENTS_PER_FEED = 128
_SAFE_JSON_ARRAY_MAX_BUFFER_CHARS = _DEFAULT_MAX_OUTPUT_CHARS * 4 + 1
_SAFE_TRACE_TOOL_NAMES = frozenset({"Read", "Edit", "Write", "Bash"})
_SAFE_TRACE_TOOL_STATUSES = frozenset(
    {
        "completed",
        "success",
        "error",
        "failed",
        "denied",
        "permission_denied",
        "unexecuted",
        "skipped",
        "not_run",
        "running",
    }
)
_SAFE_MAX_TURNS_DIAGNOSTIC = re.compile(
    r"\bmax\s+turns\s+\(\d+\)\s+exceeded\b", re.IGNORECASE
)
_WINDOWS_ENTRYPOINT_PATTERN = re.compile(
    r'"%dp0%[\\/](?P<entry>[^"]+)"\s+%\*', re.IGNORECASE
)
_WINDOWS_NODE_PATTERN = re.compile(
    r'IF\s+EXIST\s+"%dp0%[\\/](?P<node>[^"]+)"', re.IGNORECASE
)


class _CodeBuddyOutputError(ValueError):
    """Raised for native output that cannot be normalized."""


class CodeBuddyLaunchConfigurationError(RuntimeError):
    """Raised when the Windows CodeBuddy CLI cannot be resolved safely."""


def _windows_launch_error(shim: Path, detail: str) -> CodeBuddyLaunchConfigurationError:
    return CodeBuddyLaunchConfigurationError(
        f"CodeBuddy Windows launch configuration error for {shim}: {detail}"
    )


def _windows_relative_path(base: Path, relative: str) -> Path:
    return (base / relative.replace("\\", os.sep)).resolve()


def _resolve_windows_command(shim: Path) -> tuple[str, ...]:
    try:
        launcher = shim.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise _windows_launch_error(
            shim, f"cannot read launcher: {type(exc).__name__}: {exc}"
        ) from exc

    entry_match = _WINDOWS_ENTRYPOINT_PATTERN.search(launcher)
    if entry_match is None:
        raise _windows_launch_error(
            shim, "cannot identify the direct Node CLI entrypoint"
        )
    entrypoint = _windows_relative_path(shim.parent, entry_match.group("entry"))
    if not entrypoint.is_file():
        raise _windows_launch_error(
            shim, f"direct Node CLI entrypoint does not exist: {entrypoint}"
        )

    node_executable: Path | None = None
    node_match = _WINDOWS_NODE_PATTERN.search(launcher)
    if node_match is not None:
        adjacent_node = _windows_relative_path(shim.parent, node_match.group("node"))
        if adjacent_node.is_file():
            node_executable = adjacent_node
    if node_executable is None:
        node_from_path = shutil.which("node.exe") or shutil.which("node")
        if node_from_path:
            node_executable = Path(node_from_path).resolve()
    if node_executable is None or not node_executable.is_file():
        raise _windows_launch_error(
            shim, "cannot resolve a usable Node executable without the .cmd shim"
        )

    return (str(node_executable), str(entrypoint))


def _default_command() -> tuple[str, ...]:
    shim_name = shutil.which("codebuddy.cmd")
    if os.name != "nt":
        return (shim_name or "codebuddy.cmd",)
    if not shim_name:
        raise CodeBuddyLaunchConfigurationError(
            "CodeBuddy Windows launch configuration error: codebuddy.cmd was not found"
        )
    return _resolve_windows_command(Path(shim_name))


def _bounded(value: str, limit: int = _DEFAULT_MAX_DIAGNOSTIC_CHARS) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)] + "..."


def _read_bounded(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        return stream.read(limit + 1)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _walk_mappings(value: Any):
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _walk_mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_mappings(child)


def _trace_tool_events(value: Any) -> list[Mapping[str, Any]]:
    events = []
    for event in _walk_mappings(value):
        if event.get("type") in {
            "function_call",
            "function_call_result",
            "functionCall",
            "functionCallResult",
            "tool_call",
            "tool_result",
            "toolCall",
            "toolResult",
        } or event.get("name") in {"Read", "Edit", "Write", "Bash"}:
            events.append(event)
    return events


def _trace_models(value: Any) -> list[str]:
    models: list[str] = []
    for event in _walk_mappings(value):
        provider_data = event.get("providerData")
        if isinstance(provider_data, Mapping):
            model = provider_data.get("model")
            if isinstance(model, str) and model not in models:
                models.append(model)
    return models


def _trace_turn_sequence(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    sequence: list[dict[str, Any]] = []
    for index, event in enumerate(value):
        if not isinstance(event, Mapping):
            continue
        sequence.append(
            {
                "index": index,
                "type": event.get("type"),
                "name": event.get("name"),
                "call_id": event.get("callId"),
                "timestamp": event.get("timestamp"),
                "session_id": event.get("sessionId"),
                "parent_id": event.get("parentId"),
            }
        )
    return sequence


def _encode_safe_event_record(record: Mapping[str, Any]) -> str:
    """Serialize one allowlisted safe-event record as compact JSON."""

    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def _safe_native_event_fields(event: Any) -> dict[str, Any]:
    """Project a native structured event onto non-content metadata only."""

    if not isinstance(event, Mapping):
        return {
            "event_type": "unknown",
            "turn_index": None,
            "turn_index_source": "unavailable",
            "tool_name": None,
            "tool_status": None,
            "progress_kind": "unknown_event_observed",
            "terminal_reason": None,
        }

    native_type = event.get("type")
    if isinstance(native_type, str) and native_type in {
        "function_call",
        "functionCall",
        "tool_call",
        "toolCall",
    }:
        event_type = "tool_call"
        progress_kind = "tool_call_observed"
    elif isinstance(native_type, str) and native_type in {
        "function_call_result",
        "functionCallResult",
        "tool_result",
        "toolResult",
    }:
        event_type = "tool_result"
        progress_kind = "tool_result_observed"
    elif isinstance(native_type, str) and native_type in {
        "message",
        "assistant",
        "assistant_message",
    }:
        event_type = "model_event"
        progress_kind = "model_event_observed"
    elif native_type == "progress":
        event_type = "progress"
        progress_kind = "native_progress_observed"
    elif native_type == "result":
        event_type = "terminal"
        progress_kind = "native_terminal_observed"
    else:
        event_type = "unknown"
        progress_kind = "unknown_event_observed"

    raw_turn_index = event.get("turn_index")
    if type(raw_turn_index) is int and raw_turn_index >= 0:
        turn_index: int | None = raw_turn_index
        turn_index_source = "native_cli_event"
    else:
        turn_index = None
        turn_index_source = "unavailable"

    raw_name = event.get("name")
    tool_name = (
        raw_name
        if event_type in {"tool_call", "tool_result"}
        and isinstance(raw_name, str)
        and raw_name in _SAFE_TRACE_TOOL_NAMES
        else None
    )

    tool_status: str | None = None
    if event_type == "tool_result":
        if event.get("permission_denied") is True or event.get("permissionDenied") is True:
            tool_status = "denied"
        elif event.get("is_error") is True or event.get("isError") is True:
            tool_status = "error"
        else:
            raw_status = event.get("status")
            if isinstance(raw_status, str) and raw_status.lower() in _SAFE_TRACE_TOOL_STATUSES:
                tool_status = raw_status.lower()

    terminal_reason: str | None = None
    if event_type == "terminal":
        subtype = event.get("subtype")
        if subtype == "success":
            terminal_reason = "completed"
        elif subtype == "error_max_turns":
            terminal_reason = "max_turns_exceeded"
        elif event.get("is_error") is True or event.get("isError") is True:
            terminal_reason = "worker_failure"
        elif subtype == "error":
            terminal_reason = "worker_failure"
        else:
            terminal_reason = "unknown"

    return {
        "event_type": event_type,
        "turn_index": turn_index,
        "turn_index_source": turn_index_source,
        "tool_name": tool_name,
        "tool_status": tool_status,
        "progress_kind": progress_kind,
        "terminal_reason": terminal_reason,
    }


def _safe_trace_io_path(path: Path) -> Path:
    """Open long Windows evidence paths without changing their logical identity."""
    value = str(path)
    if os.name != "nt" or len(value) < 248 or value.startswith("\\\\?\\"):
        return path
    if value.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + value[2:])
    return Path("\\\\?\\" + value)


class _SafeCodeBuddyEventSink:
    """Persist only the explicitly allowlisted CodeBuddy worker metadata."""

    def __init__(
        self,
        directory: Path,
        *,
        cli_identity: Mapping[str, str] | None = None,
        trace_complete_scope: str | None = None,
        max_bytes: int | None = None,
        max_events: int | None = None,
    ) -> None:
        if not directory.is_absolute():
            raise ValueError("safe CodeBuddy trace directory must be absolute")
        self._max_bytes = _SAFE_TRACE_MAX_BYTES if max_bytes is None else max_bytes
        self._max_events = _SAFE_TRACE_MAX_EVENTS if max_events is None else max_events
        if self._max_bytes < 2 * _SAFE_TRACE_TERMINAL_RESERVE_BYTES:
            raise ValueError("safe CodeBuddy trace byte quota is too small")
        if self._max_events < 2:
            raise ValueError("safe CodeBuddy trace event quota is too small")
        self.trace_id = uuid4().hex
        self._run_id = os.environ.get(RUNTIME_RUN_ID_ENV)
        if self._run_id is not None and not _RUNTIME_RUN_ID_PATTERN.fullmatch(self._run_id):
            raise ValueError("DSH_RUNTIME_RUN_ID must use the dsh-runtime UUID namespace")
        self.path = directory / f"codebuddy-safe-worker-{self.trace_id}.jsonl"
        self._io_path = _safe_trace_io_path(self.path)
        self._stream = None
        self._event_seq = 0
        self._event_count = 0
        self._bytes_written = 0
        self._quota_exceeded = False
        self.incomplete = False
        self._cli_identity = dict(cli_identity or {})
        self._trace_complete_scope = trace_complete_scope
        try:
            _safe_trace_io_path(directory).mkdir(parents=True, exist_ok=True)
            self._stream = self._io_path.open("x", encoding="utf-8", newline="\n")
        except Exception:
            self.incomplete = True
            self._stream = None
            return
        self.emit(
            event_type="progress",
            worker_phase="starting",
            progress_kind="worker_started",
        )

    @property
    def enabled(self) -> bool:
        return self._stream is not None

    def _record(
        self,
        *,
        event_type: str,
        worker_phase: str,
        progress_kind: str | None = None,
        turn_index: int | None = None,
        turn_index_source: str = "unavailable",
        tool_name: str | None = None,
        tool_status: str | None = None,
        terminal_reason: str | None = None,
    ) -> dict[str, Any]:
        record = {
            "schema_version": 1,
            "trace_id": self.trace_id,
            "event_seq": self._event_seq,
            "captured_at_utc": _utc_timestamp(),
            "worker_phase": worker_phase,
            "event_type": event_type,
            "turn_index": turn_index,
            "turn_index_source": turn_index_source,
            "tool_name": tool_name,
            "tool_status": tool_status,
            "progress_kind": progress_kind,
            "terminal_reason": terminal_reason,
            "trace_complete": not self.incomplete,
        }
        if self._cli_identity:
            record["cli_identity"] = dict(self._cli_identity)
        if self._trace_complete_scope is not None:
            record["trace_complete_scope"] = self._trace_complete_scope
        return record

    def _write(self, record: Mapping[str, Any], *, terminal: bool = False) -> bool:
        if self._stream is None:
            return False
        if self._quota_exceeded and not terminal:
            return False
        try:
            safe_record = dict(record)
            if terminal and self._quota_exceeded:
                safe_record["progress_kind"] = "trace_quota_exceeded"
                safe_record["trace_quota_exceeded"] = True
                safe_record["trace_complete"] = False
            line = _encode_safe_event_record(safe_record)
            line_bytes = len((line + "\n").encode("utf-8"))
            event_limit = self._max_events if terminal else self._max_events - 1
            byte_limit = (
                self._max_bytes
                if terminal
                else self._max_bytes - _SAFE_TRACE_TERMINAL_RESERVE_BYTES
            )
            if (
                self._event_count + 1 > event_limit
                or self._bytes_written + line_bytes > byte_limit
            ):
                self.incomplete = True
                self._quota_exceeded = True
                return False
            self._write_line(line)
        except Exception:
            self.incomplete = True
            return False
        self._event_seq += 1
        self._event_count += 1
        self._bytes_written += line_bytes
        return True

    def _write_line(self, line: str) -> None:
        if self._stream is None:
            return
        self._stream.write(line + "\n")
        self._stream.flush()

    def emit(
        self,
        *,
        event_type: str,
        worker_phase: str,
        progress_kind: str | None = None,
        turn_index: int | None = None,
        turn_index_source: str = "unavailable",
        tool_name: str | None = None,
        tool_status: str | None = None,
        terminal_reason: str | None = None,
    ) -> None:
        record = self._record(
            event_type=event_type,
            worker_phase=worker_phase,
            progress_kind=progress_kind,
            turn_index=turn_index,
            turn_index_source=turn_index_source,
            tool_name=tool_name,
            tool_status=tool_status,
            terminal_reason=terminal_reason,
        )
        self._write(record)

    def emit_native_event(self, event: Any) -> None:
        self.emit(
            worker_phase="worker_output",
            **_safe_native_event_fields(event),
        )

    def mark_incomplete(self) -> None:
        self.incomplete = True

    def finish(self, terminal_reason: str) -> None:
        if self._stream is None:
            return
        written = self._write(
            self._record(
                event_type="terminal",
                worker_phase="settled",
                progress_kind=(
                    "trace_incomplete" if self.incomplete else "worker_settled"
                ),
                terminal_reason=terminal_reason,
            ),
            terminal=True,
        )
        if not written and self._stream is not None:
            self.incomplete = True
            fallback = self._record(
                event_type="terminal",
                worker_phase="settled",
                progress_kind=(
                    "trace_quota_exceeded"
                    if self._quota_exceeded
                    else "trace_incomplete"
                ),
                terminal_reason=terminal_reason,
            )
            if self._quota_exceeded:
                fallback["trace_quota_exceeded"] = True
            self._write(fallback, terminal=True)
        try:
            self._stream.close()
        except Exception:
            self.incomplete = True
        else:
            if self._run_id is not None:
                try:
                    marker = self.path.with_name(self.path.name + ".closed")
                    payload = {
                        "schema_version": 1,
                        "run_id": self._run_id,
                        "trace_id": self.trace_id,
                        "final_bytes": self._io_path.stat().st_size,
                    }
                    with _safe_trace_io_path(marker).open("x", encoding="utf-8", newline="\n") as stream:
                        json.dump(payload, stream, separators=(",", ":"))
                        stream.write("\n")
                except Exception:
                    self.incomplete = True
        self._stream = None


class _SafeJsonArrayEventObserver:
    """Incrementally parse top-level events without retaining payloads."""

    def __init__(
        self,
        sink: _SafeCodeBuddyEventSink,
        *,
        max_events_per_feed: int = _SAFE_OBSERVER_MAX_EVENTS_PER_FEED,
        max_buffer_chars: int = _SAFE_JSON_ARRAY_MAX_BUFFER_CHARS,
    ) -> None:
        if max_events_per_feed <= 0 or max_buffer_chars <= 0:
            raise ValueError("safe JSON-array observer bounds must be positive")
        self._sink = sink
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._json_decoder = json.JSONDecoder()
        self._buffer = ""
        self._max_events_per_feed = max_events_per_feed
        self._max_buffer_chars = max_buffer_chars
        self._array_started = False
        self._array_closed = False
        self._invalid_root = False
        self._decoder_finalized = False
        self._batch_work = 0
        self.max_batch_work_observed = 0
        self.work_budget_yields = 0

    async def feed(self, chunk: bytes) -> None:
        if self._array_closed or self._invalid_root:
            return
        try:
            decoded = self._decoder.decode(chunk)
            if len(self._buffer) + len(decoded) > self._max_buffer_chars:
                self._invalidate()
                return
            self._buffer += decoded
            await self._consume(final=False)
        except Exception:
            self._invalidate()

    async def finish(self) -> None:
        if self._array_closed or self._invalid_root:
            return
        try:
            if not self._decoder_finalized:
                self._buffer += self._decoder.decode(b"", final=True)
                self._decoder_finalized = True
            await self._consume(final=True)
            if self._array_started and not self._array_closed:
                self._sink.mark_incomplete()
        except Exception:
            self._sink.mark_incomplete()
        finally:
            if self._array_closed or self._invalid_root:
                self._buffer = ""

    async def _consume(self, *, final: bool) -> None:
        if not self._array_started:
            stripped = self._buffer.lstrip()
            if not stripped:
                self._buffer = ""
                return
            if not stripped.startswith("["):
                self._invalidate()
                return
            self._array_started = True
            self._buffer = stripped[1:]

        while True:
            self._buffer = self._buffer.lstrip()
            if self._buffer.startswith("]"):
                self._buffer = self._buffer[1:]
                if self._buffer.strip():
                    self._sink.mark_incomplete()
                self._array_closed = True
                return
            if not self._buffer:
                return
            if self._buffer.startswith(","):
                self._buffer = self._buffer[1:]
                await self._consume_work_unit()
                continue
            try:
                event, end = self._json_decoder.raw_decode(self._buffer)
            except json.JSONDecodeError:
                if final:
                    self._sink.mark_incomplete()
                    self._buffer = ""
                return
            before_length = len(self._buffer)
            if (
                not isinstance(end, int)
                or end <= 0
                or end > before_length
                or before_length - end >= before_length
            ):
                self._invalidate()
                return
            remaining = self._buffer[end:]
            if len(remaining) >= before_length:
                self._invalidate()
                return
            self._buffer = remaining
            self._sink.emit_native_event(event)
            if await self._consume_work_unit():
                continue

    async def _consume_work_unit(self) -> bool:
        self._batch_work += 1
        self.max_batch_work_observed = max(
            self.max_batch_work_observed, self._batch_work
        )
        if self._batch_work < self._max_events_per_feed:
            return False
        self._batch_work = 0
        self.work_budget_yields += 1
        await asyncio.sleep(0)
        return True

    def _invalidate(self) -> None:
        self._invalid_root = True
        self._buffer = ""
        self._sink.mark_incomplete()


def _safe_stream_cli_identity(command: Sequence[str]) -> dict[str, str]:
    """Return bounded, path-free identity metadata for an opt-in worker trace."""

    raw_executable = str(command[0]) if command else ""
    basename = raw_executable.replace("\\", "/").rsplit("/", 1)[-1]
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", basename):
        basename = "unavailable"
    lowered = basename.casefold()
    if "node" in lowered:
        category = "node"
    elif "python" in lowered:
        category = "python"
    elif "codebuddy" in lowered:
        category = "codebuddy"
    else:
        category = "other" if basename != "unavailable" else "unavailable"

    package = "unavailable"
    version = "unavailable"
    for raw_entry in command[1:]:
        if Path(str(raw_entry)).suffix.lower() not in {".js", ".mjs", ".cjs"}:
            continue
        try:
            entry = Path(str(raw_entry)).resolve()
            parents = list(entry.parents)[:6]
        except (OSError, RuntimeError, ValueError):
            continue
        for parent in parents:
            package_path = parent / "package.json"
            try:
                with package_path.open("rb") as stream:
                    raw_package = stream.read(65_537)
                if len(raw_package) > 65_536:
                    continue
                package_data = json.loads(raw_package.decode("utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            if not isinstance(package_data, Mapping):
                continue
            if package_data.get("name") != "@tencent-ai/codebuddy-code":
                continue
            raw_version = package_data.get("version")
            if isinstance(raw_version, str) and re.fullmatch(
                r"[0-9A-Za-z.+-]{1,64}", raw_version
            ):
                package = "@tencent-ai/codebuddy-code"
                version = raw_version
            break
        if package != "unavailable":
            break
    return {
        "executable_basename": basename,
        "executable_category": category,
        "package": package,
        "version": version,
    }


class _StreamJsonResultCollector:
    """Keep only the bounded business result needed by Runtime normalization."""

    def __init__(
        self,
        max_output_chars: int,
        max_stream_chars: int | None = None,
    ) -> None:
        self.max_output_chars = max_output_chars
        self.max_stream_chars = (
            max_output_chars if max_stream_chars is None else max_stream_chars
        )
        self.total_chars = 0
        self.saw_non_whitespace = False
        self.valid_event_count = 0
        self.malformed_event = False
        self.last_event_type: str | None = None
        self.result_seen = False
        self.result_subtype: Any = None
        self.result_is_error: Any = None
        self.result_detail: str | None = None
        self.result_output: str | None = None
        self.result_output_is_string = False
        self.result_output_chars = 0
        self.last_tool_failure: str | None = None

    def observe_text(self, text: str) -> None:
        self.total_chars += len(text)
        if text.strip():
            self.saw_non_whitespace = True

    def accept(self, event: Mapping[str, Any]) -> None:
        self.valid_event_count += 1
        raw_type = event.get("type")
        # Some bounded stream-json workers emit a delayed system/init frame
        # after the successful result. It is setup metadata, not a later turn,
        # so it must not hide the terminal result from the completion check.
        late_init = (
            self.result_seen
            and raw_type == "system"
            and event.get("subtype") == "init"
        )
        if not late_init:
            self.last_event_type = raw_type if isinstance(raw_type, str) else None
        if raw_type == "result":
            self.result_seen = True
            self.result_subtype = event.get("subtype")
            self.result_is_error = event.get("is_error")
            detail = event.get("error") or event.get("result") or event.get("subtype")
            self.result_detail = _bounded(str(detail)) if detail else None
            output = event.get("result")
            self.result_output_is_string = isinstance(output, str)
            if isinstance(output, str):
                self.result_output_chars = len(output)
                self.result_output = (
                    output if len(output) <= self.max_output_chars else None
                )

        if raw_type in {"assistant", "user"}:
            message = event.get("message")
            content = message.get("content") if isinstance(message, Mapping) else None
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, Mapping) or block.get("type") != "tool_result":
                        continue
                    failure = _tool_failure(block)
                    if failure is not None:
                        self.last_tool_failure = _bounded(failure)

    def normalize(self, stderr: bytes, returncode: int | None) -> PluginResult:
        if returncode not in (0, None):
            diagnostic = _bounded(stderr.decode("utf-8", errors="replace"))
            suffix = f": {diagnostic}" if diagnostic else ""
            return PluginResult(
                success=False,
                error=f"CodeBuddy process exited with code {returncode}{suffix}",
            )

        if self.total_chars > self.max_stream_chars:
            return PluginResult(
                success=False,
                error=(
                    "CodeBuddy output exceeded the configured bound; "
                    f"limit_chars={self.max_stream_chars}; "
                    f"observed_chars={self.total_chars}; "
                    f"valid_events={self.valid_event_count}; "
                    f"result_seen={str(self.result_seen).lower()}; "
                    f"result_chars={self.result_output_chars}; "
                    "last_event_type_present="
                    f"{str(self.last_event_type is not None).lower()}"
                ),
            )
        if not self.saw_non_whitespace:
            diagnostic = _bounded(stderr.decode("utf-8", errors="replace"))
            return PluginResult(
                success=False,
                error=(
                    "CodeBuddy returned empty output"
                    + (f": {diagnostic}" if diagnostic else "")
                ),
            )
        if self.malformed_event and not self.result_seen:
            return PluginResult(
                success=False,
                error="CodeBuddy bounded invocation failed: malformed JSON output",
            )
        if not self.result_seen or self.last_event_type != "result":
            return PluginResult(
                success=False,
                error="CodeBuddy bounded invocation failed: missing final result event",
            )
        if self.result_subtype != "success" or self.result_is_error is not False:
            detail_text = f": {self.result_detail}" if self.result_detail else ""
            return PluginResult(
                success=False,
                error=f"CodeBuddy native session failed{detail_text}",
            )
        if self.last_tool_failure is not None:
            return PluginResult(
                success=False,
                error=f"CodeBuddy native tool failed: {_bounded(self.last_tool_failure)}",
            )
        if not self.result_output_is_string or not (self.result_output or "").strip():
            return PluginResult(
                success=False,
                error="CodeBuddy bounded invocation failed: final result has no usable assistant output",
            )
        if self.result_output_chars > self.max_output_chars:
            return PluginResult(
                success=False,
                error="CodeBuddy final assistant output exceeded the configured bound",
            )
        return PluginResult(success=True, output=self.result_output or "")


class _SafeStreamJsonEventObserver:
    """Map official stream-json message shapes onto safe metadata only."""

    def __init__(self, sink: _SafeCodeBuddyEventSink) -> None:
        self._sink = sink
        self._tool_names_by_id: dict[str, str] = {}

    def _progress(self, kind: str, *, event_type: str = "progress") -> None:
        self._sink.emit(
            event_type=event_type,
            worker_phase="worker_output",
            progress_kind=kind,
        )

    def observe(self, event: Mapping[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == "system":
            subtype = event.get("subtype")
            if subtype == "init":
                self._progress("initialization_event_observed")
            else:
                self._progress("system_event_observed", event_type="unknown")
            return

        if event_type == "assistant":
            self._progress("message_event_observed", event_type="model_event")
            self._observe_tool_uses(event)
            return

        if event_type == "user":
            if not self._observe_tool_results(event):
                self._progress("message_event_observed", event_type="model_event")
            return

        if event_type == "result":
            subtype = event.get("subtype")
            if subtype == "success":
                terminal_reason = "completed"
            elif subtype == "error_max_turns":
                terminal_reason = "max_turns_exceeded"
            elif event.get("is_error") is True or (
                isinstance(subtype, str) and subtype.startswith("error")
            ):
                terminal_reason = "worker_failure"
            else:
                terminal_reason = "unknown"
            self._sink.emit(
                event_type="terminal",
                worker_phase="worker_output",
                progress_kind="native_terminal_observed",
                terminal_reason=terminal_reason,
            )
            return

        self._progress("unknown_event_observed", event_type="unknown")

    def _message_content(self, event: Mapping[str, Any]) -> Any:
        message = event.get("message")
        return message.get("content") if isinstance(message, Mapping) else None

    def _observe_tool_uses(self, event: Mapping[str, Any]) -> None:
        content = self._message_content(event)
        if not isinstance(content, list):
            return
        for index, block in enumerate(content):
            if index >= _STREAM_JSON_MAX_TOOL_BLOCKS_PER_EVENT:
                self._sink.mark_incomplete()
                return
            if not isinstance(block, Mapping) or block.get("type") != "tool_use":
                continue
            raw_name = block.get("name")
            tool_name = (
                raw_name
                if isinstance(raw_name, str) and raw_name in _SAFE_TRACE_TOOL_NAMES
                else None
            )
            raw_id = block.get("id")
            if (
                tool_name is not None
                and isinstance(raw_id, str)
                and 0 < len(raw_id) <= 256
                and len(self._tool_names_by_id) < _STREAM_JSON_MAX_TOOL_CORRELATIONS
            ):
                self._tool_names_by_id[raw_id] = tool_name
            self._sink.emit(
                event_type="tool_call" if tool_name is not None else "progress",
                worker_phase="worker_output",
                progress_kind="tool_call_observed",
                tool_name=tool_name,
                tool_status="running" if tool_name is not None else None,
            )

    def _observe_tool_results(self, event: Mapping[str, Any]) -> bool:
        content = self._message_content(event)
        if not isinstance(content, list):
            return False
        observed = False
        for index, block in enumerate(content):
            if index >= _STREAM_JSON_MAX_TOOL_BLOCKS_PER_EVENT:
                self._sink.mark_incomplete()
                break
            if not isinstance(block, Mapping) or block.get("type") != "tool_result":
                continue
            observed = True
            raw_id = block.get("tool_use_id")
            tool_name = (
                self._tool_names_by_id.pop(raw_id, None)
                if isinstance(raw_id, str)
                else None
            )
            if block.get("is_error") is True:
                tool_status = "error"
            elif block.get("is_error") is False:
                tool_status = "completed"
            else:
                tool_status = None
            self._sink.emit(
                event_type="tool_result",
                worker_phase="worker_output",
                progress_kind="tool_result_observed",
                tool_name=tool_name,
                tool_status=tool_status,
            )
        return observed


class _StreamJsonLineParser:
    """Consume bounded JSONL framing and discard every raw line after parsing."""

    def __init__(
        self,
        collector: _StreamJsonResultCollector,
        observer: _SafeStreamJsonEventObserver | None,
        sink: _SafeCodeBuddyEventSink | None,
        *,
        max_line_chars: int,
        max_events_per_feed: int = _STREAM_JSON_MAX_EVENTS_PER_FEED,
    ) -> None:
        if max_events_per_feed <= 0:
            raise ValueError("stream JSON parser work budget must be positive")
        self._collector = collector
        self._observer = observer
        self._sink = sink
        self._max_line_chars = max_line_chars
        self._max_events_per_feed = max_events_per_feed
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._buffer = ""
        self._discarding_line = False
        self._decoder_finalized = False
        self.closed_cleanly = False
        self.max_batch_work_observed = 0
        self.work_budget_yields = 0

    async def feed(self, chunk: bytes) -> None:
        try:
            text = self._decoder.decode(chunk)
            self._collector.observe_text(text)
            if "\ufffd" in text and self._sink is not None:
                self._sink.mark_incomplete()
            await self._feed_text(text)
        except Exception:
            self._mark_incomplete()

    async def finish(self) -> None:
        try:
            tail = ""
            if not self._decoder_finalized:
                tail = self._decoder.decode(b"", final=True)
                self._decoder_finalized = True
            if tail:
                self._collector.observe_text(tail)
                if "\ufffd" in tail and self._sink is not None:
                    self._sink.mark_incomplete()
                await self._feed_text(tail)
            if self._discarding_line:
                self._mark_incomplete()
            elif self._buffer:
                self._consume_line(self._buffer[:-1] if self._buffer.endswith("\r") else self._buffer)
            self._buffer = ""
            self.closed_cleanly = True
        except Exception:
            self._mark_incomplete()
            self._buffer = ""

    async def _feed_text(self, text: str) -> None:
        work_units = 0
        position = 0
        while position < len(text):
            newline = text.find("\n", position)
            if newline < 0:
                self._append(text[position:])
                return
            self._append(text[position:newline])
            if not self._discarding_line:
                line = self._buffer[:-1] if self._buffer.endswith("\r") else self._buffer
                self._consume_line(line)
            self._buffer = ""
            self._discarding_line = False
            position = newline + 1
            work_units += 1
            self.max_batch_work_observed = max(
                self.max_batch_work_observed, work_units
            )
            if work_units >= self._max_events_per_feed:
                work_units = 0
                self.work_budget_yields += 1
                await asyncio.sleep(0)

    def _append(self, text: str) -> None:
        if self._discarding_line or not text:
            return
        if len(self._buffer) + len(text) > self._max_line_chars:
            self._buffer = ""
            self._discarding_line = True
            self._mark_incomplete()
            return
        self._buffer += text

    def _consume_line(self, line: str) -> None:
        if not line.strip():
            return
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, RecursionError):
            self._collector.malformed_event = True
            self._mark_incomplete()
            return
        if not isinstance(event, Mapping):
            self._collector.malformed_event = True
            self._mark_incomplete()
            return
        try:
            self._collector.accept(event)
        except Exception:
            self._collector.malformed_event = True
        if self._observer is not None:
            try:
                self._observer.observe(event)
            except Exception:
                self._mark_incomplete()

    def _mark_incomplete(self) -> None:
        if self._sink is not None:
            try:
                self._sink.mark_incomplete()
            except Exception:
                pass


class _BoundedByteBuffer:
    """Retain only a bounded prefix while the pipe reader drains to EOF."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.data = bytearray()

    def feed(self, chunk: bytes) -> None:
        remaining = self.limit - len(self.data)
        if remaining > 0:
            self.data.extend(chunk[:remaining])


async def _read_stdout_pipe(
    stream: Any,
    parser: _StreamJsonLineParser,
) -> None:
    try:
        while True:
            chunk = await asyncio.to_thread(stream.read, _STREAM_JSON_READ_CHUNK)
            if not chunk:
                break
            await parser.feed(chunk)
    finally:
        try:
            await parser.finish()
        finally:
            try:
                stream.close()
            except OSError:
                pass


async def _read_stderr_pipe(stream: Any, buffer: _BoundedByteBuffer) -> None:
    try:
        while True:
            chunk = await asyncio.to_thread(stream.read, _STREAM_JSON_READ_CHUNK)
            if not chunk:
                break
            buffer.feed(chunk)
    finally:
        try:
            stream.close()
        except OSError:
            pass


async def _observe_stdout_file(
    path: Path,
    process: subprocess.Popen[bytes],
    observer: _SafeJsonArrayEventObserver,
    *,
    max_bytes: int,
) -> None:
    """Read only newly written stdout bytes while preserving the worker's fd."""

    total = 0
    try:
        with path.open("rb") as stream:
            while True:
                remaining = max_bytes - total
                if remaining > 0:
                    chunk = stream.read(min(16_384, remaining))
                else:
                    chunk = b""
                if chunk:
                    total += len(chunk)
                    await observer.feed(chunk)
                    await asyncio.sleep(0)
                    continue
                if path.stat().st_size > total:
                    observer._sink.mark_incomplete()
                    break
                if process.poll() is not None:
                    break
                await asyncio.sleep(0.02)
        await observer.finish()
    except Exception:
        observer._sink.mark_incomplete()


def _safe_terminal_reason(
    result: PluginResult | None,
    *,
    process_started: bool,
    cancelled: bool,
) -> str:
    if cancelled:
        return "cancelled"
    if not process_started:
        return "launch_failure"
    if result is None:
        return "unknown"
    if result.success:
        return "completed"
    if result.error and _SAFE_MAX_TURNS_DIAGNOSTIC.search(result.error):
        return "max_turns_exceeded"
    return "worker_failure"


def _trace_plugin_result(result: PluginResult | None) -> dict[str, Any] | None:
    if result is None:
        return None
    return {
        "success": result.success,
        "output": result.output,
        "error": result.error,
        "stop_reason": result.stop_reason.value if result.stop_reason else None,
        "cleanup_error": result.cleanup_error,
    }


def _trace_json_output(stdout: bytes) -> tuple[Any, str | None]:
    text = stdout.decode("utf-8", errors="replace")
    if not text.strip():
        return None, None
    try:
        return json.loads(text), None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _is_tool_result(event: Mapping[str, Any]) -> bool:
    return event.get("type") in {
        "function_call_result",
        "functionCallResult",
        "tool_result",
        "toolResult",
    }


def _tool_failure(event: Mapping[str, Any]) -> str | None:
    for key in ("is_error", "isError", "permission_denied", "permissionDenied"):
        if event.get(key) is True:
            return "native tool error"

    for key in ("sandboxDenied", "sandbox_denied"):
        if event.get(key) is True:
            return "native sandbox denial"

    status = event.get("status")
    if isinstance(status, str) and status.lower() in {
        "error",
        "failed",
        "failure",
        "denied",
        "permission_denied",
        "unexecuted",
        "skipped",
        "not_run",
    }:
        return f"native tool status: {status}"

    for key in ("exit_code", "exitCode", "returncode", "returnCode"):
        code = event.get(key)
        if isinstance(code, int) and code != 0:
            return f"native tool exit code: {code}"

    signal = event.get("signal")
    if signal not in (None, "", 0, False):
        return f"native tool signal: {_bounded(str(signal))}"

    for key in ("error", "tool_error", "toolError", "errorMessage"):
        error = event.get(key)
        if error not in (None, "", False):
            return _bounded(str(error))

    result = event.get("result")
    if isinstance(result, Mapping):
        nested = _tool_failure(result)
        if nested is not None:
            return nested
    if isinstance(result, str):
        lowered = result.strip().lower()
        if (
            lowered.startswith("error:")
            or ("permission" in lowered and "den" in lowered)
            or "spawn eperm" in lowered
            or ("max turn" in lowered and "exceed" in lowered)
        ):
            return _bounded(result)
    return None


def _final_result(events: Any) -> Mapping[str, Any]:
    if not isinstance(events, list) or not events:
        raise _CodeBuddyOutputError("unexpected native event root")
    if not all(isinstance(event, Mapping) for event in events):
        raise _CodeBuddyOutputError("unexpected native event shape")
    final = events[-1]
    if final.get("type") != "result":
        raise _CodeBuddyOutputError("missing final result event")
    return final


def _normalize_output(
    stdout: bytes,
    stderr: bytes,
    returncode: int | None,
    *,
    max_output_chars: int,
) -> PluginResult:
    if returncode not in (0, None):
        diagnostic = _bounded(stderr.decode("utf-8", errors="replace"))
        suffix = f": {diagnostic}" if diagnostic else ""
        return PluginResult(
            success=False,
            error=f"CodeBuddy process exited with code {returncode}{suffix}",
        )

    stdout_text = stdout.decode("utf-8", errors="replace")
    if len(stdout_text) > max_output_chars:
        return PluginResult(
            success=False,
            error="CodeBuddy output exceeded the configured bound",
        )
    if not stdout_text.strip():
        diagnostic = _bounded(stderr.decode("utf-8", errors="replace"))
        return PluginResult(
            success=False,
            error=(
                "CodeBuddy returned empty output"
                + (f": {diagnostic}" if diagnostic else "")
            ),
        )

    try:
        events = json.loads(stdout_text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _CodeBuddyOutputError("malformed JSON output") from exc

    final = _final_result(events)
    if final.get("subtype") != "success" or final.get("is_error") is not False:
        detail = final.get("error") or final.get("result") or final.get("subtype")
        detail_text = f": {_bounded(str(detail))}" if detail else ""
        return PluginResult(
            success=False,
            error=f"CodeBuddy native session failed{detail_text}",
        )

    tool_errors = [
        failure
        for event in _walk_mappings(events)
        if _is_tool_result(event)
        for failure in [_tool_failure(event)]
        if failure is not None
    ]
    if tool_errors:
        return PluginResult(
            success=False,
            error=f"CodeBuddy native tool failed: {_bounded(tool_errors[-1])}",
        )

    output = final.get("result")
    if not isinstance(output, str) or not output.strip():
        raise _CodeBuddyOutputError("final result has no usable assistant output")
    if len(output) > max_output_chars:
        return PluginResult(
            success=False,
            error="CodeBuddy final assistant output exceeded the configured bound",
        )
    return PluginResult(success=True, output=output)


def _windows_process_descendants(root_pid: int) -> set[int]:
    """Read a bounded process snapshot and return descendants of one worker PID."""

    from ctypes import wintypes

    class _ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_ProcessEntry32W),
    ]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_ProcessEntry32W),
    ]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    invalid_handle = ctypes.c_void_p(-1).value
    if snapshot == invalid_handle:
        error = ctypes.get_last_error()
        raise OSError(error, ctypes.FormatError(error))

    children_by_parent: dict[int, set[int]] = {}
    entries_seen = 0
    try:
        entry = _ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(entry)
        has_entry = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        if not has_entry and ctypes.get_last_error() != 18:
            error = ctypes.get_last_error()
            raise OSError(error, ctypes.FormatError(error))
        while has_entry:
            entries_seen += 1
            if entries_seen > 32_768:
                raise RuntimeError("Windows process snapshot exceeded its safety bound")
            process_pid = int(entry.th32ProcessID)
            parent_pid = int(entry.th32ParentProcessID)
            if process_pid > 0:
                children_by_parent.setdefault(parent_pid, set()).add(process_pid)
            entry.dwSize = ctypes.sizeof(entry)
            has_entry = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
            if not has_entry and ctypes.get_last_error() != 18:
                error = ctypes.get_last_error()
                raise OSError(error, ctypes.FormatError(error))
    finally:
        kernel32.CloseHandle(snapshot)

    descendants: set[int] = set()
    pending = [root_pid]
    while pending:
        parent_pid = pending.pop()
        for child_pid in children_by_parent.get(parent_pid, ()):
            if child_pid == root_pid or child_pid in descendants:
                continue
            descendants.add(child_pid)
            if len(descendants) > 4_096:
                raise RuntimeError("Windows worker process tree exceeded its safety bound")
            pending.append(child_pid)
    return descendants


def _terminate_windows_process(pid: int) -> str | None:
    """Force-stop one confirmed descendant, treating an exited PID as settled."""

    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(0x00101001, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        if error in {87, 1168}:
            return None
        return f"cannot open worker descendant ({error})"
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            error = ctypes.get_last_error()
            return f"cannot inspect worker descendant ({error})"
        if exit_code.value != 259:
            return None
        if not kernel32.TerminateProcess(handle, 1):
            error = ctypes.get_last_error()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)) and exit_code.value != 259:
                return None
            return f"cannot terminate worker descendant ({error})"
        return None
    finally:
        kernel32.CloseHandle(handle)


def _windows_process_is_active(pid: int) -> bool:
    """Query liveness without reading the process command line or environment."""

    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        if error in {87, 1168}:
            return False
        raise OSError(error, ctypes.FormatError(error))
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            error = ctypes.get_last_error()
            raise OSError(error, ctypes.FormatError(error))
        return exit_code.value == 259
    finally:
        kernel32.CloseHandle(handle)


def _terminate_windows_process_descendants(
    root_pid: int,
    grace_seconds: float,
    known_descendants: set[int] | None = None,
) -> str | None:
    deadline = time.monotonic() + grace_seconds
    last_error: str | None = None
    tracked_descendants = set(known_descendants or ())
    while True:
        try:
            tracked_descendants.update(_windows_process_descendants(root_pid))
        except (OSError, RuntimeError) as exc:
            if not tracked_descendants:
                return f"CodeBuddy process-tree snapshot failed: {type(exc).__name__}"
            last_error = f"CodeBuddy process-tree snapshot failed: {type(exc).__name__}"
        if not tracked_descendants:
            return None
        for pid in tuple(tracked_descendants):
            try:
                if not _windows_process_is_active(pid):
                    tracked_descendants.discard(pid)
                    continue
            except OSError as exc:
                last_error = f"cannot inspect worker descendant ({type(exc).__name__})"
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                completed = subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=remaining,
                    check=False,
                )
                error = None
                if completed.returncode != 0 or _windows_process_is_active(pid):
                    error = _terminate_windows_process(pid)
            except subprocess.TimeoutExpired:
                error = "worker descendant cleanup command timed out"
            except OSError:
                error = _terminate_windows_process(pid)
            if error is not None:
                last_error = error
            try:
                remains_active = _windows_process_is_active(pid)
                if not remains_active:
                    tracked_descendants.discard(pid)
                elif last_error is None:
                    last_error = "worker descendant remains active after termination"
            except OSError as exc:
                last_error = f"cannot verify worker descendant exit ({type(exc).__name__})"
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return last_error or "CodeBuddy worker descendants did not settle"
        time.sleep(min(0.01, remaining))


async def _terminate_process_tree(
    process: subprocess.Popen[bytes],
    grace_seconds: float,
) -> str | None:
    """Terminate one CodeBuddy-owned process tree and await its root."""

    pid = process.pid
    cleanup_errors: list[str] = []
    known_descendants: set[int] = set()
    if os.name == "nt" and pid is not None:
        try:
            known_descendants = _windows_process_descendants(pid)
        except (OSError, RuntimeError) as exc:
            cleanup_errors.append(
                f"CodeBuddy process-tree snapshot failed: {type(exc).__name__}"
            )
        try:
            killer = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    "taskkill",
                    "/PID",
                    str(pid),
                    "/T",
                    "/F",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                ),
                timeout=grace_seconds,
            )
            try:
                await asyncio.wait_for(killer.wait(), timeout=grace_seconds)
            except asyncio.TimeoutError:
                try:
                    killer.kill()
                except OSError:
                    pass
                cleanup_errors.append("CodeBuddy process-tree cleanup helper timed out")
            if killer.returncode not in (None, 0):
                cleanup_errors.append(
                    f"CodeBuddy process-tree cleanup failed (taskkill {killer.returncode})"
                )
        except (asyncio.TimeoutError, subprocess.TimeoutExpired):
            cleanup_errors.append("CodeBuddy process-tree cleanup timed out")
        except OSError as exc:
            cleanup_errors.append(
                f"CodeBuddy process-tree cleanup failed: {type(exc).__name__}"
            )
    elif process.poll() is None:
        try:
            process.terminate()
        except OSError as exc:
            cleanup_errors.append(
                f"CodeBuddy process-tree cleanup failed: {type(exc).__name__}"
            )

    if os.name != "nt":
        try:
            await asyncio.wait_for(
                asyncio.to_thread(process.wait), timeout=grace_seconds
            )
        except asyncio.TimeoutError:
            try:
                process.kill()
                await asyncio.wait_for(
                    asyncio.to_thread(process.wait), timeout=grace_seconds
                )
            except (OSError, asyncio.TimeoutError) as exc:
                cleanup_errors.append(
                    f"CodeBuddy process-tree cleanup did not settle: {type(exc).__name__}"
                )
        return "; ".join(cleanup_errors) or None

    if process.poll() is None:
        try:
            process.kill()
        except OSError as exc:
            if process.poll() is None:
                cleanup_errors.append(
                    f"CodeBuddy process root kill failed: {type(exc).__name__}"
                )
    try:
        await asyncio.wait_for(asyncio.to_thread(process.wait), timeout=grace_seconds)
    except asyncio.TimeoutError:
        cleanup_errors.append("CodeBuddy process root did not settle")

    if os.name == "nt" and pid is not None:
        try:
            descendant_error = await asyncio.wait_for(
                asyncio.to_thread(
                    _terminate_windows_process_descendants,
                    pid,
                    grace_seconds,
                    known_descendants,
                ),
                timeout=grace_seconds,
            )
        except asyncio.TimeoutError:
            descendant_error = "CodeBuddy worker descendants did not settle"
        if descendant_error is not None:
            cleanup_errors.append(descendant_error)

    return "; ".join(cleanup_errors) or None


async def _cancel_task_and_wait(
    task: asyncio.Task[Any], timeout: float
) -> bool:
    """Cancel an observer and give its cooperative cleanup a bounded turn."""

    task.cancel()
    try:
        await asyncio.wait_for(
            asyncio.gather(task, return_exceptions=True), timeout=timeout
        )
    except asyncio.TimeoutError:
        return False
    return True


class CodeBuddyPlugin:
    """Concrete one-shot CodeBuddy print-mode Plugin."""

    name = "codebuddy"

    def __init__(
        self,
        command: Sequence[str] | None = None,
        *,
        environment: Mapping[str, str] | None = None,
        max_turns: int = _DEFAULT_MAX_TURNS,
        cleanup_grace_seconds: float = 2.0,
        max_output_chars: int = _DEFAULT_MAX_OUTPUT_CHARS,
        max_stream_chars: int | None = None,
        qualification_trace_dir: str | Path | None = None,
        safe_event_trace_dir: str | Path | None = None,
    ) -> None:
        self._command = tuple(command) if command is not None else _default_command()
        if not self._command:
            raise ValueError("CodeBuddy command cannot be empty")
        if max_turns <= 0:
            raise ValueError("CodeBuddy max_turns must be positive")
        if cleanup_grace_seconds <= 0:
            raise ValueError("CodeBuddy cleanup grace must be positive")
        if max_output_chars <= 0:
            raise ValueError("CodeBuddy output bound must be positive")
        if max_stream_chars is not None and max_stream_chars <= 0:
            raise ValueError("CodeBuddy stream output bound must be positive")
        if (
            max_stream_chars is not None
            and max_stream_chars > MAX_STREAM_CHARS_HARD_LIMIT
        ):
            raise ValueError("CodeBuddy stream output bound exceeds the hard limit")
        self.max_turns = max_turns
        self.cleanup_grace_seconds = cleanup_grace_seconds
        self.max_output_chars = max_output_chars
        self.max_stream_chars = (
            max_output_chars if max_stream_chars is None else max_stream_chars
        )
        self.qualification_trace_dir = (
            Path(qualification_trace_dir)
            if qualification_trace_dir is not None
            else None
        )
        safe_trace_dir = (
            safe_event_trace_dir
            if safe_event_trace_dir is not None
            else os.environ.get(SAFE_EVENT_TRACE_DIR_ENV)
        )
        self.safe_event_trace_dir = (
            Path(safe_trace_dir) if safe_trace_dir not in (None, "") else None
        )
        self.safe_stream_json = os.environ.get(SAFE_STREAM_JSON_ENV) == "1"
        self._environment_overlay = dict(environment or {})
        self._process: subprocess.Popen[bytes] | None = None

    def _environment(self) -> dict[str, str]:
        environment = dict(os.environ)
        environment.update(self._environment_overlay)
        # This DSH-only opt-in configures the parent-side sink; keep it out of
        # the native worker environment so enabling observation does not alter
        # CodeBuddy's environment.
        environment.pop(SAFE_EVENT_TRACE_DIR_ENV, None)
        environment.pop(RUNTIME_RUN_ID_ENV, None)
        environment.pop(SAFE_STREAM_JSON_ENV, None)
        environment.pop(MAX_STREAM_CHARS_ENV, None)
        return environment

    @staticmethod
    def _prompt(ctx: ExecutionContext, params: Mapping[str, Any]) -> str | None:
        prompt = params.get("prompt", ctx.goal)
        if not isinstance(prompt, str) or not prompt.strip():
            return None
        return prompt.strip()

    def _argv(
        self,
        prompt: str,
        settings_path: Path,
        *,
        stream_json: bool = False,
    ) -> list[str]:
        return [
            *self._command,
            "--print",
            "--output-format",
            "stream-json" if stream_json else "json",
            "--input-format",
            "text",
            "--max-turns",
            str(self.max_turns),
            "--no-session-persistence",
            "--tools",
            "Read,Edit,Write,Bash",
            "--settings",
            str(settings_path),
            "--permission-mode",
            "dontAsk",
            "--allowedTools=Bash(python:*)",
            prompt,
        ]

    async def _execute_stream_json(
        self,
        cwd: Path,
        prompt: str,
    ) -> PluginResult:
        """Run the qualification-only stream-json path without raw disk capture."""

        settings_path: Path | None = None
        safe_event_sink: _SafeCodeBuddyEventSink | None = None
        safe_event_observer: _SafeStreamJsonEventObserver | None = None
        stdout_reader: asyncio.Task[None] | None = None
        stderr_reader: asyncio.Task[None] | None = None
        wait_task: asyncio.Task[int] | None = None
        process: subprocess.Popen[bytes] | None = None
        parser: _StreamJsonLineParser | None = None
        stderr_buffer = _BoundedByteBuffer(_DEFAULT_MAX_DIAGNOSTIC_CHARS + 1)
        collector = _StreamJsonResultCollector(
            self.max_output_chars, self.max_stream_chars
        )
        result: PluginResult | None = None
        cancelled = False
        cleanup_errors: list[str] = []

        try:
            if self.safe_event_trace_dir is not None:
                try:
                    safe_event_sink = _SafeCodeBuddyEventSink(
                        self.safe_event_trace_dir,
                        cli_identity=_safe_stream_cli_identity(self._command),
                        trace_complete_scope="observable_stream_lifecycle_only",
                    )
                    if safe_event_sink.enabled:
                        safe_event_observer = _SafeStreamJsonEventObserver(
                            safe_event_sink
                        )
                except Exception:
                    # Safe observability setup is best-effort and cannot change
                    # the worker invocation or its normalized result.
                    safe_event_sink = None
                    safe_event_observer = None

            fd, raw_settings_path = tempfile.mkstemp(
                prefix="dsh-codebuddy-", suffix=".json"
            )
            os.close(fd)
            settings_path = Path(raw_settings_path)
            settings_path.write_text(
                json.dumps(_SETTINGS, separators=(",", ":")), encoding="utf-8"
            )

            process = subprocess.Popen(
                self._argv(prompt, settings_path, stream_json=True),
                cwd=str(cwd),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._environment(),
                shell=False,
                bufsize=0,
            )
            self._process = process
            if process.stdout is None or process.stderr is None:
                raise OSError("CodeBuddy stream pipes were not created")
            parser = _StreamJsonLineParser(
                collector,
                safe_event_observer,
                safe_event_sink,
                max_line_chars=max(1, self.max_stream_chars),
            )
            stdout_reader = asyncio.create_task(
                _read_stdout_pipe(process.stdout, parser)
            )
            stderr_reader = asyncio.create_task(
                _read_stderr_pipe(process.stderr, stderr_buffer)
            )
            wait_task = asyncio.create_task(asyncio.to_thread(process.wait))
            await asyncio.shield(wait_task)
            await asyncio.gather(stdout_reader, stderr_reader)
            result = collector.normalize(
                bytes(stderr_buffer.data), process.returncode
            )
        except asyncio.CancelledError:
            cancelled = True
            raise
        except (OSError, ValueError) as exc:
            result = PluginResult(
                success=False,
                error=f"CodeBuddy bounded invocation failed: {_bounded(str(exc))}",
            )
        finally:
            if process is not None and (cancelled or process.poll() is None):
                try:
                    cleanup_error = await _terminate_process_tree(
                        process, self.cleanup_grace_seconds
                    )
                    if cleanup_error is not None:
                        cleanup_errors.append(cleanup_error)
                except Exception as exc:
                    cleanup_errors.append(
                        f"CodeBuddy process-tree cleanup failed: {type(exc).__name__}"
                    )
            if cancelled and safe_event_sink is not None:
                try:
                    safe_event_sink.mark_incomplete()
                except Exception:
                    pass
            if wait_task is not None and not wait_task.done():
                try:
                    await asyncio.wait_for(
                        asyncio.shield(wait_task),
                        timeout=self.cleanup_grace_seconds,
                    )
                except (asyncio.TimeoutError, OSError, ValueError) as exc:
                    cleanup_errors.append(
                        f"CodeBuddy process wait did not settle: {type(exc).__name__}"
                    )
            for reader in (stdout_reader, stderr_reader):
                if reader is not None:
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(reader),
                            timeout=self.cleanup_grace_seconds,
                        )
                    except asyncio.TimeoutError:
                        await _cancel_task_and_wait(
                            reader, self.cleanup_grace_seconds
                        )
                        if safe_event_sink is not None:
                            try:
                                safe_event_sink.mark_incomplete()
                            except Exception:
                                pass
                    except Exception:
                        if safe_event_sink is not None:
                            try:
                                safe_event_sink.mark_incomplete()
                            except Exception:
                                pass
            if parser is not None and not parser.closed_cleanly and safe_event_sink is not None:
                try:
                    safe_event_sink.mark_incomplete()
                except Exception:
                    pass
            if safe_event_sink is not None:
                try:
                    safe_event_sink.finish(
                        _safe_terminal_reason(
                            result,
                            process_started=process is not None,
                            cancelled=cancelled,
                        )
                    )
                except Exception:
                    # Sink close/serialization failures are evidence-only.
                    pass
            for stream in (
                process.stdout if process is not None else None,
                process.stderr if process is not None else None,
            ):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
            if settings_path is not None:
                try:
                    settings_path.unlink(missing_ok=True)
                except OSError as exc:
                    cleanup_errors.append(
                        f"CodeBuddy settings cleanup failed: {type(exc).__name__}"
                    )
            self._process = None

            if cleanup_errors:
                cleanup_diagnostic = "; ".join(cleanup_errors)
                if cancelled:
                    raise RuntimeError(cleanup_diagnostic)
                if result is None:
                    result = PluginResult(success=False, error=cleanup_diagnostic)
                else:
                    result = replace(
                        result,
                        success=False,
                        error=result.error or cleanup_diagnostic,
                        cleanup_error=cleanup_diagnostic,
                    )

        return result or PluginResult(
            success=False, error="CodeBuddy invocation produced no result"
        )

    async def execute(
        self, ctx: ExecutionContext, params: dict[str, Any]
    ) -> PluginResult:
        if ctx.cwd is None:
            return PluginResult(success=False, error="CodeBuddy workspace cwd is missing")
        cwd = Path(ctx.cwd)
        if not cwd.exists() or not cwd.is_dir():
            return PluginResult(success=False, error="CodeBuddy workspace cwd is invalid")
        if ctx.allow_workspace_write is not True:
            return PluginResult(
                success=False,
                error="CodeBuddy requires workspace write authority",
            )
        prompt = self._prompt(ctx, params)
        if prompt is None:
            return PluginResult(success=False, error="CodeBuddy prompt must be non-empty text")
        if self.safe_stream_json:
            return await self._execute_stream_json(cwd, prompt)

        settings_path: Path | None = None
        stdout_path: Path | None = None
        stderr_path: Path | None = None
        trace_path: Path | None = None
        trace_id: str | None = None
        safe_event_sink: _SafeCodeBuddyEventSink | None = None
        safe_event_observer: _SafeJsonArrayEventObserver | None = None
        safe_event_observer_task: asyncio.Task[None] | None = None
        process: subprocess.Popen[bytes] | None = None
        stdout_file = None
        stderr_file = None
        wait_task: asyncio.Task[int] | None = None
        result: PluginResult | None = None
        cancelled = False
        cleanup_errors: list[str] = []
        trace_error: str | None = None
        trace_started_at = _utc_timestamp()
        try:
            if self.safe_event_trace_dir is not None:
                try:
                    safe_event_sink = _SafeCodeBuddyEventSink(
                        self.safe_event_trace_dir
                    )
                    if safe_event_sink.enabled:
                        safe_event_observer = _SafeJsonArrayEventObserver(
                            safe_event_sink
                        )
                except Exception:
                    # Qualification observability is best-effort and must not
                    # change the worker's invocation or result.
                    safe_event_sink = None
                    safe_event_observer = None
            if self.qualification_trace_dir is not None:
                try:
                    self.qualification_trace_dir.mkdir(parents=True, exist_ok=True)
                    trace_id = uuid4().hex
                    trace_path = self.qualification_trace_dir / (
                        f"codebuddy-worker-{trace_id}.json"
                    )
                except OSError as exc:
                    return PluginResult(
                        success=False,
                        error=(
                            f"{_QUALIFICATION_OBSERVABILITY_FAILURE}: "
                            f"cannot prepare trace sink: {type(exc).__name__}: {exc}"
                        ),
                    )
            fd, raw_path = tempfile.mkstemp(prefix="dsh-codebuddy-", suffix=".json")
            os.close(fd)
            settings_path = Path(raw_path)
            settings_path.write_text(
                json.dumps(_SETTINGS, separators=(",", ":")), encoding="utf-8"
            )
            fd, raw_stdout_path = tempfile.mkstemp(prefix="dsh-codebuddy-", suffix=".stdout")
            os.close(fd)
            stdout_path = Path(raw_stdout_path)
            fd, raw_stderr_path = tempfile.mkstemp(prefix="dsh-codebuddy-", suffix=".stderr")
            os.close(fd)
            stderr_path = Path(raw_stderr_path)
            stdout_file = stdout_path.open("wb")
            stderr_file = stderr_path.open("wb")
            process = subprocess.Popen(
                self._argv(prompt, settings_path),
                cwd=str(cwd),
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                env=self._environment(),
                shell=False,
            )
            stdout_file.close()
            stdout_file = None
            stderr_file.close()
            stderr_file = None
            self._process = process
            if (
                safe_event_sink is not None
                and safe_event_sink.enabled
                and safe_event_observer is not None
                and stdout_path is not None
            ):
                safe_event_observer_task = asyncio.create_task(
                    _observe_stdout_file(
                        stdout_path,
                        process,
                        safe_event_observer,
                        max_bytes=self.max_output_chars * 4 + 1,
                    )
                )
            wait_task = asyncio.create_task(asyncio.to_thread(process.wait))
            await asyncio.shield(wait_task)
            if safe_event_observer_task is not None:
                try:
                    await safe_event_observer_task
                except Exception:
                    if safe_event_sink is not None:
                        safe_event_sink.mark_incomplete()
            stdout = _read_bounded(stdout_path, self.max_output_chars * 4)
            stderr = _read_bounded(stderr_path, _DEFAULT_MAX_DIAGNOSTIC_CHARS)
            result = _normalize_output(
                stdout,
                stderr,
                process.returncode,
                max_output_chars=self.max_output_chars,
            )
        except asyncio.CancelledError:
            cancelled = True
            raise
        except (OSError, ValueError) as exc:
            result = PluginResult(
                success=False,
                error=f"CodeBuddy bounded invocation failed: {_bounded(str(exc))}",
            )
        finally:
            for stream in (stdout_file, stderr_file):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
            if process is not None and (cancelled or process.poll() is None):
                cleanup_error = await _terminate_process_tree(
                    process, self.cleanup_grace_seconds
                )
                if cleanup_error is not None:
                    cleanup_errors.append(cleanup_error)
            if cancelled and safe_event_sink is not None:
                safe_event_sink.mark_incomplete()
            if cancelled and wait_task is not None and not wait_task.done():
                try:
                    await asyncio.wait_for(
                        asyncio.shield(wait_task),
                        timeout=self.cleanup_grace_seconds,
                    )
                except (asyncio.TimeoutError, OSError, ValueError) as exc:
                    cleanup_errors.append(
                        f"CodeBuddy process wait did not settle: {type(exc).__name__}"
                    )

            if safe_event_observer_task is not None:
                try:
                    await asyncio.wait_for(
                        asyncio.shield(safe_event_observer_task),
                        timeout=self.cleanup_grace_seconds,
                    )
                except asyncio.TimeoutError:
                    await _cancel_task_and_wait(
                        safe_event_observer_task,
                        self.cleanup_grace_seconds,
                    )
                    if safe_event_sink is not None:
                        safe_event_sink.mark_incomplete()
                except Exception:
                    if safe_event_sink is not None:
                        safe_event_sink.mark_incomplete()
            if safe_event_sink is not None:
                try:
                    safe_event_sink.finish(
                        _safe_terminal_reason(
                            result,
                            process_started=process is not None,
                            cancelled=cancelled,
                        )
                    )
                except Exception:
                    # Safe observability must not prevent temp cleanup below.
                    pass

            if trace_path is not None:
                trace_stdout = b""
                trace_stderr = b""
                trace_capture_errors: list[str] = []
                if stdout_path is not None and stdout_path.exists():
                    try:
                        trace_stdout = _read_bounded(
                            stdout_path, self.max_output_chars * 4
                        )
                    except OSError as exc:
                        trace_capture_errors.append(
                            f"stdout capture read failed: {type(exc).__name__}: {exc}"
                        )
                if stderr_path is not None and stderr_path.exists():
                    try:
                        trace_stderr = _read_bounded(
                            stderr_path, _DEFAULT_MAX_DIAGNOSTIC_CHARS
                        )
                    except OSError as exc:
                        trace_capture_errors.append(
                            f"stderr capture read failed: {type(exc).__name__}: {exc}"
                        )
                parsed_output, parse_error = _trace_json_output(trace_stdout)
                observed_models = _trace_models(parsed_output)
                terminal_result = {
                    "exit_code": process.returncode if process is not None else None,
                    "signal": None,
                    "spawn_error": result.error
                    if process is None and result is not None
                    else None,
                    "cancelled": cancelled,
                }
                trace_payload = {
                    "schema_version": 1,
                    "trace_id": trace_id,
                    "started_at": trace_started_at,
                    "settled_at": _utc_timestamp(),
                    "pid": process.pid if process is not None else None,
                    "model": observed_models[0] if observed_models else None,
                    "observed_models": observed_models,
                    "task_id": ctx.task_id,
                    "workspace_id": ctx.workspace_id,
                    "cwd": str(cwd),
                    "goal": ctx.goal,
                    "effective_prompt": prompt,
                    "allow_workspace_write": ctx.allow_workspace_write,
                    "argv": self._argv(prompt, settings_path)
                    if settings_path is not None
                    else None,
                    "settings": _SETTINGS,
                    "temporary_artifacts": {
                        "settings": str(settings_path) if settings_path else None,
                        "stdout": str(stdout_path) if stdout_path else None,
                        "stderr": str(stderr_path) if stderr_path else None,
                    },
                    "turn_sequence": _trace_turn_sequence(parsed_output),
                    "tool_events": _trace_tool_events(parsed_output),
                    "worker_result": (
                        parsed_output[-1]
                        if isinstance(parsed_output, list) and parsed_output
                        else None
                    ),
                    "stdout": trace_stdout.decode("utf-8", errors="replace"),
                    "stdout_base64": base64.b64encode(trace_stdout).decode("ascii"),
                    "stderr": trace_stderr.decode("utf-8", errors="replace"),
                    "stderr_base64": base64.b64encode(trace_stderr).decode("ascii"),
                    "parse_error": parse_error,
                    "capture_errors": trace_capture_errors,
                    "terminal": terminal_result,
                    "plugin_result": _trace_plugin_result(result),
                    "cleanup": {
                        "trace_written_before_temp_cleanup": True,
                        "temporary_files_deleted_after_trace": True,
                    },
                }
                try:
                    trace_path.write_text(
                        json.dumps(trace_payload, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                except (OSError, TypeError, ValueError) as exc:
                    trace_error = (
                        f"{_QUALIFICATION_OBSERVABILITY_FAILURE}: "
                        f"cannot persist trace: {type(exc).__name__}: {exc}"
                    )
                if trace_capture_errors and trace_error is None:
                    trace_error = (
                        f"{_QUALIFICATION_OBSERVABILITY_FAILURE}: "
                        + "; ".join(trace_capture_errors)
                    )
            for artifact_name, artifact_path in (
                ("settings", settings_path),
                ("stdout", stdout_path),
                ("stderr", stderr_path),
            ):
                if artifact_path is not None:
                    try:
                        artifact_path.unlink(missing_ok=True)
                    except OSError as exc:
                        cleanup_errors.append(
                            f"CodeBuddy {artifact_name} cleanup failed: {type(exc).__name__}"
                        )
            self._process = None

            if trace_error is not None and not cancelled:
                cleanup_errors.append(trace_error)

            if cleanup_errors:
                cleanup_diagnostic = "; ".join(cleanup_errors)
                if cancelled:
                    raise RuntimeError(cleanup_diagnostic)
                if result is None:
                    result = PluginResult(success=False, error=cleanup_diagnostic)
                else:
                    result = replace(
                        result,
                        success=False,
                        error=(
                            trace_error
                            if trace_error is not None
                            else result.error or cleanup_diagnostic
                        ),
                        cleanup_error=cleanup_diagnostic,
                    )

        return result or PluginResult(
            success=False, error="CodeBuddy invocation produced no result"
        )
