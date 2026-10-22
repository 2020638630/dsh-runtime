"""Bounded read-only workspace tools for the API agent prototype."""

from __future__ import annotations

from pathlib import Path
from typing import Any


MAX_READ_BYTES = 32_768
MAX_SEARCH_FILES = 100
MAX_SEARCH_MATCHES = 30
MAX_LIST_ENTRIES = 100
_BLOCKED_PARTS = frozenset({
    ".git", ".codex", ".ssh", "node_modules", ".npmrc", ".pypirc",
    "credentials.json", "connections.local.json", "id_rsa", "id_ed25519",
})


def _sensitive(part: str) -> bool:
    lower = part.lower()
    return (
        lower in _BLOCKED_PARTS or lower == ".env" or lower.startswith(".env.")
        or lower.endswith((".pem", ".key", ".p12", ".pfx"))
        or "secret" in lower or "credential" in lower
    )


def _linked(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


class WorkspaceReadBroker:
    def __init__(self, workspace: Path) -> None:
        root = workspace.resolve(strict=True)
        if not root.is_dir():
            raise ValueError("workspace must be a directory")
        self.root = root

    def _path(self, relative: str, *, directory: bool | None = None) -> Path:
        if not isinstance(relative, str) or not relative or len(relative) > 512:
            raise ValueError("path is invalid")
        path = Path(relative)
        if path.is_absolute() or any(part in {"..", ""} or _sensitive(part) for part in path.parts):
            raise ValueError("path is outside allowed workspace scope")
        candidate = self.root
        for part in path.parts:
            candidate = candidate / part
            if _linked(candidate):
                raise ValueError("linked paths are not allowed")
        target = (self.root / path).resolve(strict=True)
        if not target.is_relative_to(self.root):
            raise ValueError("path leaves workspace")
        if directory is True and not target.is_dir():
            raise ValueError("path must be a directory")
        if directory is False and not target.is_file():
            raise ValueError("path must be a file")
        return target

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        if name == "list_files":
            if set(arguments) != {"path"}:
                raise ValueError("list_files requires path")
            directory = self._path(arguments["path"], directory=True)
            names = sorted(
                child.name + ("/" if child.is_dir() else "")
                for child in directory.iterdir()
                if not _sensitive(child.name) and not _linked(child)
                and child.resolve().is_relative_to(self.root)
            )
            if len(names) > MAX_LIST_ENTRIES:
                raise ValueError("directory listing is too large")
            return "\n".join(names)
        if name == "read_file":
            if set(arguments) != {"path"}:
                raise ValueError("read_file requires path")
            return self._read(self._path(arguments["path"], directory=False))
        if name == "search_text":
            if set(arguments) != {"path", "query"}:
                raise ValueError("search_text requires path and query")
            query = arguments["query"]
            if not isinstance(query, str) or not 1 <= len(query) <= 128:
                raise ValueError("query is invalid")
            directory = self._path(arguments["path"], directory=True)
            return self._search(directory, query)
        raise ValueError("tool is unsupported")

    @staticmethod
    def _read(path: Path) -> str:
        if path.stat().st_size > MAX_READ_BYTES:
            raise ValueError("file is too large")
        content = path.read_bytes()
        if len(content) > MAX_READ_BYTES or b"\x00" in content:
            raise ValueError("file is too large or binary")
        try:
            return content.decode("utf-8")
        except UnicodeError:
            raise ValueError("file is not UTF-8") from None

    def _search(self, directory: Path, query: str) -> str:
        results: list[str] = []
        files_seen = 0
        pending = [directory]
        while pending:
            current = pending.pop()
            for path in sorted(current.iterdir(), reverse=True):
                relative = path.relative_to(self.root)
                if any(_sensitive(part) for part in relative.parts) or _linked(path):
                    continue
                if path.is_dir():
                    pending.append(path)
                    continue
                if not path.is_file():
                    continue
                if not path.resolve().is_relative_to(self.root):
                    raise ValueError("search path leaves workspace")
                files_seen += 1
                if files_seen > MAX_SEARCH_FILES:
                    raise ValueError("search file budget exhausted")
                try:
                    content = self._read(path)
                except ValueError:
                    continue
                for number, line in enumerate(content.splitlines(), 1):
                    if query in line:
                        results.append(f"{relative.as_posix()}:{number}:{line[:200]}")
                        if len(results) >= MAX_SEARCH_MATCHES:
                            return "\n".join(results)
        return "\n".join(results)
