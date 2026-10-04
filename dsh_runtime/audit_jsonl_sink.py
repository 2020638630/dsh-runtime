"""Single-writer append-only JSONL adapter for pre-start audit records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
import json
import math
import os
from os import PathLike
from pathlib import Path
from typing import Any

from .audit_persistence import AuditPersistenceOutcome
from .pre_start_audit import PreStartAuditRecord


_STORAGE_SCHEMA_VERSION = "1"


class AuditJsonlAdapterError(Exception):
    """Base failure raised by the append-only JSONL adapter."""


class AuditJsonlPathValidationError(AuditJsonlAdapterError):
    """The configured trusted audit path is invalid or unavailable."""


class AuditRecordSerializationError(AuditJsonlAdapterError):
    """An audit record could not be serialized deterministically."""


class IncompleteAuditTailError(AuditJsonlAdapterError):
    """An existing non-empty audit file does not end with LF."""


def _to_json_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise AuditRecordSerializationError(
                "audit records cannot contain non-finite numbers"
            )
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _to_json_value(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise AuditRecordSerializationError(
                "audit record mappings must contain only string keys"
            )
        return {key: _to_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        if any(not isinstance(item, str) for item in value):
            raise AuditRecordSerializationError(
                "audit record sets must contain only strings"
            )
        return sorted(value)
    raise AuditRecordSerializationError(
        f"unsupported audit record value: {type(value).__name__}"
    )


def serialize_pre_start_audit_record(record: PreStartAuditRecord) -> bytes:
    """Return canonical UTF-8 JSONL bytes for one existing logical record."""

    if not isinstance(record, PreStartAuditRecord):
        raise AuditRecordSerializationError(
            "record must be a PreStartAuditRecord"
        )
    envelope = {
        "storage_schema_version": _STORAGE_SCHEMA_VERSION,
        "record": _to_json_value(record),
    }
    try:
        document = json.dumps(
            envelope,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise AuditRecordSerializationError(
            "audit record could not be serialized"
        ) from exc
    return document.encode("utf-8") + b"\n"


def _write_all(file_descriptor: int, payload: bytes) -> None:
    remaining = memoryview(payload)
    while remaining:
        written = os.write(file_descriptor, remaining)
        if written <= 0:
            raise OSError("audit write made no forward progress")
        remaining = remaining[written:]


@dataclass(frozen=True)
class AppendOnlyJsonlAuditSink:
    """Append and fsync records at one trusted path; single-writer use only."""

    audit_path: str | PathLike[str]

    def __post_init__(self) -> None:
        if not isinstance(self.audit_path, (str, os.PathLike)):
            raise AuditJsonlPathValidationError(
                "audit_path must be a filesystem path"
            )
        try:
            path = Path(self.audit_path)
        except TypeError as exc:
            raise AuditJsonlPathValidationError(
                "audit_path must be a text filesystem path"
            ) from exc
        if not path.is_absolute():
            raise AuditJsonlPathValidationError(
                "audit_path must be absolute"
            )
        object.__setattr__(self, "audit_path", path)

    def persist(
        self,
        record: PreStartAuditRecord,
    ) -> AuditPersistenceOutcome:
        """Append exactly one complete line and fsync it, or raise failure."""

        path = Path(self.audit_path)
        parent = path.parent
        if not parent.exists() or not parent.is_dir():
            raise AuditJsonlPathValidationError(
                "audit_path parent must already exist as a directory"
            )
        if path.exists() and not path.is_file():
            raise AuditJsonlPathValidationError(
                "audit_path must identify a file"
            )

        payload = serialize_pre_start_audit_record(record)
        flags = os.O_APPEND | os.O_CREAT | os.O_RDWR
        flags |= getattr(os, "O_BINARY", 0)
        file_descriptor = os.open(path, flags, 0o600)
        try:
            size = os.lseek(file_descriptor, 0, os.SEEK_END)
            if size:
                os.lseek(file_descriptor, -1, os.SEEK_END)
                if os.read(file_descriptor, 1) != b"\n":
                    raise IncompleteAuditTailError(
                        "existing audit file has an incomplete final line"
                    )
            _write_all(file_descriptor, payload)
            os.fsync(file_descriptor)
        finally:
            os.close(file_descriptor)
        return AuditPersistenceOutcome.SUCCESS
