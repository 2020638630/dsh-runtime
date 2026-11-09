"""Fixed, Desktop-only login and status commands for the Runtime's two CLIs."""

import argparse
import json
import os
import re
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
_MODEL_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}\Z')


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


def _codex_model_pages(child: subprocess.Popen) -> dict:
    def send(method: str, params: dict, request_id: int | None = None) -> None:
        frame = {'jsonrpc': '2.0', 'method': method, 'params': params}
        if request_id is not None:
            frame['id'] = request_id
        child.stdin.write((json.dumps(frame) + '\n').encode('utf-8'))
        child.stdin.flush()

    def receive(request_id: int) -> dict:
        for _ in range(32):
            line = child.stdout.readline(262_145)
            if not line or len(line) > 262_144:
                break
            frame = json.loads(line)
            if isinstance(frame, dict) and frame.get('id') == request_id and 'method' not in frame:
                return frame
        raise ValueError('Codex App Server reply unavailable')

    send('initialize', {'clientInfo': {'name': 'dsh_runtime_models', 'version': '1.0.0'}}, 1)
    if not isinstance(receive(1).get('result'), dict):
        return {'status': 'unavailable'}
    send('initialized', {})
    models: dict[str, None] = {}
    cursor = None
    seen_cursors: set[str] = set()
    for request_id in range(2, 10):
        params = {'limit': 64, 'includeHidden': False}
        if cursor is not None:
            params['cursor'] = cursor
        send('model/list', params, request_id)
        frame = receive(request_id)
        error = frame.get('error')
        if isinstance(error, dict):
            return {'status': 'unsupported' if error.get('code') == -32601 else 'unavailable'}
        result = frame.get('result')
        rows = result.get('data') if isinstance(result, dict) else None
        if not isinstance(rows, list) or len(rows) > 64:
            return {'status': 'invalid_response'}
        for row in rows:
            model = row.get('model') if isinstance(row, dict) else None
            if isinstance(model, str) and _MODEL_ID.fullmatch(model) and row.get('hidden') is not True:
                models[model] = None
        cursor = result.get('nextCursor')
        if cursor is None:
            break
        if not isinstance(cursor, str) or not 0 < len(cursor) <= 1024 or cursor in seen_cursors:
            return {'status': 'invalid_response'}
        seen_cursors.add(cursor)
    return {'status': 'ok', 'models': list(models), 'truncated': cursor is not None}


def _codex_models(command: tuple[str, ...], cwd: Path, env: dict[str, str]) -> dict:
    outcome: Queue[dict] = Queue(maxsize=1)
    with subprocess.Popen(
        (*command, 'app-server', '--stdio'),
        cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
    ) as child:
        def probe() -> None:
            try:
                outcome.put(_codex_model_pages(child))
            except (OSError, ValueError, RecursionError):
                outcome.put({'status': 'invalid_response'})

        reader = Thread(target=probe, daemon=True)
        reader.start()
        try:
            return outcome.get(timeout=12)
        except Empty:
            return {'status': 'timeout'}
        finally:
            if child.poll() is None:
                child.kill()
            child.wait()
            reader.join(timeout=1)


def run(operation: str, cli: str) -> str | dict:
    if os.name != 'nt':
        return 'unsupported'
    if operation == 'models' and cli != 'codex':
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
        if operation in ('status', 'models') and not home.authentication_ready:
            return 'signed_out'
        home.prepare()
        env = ManagedCodexPlugin(home)._environment()
    else:
        env = dict(os.environ)
        env['DISABLE_AUTOUPDATER'] = '1'
    env.pop('ELECTRON_RUN_AS_NODE', None)

    if operation == 'models':
        return _codex_models(command, cwd, env)

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
    parser.add_argument('operation', choices=('status', 'login', 'models'))
    parser.add_argument('cli', choices=('codex', 'codebuddy'))
    args = parser.parse_args()
    try:
        result = run(args.operation, args.cli)
    except (CodexRuntimeHomeError, OSError, ValueError, subprocess.SubprocessError):
        result = 'unknown'
    if args.operation == 'models':
        payload = result if isinstance(result, dict) else {'status': result}
        print(json.dumps(payload, separators=(',', ':')), flush=True)
    else:
        print(result, flush=True)
