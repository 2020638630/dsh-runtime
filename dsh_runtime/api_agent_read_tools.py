"""Bounded read-only workspace tools for the API agent prototype."""

from __future__ import annotations

import os
from pathlib import Path
import stat
from typing import Any


MAX_READ_BYTES = 32_768
MAX_SEARCH_FILES = 100
MAX_SEARCH_ENTRIES = 500
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
            before = self._directory_identity(directory)
            names: list[str] = []
            entries_seen = 0
            for child in directory.iterdir():
                entries_seen += 1
                if entries_seen > MAX_LIST_ENTRIES:
                    raise ValueError("directory listing is too large")
                if (_sensitive(child.name) or _linked(child)
                    or not child.resolve().is_relative_to(self.root)):
                    continue
                names.append(child.name + ("/" if child.is_dir() else ""))
            self._check_directory_unchanged(arguments["path"], before)
            return "\n".join(sorted(names))
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
    def _directory_identity(directory: Path) -> tuple[int, int]:
        current = directory.stat()
        return current.st_dev, current.st_ino

    def _check_directory_unchanged(
        self, relative: str, identity: tuple[int, int],
    ) -> None:
        checked = self._path(relative, directory=True)
        if self._directory_identity(checked) != identity:
            raise ValueError("directory changed during enumeration")

    def _read(self, path: Path) -> str:
        # A path checked by _path() can be replaced before open(). Verify the
        # opened handle itself before reading any bytes into the model context.
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags)
        except OSError:
            raise ValueError("file could not be opened safely") from None
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("path must be a regular file")
            opened_path = _opened_file_path(fd)
            if not opened_path.is_relative_to(self.root):
                raise ValueError("opened file leaves workspace")
            if any(_sensitive(part) for part in opened_path.relative_to(self.root).parts):
                raise ValueError("opened file is outside allowed scope")
            if before.st_size > MAX_READ_BYTES:
                raise ValueError("file is too large")
            chunks: list[bytes] = []
            remaining = MAX_READ_BYTES + 1
            while remaining:
                chunk = os.read(fd, remaining)
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            after = os.fstat(fd)
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
            ):
                raise ValueError("file changed during read")
            content = b"".join(chunks)
        finally:
            os.close(fd)
        if len(content) > MAX_READ_BYTES or b"\x00" in content:
            raise ValueError("file is too large or binary")
        try:
            return content.decode("utf-8")
        except UnicodeError:
            raise ValueError("file is not UTF-8") from None


    def _search(self, directory: Path, query: str) -> str:
        results: list[str] = []
        files_seen = 0
        entries_seen = 0
        pending = [directory]
        while pending:
            current = pending.pop()
            relative_current = current.relative_to(self.root).as_posix()
            checked = self._path(relative_current, directory=True)
            identity = self._directory_identity(checked)
            entries: list[Path] = []
            for path in current.iterdir():
                entries_seen += 1
                if entries_seen > MAX_SEARCH_ENTRIES:
                    raise ValueError("search entry budget exhausted")
                entries.append(path)
            for path in sorted(entries, reverse=True):
                relative = path.relative_to(self.root)
                if any(_sensitive(part) for part in relative.parts) or _linked(path):
                    continue
                if path.is_dir():
                    self._path(relative.as_posix(), directory=True)
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
                            self._check_directory_unchanged(relative_current, identity)
                            return "\n".join(results)
            self._check_directory_unchanged(relative_current, identity)
        return "\n".join(results)


def _opened_file_path(fd: int) -> Path:
    """Resolve the actual opened object; fail closed on unsupported platforms."""
    if os.name == "nt":
        import ctypes
        import msvcrt
        from ctypes import wintypes

        get_path = ctypes.windll.kernel32.GetFinalPathNameByHandleW
        get_path.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
        get_path.restype = wintypes.DWORD
        handle = msvcrt.get_osfhandle(fd)
        buffer = ctypes.create_unicode_buffer(32768)
        length = get_path(handle, buffer, len(buffer), 0)
        if not length or length >= len(buffer):
            raise ValueError("opened file path is unavailable")
        raw = buffer.value
        if raw.startswith("\\\\?\\UNC\\"):
            raw = "\\\\" + raw[8:]
        elif raw.startswith("\\\\?\\"):
            raw = raw[4:]
        else:
            raise ValueError("opened file path is unavailable")
        return Path(raw)
    if Path("/proc/self/fd").is_dir():
        return Path(os.readlink(f"/proc/self/fd/{fd}"))
    raise ValueError("opened file path is unavailable")
