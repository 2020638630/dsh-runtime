"""Minimal logical workspace identity to local cwd mapping."""

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class WorkspaceResolutionError(ValueError):
    """Raised when a logical workspace cannot be resolved to a valid cwd."""


@dataclass(frozen=True)
class Workspace:
    workspace_id: str = "dsh.main"
    cwd: Path | None = None


class WorkspaceManager:
    """Resolve the current local logical workspace without changing its identity."""

    def __init__(
        self,
        workspaces: Mapping[str, Workspace] | None = None,
        default_cwd: str | Path | None = None,
    ) -> None:
        self._default_cwd = Path(default_cwd or Path.cwd()).resolve()
        self._workspaces = dict(workspaces or {})
        self._workspaces.setdefault(
            "dsh.main",
            Workspace("dsh.main", self._default_cwd),
        )

    def resolve_cwd(self, workspace_id: str) -> Path:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise WorkspaceResolutionError(
                f"workspace resolution failed: unknown workspace {workspace_id!r}"
            )
        cwd = (workspace.cwd or self._default_cwd).resolve()
        if not cwd.exists() or not cwd.is_dir():
            raise WorkspaceResolutionError(
                f"workspace resolution failed: cwd is not a directory for {workspace_id!r}"
            )
        return cwd
