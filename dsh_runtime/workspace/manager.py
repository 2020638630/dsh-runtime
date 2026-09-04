"""Minimal logical workspace context."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Workspace:
    workspace_id: str = "dsh.main"
