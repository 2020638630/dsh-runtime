"""Desktop owner-only administration for the existing API connection catalog."""

from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from dsh_runtime.api_agent_connections import (
    Connection, _ENDPOINTS, _MAX_FILE_BYTES, _unique_fields, catalog_path,
    decode_catalog, read_catalog_bytes, validate_connection, validate_reference,
)


_MAX_REQUEST_BYTES = 4096
_MAX_PROBE_BYTES = 262_144
_MAX_MODEL_BYTES = 4_194_304
_MAX_MODELS = 512
_PROBES = {"openrouter": "/key", "siliconflow": "/models?sub_type=chat"}
_MODEL_PATHS = {**_PROBES, "openrouter": "/models"}
_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}\Z")


class Conflict(Exception):
    pass


class InvalidDraft(Exception):
    pass


def _read(path: Path) -> bytes | None:
    try:
        return read_catalog_bytes(catalog_path(path, allow_missing=True))
    except FileNotFoundError:
        return None


def _revision(raw: bytes | None, secret: bytes) -> str:
    return hmac.digest(secret, b"\x00" if raw is None else b"\x01" + raw, hashlib.sha256).hex()


@contextmanager
def _catalog_lock(path: Path):
    lock = catalog_path(path.with_name(f".{path.name}.dsh-lock"), allow_missing=True)
    with lock.open("a+b") as file:
        info = os.fstat(file.fileno())
        current = lock.lstat()
        if (not stat.S_ISREG(current.st_mode) or info.st_nlink != 1 or info.st_size != 0
            or not os.path.samestat(info, current)):
            raise ValueError("invalid catalog lock")
        try:
            if os.name == "nt":
                import msvcrt
                file.seek(0)
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise Conflict from None
        yield
        # Closing the handle also releases the lock on cancellation or crash.


