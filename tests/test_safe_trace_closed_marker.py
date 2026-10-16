"""Closure evidence for the opt-in visualization run namespace."""

import json
import os
from pathlib import Path

import pytest

from dsh_runtime.plugins.codebuddy import (
    CodeBuddyPlugin,
    _SafeCodeBuddyEventSink,
    _safe_trace_io_path,
)


RUN_ID = "dsh-runtime-7a8b9c0d-1e2f-4a3b-8c5d-6e7f8a9b0c1d"


def test_closed_marker_binds_run_and_final_trace_size(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DSH_RUNTIME_RUN_ID", RUN_ID)
    sink = _SafeCodeBuddyEventSink(tmp_path.resolve())
    marker = sink.path.with_name(sink.path.name + ".closed")
    assert not marker.exists()

    sink.finish("completed")

    assert marker.exists()
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload == {
        "schema_version": 1,
        "run_id": RUN_ID,
        "trace_id": sink.trace_id,
        "final_bytes": sink.path.stat().st_size,
    }
    assert sink.path.read_bytes().endswith(b"\n")


def test_no_marker_without_visualization_run_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DSH_RUNTIME_RUN_ID", raising=False)
    sink = _SafeCodeBuddyEventSink(tmp_path.resolve())
    sink.finish("completed")
    assert not sink.path.with_name(sink.path.name + ".closed").exists()


def test_invalid_visualization_run_id_rejected_before_trace_creation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DSH_RUNTIME_RUN_ID", "d2-business-123")
    with pytest.raises(ValueError, match="dsh-runtime UUID namespace"):
        _SafeCodeBuddyEventSink(tmp_path.resolve())
    assert list(tmp_path.iterdir()) == []


def test_close_failure_does_not_publish_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DSH_RUNTIME_RUN_ID", RUN_ID)
    sink = _SafeCodeBuddyEventSink(tmp_path.resolve())
    stream = sink._stream
    assert stream is not None

    class FailingClose:
        def write(self, value: str) -> int:
            return stream.write(value)

        def flush(self) -> None:
            stream.flush()

        def close(self) -> None:
            stream.close()
            raise OSError("close failed")

    sink._stream = FailingClose()
    sink.finish("completed")

    assert sink.incomplete is True
    assert not sink.path.with_name(sink.path.name + ".closed").exists()


def test_visualization_run_id_is_not_forwarded_to_native_worker(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSH_RUNTIME_RUN_ID", RUN_ID)
    plugin = CodeBuddyPlugin(command=["codebuddy"])
    assert "DSH_RUNTIME_RUN_ID" not in plugin._environment()


@pytest.mark.skipif(os.name != "nt", reason="Windows extended path behavior")
def test_closed_marker_survives_long_windows_evidence_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DSH_RUNTIME_RUN_ID", RUN_ID)
    filler = "x" * max(1, 220 - len(str(tmp_path)) - 1)
    directory = tmp_path / filler
    sink = _SafeCodeBuddyEventSink(directory)
    assert len(str(sink.path)) > 260
    assert sink.enabled is True

    sink.finish("completed")

    trace = _safe_trace_io_path(sink.path)
    marker = _safe_trace_io_path(sink.path.with_name(sink.path.name + ".closed"))
    assert marker.exists()
    assert json.loads(marker.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "run_id": RUN_ID,
        "trace_id": sink.trace_id,
        "final_bytes": trace.stat().st_size,
    }
