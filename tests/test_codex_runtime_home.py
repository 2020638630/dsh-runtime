import asyncio
import os
from pathlib import Path

import pytest

from dsh_runtime.codex_runtime_home import (
    CODEX_AUTH_FILENAME,
    CODEX_CONFIG_FILENAME,
    CODEX_HOME_DIRECTORY,
    CODEX_SQLITE_HOME_DIRECTORY,
    MANAGED_CONFIG_TEXT,
    STATE_ROOT_ENV,
    CodexRuntimeHome,
    CodexRuntimeHomeError,
    ManagedCodexPlugin,
    resolve_state_root,
)
from dsh_runtime.plugins.codex import CodexPlugin
from dsh_runtime.runtime.plugin import ExecutionContext


def test_explicit_state_root_wins_and_derives_managed_paths(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit-state"
    home = CodexRuntimeHome.from_environment(
        state_root=explicit,
        environment={"LOCALAPPDATA": str(tmp_path / "local")},
    )

    assert home.state_root == explicit.resolve()
    assert home.codex_home == explicit / CODEX_HOME_DIRECTORY
    assert home.codex_sqlite_home == explicit / CODEX_SQLITE_HOME_DIRECTORY
    assert home.environment_overlay == {
        "CODEX_HOME": str(explicit / CODEX_HOME_DIRECTORY),
        "CODEX_SQLITE_HOME": str(explicit / CODEX_SQLITE_HOME_DIRECTORY),
    }


def test_default_state_root_is_deterministic(tmp_path: Path) -> None:
    local_app_data = tmp_path / "local-app-data"

    assert resolve_state_root(
        environment={"LOCALAPPDATA": str(local_app_data)}
    ) == (local_app_data / "DSH-Runtime").resolve()


def test_host_state_root_variable_is_used_and_never_in_overlay(tmp_path: Path) -> None:
    configured = tmp_path / "configured-state"
    home = CodexRuntimeHome.from_environment(
        environment={STATE_ROOT_ENV: str(configured)}
    )

    assert home.state_root == configured.resolve()
    assert STATE_ROOT_ENV not in home.environment_overlay


def test_missing_local_app_data_fails_closed() -> None:
    with pytest.raises(CodexRuntimeHomeError, match="LOCALAPPDATA"):
        resolve_state_root(environment={})


def test_prepare_creates_only_managed_dirs_and_minimal_config(tmp_path: Path) -> None:
    home = CodexRuntimeHome(tmp_path / "state")

    home.prepare()

    assert home.state_root.is_dir()
    assert home.codex_home.is_dir()
    assert home.codex_sqlite_home.is_dir()
    assert home.config_path.read_text(encoding="utf-8") == MANAGED_CONFIG_TEXT
    assert not home.auth_path.exists()
    assert home.config_path.name == CODEX_CONFIG_FILENAME
    assert home.auth_path.name == CODEX_AUTH_FILENAME
    assert home.authentication_ready is False


def test_prepare_does_not_copy_user_home_auth_or_state(tmp_path: Path) -> None:
    user_home = tmp_path / "user-global-codex"
    user_home.mkdir()
    (user_home / "auth.json").write_text("credential-bytes", encoding="utf-8")
    (user_home / "sessions").mkdir()
    (user_home / "installation_id").write_text("user-id", encoding="utf-8")

    home = CodexRuntimeHome(tmp_path / "state")
    home.prepare()

    assert not (home.codex_home / "auth.json").exists()
    assert not (home.codex_home / "sessions").exists()
    assert not (home.codex_home / "installation_id").exists()


def test_conflicting_managed_config_fails_closed(tmp_path: Path) -> None:
    home = CodexRuntimeHome(tmp_path / "state")
    home.codex_home.mkdir(parents=True)
    home.config_path.write_text(
        'model = "wrong-model"\n',
        encoding="utf-8",
    )

    with pytest.raises(CodexRuntimeHomeError, match="incompatible"):
        home.prepare()


def test_state_root_file_fails_closed(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    state_root.write_text("not a directory", encoding="utf-8")

    with pytest.raises(CodexRuntimeHomeError, match="not a directory"):
        CodexRuntimeHome(state_root).prepare()


def test_authentication_absence_is_explicit_and_pre_spawn(tmp_path: Path) -> None:
    home = CodexRuntimeHome(tmp_path / "state")
    plugin = ManagedCodexPlugin(
        home,
        command=(str(tmp_path / "must-not-spawn"),),
    )

    async def scenario():
        return await plugin.execute(
            ExecutionContext(
                task_id="auth-readiness",
                workspace_id="workspace",
                goal="read-only",
                cwd=str(tmp_path),
                allow_workspace_write=False,
            ),
            {"prompt": "read-only"},
        )

    result = asyncio.run(scenario())

    assert result.success is False
    assert result.error == "managed CODEX_HOME authentication is not bootstrapped"
    assert not (tmp_path / "must-not-spawn").exists()


def test_managed_plugin_uses_required_config_and_auth_readiness(tmp_path: Path) -> None:
    home = CodexRuntimeHome(tmp_path / "state")
    home.prepare()
    home.auth_path.write_text("placeholder-for-test", encoding="utf-8")
    plugin = ManagedCodexPlugin(home, command=("unused",))

    assert plugin.runtime_home is home
    assert plugin._environment_overlay == home.environment_overlay
    assert home.authentication_ready is True


def test_dsh_host_configuration_is_filtered_before_child_environment(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv(STATE_ROOT_ENV, str(tmp_path / "host-state"))
    home = CodexRuntimeHome.from_environment()
    plugin = ManagedCodexPlugin(home, command=("unused",))

    child_environment = plugin._environment()

    assert STATE_ROOT_ENV not in child_environment
    assert child_environment["CODEX_HOME"] == str(home.codex_home)
    assert child_environment["CODEX_SQLITE_HOME"] == str(home.codex_sqlite_home)
    assert isinstance(plugin, CodexPlugin)


def test_no_real_user_codex_home_is_referenced_by_default_contract(tmp_path: Path) -> None:
    home = CodexRuntimeHome.from_environment(
        environment={"LOCALAPPDATA": str(tmp_path / "local")}
    )

    assert home.codex_home != Path(os.environ.get("USERPROFILE", "")) / ".codex"
    assert ".codex" not in str(home.codex_home)