def _restrict_windows_file(path: Path) -> None:
    system = Path(os.environ["SystemRoot"]) / "System32"
    identity = subprocess.run(
        [str(system / "whoami.exe"), "/user", "/fo", "csv", "/nh"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3, check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    row = next(csv.reader(identity.stdout.decode("ascii", errors="replace").strip().splitlines()), [])
    if len(row) != 2 or not re.fullmatch(r"S-1-(?:\d+-)*\d+", row[1]):
        raise ValueError("cannot resolve the current Windows user")
    subprocess.run(
        [str(system / "icacls.exe"), str(path), "/inheritance:r", "/grant:r", f"*{row[1]}:(F)"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3, check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def _replace(path: Path, raw: bytes | None, entries: dict[str, Connection]) -> bytes:
    document = {"schema_version": 1, "connections": {
        name: {"provider": entry.provider, "base_url": entry.base_url, "api_key": entry.api_key}
        for name, entry in entries.items()
    }}
    payload = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(payload) > _MAX_FILE_BYTES:
        raise ValueError("catalog exceeds its size bound")
    fd, filename = tempfile.mkstemp(prefix=".dsh-api-", suffix=".tmp", dir=path.parent)
    staging = Path(filename)
    try:
        with os.fdopen(fd, "wb") as file:
            if os.name == "nt":
                _restrict_windows_file(staging)
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        if _read(path) != raw:
            raise Conflict
        os.replace(staging, path)
        return payload
    finally:
        staging.unlink(missing_ok=True)


def _public_catalog(raw: bytes | None, secret: bytes, entries: dict[str, Connection]) -> dict:
    return {"status": "ok", "revision": _revision(raw, secret),
            "connections": [{"reference": reference, "provider": item.provider, "keySet": True}
                            for reference, item in sorted(entries.items())]}


def _draft(command: dict, entries: dict[str, Connection]) -> tuple[str, Connection]:
    reference = validate_reference(command.get("reference"))
    provider = command.get("provider")
    if not isinstance(provider, str) or provider not in _ENDPOINTS:
        raise ValueError("unknown provider")
    previous = entries.get(reference)
    if previous and previous.provider != provider:
        raise ValueError("cannot change the provider of an existing reference")
    key = command.get("key")
    if key is None and previous:
        return reference, previous
    if not isinstance(key, str) or not re.fullmatch(r"[\x21-\x7e]{8,512}", key):
        raise ValueError("invalid new key")
    return reference, validate_connection({"provider": provider, "base_url": _ENDPOINTS[provider], "api_key": key})


def _provider_json(connection: Connection, suffix: str, limit: int, transport: Any) -> tuple[str, dict]:
    if _ENDPOINTS.get(connection.provider) != connection.base_url:
        return "invalid", {}
    try:
        import httpx
    except ImportError:
        return "client_unavailable", {}
    try:
        with httpx.Client(timeout=6, follow_redirects=False, trust_env=False, transport=transport) as client:
            with client.stream("GET", connection.base_url + suffix, headers={
                "Authorization": "Bearer " + connection.api_key, "Accept-Encoding": "identity",
            }) as response:
                if response.status_code in (401, 403):
                    return "auth_rejected", {}
                if response.status_code == 429:
                    return "rate_limited", {}
                if 300 <= response.status_code < 400:
                    return "redirect_rejected", {}
                if response.status_code != 200:
                    return "http_error", {}
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    return "invalid_response", {}
                raw = bytearray()
                for chunk in response.iter_bytes():
                    if len(raw) + len(chunk) > limit:
                        return "invalid_response", {}
                    raw.extend(chunk)
        document = json.loads(raw)
        return ("ok", document) if isinstance(document, dict) else ("invalid_response", {})
    except httpx.TimeoutException:
        return "timeout", {}
    except httpx.HTTPError:
        return "network_error", {}
    except (TypeError, ValueError, RecursionError):
        return "invalid_response", {}


def probe_connection(connection: Connection, *, transport: Any = None) -> str:
    status, document = _provider_json(connection, _PROBES.get(connection.provider, ""),
                                      _MAX_PROBE_BYTES, transport)
    if status != "ok":
        return status
    data = document.get("data")
    if connection.provider == "openrouter" and isinstance(data, dict) and isinstance(data.get("label"), str):
        return "authenticated"
    if connection.provider == "siliconflow" and document.get("object") == "list" and isinstance(data, list):
        return "model_catalog_readable"
    return "invalid_response"


def provider_models(connection: Connection, *, transport: Any = None) -> dict:
    status, document = _provider_json(connection, _MODEL_PATHS.get(connection.provider, ""),
                                      _MAX_MODEL_BYTES, transport)
    if status != "ok":
        return {"status": status}
    rows = document.get("data")
    if not isinstance(rows, list) or (connection.provider == "siliconflow" and document.get("object") != "list"):
        return {"status": "invalid_response"}
    models: set[str] = set()
    for row in rows:
        model = row.get("id") if isinstance(row, dict) else None
        if not isinstance(model, str) or not _MODEL_ID.fullmatch(model) or connection.api_key in model:
            continue
        # The Runtime's API Agent calls Chat Completions. Exclude explicitly incompatible models.
        if connection.provider == "openrouter":
            endpoints = row.get("endpoints")
            if isinstance(endpoints, list) and "/api/v1/chat/completions" not in endpoints:
                continue
        models.add(model)
        if len(models) > _MAX_MODELS:
            break
    return {"status": "ok", "models": sorted(models)[:_MAX_MODELS], "truncated": len(models) > _MAX_MODELS}


def handle(path: Path, command: dict, secret: bytes) -> dict:
    action = command.get("action")
    if action not in ("list", "save", "test", "models"):
        return {"status": "invalid"}
    expected = {"action"}
    if action != "list":
        expected |= {"reference", "provider", "revision"}
    if action in ("save", "test"):
        expected.add("key")
    if command.keys() != expected:
        return {"status": "invalid"}
    try:
        path = catalog_path(path, allow_missing=True)
        if path.is_relative_to(Path.cwd().resolve()):
            return {"status": "unavailable"}
        if action == "save":
            with _catalog_lock(path):
                raw = _read(path)
                entries = {} if raw is None else decode_catalog(raw)
                reference, candidate = _checked_draft(command, raw, entries, secret)
                if entries.get(reference) != candidate:
                    entries[reference] = candidate
                    raw = _replace(path, raw, entries)
                return _public_catalog(raw, secret, entries)
        raw = _read(path)
        entries = {} if raw is None else decode_catalog(raw)
        if action == "list":
            return _public_catalog(raw, secret, entries)
        if action == "models":
            _check_revision(command, raw, secret)
            reference = validate_reference(command["reference"])
            candidate = entries.get(reference)
            if candidate is None or candidate.provider != command["provider"]:
                return {"status": "missing_connection"}
            return provider_models(candidate)
        _, candidate = _checked_draft(command, raw, entries, secret)
        return {"status": probe_connection(candidate)}
    except Conflict:
        return {"status": "conflict"}
    except InvalidDraft:
        return {"status": "invalid"}
    except (KeyError, OSError, ValueError, subprocess.SubprocessError):
        return {"status": "unavailable"}


def _checked_draft(command: dict, raw: bytes | None, entries: dict[str, Connection],
                   secret: bytes) -> tuple[str, Connection]:
    _check_revision(command, raw, secret)
    try:
        return _draft(command, entries)
    except ValueError:
        raise InvalidDraft from None


def _check_revision(command: dict, raw: bytes | None, secret: bytes) -> None:
    revision = command.get("revision")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{64}", revision):
        raise InvalidDraft
    if not hmac.compare_digest(revision, _revision(raw, secret)):
        raise Conflict


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("catalog", type=Path)
    path = parser.parse_args().catalog
    try:
        raw = sys.stdin.buffer.read(_MAX_REQUEST_BYTES + 1)
        envelope = json.loads(raw, object_pairs_hook=_unique_fields) if len(raw) <= _MAX_REQUEST_BYTES else None
        if not isinstance(envelope, dict) or set(envelope) != {"request", "secret"}:
            raise ValueError
        secret = bytes.fromhex(envelope["secret"])
        if len(secret) != 32 or not isinstance(envelope["request"], dict):
            raise ValueError
        result = handle(path, envelope["request"], secret)
    except (TypeError, ValueError):
        result = {"status": "invalid"}
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
