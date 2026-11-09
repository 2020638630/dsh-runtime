"""Fixed, Desktop-only login and status commands for the Runtime's two CLIs."""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from queue import Empty, Queue
from threading import Thread

from dsh_runtime.codex_runtime_home import (
    CodexRuntimeHome,
    CodexRuntimeHomeError,
    ManagedCodexPlugin,
)
from dsh_runtime.plugins.codebuddy import (
    CodeBuddyLaunchConfigurationError,
    _default_command as codebuddy_command,
    _resolve_windows_command,
)


_CODEX_STORE = ('-c', 'cli_auth_credentials_store="file"')
_CODEBUDDY_FLAGS = ('--no-session-persistence', '--setting-sources', 'user',
                    '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}')


def _codex_command() -> tuple[str, ...]:
    executable = shutil.which('codex')
    if executable is None:
        raise FileNotFoundError()
    if Path(executable).suffix.lower() == '.cmd':
        return _resolve_windows_command(Path(executable))
    if Path(executable).suffix.lower() != '.exe':
        raise FileNotFoundError()
    return (executable,)


def _read_codebuddy_reply(child: subprocess.Popen, request_id: int) -> dict:
    for _ in range(32):
        line = child.stdout.readline(65_537)
        if not line or len(line) > 65_536:
            break
        try:
            frame = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        if isinstance(frame, dict) and frame.get('id') == request_id:
            result = frame.get('result')
            if frame.get('jsonrpc') == '2.0' and isinstance(result, dict) and 'error' not in frame:
                return result
            break
    raise ValueError('CodeBuddy ACP reply unavailable')


def _codebuddy_status(command: tuple[str, ...], cwd: Path, env: dict[str, str]) -> str:
    outcome: Queue[str] = Queue(maxsize=1)
    with subprocess.Popen(
        (*command, *_CODEBUDDY_FLAGS, '--acp'),
        cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
    ) as child:
        def probe() -> None:
            try:
                requests = (
                    ('initialize', {'protocolVersion': 1, 'clientCapabilities': {}}),
                    ('_codebuddy.ai/getUserInfo', {}),
                )
                for request_id, (method, params) in enumerate(requests, 1):
                    frame = {'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params}
                    child.stdin.write(json.dumps(frame).encode('utf-8') + b'\n')
                    child.stdin.flush()
                    reply = _read_codebuddy_reply(child, request_id)
                identity = reply.get('userInfo')
                if identity is None:
                    outcome.put('signed_out')
                elif isinstance(identity, dict) and identity.get('userId'):
                    outcome.put('signed_in')
                else:
                    outcome.put('unknown')
            except (OSError, ValueError):
                outcome.put('unknown')

        reader = Thread(target=probe, daemon=True)
        reader.start()
        try:
            return outcome.get(timeout=12)
        except Empty:
            return 'unknown'
        finally:
            child.kill()
            child.wait()
            reader.join(timeout=1)


def run(operation: str, cli: str) -> str:
    if os.name != 'nt':
        return 'unsupported'
    try:
        command = _codex_command() if cli == 'codex' else codebuddy_command()
    except (CodeBuddyLaunchConfigurationError, FileNotFoundError):
        return 'unavailable'

    home = CodexRuntimeHome.from_environment()
    # Keep both commands out of the user's workspace and its project settings.
    cwd = home.state_root
    cwd.mkdir(parents=True, exist_ok=True)
    if cli == 'codex':
        if operation == 'status' and not home.authentication_ready:
            return 'signed_out'
        home.prepare()
        env = ManagedCodexPlugin(home)._environment()
    else:
        env = dict(os.environ)
        env['DISABLE_AUTOUPDATER'] = '1'
    env.pop('ELECTRON_RUN_AS_NODE', None)

    if operation == 'status':
        if cli == 'codebuddy':
            return _codebuddy_status(command, cwd, env)
        result = subprocess.run(
            (*command, 'login', 'status', *_CODEX_STORE), cwd=cwd, env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=8, creationflags=subprocess.CREATE_NO_WINDOW, check=False,
        )
        return 'signed_in' if result.returncode == 0 else 'unknown'

    args = ('login', *_CODEX_STORE) if cli == 'codex' else _CODEBUDDY_FLAGS
    # The CLI owns all interaction, including any browser link or sensitive output.
    with subprocess.Popen((*command, *args), cwd=cwd, env=env,
                          creationflags=subprocess.CREATE_NEW_CONSOLE) as child:
        child.wait()
    return 'closed'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('status', 'login'))
    parser.add_argument('cli', choices=('codex', 'codebuddy'))
    args = parser.parse_args()
    try:
        result = run(args.operation, args.cli)
    except (CodexRuntimeHomeError, OSError, ValueError, subprocess.SubprocessError):
        result = 'unknown'
    print(result, flush=True)
