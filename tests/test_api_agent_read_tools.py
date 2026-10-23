"""No-network checks for the explicit-file API inspector boundary."""

import asyncio
import os
import subprocess
from pathlib import Path

import pytest

from dsh_runtime.api_agent_read_tools import WorkspaceReadBroker


def call(broker, name, **arguments):
    return asyncio.run(broker.execute(name, arguments))


def test_only_explicit_read_is_exposed_and_credentials_are_excluded(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_bytes(b"hello\nworld\n")
    (workspace / ".env").write_text("API_KEY=secret", encoding="utf-8")
    (workspace / "credentials.json").write_text("secret", encoding="utf-8")
    broker = WorkspaceReadBroker(workspace)
    assert call(broker, "read_file", path="README.md") == "hello\nworld\n"
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
    assert call(broker, "read_file", path="README.md") == "isolated trial\n"
    with pytest.raises(ValueError):
        call(broker, "read_file", path=".git/config")


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
    assert call(broker, "read_file", path="README.md") == "bounded read"
