import asyncio
import os
import subprocess
from pathlib import Path

import pytest

from dsh_runtime.api_agent_read_tools import WorkspaceReadBroker


def call(broker, name, **arguments):
    return asyncio.run(broker.execute(name, arguments))


def test_read_tools_are_bounded_to_workspace_and_exclude_credentials(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_bytes(b"hello\nworld\n")
    (workspace / ".env").write_text("API_KEY=secret", encoding="utf-8")
    (workspace / "credentials.json").write_text("secret", encoding="utf-8")
    broker = WorkspaceReadBroker(workspace)
    assert call(broker, "list_files", path=".") == "README.md"
    assert call(broker, "read_file", path="README.md") == "hello\nworld\n"
    assert call(broker, "search_text", path=".", query="world") == "README.md:2:world"
    with pytest.raises(ValueError):
        call(broker, "read_file", path="../outside.txt")
    with pytest.raises(ValueError):
        call(broker, "read_file", path=".env")
    with pytest.raises(ValueError):
        call(broker, "read_file", path="credentials.json")
    with pytest.raises(ValueError):
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
    assert call(broker, "list_files", path=".") == ""
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
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
        capture_output=True, text=True, check=False,
    )
    if created.returncode != 0:
        pytest.skip("junction creation unavailable")
    assert link.is_junction()
    broker = WorkspaceReadBroker(workspace)
    assert call(broker, "list_files", path=".") == ""
    with pytest.raises(ValueError, match="linked paths"):
        call(broker, "read_file", path="linked/README.md")


def test_read_tools_on_fresh_isolated_git_repository(tmp_path):
    workspace = tmp_path / "trial-repo"
    workspace.mkdir()
    subprocess.run(["git", "init", "-q", str(workspace)], check=True)
    (workspace / "README.md").write_bytes(b"isolated trial\n")
    broker = WorkspaceReadBroker(workspace)
    assert call(broker, "list_files", path=".") == "README.md"
    assert call(broker, "read_file", path="README.md") == "isolated trial\n"
    with pytest.raises(ValueError):
        call(broker, "read_file", path=".git/config")
