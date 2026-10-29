"""No-network checks for the explicit-file API inspector boundary."""

import asyncio
from hashlib import sha256
import json
import os
import subprocess
from pathlib import Path

import pytest

from dsh_runtime.api_agent_read_tools import WorkspaceReadBroker


def call(broker, name, **arguments):
    return asyncio.run(broker.execute(name, arguments))


def read_content(broker, path):
    return json.loads(call(broker, "read_file", path=path))


def test_only_explicit_read_is_exposed_and_credentials_are_excluded(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_bytes(b"hello\nworld\n")
    (workspace / ".env").write_text("API_KEY=secret", encoding="utf-8")
    (workspace / "credentials.json").write_text("secret", encoding="utf-8")
    broker = WorkspaceReadBroker(workspace)
    assert read_content(broker, "README.md") == {
        "schema_version": 1,
        "byte_length": 12,
        "sha256": sha256(b"hello\nworld\n").hexdigest(),
        "content": "hello\nworld\n",
    }
    for tool, arguments in (("list_files", {"path": "."}),
                            ("search_text", {"path": ".", "query": "world"})):
        with pytest.raises(ValueError, match="tool is unsupported"):
            call(broker, tool, **arguments)
    for path in ("../outside.txt", ".env", "credentials.json"):
        with pytest.raises(ValueError):
            call(broker, "read_file", path=path)
    with pytest.raises(ValueError, match="tool is unsupported"):
        call(broker, "apply_patch", path="README.md")


def test_linked_path_is_rejected(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = workspace / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation unavailable")
    broker = WorkspaceReadBroker(workspace)
    with pytest.raises(ValueError, match="linked paths"):
        call(broker, "read_file", path="link.txt")


@pytest.mark.skipif(os.name != "nt" or not hasattr(Path("."), "is_junction"),
                    reason="Windows junction support required")
def test_windows_junction_is_not_traversed(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "README.md").write_text("outside", encoding="utf-8")
    link = workspace / "linked"
    created = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                             capture_output=True, text=True, check=False)
    if created.returncode != 0:
        pytest.skip("junction creation unavailable")
    broker = WorkspaceReadBroker(workspace)
    with pytest.raises(ValueError, match="linked paths"):
        call(broker, "read_file", path="linked/README.md")


def test_read_file_on_fresh_isolated_git_repository(tmp_path):
    workspace = tmp_path / "trial-repo"
    workspace.mkdir()
    subprocess.run(["git", "init", "-q", str(workspace)], check=True)
    (workspace / "README.md").write_bytes(b"isolated trial\n")
    broker = WorkspaceReadBroker(workspace)
    assert read_content(broker, "README.md")["content"] == "isolated trial\n"
    with pytest.raises(ValueError):
        call(broker, "read_file", path=".git/config")


def test_missing_relative_file_has_bounded_error(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    broker = WorkspaceReadBroker(workspace)
    with pytest.raises(ValueError, match="^path is unavailable$") as failure:
        call(broker, "read_file", path="missing-private-name.txt")
    assert "missing-private-name" not in str(failure.value)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction race probe")
def test_file_replaced_by_junction_after_path_check_is_rejected(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    slot = workspace / "slot"
    slot.mkdir()
    (slot / "README.md").write_text("safe", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "README.md").write_text("outside-private-marker", encoding="utf-8")
    broker = WorkspaceReadBroker(workspace)
    original_path = broker._path

    def swap_after_check(relative, *, directory=None):
        checked = original_path(relative, directory=directory)
        slot.rename(workspace / "moved-slot")
        created = subprocess.run(["cmd", "/c", "mklink", "/J", str(slot), str(outside)],
                                 capture_output=True, text=True, check=False)
        if created.returncode != 0:
            pytest.skip("junction creation unavailable")
        return checked

    monkeypatch.setattr(broker, "_path", swap_after_check)
    with pytest.raises(ValueError, match="opened file leaves workspace"):
        call(broker, "read_file", path="slot/README.md")
    assert (outside / "README.md").read_text(encoding="utf-8") == "outside-private-marker"


def test_read_file_assembles_short_os_reads(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("bounded read", encoding="utf-8")
    broker = WorkspaceReadBroker(workspace)
    original_read = os.read

    def short_read(fd, count):
        return original_read(fd, min(count, 2))

    monkeypatch.setattr(os, "read", short_read)
    assert read_content(broker, "README.md")["content"] == "bounded read"


def test_read_file_reports_verified_bytes_for_utf8_and_newline(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    data = "你好\n".encode("utf-8")
    (workspace / "note.txt").write_bytes(data)
    response = read_content(WorkspaceReadBroker(workspace), "note.txt")
    assert response["content"] == "你好\n"
    assert response["byte_length"] == len(data)
    assert response["sha256"] == sha256(data).hexdigest()


def test_read_file_rejects_excessive_json_escape_expansion(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "controls.txt").write_bytes(b"\x01" * 20_000)
    with pytest.raises(ValueError, match="response is too large"):
        read_content(WorkspaceReadBroker(workspace), "controls.txt")


def test_hardlink_to_outside_file_is_rejected_before_read(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "private.txt"
    outside.write_bytes(b"SYNTHETIC_PRIVATE_MARKER")
    os.link(outside, workspace / "README.md")
    reads = []
    original_read = os.read

    def observe_read(fd, count):
        reads.append(fd)
        return original_read(fd, count)

    monkeypatch.setattr(os, "read", observe_read)
    with pytest.raises(ValueError):
        read_content(WorkspaceReadBroker(workspace), "README.md")
    assert reads == []


@pytest.mark.skipif(os.name != "nt", reason="NTFS alternate data streams")
def test_sensitive_file_named_stream_is_rejected(tmp_path):
    (tmp_path / ".env").write_bytes(b"SYNTHETIC_MAIN_STREAM")
    Path(str(tmp_path / ".env") + ":review").write_bytes(b"SYNTHETIC_PRIVATE_STREAM")
    with pytest.raises(ValueError):
        read_content(WorkspaceReadBroker(tmp_path), ".env:review")
