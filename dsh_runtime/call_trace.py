"""Privacy-preserving, append-only lifecycle records for Runtime calls."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any


CALL_TRACE_PATH_ENV = "DSH_RUNTIME_CALL_TRACE_PATH"
_SCHEMA_VERSION = "1"
_CALL_ID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z"
)
_HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_TYPE_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,79}\Z")
_TASK_STATUSES = {
    "pending",
    "running",
    "completed",
    "failed",
    "timed_out",
    "max_iterations",
}
_ERROR_CODES = {
    "stdout_invalid_utf8",
    "stderr_invalid_utf8",
    "nonzero_exit",
    "unexpected_stderr",
    "invalid_terminal_record_count",
    "malformed_terminal_json",
    "terminal_response_not_object",
    "process_boundary_exception",
    "invalid_process_output_type",
    "adapter_processing_exception",
}
_STARTED_FIELDS = {
    "schema_version",
    "event",
    "call_id",
    "timestamp",
    "state",
    "invocation_count",
}
_TERMINAL_FIELDS = {
    "schema_version",
    "event",
    "call_id",
    "timestamp",
    "state",
    "duration_ms",
    "runtime_exit_code",
    "stdout_bytes",
    "stdout_sha256",
    "stderr_bytes",
    "stderr_sha256",
    "task_status",
    "result_sha256",
    "error_code",
    "error_type",
}


class CallTraceError(Exception):
    """A configured call-trace path or append operation failed."""


def resolve_call_trace_path() -> Path:
    """Return the configured path or the user's local application state path."""

    configured = os.environ.get(CALL_TRACE_PATH_ENV)
    if configured:
        path = Path(configured)
    elif os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        root = (
            Path(local_app_data)
            if local_app_data
            else Path.home() / "AppData" / "Local"
        )
        path = root / "DSH-Runtime" / "calls.jsonl"
    else:
        state_home = os.environ.get("XDG_STATE_HOME")
        root = Path(state_home) if state_home else Path.home() / ".local" / "state"
        path = root / "dsh-runtime" / "calls.jsonl"

    if not path.is_absolute():
        raise CallTraceError(f"{CALL_TRACE_PATH_ENV} must be an absolute path")
    return path


def _serialize_record(record: dict[str, Any]) -> bytes:
    if not isinstance(record, dict):
        raise CallTraceError("call trace record must be an object")
    event = record.get("event")
    expected_fields = (
        _STARTED_FIELDS if event == "call_started" else _TERMINAL_FIELDS
    )
    if (
        set(record) != expected_fields
        or record.get("schema_version") != _SCHEMA_VERSION
    ):
        raise CallTraceError("call trace record has an invalid schema")
    call_id = record.get("call_id")
    timestamp = record.get("timestamp")
    if not isinstance(call_id, str) or _CALL_ID_PATTERN.fullmatch(call_id) is None:
        raise CallTraceError("call trace record has an invalid call identifier")
    if (
        not isinstance(timestamp, str)
        or len(timestamp) > 40
        or not timestamp.endswith("Z")
        or not timestamp[0:4].isdigit()
    ):
        raise CallTraceError("call trace record has an invalid timestamp")
    if event == "call_started":
        invocation_count = record.get("invocation_count")
        if (
            record.get("state") != "started"
            or isinstance(invocation_count, bool)
            or invocation_count != 1
        ):
            raise CallTraceError("call start record has an invalid state")
    elif event == "call_terminal":
        state = record.get("state")
        if not isinstance(state, str) or state not in {
            "returned",
            "process_error",
            "transport_error",
        }:
            raise CallTraceError("call terminal record has an invalid state")
        for name in ("duration_ms", "stdout_bytes", "stderr_bytes"):
            value = record.get(name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise CallTraceError("call terminal record has invalid byte or time data")
        returncode = record.get("runtime_exit_code")
        if returncode is not None and (
            isinstance(returncode, bool) or not isinstance(returncode, int)
        ):
            raise CallTraceError("call terminal record has an invalid exit code")
        for name in ("stdout_sha256", "stderr_sha256"):
            value = record.get(name)
            if not isinstance(value, str) or _HASH_PATTERN.fullmatch(value) is None:
                raise CallTraceError("call terminal record has an invalid output hash")
        result_hash = record.get("result_sha256")
        if result_hash is not None and (
            not isinstance(result_hash, str)
            or _HASH_PATTERN.fullmatch(result_hash) is None
        ):
            raise CallTraceError("call terminal record has an invalid result hash")
        task_status = record.get("task_status")
        if task_status is not None and (
            not isinstance(task_status, str) or task_status not in _TASK_STATUSES
        ):
            raise CallTraceError("call terminal record has an invalid task status")
        error_code = record.get("error_code")
        if error_code is not None and (
            not isinstance(error_code, str) or error_code not in _ERROR_CODES
        ):
            raise CallTraceError("call terminal record has an invalid error code")
        error_type = record.get("error_type")
        if error_type is not None and (
            not isinstance(error_type, str) or _TYPE_PATTERN.fullmatch(error_type) is None
        ):
            raise CallTraceError("call terminal record has an invalid error type")
    else:
        raise CallTraceError("call trace record has an unknown event")

    try:
        payload = json.dumps(
            record,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise CallTraceError("call trace record could not be serialized") from exc
    return payload + b"\n"


def _write_all(file_descriptor: int, payload: bytes) -> None:
    remaining = memoryview(payload)
    while remaining:
        written = os.write(file_descriptor, remaining)
        if written <= 0:
            raise OSError("call trace write made no forward progress")
        remaining = remaining[written:]


def append_call_trace(path: Path, record: dict[str, Any]) -> None:
    """Append and fsync one schema-limited JSONL record at the trusted path."""

    if not isinstance(path, Path) or not path.is_absolute():
        raise CallTraceError("call trace path must be an absolute Path")
    payload = _serialize_record(record)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_APPEND | os.O_CREAT | os.O_RDWR
        flags |= getattr(os, "O_BINARY", 0)
        file_descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise CallTraceError("call trace file could not be opened") from exc

    try:
        size = os.lseek(file_descriptor, 0, os.SEEK_END)
        if size:
            os.lseek(file_descriptor, -1, os.SEEK_END)
            if os.read(file_descriptor, 1) != b"\n":
                raise CallTraceError("call trace has an incomplete final line")
        _write_all(file_descriptor, payload)
        os.fsync(file_descriptor)
    except OSError as exc:
        raise CallTraceError("call trace record could not be persisted") from exc
    finally:
        os.close(file_descriptor)
