"""DSH-owned Codex runtime-home composition.

This module owns only the filesystem/environment contract around Codex. It
does not contain Codex protocol or lifecycle logic. Authentication is
deliberately not bootstrapped here; a missing authentication state is exposed
as a pre-spawn readiness failure.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .plugins.codex import CodexPlugin
from .runtime.plugin import ExecutionContext, PluginResult, StopReason


STATE_ROOT_ENV = "DSH_RUNTIME_STATE_ROOT"
DEFAULT_STATE_DIRECTORY = "DSH-Runtime"
CODEX_HOME_DIRECTORY = "codex-home"
CODEX_SQLITE_HOME_DIRECTORY = "codex-sqlite"
CODEX_CONFIG_FILENAME = "config.toml"
CODEX_AUTH_FILENAME = "auth.json"

# Keep this intentionally small. The Windows sandbox setting preserves the
# installed Codex contract; Runtime still supplies per-invocation authority.
MANAGED_CONFIG_TEXT = (
    'model = "gpt-5.6-luna"\n'
    'model_reasoning_effort = "xhigh"\n'
    'sandbox_mode = "workspace-write"\n'
    "[windows]\n"
    'sandbox = "unelevated"\n'
)


class CodexRuntimeHomeError(RuntimeError):
    """Stable configuration/readiness failure for a DSH-owned Codex Home."""


def _absolute_path(raw: str | os.PathLike[str], *, label: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise CodexRuntimeHomeError(f"{label} must be an absolute path")
    return path.resolve(strict=False)


def resolve_state_root(
    explicit: str | os.PathLike[str] | None = None,
    *,
    environment: Mapping[str, str] | None = None,
) -> Path:
    """Resolve the DSH host state root without touching the filesystem."""

    env = os.environ if environment is None else environment
    if explicit is not None:
        return _absolute_path(explicit, label="DSH runtime state root")

    configured = env.get(STATE_ROOT_ENV)
    if configured is not None:
        if not configured.strip():
            raise CodexRuntimeHomeError(f"{STATE_ROOT_ENV} must not be empty")
        return _absolute_path(configured, label=STATE_ROOT_ENV)

    local_app_data = env.get("LOCALAPPDATA")
    if local_app_data is None or not local_app_data.strip():
        raise CodexRuntimeHomeError(
            "DSH runtime state root cannot be resolved: LOCALAPPDATA is unavailable"
        )
    return _absolute_path(
        Path(local_app_data) / DEFAULT_STATE_DIRECTORY,
        label="Windows DSH runtime state root",
    )


@dataclass(frozen=True)
class CodexRuntimeHome:
    """Paths and readiness contract for one DSH-owned Codex installation."""

    state_root: Path

    @classmethod
    def from_environment(
        cls,
        *,
        state_root: str | os.PathLike[str] | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> "CodexRuntimeHome":
        return cls(resolve_state_root(state_root, environment=environment))

    @property
    def codex_home(self) -> Path:
        return self.state_root / CODEX_HOME_DIRECTORY

    @property
    def codex_sqlite_home(self) -> Path:
        return self.state_root / CODEX_SQLITE_HOME_DIRECTORY

    @property
    def config_path(self) -> Path:
        return self.codex_home / CODEX_CONFIG_FILENAME

    @property
    def auth_path(self) -> Path:
        return self.codex_home / CODEX_AUTH_FILENAME

    @property
    def environment_overlay(self) -> dict[str, str]:
        """Return only child-facing Codex variables; no DSH host variables."""

        return {
            "CODEX_HOME": str(self.codex_home),
            "CODEX_SQLITE_HOME": str(self.codex_sqlite_home),
        }

    @property
    def authentication_ready(self) -> bool:
        # Deliberately inspect existence/type only; never read credential bytes.
        return self.auth_path.is_file()

    def prepare(self) -> "CodexRuntimeHome":
        """Create/validate managed directories and the canonical config."""

        self._ensure_directory(self.state_root, "DSH runtime state root")
        self._ensure_directory(self.codex_home, "managed CODEX_HOME")
        self._ensure_directory(
            self.codex_sqlite_home,
            "managed CODEX_SQLITE_HOME",
        )
        self._ensure_config()
        return self

    def require_execution_ready(self) -> "CodexRuntimeHome":
        """Validate everything required before a workload Codex spawn."""

        self.prepare()
        if not self.authentication_ready:
            raise CodexRuntimeHomeError(
                "managed CODEX_HOME authentication is not bootstrapped"
            )
        return self

    @staticmethod
    def _ensure_directory(path: Path, label: str) -> None:
        if path.exists() and not path.is_dir():
            raise CodexRuntimeHomeError(f"{label} is not a directory")
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise CodexRuntimeHomeError(f"{label} is unavailable") from exc
        if not os.access(path, os.W_OK | os.X_OK):
            raise CodexRuntimeHomeError(f"{label} is not writable")

    def _ensure_config(self) -> None:
        if self.config_path.exists():
            if not self.config_path.is_file():
                raise CodexRuntimeHomeError(
                    "managed CODEX_HOME config.toml is not a file"
                )
            try:
                current = self.config_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise CodexRuntimeHomeError(
                    "managed CODEX_HOME config.toml cannot be read"
                ) from exc
            if current != MANAGED_CONFIG_TEXT:
                raise CodexRuntimeHomeError(
                    "managed CODEX_HOME config.toml is incompatible"
                )
            return

        try:
            self.config_path.write_text(
                MANAGED_CONFIG_TEXT,
                encoding="utf-8",
                newline="",
            )
        except OSError as exc:
            raise CodexRuntimeHomeError(
                "managed CODEX_HOME config.toml cannot be created"
            ) from exc


class ManagedCodexPlugin(CodexPlugin):
    """CodexPlugin with a pre-spawn DSH runtime-home readiness gate."""

    def __init__(self, runtime_home: CodexRuntimeHome, **kwargs: Any) -> None:
        if "environment" in kwargs:
            raise ValueError("ManagedCodexPlugin owns the Codex environment overlay")
        self.runtime_home = runtime_home
        super().__init__(environment=runtime_home.environment_overlay, **kwargs)

    async def execute(
        self,
        ctx: ExecutionContext,
        params: dict[str, Any],
    ) -> PluginResult:
        try:
            self.runtime_home.require_execution_ready()
        except CodexRuntimeHomeError as exc:
            return PluginResult(
                success=False,
                error=str(exc),
                stop_reason=StopReason.FAILED,
            )
        # Call the base seam explicitly so existing deterministic tests and
        # host adapters that patch CodexPlugin.execute retain their boundary.
        return await CodexPlugin.execute(self, ctx, params)
