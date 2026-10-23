"""Deterministic tests for the bounded CodeBuddy capability."""

import asyncio
import ctypes
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from dsh_runtime.plugins.codebuddy import CodeBuddyPlugin
from dsh_runtime.plugins import codebuddy as codebuddy_module
from dsh_runtime.plugins.codebuddy import SAFE_EVENT_TRACE_DIR_ENV
from dsh_runtime.runtime.executor import Executor
from dsh_runtime.runtime.plugin import ExecutionContext, StopReason
from dsh_runtime.runtime.registry import PluginRegistry


R2_MULTILINE_PROMPT = (
    "In the disposable qualification repository, create exactly one file at the "
    "repository root named `c3_a_change.txt` with exactly this single line and no "
    "trailing newline:\n"
    "DSH_C3_A_REPOSITORY_CHANGE\n"
    "Do not create, modify, delete, or rename any other file. Finish only when "
    "that file has exactly the requested content."
)


FAKE_CLI = '''
import json
import os
import subprocess
import sys
import time
from pathlib import Path

args = sys.argv[1:]
capture = os.environ.get("CODEBUDDY_TEST_CAPTURE")
mode = os.environ.get("CODEBUDDY_TEST_MODE", "success")
settings_path = args[args.index("--settings") + 1]
if capture:
    with open(capture, "w", encoding="utf-8") as handle:
        json.dump({
            "argv": args,
            "cwd": os.getcwd(),
            "settings": settings_path,
            "settings_data": open(settings_path, encoding="utf-8").read(),
            "safe_trace_dir_visible": os.environ.get(
                "DSH_CODEBUDDY_SAFE_EVENT_TRACE_DIR"
            ),
        }, handle)

if mode == "hold":
    time.sleep(60)
elif mode == "hold-tree":
    child = subprocess.Popen([
        sys.executable,
        "-c",
        "import os,time; open(os.environ['CODEBUDDY_CHILD_MARKER'],'w').write(str(os.getpid())); time.sleep(60)",
    ])
    with open(os.environ["CODEBUDDY_CHILD_PID"], "w", encoding="utf-8") as handle:
        handle.write(str(child.pid))
    with open(os.environ["CODEBUDDY_ROOT_MARKER"], "w", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))
    time.sleep(60)
elif mode == "malformed":
    print("not json")
elif mode == "truncated-array":
    sys.stdout.write('[{"type":"message"}')
    sys.stdout.flush()
elif mode == "missing-final":
    print(json.dumps([{"type": "message", "result": "partial"}]))
elif mode == "nested-result":
    print(json.dumps([{"type": "message", "payload": {"type": "result", "subtype": "success", "is_error": False, "result": "nested fake"}}]))
elif mode == "root-object":
    print(json.dumps({"wrapper": {"type": "result", "subtype": "success", "is_error": False, "result": "fake success"}}))
elif mode == "native-failure":
    print(json.dumps([{"type": "result", "subtype": "error", "is_error": True, "result": "service failed"}]))
elif mode == "permission-denied":
    print(json.dumps([
        {"type": "function_call_result", "is_error": True, "result": "Error: permission denied"},
        {"type": "result", "subtype": "success", "is_error": False, "result": "nominal"},
    ]))
elif mode == "max-turns":
    print(json.dumps([{"type": "result", "subtype": "error_max_turns", "is_error": False, "result": "Max turns (6) exceeded"}]))
elif mode == "false-success":
    print(json.dumps([
        {"type": "function_call_result", "is_error": True, "result": "Error: spawn EPERM"},
        {"type": "result", "subtype": "success", "is_error": False, "result": "I completed the task"},
    ]))
elif mode in {"trace-events", "trace-stream"}:
    content = os.environ.get("CODEBUDDY_TEST_WRITE_CONTENT", "DSH_C3_A_REPOSITORY_CHANGE")
    stderr_text = os.environ.get("CODEBUDDY_TEST_STDERR")
    if stderr_text:
        print(stderr_text, file=sys.stderr)
    tool_output = os.environ.get(
        "CODEBUDDY_TEST_TOOL_OUTPUT",
        f"Successfully wrote {len(content.encode('utf-8'))} bytes",
    )
    events = [
        {"type": "message", "providerData": {"model": "fake-trace-model"}},
        {
            "type": "function_call",
            "name": "Write",
            "arguments": json.dumps({
                "file_path": "c3_a_change.txt",
                "content": content,
            }),
            "providerData": {"model": "fake-trace-model"},
        },
        {
            "type": "function_call_result",
            "name": "Write",
            "status": "completed",
            "output": {
                "type": "text",
                "text": tool_output,
            },
            "providerData": {"model": "fake-trace-model"},
        },
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "trace final result",
            "providerData": {"model": "fake-trace-model"},
        },
    ]
    if mode == "trace-stream":
        events[0]["index"] = 17
        events[0]["message"] = {"content": "synthetic model message"}
        sys.stdout.write("[")
        sys.stdout.flush()
        for index, event in enumerate(events):
            if index:
                sys.stdout.write(",")
            sys.stdout.write(json.dumps(event))
            sys.stdout.flush()
            if index == 0:
                trace_dir = os.environ.get("CODEBUDDY_TEST_SAFE_TRACE_DIR")
                marker = os.environ.get("CODEBUDDY_TEST_OBSERVER_MARKER")
                if trace_dir and marker:
                    deadline = time.monotonic() + 1.5
                    while time.monotonic() < deadline and not os.path.exists(marker):
                        for trace_path in Path(trace_dir).glob("*.jsonl"):
                            try:
                                if len(trace_path.read_text(encoding="utf-8").splitlines()) >= 2:
                                    Path(marker).write_text("observed", encoding="utf-8")
                                    break
                            except OSError:
                                pass
                        if not os.path.exists(marker):
                            time.sleep(0.01)
            time.sleep(0.03)
        sys.stdout.write("]")
        sys.stdout.flush()
    else:
        print(json.dumps(events))
elif mode == "nonzero":
    print("native failure", file=sys.stderr)
    sys.exit(7)
elif mode == "empty-max-turns":
    max_turns = args[args.index("--max-turns") + 1]
    print(f"Max turns ({max_turns}) exceeded", file=sys.stderr)
elif mode in {"trace-flood", "trace-flood-hold"}:
    event_count = int(os.environ.get("CODEBUDDY_TEST_EVENT_COUNT", "256"))
    events = [{"type": "message"} for _ in range(event_count)]
    events.append({
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "bounded flood result",
    })
    print(json.dumps(events))
    if mode == "trace-flood-hold":
        time.sleep(60)
elif mode == "unknown-event":
    event_type = os.environ.get("CODEBUDDY_TEST_UNKNOWN_TYPE", "unrecognized")
    payload = os.environ.get("CODEBUDDY_TEST_UNKNOWN_PAYLOAD", "synthetic payload")
    print(json.dumps([
        {"type": event_type, "payload": payload},
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "bounded final assistant result",
        },
    ]))
else:
    print(json.dumps([
        {"type": "message", "message": {"content": "working"}},
        {"type": "function_call_result", "is_error": False, "result": {"stdout": "LOCAL_TEST_OK", "exit_code": 0}},
        {"type": "result", "subtype": "success", "is_error": False, "result": "bounded final assistant result"},
    ]))
'''


def write_fake_cli(tmp_path: Path) -> Path:
    path = tmp_path / "fake_codebuddy.py"
    path.write_text(FAKE_CLI, encoding="utf-8")
    return path


def plugin(
    tmp_path: Path,
    *,
    mode: str = "success",
    capture: Path | None = None,
    trace_dir: Path | None = None,
    safe_trace_dir: Path | None = None,
    **extra: str,
) -> CodeBuddyPlugin:
    environment = {"CODEBUDDY_TEST_MODE": mode}
    if capture is not None:
        environment["CODEBUDDY_TEST_CAPTURE"] = str(capture)
    environment.update(extra)
    return CodeBuddyPlugin(
        command=(sys.executable, str(write_fake_cli(tmp_path))),
        environment=environment,
        cleanup_grace_seconds=0.2,
        qualification_trace_dir=trace_dir,
        safe_event_trace_dir=safe_trace_dir,
    )


def context(cwd: Path, *, allow_workspace_write: bool = True) -> ExecutionContext:
    return ExecutionContext(
        task_id="codebuddy-test",
        workspace_id="logical.test",
        goal="fallback goal",
        cwd=str(cwd),
        allow_workspace_write=allow_workspace_write,
    )


def run(
    plugin_instance: CodeBuddyPlugin,
    ctx: ExecutionContext,
    params: dict | None = None,
    timeout: float = 1.0,
):
    registry = PluginRegistry()
    registry.register(plugin_instance)
    return asyncio.run(
        Executor(registry).execute(
            "codebuddy", ctx, params or {"prompt": "do work"}, timeout
        )
    )


def track_temporary_artifacts(monkeypatch) -> list[Path]:
    paths: list[Path] = []
    original_mkstemp = codebuddy_module.tempfile.mkstemp

    def track_mkstemp(*args, **kwargs):
        fd, raw_path = original_mkstemp(*args, **kwargs)
        paths.append(Path(raw_path))
        return fd, raw_path

    monkeypatch.setattr(codebuddy_module.tempfile, "mkstemp", track_mkstemp)
    return paths


_SAFE_TRACE_CHILD_DRIVER = r'''
import asyncio
import json
import os
import sys
import time
import tempfile
from pathlib import Path

from dsh_runtime.plugins import codebuddy as codebuddy_module
from dsh_runtime.plugins.codebuddy import CodeBuddyPlugin
from dsh_runtime.runtime.executor import Executor
from dsh_runtime.runtime.plugin import ExecutionContext
from dsh_runtime.runtime.registry import PluginRegistry

config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
temporary_paths = []
original_mkstemp = tempfile.mkstemp

def track_mkstemp(*args, **kwargs):
    fd, raw_path = original_mkstemp(*args, **kwargs)
    temporary_paths.append(raw_path)
    return fd, raw_path

tempfile.mkstemp = track_mkstemp
if config.get("max_bytes") is not None:
    codebuddy_module._SAFE_TRACE_MAX_BYTES = config["max_bytes"]
if config.get("max_events") is not None:
    codebuddy_module._SAFE_TRACE_MAX_EVENTS = config["max_events"]

observer_instances = []
parser_instances = []
if config.get("stream_json"):
    os.environ[codebuddy_module.SAFE_STREAM_JSON_ENV] = "1"
    original_parser_init = codebuddy_module._StreamJsonLineParser.__init__

    def track_parser(self, *args, **kwargs):
        original_parser_init(self, *args, **kwargs)
        parser_instances.append(self)

    codebuddy_module._StreamJsonLineParser.__init__ = track_parser
    worker_environment = {
        "DSH_STREAM_TEST_MODE": "flood-hold",
        "DSH_STREAM_TEST_EVENT_COUNT": str(config["event_count"]),
    }
else:
    original_observer_init = codebuddy_module._SafeJsonArrayEventObserver.__init__

    def track_observer(self, *args, **kwargs):
        original_observer_init(self, *args, **kwargs)
        observer_instances.append(self)

    codebuddy_module._SafeJsonArrayEventObserver.__init__ = track_observer
    worker_environment = {
        "CODEBUDDY_TEST_MODE": config["mode"],
        "CODEBUDDY_TEST_EVENT_COUNT": str(config["event_count"]),
    }
plugin = CodeBuddyPlugin(
    command=(sys.executable, config["fake_cli"]),
    environment=worker_environment,
    cleanup_grace_seconds=0.2,
    safe_event_trace_dir=config["trace_dir"],
)
registry = PluginRegistry()
registry.register(plugin)
ctx = ExecutionContext(
    task_id="safe-trace-bounded-test",
    workspace_id="safe-trace-bounded-test",
    goal="synthetic bounded observer test",
    cwd=config["workspace"],
    allow_workspace_write=True,
)
result = asyncio.run(
    Executor(registry).execute(
        "codebuddy", ctx, {"prompt": "synthetic bounded observer test"}, config["timeout"]
    )
)
report = {
    "success": result.success,
    "output": result.output,
    "error": result.error,
    "stop_reason": result.stop_reason.value if result.stop_reason else None,
    "cleanup_error": result.cleanup_error,
    "temporary_paths_clean": not any(Path(path).exists() for path in temporary_paths),
    "temporary_path_count": len(temporary_paths),
    "temporary_suffixes": [Path(path).suffix for path in temporary_paths],
    "observer_work_budget_yields": (parser_instances or observer_instances)[0].work_budget_yields
    if parser_instances or observer_instances else 0,
    "observer_max_batch_work": (parser_instances or observer_instances)[0].max_batch_work_observed
    if parser_instances or observer_instances else 0,
}
print(json.dumps(report, separators=(",", ":")))
'''


def run_safe_trace_child(
    tmp_path: Path,
    *,
    trace_dir: Path,
    mode: str,
    event_count: int,
    timeout: float,
    watchdog: float = 4.0,
    max_bytes: int | None = None,
    max_events: int | None = None,
    stream_json: bool = False,
) -> dict:
    fake_cli = tmp_path / "fake_stream_codebuddy.py" if stream_json else write_fake_cli(tmp_path)
    if stream_json:
        fake_cli.write_text(FAKE_STREAM_JSON_CLI, encoding="utf-8")
    driver_path = tmp_path / "safe_trace_child_driver.py"
    config_path = tmp_path / "safe_trace_child_config.json"
    driver_path.write_text(_SAFE_TRACE_CHILD_DRIVER, encoding="utf-8")
    config_path.write_text(
        json.dumps(
            {
                "fake_cli": str(fake_cli),
                "workspace": str(tmp_path),
                "trace_dir": str(trace_dir),
                "mode": mode,
                "event_count": event_count,
                "timeout": timeout,
                "max_bytes": max_bytes,
                "max_events": max_events,
                "stream_json": stream_json,
            }
        ),
        encoding="utf-8",
    )
    environment = os.environ.copy()
    project_root = str(Path(__file__).resolve().parents[1])
    existing_python_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        project_root
        if not existing_python_path
        else os.pathsep.join((project_root, existing_python_path))
    )
    completed = subprocess.run(
        [sys.executable, str(driver_path), str(config_path)],
        capture_output=True,
        text=True,
        timeout=watchdog,
        check=False,
        env=environment,
    )
    assert completed.returncode == 0, "bounded fake worker subprocess failed"
    return json.loads(completed.stdout)


def run_bounded_parser_probe(
    trace_dir: Path,
    source: str,
    *,
    watchdog: float = 4.0,
) -> dict:
    environment = os.environ.copy()
    environment["DSH_TEST_SAFE_TRACE_DIR"] = str(trace_dir.resolve())
    completed = subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        timeout=watchdog,
        check=False,
        env=environment,
        cwd=Path.cwd(),
    )
    assert completed.returncode == 0, "bounded synthetic parser subprocess failed"
    return json.loads(completed.stdout)


def test_input_authority_and_cwd_validation(tmp_path: Path) -> None:
    cb = plugin(tmp_path)
    assert (
        asyncio.run(cb.execute(context(tmp_path), {"prompt": "   "})).error
        == "CodeBuddy prompt must be non-empty text"
    )


def test_windows_default_command_bypasses_cmd_shim(tmp_path: Path) -> None:
    shim = tmp_path / "codebuddy.cmd"
    node = tmp_path / "node.exe"
    entrypoint = tmp_path / "node_modules" / "@tencent-ai" / "codebuddy-code" / "bin" / "codebuddy"
    node.write_bytes(b"node")
    entrypoint.parent.mkdir(parents=True)
    entrypoint.write_text("#!/usr/bin/env node\n", encoding="utf-8")
    shim.write_text(
        '@ECHO off\n'
        'IF EXIST "%dp0%\\node.exe" (\n'
        '  SET "_prog=%dp0%\\node.exe"\n'
        ')\n'
        'endLocal & "%_prog%" "%dp0%\\node_modules\\@tencent-ai\\codebuddy-code\\bin\\codebuddy" %*\n',
        encoding="utf-8",
    )
    with patch.object(codebuddy_module.os, "name", "nt"), patch.object(
        codebuddy_module.shutil, "which", side_effect=lambda name: str(shim)
    ):
        assert codebuddy_module._default_command() == (str(node), str(entrypoint))


def test_windows_default_command_fails_without_direct_entrypoint(tmp_path: Path) -> None:
    shim = tmp_path / "codebuddy.cmd"
    shim.write_text('@ECHO off\nendLocal & "%_prog%" "%dp0%\\missing" %*\n', encoding="utf-8")
    with patch.object(codebuddy_module.os, "name", "nt"), patch.object(
        codebuddy_module.shutil, "which", side_effect=lambda name: str(shim)
    ), pytest.raises(
        codebuddy_module.CodeBuddyLaunchConfigurationError,
        match="direct Node CLI entrypoint does not exist",
    ):
        codebuddy_module._default_command()


@pytest.mark.parametrize(
    "prompt",
    [
        "single line prompt",
        R2_MULTILINE_PROMPT,
        "line one\r\nline two\r\nline three",
        "line one\n\nline three\nline four",
        'shell & | < > ^ % ! " \' ( ) and `backticks`',
        "Unicode 中文 🚀 and D:\\repo\\path\\file.json",
    ],
)
def test_prompt_payload_is_preserved_as_one_argument(
    tmp_path: Path, prompt: str
) -> None:
    capture = tmp_path / "capture.json"
    result = run(
        plugin(tmp_path, capture=capture),
        context(tmp_path),
        {"prompt": prompt},
    )
    assert result.success is True
    captured = json.loads(capture.read_text(encoding="utf-8"))
    assert captured["argv"][-1] == prompt


def test_actual_windows_direct_node_transport_preserves_r2_prompt(tmp_path: Path) -> None:
    if os.name != "nt":
        pytest.skip("requires Windows process transport")
    real_node = shutil.which("node.exe") or shutil.which("node")
    if real_node is None:
        pytest.skip("requires a Node executable")

    shim = tmp_path / "codebuddy.cmd"
    entrypoint = tmp_path / "entry.cjs"
    capture = tmp_path / "node-capture.json"
    shim.write_text(
        '@ECHO off\n'
        'endLocal & "%_prog%" "%dp0%\\entry.cjs" %*\n',
        encoding="utf-8",
    )
    entrypoint.write_text(
        "const fs = require('fs');\n"
        "const args = process.argv.slice(2);\n"
        "fs.writeFileSync(process.env.CODEBUDDY_NODE_CAPTURE, JSON.stringify({args}), 'utf8');\n"
        "process.stdout.write(JSON.stringify([{type:'result', subtype:'success', is_error:false, result:'probe'}]));\n",
        encoding="utf-8",
    )

    original_which = shutil.which

    def which(name: str):
        if name == "codebuddy.cmd":
            return str(shim)
        if name == "node.exe":
            return real_node
        return original_which(name)

    with patch.object(codebuddy_module.shutil, "which", side_effect=which):
        cb = CodeBuddyPlugin(
            environment={"CODEBUDDY_NODE_CAPTURE": str(capture)},
        )
        assert cb._command == (str(Path(real_node).resolve()), str(entrypoint))
        result = run(cb, context(tmp_path), {"prompt": R2_MULTILINE_PROMPT})

    assert result.success is True
    node_args = json.loads(capture.read_text(encoding="utf-8"))["args"]
    assert node_args[-1] == R2_MULTILINE_PROMPT
    assert len(node_args[-1]) == len(R2_MULTILINE_PROMPT)
    with patch("dsh_runtime.plugins.codebuddy.subprocess.Popen") as popen:
        assert (
            asyncio.run(
                cb.execute(
                    context(tmp_path, allow_workspace_write=False), {"prompt": "work"}
                )
            ).error
            == "CodeBuddy requires workspace write authority"
        )
        popen.assert_not_called()
    assert (
        asyncio.run(cb.execute(context(tmp_path / "missing"), {"prompt": "work"})).error
        == "CodeBuddy workspace cwd is invalid"
    )
    assert (
        asyncio.run(
            cb.execute(ExecutionContext("id", "ws", "goal"), {"prompt": "work"})
        ).error
        == "CodeBuddy workspace cwd is missing"
    )


def test_exact_bounded_argv_cwd_and_private_settings(tmp_path: Path) -> None:
    capture = tmp_path / "capture.json"
    result = run(
        plugin(tmp_path, capture=capture),
        context(tmp_path),
        {"prompt": "bounded prompt"},
    )
    assert result.success is True
    captured = json.loads(capture.read_text(encoding="utf-8"))
    argv = captured["argv"]
    assert captured["cwd"] == str(tmp_path.resolve())
    assert "--print" in argv
    assert argv[argv.index("--output-format") + 1] == "json"
    assert argv[argv.index("--input-format") + 1] == "text"
    assert argv[argv.index("--max-turns") + 1] == "12"
    assert "--no-session-persistence" in argv
    assert argv[argv.index("--tools") + 1] == "Read,Edit,Write,Bash"
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert "--allowedTools=Bash(python:*)" in argv
    assert not any(
        flag in argv
        for flag in (
            "-y",
            "--dangerously-skip-permissions",
            "bypassPermissions",
            "--add-dir",
        )
    )
    settings = json.loads(captured["settings_data"])
    assert settings == {
        "permissions": {
            "defaultMode": "dontAsk",
            "allow": ["Read", "Edit", "Write", "Bash(python:*)"],
        }
    }
    assert not Path(captured["settings"]).exists()

    with patch(
        "dsh_runtime.plugins.codebuddy.subprocess.Popen",
        wraps=subprocess.Popen,
    ) as popen:
        run(plugin(tmp_path), context(tmp_path))
        assert popen.call_args.kwargs["shell"] is False


def test_explicit_model_uses_cli_flag_and_records_requested_model(tmp_path: Path) -> None:
    capture = tmp_path / "capture.json"
    trace_dir = tmp_path / "trace"
    result = run(
        plugin(tmp_path, mode="trace-events", capture=capture, trace_dir=trace_dir),
        context(tmp_path),
        {"prompt": "bounded prompt", "model": "glm-5.3-flash"},
    )
    assert result.success is True
    argv = json.loads(capture.read_text(encoding="utf-8"))["argv"]
    assert argv[argv.index("--model") + 1] == "glm-5.3-flash"
    assert argv[-1] == "bounded prompt"
    trace = json.loads(next(trace_dir.glob("codebuddy-worker-*.json")).read_text())
    assert trace["requested_model"] == "glm-5.3-flash"
    assert trace["observed_models"] == ["fake-trace-model"]


def test_invalid_model_fails_before_codebuddy_spawn(tmp_path: Path) -> None:
    with patch("dsh_runtime.plugins.codebuddy.subprocess.Popen") as popen:
        result = asyncio.run(
            plugin(tmp_path).execute(context(tmp_path), {"prompt": "work", "model": "bad model"})
        )
    assert result.success is False
    assert result.error == "CodeBuddy model must be a bounded model ID"
    popen.assert_not_called()


def test_explicit_max_turns_override_is_preserved(tmp_path: Path) -> None:
    capture = tmp_path / "capture.json"
    cb = CodeBuddyPlugin(
        command=(sys.executable, str(write_fake_cli(tmp_path))),
        environment={
            "CODEBUDDY_TEST_CAPTURE": str(capture),
        },
        max_turns=3,
        cleanup_grace_seconds=0.2,
    )
    result = run(cb, context(tmp_path), {"prompt": "bounded prompt"})
    assert result.success is True
    argv = json.loads(capture.read_text(encoding="utf-8"))["argv"]
    assert argv[argv.index("--max-turns") + 1] == "3"
    assert "--allowedTools=Bash(python:*)" in argv


@pytest.mark.parametrize("invalid_max_turns", [0, -1])
def test_max_turns_validation_remains_positive(
    tmp_path: Path, invalid_max_turns: int
) -> None:
    with pytest.raises(ValueError, match="max_turns must be positive"):
        CodeBuddyPlugin(
            command=(sys.executable, str(write_fake_cli(tmp_path))),
            max_turns=invalid_max_turns,
        )


def test_success_output_is_final_text_and_settings_are_cleaned(tmp_path: Path) -> None:
    capture = tmp_path / "capture.json"
    result = run(plugin(tmp_path, capture=capture), context(tmp_path))
    assert result.success is True
    assert result.stop_reason is StopReason.COMPLETED
    assert result.output == "bounded final assistant result"
    assert "function_call_result" not in result.output
    assert not Path(json.loads(capture.read_text())["settings"]).exists()


def test_qualification_trace_is_opt_in(tmp_path: Path) -> None:
    result = run(plugin(tmp_path), context(tmp_path))
    assert result.success is True
    assert not (tmp_path / "trace").exists()


@pytest.mark.parametrize(
    "write_content",
    ["ABC", "ABC\n", "c3_a_change\n", "DSH_C3_A_REPOSITORY_CHANGE"],
)
def test_qualification_trace_preserves_exact_write_arguments_and_survives_cleanup(
    tmp_path: Path, write_content: str
) -> None:
    trace_dir = tmp_path / "trace"
    result = run(
        plugin(
            tmp_path,
            mode="trace-events",
            trace_dir=trace_dir,
            CODEBUDDY_TEST_WRITE_CONTENT=write_content,
        ),
        context(tmp_path),
        {"prompt": "exact qualification prompt"},
    )
    assert result.success is True
    traces = list(trace_dir.glob("codebuddy-worker-*.json"))
    assert len(traces) == 1
    trace = json.loads(traces[0].read_text(encoding="utf-8"))
    assert trace["effective_prompt"] == "exact qualification prompt"
    assert trace["argv"][-1] == "exact qualification prompt"
    assert trace["observed_models"] == ["fake-trace-model"]
    write_call = next(
        event
        for event in trace["tool_events"]
        if event.get("type") == "function_call" and event.get("name") == "Write"
    )
    assert json.loads(write_call["arguments"])["content"] == write_content
    write_result = next(
        event
        for event in trace["tool_events"]
        if event.get("type") == "function_call_result"
        and event.get("name") == "Write"
    )
    assert write_result["status"] == "completed"
    assert trace["worker_result"]["result"] == "trace final result"
    assert trace["terminal"]["exit_code"] == 0
    assert trace["plugin_result"]["success"] is True
    assert trace["stdout"]
    assert not Path(trace["temporary_artifacts"]["settings"]).exists()
    assert not Path(trace["temporary_artifacts"]["stdout"]).exists()
    assert not Path(trace["temporary_artifacts"]["stderr"]).exists()


@pytest.mark.parametrize("mode", ["max-turns", "nonzero"])
def test_qualification_trace_survives_worker_failure_and_cleanup(
    tmp_path: Path, mode: str
) -> None:
    trace_dir = tmp_path / "trace"
    result = run(
        plugin(tmp_path, mode=mode, trace_dir=trace_dir),
        context(tmp_path),
    )
    assert result.success is False
    traces = list(trace_dir.glob("codebuddy-worker-*.json"))
    assert len(traces) == 1
    trace = json.loads(traces[0].read_text(encoding="utf-8"))
    assert trace["plugin_result"]["success"] is False
    assert trace["terminal"]["exit_code"] == (0 if mode == "max-turns" else 7)
    if mode == "max-turns":
        assert trace["worker_result"]["subtype"] == "error_max_turns"
    else:
        assert "native failure" in trace["stderr"]
    assert not Path(trace["temporary_artifacts"]["settings"]).exists()
    assert not Path(trace["temporary_artifacts"]["stdout"]).exists()
    assert not Path(trace["temporary_artifacts"]["stderr"]).exists()


def _safe_trace_records(trace_dir: Path) -> tuple[Path, list[dict]]:
    traces = list(trace_dir.glob("codebuddy-safe-worker-*.jsonl"))
    assert len(traces) == 1
    path = traces[0]
    assert path.stat().st_size <= codebuddy_module._SAFE_TRACE_MAX_BYTES
    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(records) <= codebuddy_module._SAFE_TRACE_MAX_EVENTS
    return path, records


def test_safe_json_array_observer_consumes_successful_decode_buffer(
    tmp_path: Path,
) -> None:
    trace_dir = tmp_path / "safe-trace"
    report = run_bounded_parser_probe(
        trace_dir,
        r'''
import asyncio, json, os
from pathlib import Path
from dsh_runtime.plugins import codebuddy as m
sink = m._SafeCodeBuddyEventSink(Path(os.environ["DSH_TEST_SAFE_TRACE_DIR"]))
observer = m._SafeJsonArrayEventObserver(sink)
before_finish = {}
async def main():
    await observer.feed(b'[{"type":"message"}')
    before_finish.update({"buffer": observer._buffer, "event_count": sink._event_count})
    await observer.finish()
asyncio.run(main())
sink.finish("worker_failure")
print(json.dumps(before_finish))
''',
    )

    assert report == {"buffer": "", "event_count": 2}
    _, records = _safe_trace_records(trace_dir)
    assert records[-1]["progress_kind"] == "trace_incomplete"
    assert records[-1]["trace_complete"] is False


def test_safe_json_array_observer_reports_exact_event_count(tmp_path: Path) -> None:
    trace_dir = tmp_path / "safe-trace"
    run_bounded_parser_probe(
        trace_dir,
        r'''
import asyncio, json, os
from pathlib import Path
from dsh_runtime.plugins import codebuddy as m
sink = m._SafeCodeBuddyEventSink(Path(os.environ["DSH_TEST_SAFE_TRACE_DIR"]))
observer = m._SafeJsonArrayEventObserver(sink)
events = [{"type":"message"}, {"type":"function_call","name":"Read"}, {"type":"result","subtype":"success","is_error":False}]
async def main():
    await observer.feed(json.dumps(events).encode("utf-8"))
    await observer.finish()
asyncio.run(main())
sink.finish("completed")
print(json.dumps({"ok": True}))
''',
    )

    _, records = _safe_trace_records(trace_dir)
    assert [record["event_seq"] for record in records] == list(range(5))
    assert [record["event_type"] for record in records] == [
        "progress",
        "model_event",
        "tool_call",
        "terminal",
        "terminal",
    ]


def test_safe_json_array_observer_rejects_no_progress_decode(
    monkeypatch, tmp_path: Path
) -> None:
    trace_dir = tmp_path / "safe-trace"
    report = run_bounded_parser_probe(
        trace_dir,
        r'''
import asyncio, json, os
from pathlib import Path
from dsh_runtime.plugins import codebuddy as m
sink = m._SafeCodeBuddyEventSink(Path(os.environ["DSH_TEST_SAFE_TRACE_DIR"]))
observer = m._SafeJsonArrayEventObserver(sink)
calls = []
def no_progress(_buffer):
    calls.append(1)
    return {"type":"message"}, 0
observer._json_decoder.raw_decode = no_progress
asyncio.run(observer.feed(b'[{"type":"message"}]'))
sink.finish("worker_failure")
print(json.dumps({"calls":len(calls),"buffer":observer._buffer,"invalid":observer._invalid_root,"incomplete":sink.incomplete,"event_count":sink._event_count}))
''',
        watchdog=2.0,
    )

    assert report == {
        "calls": 1,
        "buffer": "",
        "invalid": True,
        "incomplete": True,
        "event_count": 2,
    }
    _, records = _safe_trace_records(trace_dir)
    assert records[-1]["trace_complete"] is False


def test_safe_json_array_observer_yields_within_high_volume_feed(
    tmp_path: Path,
) -> None:
    trace_dir = tmp_path / "safe-trace"
    report = run_bounded_parser_probe(
        trace_dir,
        r'''
import asyncio, json, os
from pathlib import Path
from dsh_runtime.plugins import codebuddy as m
sink = m._SafeCodeBuddyEventSink(Path(os.environ["DSH_TEST_SAFE_TRACE_DIR"]))
observer = m._SafeJsonArrayEventObserver(sink)
events = [{"type":"message"} for _ in range(1024)]
raw = json.dumps(events, separators=(",", ":")).encode("utf-8")
assert len(raw) <= 64_000
tick_seen = []
async def tick():
    await asyncio.sleep(0)
    tick_seen.append(True)
async def exercise():
    await asyncio.gather(observer.feed(raw), tick())
    await observer.finish()
asyncio.run(exercise())
sink.finish("completed")
print(json.dumps({"input_bytes":len(raw),"tick_seen":bool(tick_seen),"work_budget_yields":observer.work_budget_yields,"max_batch_work":observer.max_batch_work_observed}))
''',
        watchdog=4.0,
    )

    _, records = _safe_trace_records(trace_dir)
    assert report["input_bytes"] <= 64_000
    assert report["tick_seen"] is True
    assert report["work_budget_yields"] > 0
    assert report["max_batch_work"] <= 128
    assert len(records) == 1026


@pytest.mark.parametrize("quota", ["max_events", "max_bytes"])
def test_safe_trace_sink_quota_stops_growth_and_writes_terminal(
    tmp_path: Path, quota: str
) -> None:
    trace_dir = tmp_path / "safe-trace"
    options = {"max_events": 4} if quota == "max_events" else {
        "max_bytes": 4_096,
        "max_events": 128,
    }
    sink = codebuddy_module._SafeCodeBuddyEventSink(trace_dir.resolve(), **options)

    for _ in range(128):
        sink.emit(
            event_type="progress",
            worker_phase="worker_output",
            progress_kind="synthetic_event",
        )
        if sink._quota_exceeded:
            break

    assert sink._quota_exceeded is True
    size_at_quota = sink.path.stat().st_size
    sink.emit(
        event_type="progress",
        worker_phase="worker_output",
        progress_kind="after_quota",
    )
    assert sink.path.stat().st_size == size_at_quota
    sink.finish("completed")

    path, records = _safe_trace_records(trace_dir)
    byte_limit = options.get("max_bytes", codebuddy_module._SAFE_TRACE_MAX_BYTES)
    event_limit = options.get("max_events", codebuddy_module._SAFE_TRACE_MAX_EVENTS)
    assert path.stat().st_size <= byte_limit
    assert len(records) <= event_limit
    assert records[-1]["event_type"] == "terminal"
    assert records[-1]["progress_kind"] == "trace_quota_exceeded"
    assert records[-1]["trace_quota_exceeded"] is True
    assert records[-1]["trace_complete"] is False


@pytest.mark.parametrize("quota", ["max_events", "max_bytes"])
def test_safe_trace_quota_does_not_change_worker_result(
    monkeypatch, tmp_path: Path, quota: str
) -> None:
    environment = {"CODEBUDDY_TEST_EVENT_COUNT": "256"}
    expected = run(
        plugin(tmp_path, mode="trace-flood", **environment),
        context(tmp_path),
        timeout=4.0,
    )
    if quota == "max_events":
        monkeypatch.setattr(codebuddy_module, "_SAFE_TRACE_MAX_EVENTS", 8)
        quota_args = {"max_events": 8}
    else:
        monkeypatch.setattr(codebuddy_module, "_SAFE_TRACE_MAX_BYTES", 4_096)
        quota_args = {"max_bytes": 4_096}
    trace_dir = tmp_path / "safe-trace"

    result = run_safe_trace_child(
        tmp_path,
        trace_dir=trace_dir,
        mode="trace-flood",
        event_count=256,
        timeout=4.0,
        **quota_args,
    )

    assert (result["success"], result["output"], result["error"], result["stop_reason"]) == (
        expected.success,
        expected.output,
        expected.error,
        expected.stop_reason.value if expected.stop_reason else None,
    )
    path, records = _safe_trace_records(trace_dir)
    if quota == "max_events":
        assert len(records) <= 8
    else:
        assert path.stat().st_size <= 4_096
    assert records[-1]["progress_kind"] == "trace_quota_exceeded"
    assert records[-1]["trace_quota_exceeded"] is True
    assert records[-1]["trace_complete"] is False


def test_safe_event_trace_is_disabled_by_default(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(SAFE_EVENT_TRACE_DIR_ENV, raising=False)

    result = run(plugin(tmp_path), context(tmp_path))

    assert result.success is True
    assert not list(tmp_path.glob("codebuddy-safe-worker-*.jsonl"))


def test_safe_event_trace_streams_only_allowlisted_metadata(
    monkeypatch, tmp_path: Path
) -> None:
    trace_dir = tmp_path / "safe-trace"
    monkeypatch.setenv(SAFE_EVENT_TRACE_DIR_ENV, str(trace_dir))
    sentinel = "DSH_CODEBUDDY_SAFE_TRACE_SECRET_SENTINEL"
    marker = tmp_path / "observed-before-worker-exit.marker"
    capture = tmp_path / "worker-capture.json"
    cb = plugin(
        tmp_path,
        mode="trace-stream",
        capture=capture,
        CODEBUDDY_TEST_WRITE_CONTENT=sentinel,
        CODEBUDDY_TEST_TOOL_OUTPUT=sentinel,
        CODEBUDDY_TEST_STDERR=sentinel,
        CODEBUDDY_TEST_SAFE_TRACE_DIR=str(trace_dir),
        CODEBUDDY_TEST_OBSERVER_MARKER=str(marker),
    )
    ctx = ExecutionContext(
        task_id="safe-trace-test",
        workspace_id="logical.safe-trace",
        goal=f"goal {sentinel}",
        cwd=str(tmp_path),
        allow_workspace_write=True,
    )

    result = run(cb, ctx, {"prompt": f"prompt {sentinel}"}, timeout=4.0)

    assert result.success is True
    assert result.output == "trace final result"
    assert marker.read_text(encoding="utf-8") == "observed"
    captured = json.loads(capture.read_text(encoding="utf-8"))
    argv = captured["argv"]
    assert captured["cwd"] == str(tmp_path.resolve())
    assert captured["safe_trace_dir_visible"] is None
    assert argv[argv.index("--max-turns") + 1] == "12"
    assert "--no-session-persistence" in argv
    assert argv[-1] == f"prompt {sentinel}"

    trace_path, records = _safe_trace_records(trace_dir)
    trace_text = trace_path.read_text(encoding="utf-8")
    assert sentinel not in trace_text
    assert trace_path.name.startswith("codebuddy-safe-worker-")
    assert len(records) == 6
    expected_keys = {
        "schema_version",
        "trace_id",
        "event_seq",
        "captured_at_utc",
        "worker_phase",
        "event_type",
        "turn_index",
        "turn_index_source",
        "tool_name",
        "tool_status",
        "progress_kind",
        "terminal_reason",
        "trace_complete",
    }
    assert all(set(record) == expected_keys for record in records)
    assert [record["event_seq"] for record in records] == list(range(len(records)))
    assert {record["event_type"] for record in records} >= {
        "progress",
        "model_event",
        "tool_call",
        "tool_result",
        "terminal",
    }
    assert all(record["turn_index"] is None for record in records)
    assert all(
        record["turn_index_source"] == "unavailable"
        for record in records
    )
    assert all(record["trace_complete"] is True for record in records)
    assert not any(
        forbidden in record
        for record in records
        for forbidden in {
            "goal",
            "prompt",
            "argv",
            "stdout",
            "stderr",
            "arguments",
            "result",
            "output",
            "message",
            "reasoning",
        }
    )
    write_call = next(record for record in records if record["event_type"] == "tool_call")
    write_result = next(
        record for record in records if record["event_type"] == "tool_result"
    )
    assert write_call["tool_name"] == "Write"
    assert write_call["tool_status"] is None
    assert write_result["tool_name"] == "Write"
    assert write_result["tool_status"] == "completed"
    terminal = [record for record in records if record["event_type"] == "terminal"]
    assert terminal[-1]["terminal_reason"] == "completed"


def test_safe_trace_observer_waits_for_late_final_stdout_byte(tmp_path: Path) -> None:
    """A settled Windows child may expose its last redirected byte late."""
    path = tmp_path / "delayed-stdout.json"
    path.write_bytes(b'[{"type":"message"}')

    class Sink:
        def __init__(self) -> None:
            self.events = []
            self.incomplete = False

        def emit_native_event(self, event) -> None:
            self.events.append(event["type"])

        def mark_incomplete(self) -> None:
            self.incomplete = True

    class ExitedProcess:
        def poll(self) -> int:
            return 0

    async def scenario() -> Sink:
        sink = Sink()
        observer = codebuddy_module._SafeJsonArrayEventObserver(sink)

        async def finish_stdout() -> None:
            await asyncio.sleep(0.025)
            with path.open("ab") as stream:
                stream.write(b"]")

        await asyncio.gather(
            codebuddy_module._observe_stdout_file(
                path, ExitedProcess(), observer, max_bytes=1024,
            ),
            finish_stdout(),
        )
        return sink

    sink = asyncio.run(scenario())
    assert sink.events == ["message"]
    assert sink.incomplete is False


def test_safe_event_trace_records_empty_stdout_max_turns_without_inventing_turns(
    tmp_path: Path,
) -> None:
    trace_dir = tmp_path / "safe-trace"
    capture = tmp_path / "worker-capture.json"
    result = run(
        plugin(
            tmp_path,
            mode="empty-max-turns",
            capture=capture,
            safe_trace_dir=trace_dir,
        ),
        context(tmp_path),
    )

    assert result.success is False
    assert result.error == "CodeBuddy returned empty output: Max turns (12) exceeded"
    captured = json.loads(capture.read_text(encoding="utf-8"))
    assert captured["argv"][captured["argv"].index("--max-turns") + 1] == "12"
    _, records = _safe_trace_records(trace_dir)
    assert [record["event_type"] for record in records] == [
        "progress",
        "terminal",
    ]
    assert records[-1]["terminal_reason"] == "max_turns_exceeded"
    assert records[-1]["turn_index"] is None
    assert records[-1]["turn_index_source"] == "unavailable"


def test_safe_event_trace_handles_unknown_events_without_persisting_payload(
    tmp_path: Path,
) -> None:
    trace_dir = tmp_path / "safe-trace"
    sentinel = "DSH_CODEBUDDY_SAFE_TRACE_SECRET_SENTINEL"
    result = run(
        plugin(
            tmp_path,
            mode="unknown-event",
            safe_trace_dir=trace_dir,
            CODEBUDDY_TEST_UNKNOWN_TYPE=sentinel,
            CODEBUDDY_TEST_UNKNOWN_PAYLOAD=sentinel,
        ),
        context(tmp_path),
    )

    assert result.success is True
    trace_path, records = _safe_trace_records(trace_dir)
    assert sentinel not in trace_path.read_text(encoding="utf-8")
    assert any(record["event_type"] == "unknown" for record in records)
    assert all(record["turn_index"] is None for record in records)


@pytest.mark.parametrize("failure_mode", ["open", "write", "serialize"])
@pytest.mark.parametrize("worker_mode", ["success", "max-turns"])
def test_safe_trace_failure_does_not_change_worker_result(
    monkeypatch, tmp_path: Path, failure_mode: str, worker_mode: str
) -> None:
    expected = run(plugin(tmp_path, mode=worker_mode), context(tmp_path))
    trace_dir = tmp_path / "safe-trace"
    if failure_mode == "open":
        trace_dir.write_text("not a directory", encoding="utf-8")
    elif failure_mode == "write":
        original_write_line = codebuddy_module._SafeCodeBuddyEventSink._write_line
        fail_once = [True]

        def fail_first_write(self, line: str) -> None:
            if fail_once[0]:
                fail_once[0] = False
                raise OSError("synthetic safe sink write failure")
            original_write_line(self, line)

        monkeypatch.setattr(
            codebuddy_module._SafeCodeBuddyEventSink,
            "_write_line",
            fail_first_write,
        )
    else:
        original_encode = codebuddy_module._encode_safe_event_record
        fail_once = [True]

        def fail_first_encode(record) -> str:
            if fail_once[0]:
                fail_once[0] = False
                raise ValueError("synthetic safe sink serialization failure")
            return original_encode(record)

        monkeypatch.setattr(
            codebuddy_module,
            "_encode_safe_event_record",
            fail_first_encode,
        )

    result = run(
        plugin(tmp_path, mode=worker_mode, safe_trace_dir=trace_dir),
        context(tmp_path),
    )

    assert (
        result.success,
        result.output,
        result.error,
        result.stop_reason,
        result.cleanup_error,
    ) == (
        expected.success,
        expected.output,
        expected.error,
        expected.stop_reason,
        expected.cleanup_error,
    )
    if failure_mode != "open":
        _, records = _safe_trace_records(trace_dir)
        assert any(record["trace_complete"] is False for record in records)


def test_safe_trace_opt_in_preserves_worker_environment_and_invocation(
    monkeypatch, tmp_path: Path
) -> None:
    trace_dir = tmp_path / "safe-trace"
    capture = tmp_path / "worker-capture.json"
    monkeypatch.setenv("DSH_SAFE_TRACE_TEST_ENV", "stable")
    monkeypatch.delenv(SAFE_EVENT_TRACE_DIR_ENV, raising=False)
    baseline_plugin = plugin(tmp_path, capture=capture)
    baseline_result = run(
        baseline_plugin, context(tmp_path), {"prompt": "same bounded prompt"}
    )
    baseline_capture = json.loads(capture.read_text(encoding="utf-8"))

    monkeypatch.setenv(SAFE_EVENT_TRACE_DIR_ENV, str(trace_dir))
    monkeypatch.setenv(codebuddy_module.MAX_STREAM_CHARS_ENV, "500000")
    cb = plugin(tmp_path, capture=capture)

    child_environment = cb._environment()
    result = run(cb, context(tmp_path), {"prompt": "same bounded prompt"})
    enabled_capture = json.loads(capture.read_text(encoding="utf-8"))

    assert result.success is True
    assert (
        result.success,
        result.output,
        result.error,
        result.stop_reason,
        result.cleanup_error,
    ) == (
        baseline_result.success,
        baseline_result.output,
        baseline_result.error,
        baseline_result.stop_reason,
        baseline_result.cleanup_error,
    )
    assert cb._command == baseline_plugin._command
    assert SAFE_EVENT_TRACE_DIR_ENV not in child_environment
    assert codebuddy_module.MAX_STREAM_CHARS_ENV not in child_environment
    assert child_environment.get("DSH_SAFE_TRACE_TEST_ENV") == "stable"
    assert baseline_capture["safe_trace_dir_visible"] is None
    assert enabled_capture["safe_trace_dir_visible"] is None
    assert baseline_capture["cwd"] == enabled_capture["cwd"] == str(
        tmp_path.resolve()
    )
    baseline_argv = baseline_capture["argv"][:]
    enabled_argv = enabled_capture["argv"][:]
    settings_index = baseline_argv.index("--settings") + 1
    assert enabled_argv.index("--settings") + 1 == settings_index
    baseline_argv[settings_index] = "<temporary-settings-file>"
    enabled_argv[settings_index] = "<temporary-settings-file>"
    assert baseline_argv == enabled_argv
    assert baseline_capture["settings_data"] == enabled_capture["settings_data"]
    argv = enabled_capture["argv"]
    assert argv[argv.index("--max-turns") + 1] == "12"
    assert argv[argv.index("--output-format") + 1] == "json"
    assert argv[-1] == "same bounded prompt"
    assert result.output == "bounded final assistant result"
    records = list(trace_dir.glob("codebuddy-safe-worker-*.jsonl"))
    assert len(records) == 1


def test_qualification_trace_sink_failure_is_distinct(tmp_path: Path) -> None:
    trace_sink = tmp_path / "trace-file"
    trace_sink.write_text("not a directory", encoding="utf-8")
    result = run(
        plugin(tmp_path, trace_dir=trace_sink),
        context(tmp_path),
    )
    assert result.success is False
    assert result.error.startswith("QUALIFICATION OBSERVABILITY FAILURE:")


def test_qualification_trace_does_not_change_worker_authority_configuration(
    tmp_path: Path,
) -> None:
    trace_dir = tmp_path / "trace"
    result = run(
        plugin(tmp_path, mode="trace-events", trace_dir=trace_dir),
        context(tmp_path, allow_workspace_write=True),
        {"prompt": "authority prompt"},
    )
    assert result.success is True
    trace = json.loads(next(trace_dir.glob("*.json")).read_text(encoding="utf-8"))
    argv = trace["argv"]
    assert argv[argv.index("--max-turns") + 1] == "12"
    assert argv[argv.index("--tools") + 1] == "Read,Edit,Write,Bash"
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert "--allowedTools=Bash(python:*)" in argv
    assert trace["settings"] == {
        "permissions": {
            "defaultMode": "dontAsk",
            "allow": ["Read", "Edit", "Write", "Bash(python:*)"],
        }
    }
    assert trace["allow_workspace_write"] is True


@pytest.mark.parametrize(
    "mode",
    [
        "malformed",
        "missing-final",
        "nested-result",
        "root-object",
        "native-failure",
        "permission-denied",
        "max-turns",
        "false-success",
        "nonzero",
    ],
)
def test_native_failures_never_become_false_success(
    tmp_path: Path, mode: str
) -> None:
    result = run(plugin(tmp_path, mode=mode), context(tmp_path))
    assert result.success is False
    assert result.stop_reason is StopReason.FAILED
    assert result.error
    assert "[{" not in result.error


def test_settings_are_cleaned_on_native_failure(tmp_path: Path) -> None:
    capture = tmp_path / "capture.json"
    result = run(
        plugin(tmp_path, mode="malformed", capture=capture), context(tmp_path)
    )
    assert result.success is False
    assert not Path(json.loads(capture.read_text())["settings"]).exists()


def test_truncated_array_marks_evidence_incomplete_without_changing_result(
    tmp_path: Path,
) -> None:
    expected = run(
        plugin(tmp_path, mode="truncated-array"),
        context(tmp_path),
    )
    trace_dir = tmp_path / "safe-trace"
    result = run(
        plugin(tmp_path, mode="truncated-array", safe_trace_dir=trace_dir),
        context(tmp_path),
    )

    assert (result.success, result.output, result.error, result.stop_reason) == (
        expected.success,
        expected.output,
        expected.error,
        expected.stop_reason,
    )
    _, records = _safe_trace_records(trace_dir)
    assert records[-1]["trace_complete"] is False
    assert records[-1]["progress_kind"] == "trace_incomplete"


def test_normal_completion_does_not_call_forced_cleanup(tmp_path: Path) -> None:
    calls = []

    async def forbidden(*args):
        calls.append(args)
        return None

    with patch(
        "dsh_runtime.plugins.codebuddy._terminate_process_tree", forbidden
    ):
        result = run(plugin(tmp_path), context(tmp_path))
    assert result.success is True
    assert calls == []


def test_timeout_invokes_bounded_cleanup_and_returns_timed_out(
    monkeypatch, tmp_path: Path
) -> None:
    temporary_paths = track_temporary_artifacts(monkeypatch)
    capture = tmp_path / "capture.json"
    result = run(
        plugin(tmp_path, mode="hold", capture=capture), context(tmp_path), timeout=0.05
    )
    assert result.success is False
    assert result.stop_reason is StopReason.TIMED_OUT
    assert result.cleanup_error is None or result.cleanup_error.startswith(
        "RuntimeError: CodeBuddy process-tree cleanup"
    )
    assert not Path(json.loads(capture.read_text())["settings"]).exists()
    assert len(temporary_paths) == 3
    assert all(not path.exists() for path in temporary_paths)


def test_safe_observer_yields_and_cleans_temp_files_on_timeout(
    monkeypatch, tmp_path: Path,
) -> None:
    temporary_paths = track_temporary_artifacts(monkeypatch)
    event_count = 4_096
    baseline = run(
        plugin(
            tmp_path,
            mode="trace-flood-hold",
            CODEBUDDY_TEST_EVENT_COUNT=str(event_count),
        ),
        context(tmp_path),
        timeout=0.5,
    )
    trace_dir = tmp_path / "safe-trace"
    result = run_safe_trace_child(
        tmp_path,
        trace_dir=trace_dir,
        mode="trace-flood-hold",
        event_count=event_count,
        timeout=0.5,
        watchdog=4.0,
    )

    assert (result["success"], result["error"], result["stop_reason"]) == (
        baseline.success,
        baseline.error,
        baseline.stop_reason.value if baseline.stop_reason else None,
    )
    assert result["stop_reason"] == StopReason.TIMED_OUT.value
    assert result["temporary_path_count"] == 3
    assert result["temporary_paths_clean"] is True
    assert result["observer_work_budget_yields"] > 0
    assert result["observer_max_batch_work"] <= 128
    assert len(temporary_paths) == 3
    assert all(not path.exists() for path in temporary_paths)
    path, records = _safe_trace_records(trace_dir)
    assert path.stat().st_size <= codebuddy_module._SAFE_TRACE_MAX_BYTES
    assert records[-1]["trace_complete"] is False


def test_stream_json_observer_yields_and_cleans_settings_on_timeout(
    tmp_path: Path,
) -> None:
    trace_dir = tmp_path / "safe-stream-trace"
    result = run_safe_trace_child(
        tmp_path,
        trace_dir=trace_dir,
        mode="stream-flood-hold",
        event_count=2_048,
        timeout=0.5,
        watchdog=4.0,
        stream_json=True,
    )

    assert result["success"] is False
    assert result["stop_reason"] == StopReason.TIMED_OUT.value
    assert result["temporary_path_count"] == 1
    assert result["temporary_suffixes"] == [".json"]
    assert result["temporary_paths_clean"] is True
    assert result["observer_work_budget_yields"] > 0
    assert result["observer_max_batch_work"] <= 128
    path, records = _safe_trace_records(trace_dir)
    assert path.stat().st_size <= codebuddy_module._SAFE_TRACE_MAX_BYTES
    assert len(records) <= codebuddy_module._SAFE_TRACE_MAX_EVENTS
    assert records[-1]["trace_complete"] is False


@pytest.mark.parametrize("stream_json", [False, True])
def test_outer_cancellation_marks_safe_trace_and_cleans_temporary_files(
    monkeypatch, tmp_path: Path, stream_json: bool
) -> None:
    trace_dir = tmp_path / ("safe-stream-trace" if stream_json else "safe-trace")
    capture = tmp_path / "fake-cli-started.json"
    temporary_paths = track_temporary_artifacts(monkeypatch)
    if stream_json:
        monkeypatch.setenv(codebuddy_module.SAFE_STREAM_JSON_ENV, "1")
        cb = _stream_json_plugin(
            tmp_path,
            chunks=[],
            trace_dir=trace_dir,
            capture=capture,
            mode="flood-hold",
            event_count=512,
        )
    else:
        cb = plugin(
            tmp_path,
            mode="trace-flood-hold",
            capture=capture,
            safe_trace_dir=trace_dir,
            CODEBUDDY_TEST_EVENT_COUNT="512",
        )

    async def scenario() -> None:
        registry = PluginRegistry()
        registry.register(cb)
        task = asyncio.create_task(
            Executor(registry).execute(
                "codebuddy", context(tmp_path), {"prompt": "cancel"}, 3.0
            )
        )
        try:
            deadline = asyncio.get_running_loop().time() + 2.0
            while not capture.exists() and asyncio.get_running_loop().time() < deadline:
                if task.done():
                    await task
                    raise AssertionError("fake CodeBuddy did not remain active")
                await asyncio.sleep(0.01)
            assert capture.exists(), "fake CodeBuddy did not start within the bound"
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())

    assert temporary_paths
    assert all(not path.exists() for path in temporary_paths)
    _, records = _safe_trace_records(trace_dir)
    assert records[-1]["event_type"] == "terminal"
    assert records[-1]["terminal_reason"] == "cancelled"
    assert records[-1]["trace_complete"] is False


def test_outer_cancellation_is_repropagated_after_cleanup(
    monkeypatch, tmp_path: Path
) -> None:
    capture = tmp_path / "fake-cli-started.json"
    temporary_paths = track_temporary_artifacts(monkeypatch)

    async def scenario() -> None:
        cb = plugin(tmp_path, mode="hold", capture=capture)
        registry = PluginRegistry()
        registry.register(cb)
        task = asyncio.create_task(
            Executor(registry).execute(
                "codebuddy", context(tmp_path), {"prompt": "cancel"}, 2.0
            )
        )
        try:
            deadline = asyncio.get_running_loop().time() + 1.0
            while not capture.exists() and asyncio.get_running_loop().time() < deadline:
                if task.done():
                    await task
                    raise AssertionError("fake CodeBuddy did not remain active")
                await asyncio.sleep(0.01)
            assert capture.exists(), "fake CodeBuddy did not start within the bound"
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())
    assert len(temporary_paths) == 3
    assert all(not path.exists() for path in temporary_paths)


def test_cleanup_failure_is_observable_without_changing_timeout(
    monkeypatch, tmp_path: Path,
) -> None:
    temporary_paths = track_temporary_artifacts(monkeypatch)
    async def failed_cleanup(*args):
        process = args[0]
        process.kill()
        await asyncio.to_thread(process.wait)
        return "CodeBuddy process-tree cleanup failed: test"

    cb = plugin(tmp_path, mode="hold")
    try:
        with patch(
            "dsh_runtime.plugins.codebuddy._terminate_process_tree", failed_cleanup
        ):
            result = run(cb, context(tmp_path), timeout=0.05)
        assert result.stop_reason is StopReason.TIMED_OUT
        assert result.cleanup_error == (
            "RuntimeError: CodeBuddy process-tree cleanup failed: test"
        )
        assert len(temporary_paths) == 3
        assert all(not path.exists() for path in temporary_paths)
    finally:
        if cb._process is not None:
            cb._process.kill()
            cb._process.wait()


@pytest.mark.skipif(os.name != "nt", reason="CodeBuddy tree cleanup is Windows-specific")
def test_non_successful_tree_termination_is_not_reported_as_success(
    tmp_path: Path,
) -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    class FailedTaskkill:
        returncode = 1

        async def wait(self):
            return self.returncode

    async def fake_create_taskkill(*args, **kwargs):
        return FailedTaskkill()

    async def scenario():
        with patch(
            "dsh_runtime.plugins.codebuddy.asyncio.create_subprocess_exec",
            side_effect=fake_create_taskkill,
        ):
            return await codebuddy_module._terminate_process_tree(process, 0.2)

    try:
        diagnostic = asyncio.run(scenario())
        assert diagnostic is not None
        assert "process-tree cleanup failed" in diagnostic
        assert process.poll() is not None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_outer_cancellation_with_cleanup_failure_remains_cancellation(
    monkeypatch, tmp_path: Path, caplog
) -> None:
    temporary_paths = track_temporary_artifacts(monkeypatch)
    caplog.set_level(logging.INFO, logger="dsh_runtime")
    async def failed_cleanup(*args):
        process = args[0]
        process.kill()
        await asyncio.to_thread(process.wait)
        return "CodeBuddy process-tree cleanup failed: cancellation test"

    async def scenario() -> None:
        cb = plugin(tmp_path, mode="hold")
        registry = PluginRegistry()
        registry.register(cb)
        task = asyncio.create_task(
            Executor(registry).execute(
                "codebuddy", context(tmp_path), {"prompt": "cancel"}, 2.0
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    with patch(
        "dsh_runtime.plugins.codebuddy._terminate_process_tree", failed_cleanup
    ):
        asyncio.run(scenario())
    assert any(
        "plugin_cleanup_failed" in record.getMessage()
        and "cancellation test" in record.getMessage()
        for record in caplog.records
    )
    assert len(temporary_paths) == 3
    assert all(not path.exists() for path in temporary_paths)


@pytest.mark.skipif(os.name != "nt", reason="CodeBuddy tree cleanup is Windows-specific")
def test_windows_cancellation_settles_owned_descendant(
    monkeypatch, tmp_path: Path
) -> None:
    temporary_paths = track_temporary_artifacts(monkeypatch)
    cleanup_results: list[str | None] = []
    original_tree_cleanup = codebuddy_module._terminate_process_tree

    async def track_tree_cleanup(process, grace_seconds):
        result = await original_tree_cleanup(process, grace_seconds)
        cleanup_results.append(result)
        return result

    monkeypatch.setattr(
        codebuddy_module, "_terminate_process_tree", track_tree_cleanup
    )
    child_pid = tmp_path / "child.pid"
    child_marker = tmp_path / "child.started"
    root_marker = tmp_path / "root.pid"
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.GetExitCodeProcess.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    kernel32.GetExitCodeProcess.restype = ctypes.c_int
    kernel32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.TerminateProcess.restype = ctypes.c_int
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    process_handles: list[tuple[str, int]] = []
    cb = plugin(
        tmp_path,
        mode="hold-tree",
        CODEBUDDY_CHILD_PID=str(child_pid),
        CODEBUDDY_CHILD_MARKER=str(child_marker),
        CODEBUDDY_ROOT_MARKER=str(root_marker),
    )

    async def cancel_after_descendant_starts() -> None:
        registry = PluginRegistry()
        registry.register(cb)
        task = asyncio.create_task(
            Executor(registry).execute(
                "codebuddy", context(tmp_path), {"prompt": "cancel tree"}, 5.0
            )
        )
        try:
            deadline = asyncio.get_running_loop().time() + 2.0
            while not child_marker.exists() and asyncio.get_running_loop().time() < deadline:
                if task.done():
                    await task
                    raise AssertionError("worker descendant did not start")
                await asyncio.sleep(0.01)
            assert child_marker.exists(), "worker descendant did not start within the bound"
            assert child_pid.exists() and root_marker.exists()
            child_id = int(child_pid.read_text(encoding="utf-8"))
            root_id = int(root_marker.read_text(encoding="utf-8"))
            for role, pid in (("descendant", child_id), ("root", root_id)):
                handle = kernel32.OpenProcess(0x00101001, False, pid)
                assert handle, f"cannot hold {role} process identity before cancellation"
                process_handles.append((role, handle))
            observed_descendants = codebuddy_module._windows_process_descendants(root_id)
            assert child_id in observed_descendants, (
                "bounded Windows process snapshot missed the started descendant; "
                f"observed_count={len(observed_descendants)}"
            )
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    try:
        asyncio.run(cancel_after_descendant_starts())
        deadline = time.monotonic() + 1.0
        def process_states() -> dict[str, bool]:
            states = {}
            for role, handle in process_handles:
                exit_code = ctypes.c_uint32()
                assert kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                states[role] = exit_code.value == 259
            return states

        while any(process_states().values()) and time.monotonic() < deadline:
            time.sleep(0.01)
        states = process_states()
        assert not any(states.values()), (
            "owned process tree did not settle: "
            f"process_states={states!r}, "
            f"cleanup_results={cleanup_results!r}"
        )
        assert len(temporary_paths) == 3
        assert all(not path.exists() for path in temporary_paths)
    finally:
        for _, handle in process_handles:
            try:
                exit_code = ctypes.c_uint32()
                if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)) and exit_code.value == 259:
                    kernel32.TerminateProcess(handle, 1)
                    kernel32.WaitForSingleObject(handle, 1_000)
            finally:
                kernel32.CloseHandle(handle)


FAKE_STREAM_JSON_CLI = r'''
import json
import os
import sys
import time

argv = sys.argv
capture_path = os.environ.get("DSH_STREAM_TEST_CAPTURE")
if capture_path:
    metadata = {
        "output_format": argv[argv.index("--output-format") + 1],
        "input_format": argv[argv.index("--input-format") + 1],
        "max_turns": argv[argv.index("--max-turns") + 1],
        "print_mode": "--print" in argv,
        "verbose": "--verbose" in argv,
        "partial_messages": "--include-partial-messages" in argv,
        "no_session_persistence": "--no-session-persistence" in argv,
        "tools": argv[argv.index("--tools") + 1],
        "permission_mode": argv[argv.index("--permission-mode") + 1],
        "allowed_tools": next(value for value in argv if value.startswith("--allowedTools=")),
        "model": argv[argv.index("--model") + 1] if "--model" in argv else None,
        "stream_opt_in_visible": "DSH_CODEBUDDY_SAFE_STREAM_JSON" in os.environ,
        "safe_trace_dir_visible": "DSH_CODEBUDDY_SAFE_EVENT_TRACE_DIR" in os.environ,
    }
    settings_path = argv[argv.index("--settings") + 1]
    with open(settings_path, encoding="utf-8") as settings_stream:
        settings = json.load(settings_stream)
    metadata["settings_default_mode"] = settings["permissions"]["defaultMode"]
    metadata["settings_allowlist"] = settings["permissions"]["allow"]
    with open(capture_path, "w", encoding="utf-8") as stream:
        json.dump(metadata, stream)

if os.environ.get("DSH_STREAM_TEST_MODE") == "flood-hold":
    event_count = int(os.environ.get("DSH_STREAM_TEST_EVENT_COUNT", "1024"))
    events = [
        {"type": "assistant", "message": {"content": []}}
        for _ in range(event_count)
    ]
    sys.stdout.write(
        "".join(json.dumps(event, separators=(",", ":")) + "\n" for event in events)
    )
    sys.stdout.flush()
    time.sleep(60)
else:
    for chunk in json.loads(os.environ.get("DSH_STREAM_TEST_CHUNKS", "[]")):
        sys.stdout.buffer.write(chunk.encode("utf-8"))
        sys.stdout.buffer.flush()

stderr_text = os.environ.get("DSH_STREAM_TEST_STDERR", "")
if stderr_text:
    sys.stderr.buffer.write(stderr_text.encode("utf-8"))
    sys.stderr.buffer.flush()

sys.exit(int(os.environ.get("DSH_STREAM_TEST_EXIT", "0")))
'''


def _stream_json_plugin(
    tmp_path: Path,
    *,
    chunks: list[str],
    trace_dir: Path | None = None,
    qualification_trace_dir: Path | None = None,
    capture: Path | None = None,
    stderr: str = "",
    returncode: int = 0,
    max_output_chars: int = 100_000,
    mode: str | None = None,
    event_count: int | None = None,
) -> CodeBuddyPlugin:
    cli_path = tmp_path / "fake_stream_codebuddy.py"
    cli_path.write_text(FAKE_STREAM_JSON_CLI, encoding="utf-8")
    environment = {
        "DSH_STREAM_TEST_CHUNKS": json.dumps(chunks),
        "DSH_STREAM_TEST_STDERR": stderr,
        "DSH_STREAM_TEST_EXIT": str(returncode),
    }
    if mode is not None:
        environment["DSH_STREAM_TEST_MODE"] = mode
    if event_count is not None:
        environment["DSH_STREAM_TEST_EVENT_COUNT"] = str(event_count)
    if capture is not None:
        environment["DSH_STREAM_TEST_CAPTURE"] = str(capture)
    return CodeBuddyPlugin(
        command=(sys.executable, str(cli_path)),
        environment=environment,
        cleanup_grace_seconds=0.2,
        max_output_chars=max_output_chars,
        qualification_trace_dir=qualification_trace_dir,
        safe_event_trace_dir=trace_dir,
    )


def _stream_json_line(event: dict) -> str:
    return json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"


def _stream_success_event(output: str = "stream result") -> dict:
    return {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": output,
    }


def test_stream_json_model_uses_same_cli_flag(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(codebuddy_module.SAFE_STREAM_JSON_ENV, "1")
    capture = tmp_path / "stream-capture.json"
    cb = _stream_json_plugin(
        tmp_path,
        chunks=[_stream_json_line(_stream_success_event())],
        capture=capture,
    )
    result = run(cb, context(tmp_path), {"prompt": "work", "model": "glm-5.3-flash"})
    assert result.success is True
    assert json.loads(capture.read_text(encoding="utf-8"))["model"] == "glm-5.3-flash"


def test_safe_stream_json_opt_in_preserves_invocation_and_discards_raw_stream(
    monkeypatch, tmp_path: Path
) -> None:
    opt_in = codebuddy_module.SAFE_STREAM_JSON_ENV
    monkeypatch.setenv(opt_in, "1")
    trace_dir = tmp_path / "safe-trace"
    raw_trace_dir = tmp_path / "qualification-raw-trace"
    capture = tmp_path / "safe-cli-metadata.json"
    sentinel = "SYNTHETIC_STREAM_PRIVACY_SENTINEL"
    chunks = [
        _stream_json_line({"type": "system", "subtype": "init", "message": sentinel}),
        _stream_json_line(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": sentinel},
                        {
                            "type": "tool_use",
                            "id": "private-tool-id",
                            "name": "Write",
                            "input": {"file_path": "private/path", "content": sentinel},
                        },
                    ]
                },
            }
        ),
        _stream_json_line(
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "private-tool-id",
                            "is_error": False,
                            "content": sentinel,
                        }
                    ]
                },
            }
        ),
        _stream_json_line(_stream_success_event("stream final result")),
    ]
    cb = _stream_json_plugin(
        tmp_path,
        chunks=chunks,
        trace_dir=trace_dir,
        qualification_trace_dir=raw_trace_dir,
        capture=capture,
        stderr=f"{sentinel} on stderr",
    )
    original_mkstemp = codebuddy_module.tempfile.mkstemp
    temp_suffixes: list[str] = []
    original_popen = codebuddy_module.subprocess.Popen
    pipe_configuration: list[tuple[int, int]] = []

    def track_mkstemp(*args, **kwargs):
        temp_suffixes.append(kwargs.get("suffix", ""))
        return original_mkstemp(*args, **kwargs)

    def track_popen(*args, **kwargs):
        pipe_configuration.append((kwargs.get("stdout"), kwargs.get("stderr")))
        return original_popen(*args, **kwargs)

    monkeypatch.setattr(codebuddy_module.tempfile, "mkstemp", track_mkstemp)
    monkeypatch.setattr(codebuddy_module.subprocess, "Popen", track_popen)
    result = run(cb, context(tmp_path), timeout=4.0)

    assert result.success is True
    assert result.output == "stream final result"
    assert temp_suffixes == [".json"]
    assert pipe_configuration == [(subprocess.PIPE, subprocess.PIPE)]
    assert not raw_trace_dir.exists()
    invocation = json.loads(capture.read_text(encoding="utf-8"))
    assert invocation == {
        "output_format": "stream-json",
        "input_format": "text",
        "max_turns": "12",
        "print_mode": True,
        "verbose": False,
        "partial_messages": False,
        "no_session_persistence": True,
        "tools": "Read,Edit,Write,Bash",
        "permission_mode": "dontAsk",
        "allowed_tools": "--allowedTools=Bash(python:*)",
        "model": None,
        "stream_opt_in_visible": False,
        "safe_trace_dir_visible": False,
        "settings_default_mode": "dontAsk",
        "settings_allowlist": ["Read", "Edit", "Write", "Bash(python:*)"],
    }
    trace_path, records = _safe_trace_records(trace_dir)
    trace_text = trace_path.read_text(encoding="utf-8")
    assert sentinel not in trace_text
    assert "private-tool-id" not in trace_text
    assert "private/path" not in trace_text
    assert str(tmp_path) not in trace_text
    assert all(record["turn_index"] is None for record in records)
    assert all(record["turn_index_source"] == "unavailable" for record in records)
    assert [record["event_seq"] for record in records] == list(range(len(records)))
    assert all(
        record["trace_complete_scope"] == "observable_stream_lifecycle_only"
        for record in records
    )
    assert records[-1]["trace_complete"] is True
    call_record = next(record for record in records if record["event_type"] == "tool_call")
    result_record = next(record for record in records if record["event_type"] == "tool_result")
    assert (call_record["tool_name"], call_record["tool_status"]) == ("Write", "running")
    assert (result_record["tool_name"], result_record["tool_status"]) == (
        "Write",
        "completed",
    )
    identity = records[0]["cli_identity"]
    assert identity["executable_category"] == "python"
    assert identity["package"] == "unavailable"
    assert identity["version"] == "unavailable"
    assert "executable_basename" in identity


def test_safe_stream_json_disabled_keeps_default_json_invocation(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(codebuddy_module.SAFE_STREAM_JSON_ENV, raising=False)
    capture = tmp_path / "default-cli-metadata.json"
    result = run(
        plugin(tmp_path, mode="success", capture=capture),
        context(tmp_path),
    )

    assert result.success is True
    invocation = json.loads(capture.read_text(encoding="utf-8"))
    assert invocation["argv"][invocation["argv"].index("--output-format") + 1] == "json"
    assert invocation["argv"][invocation["argv"].index("--max-turns") + 1] == "12"


def test_stream_json_parser_handles_single_multiple_split_and_crlf_lines() -> None:
    collector = codebuddy_module._StreamJsonResultCollector(100_000)
    parser = codebuddy_module._StreamJsonLineParser(
        collector, None, None, max_line_chars=100_000
    )
    raw = (
        _stream_json_line({"type": "system", "subtype": "init"}).replace("\n", "\r\n")
        + _stream_json_line(
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "x"}]}}
        )
        + _stream_json_line(_stream_success_event("split result"))
    ).encode("utf-8")
    split_points = (3, len(raw) // 3, (len(raw) * 2) // 3)
    start = 0

    async def feed_chunks() -> None:
        nonlocal start
        for end in split_points + (len(raw),):
            await parser.feed(raw[start:end])
            start = end
        await parser.finish()

    asyncio.run(feed_chunks())

    result = collector.normalize(b"", 0)
    assert result.success is True
    assert result.output == "split result"
    assert collector.valid_event_count == 3
    assert parser.closed_cleanly is True


def test_stream_json_parser_keeps_success_when_system_init_arrives_after_result() -> None:
    collector = codebuddy_module._StreamJsonResultCollector(100_000)
    parser = codebuddy_module._StreamJsonLineParser(
        collector, None, None, max_line_chars=100_000
    )
    raw = (
        _stream_json_line(_stream_success_event("late init still succeeds"))
        + _stream_json_line({"type": "system", "subtype": "init"})
    ).encode("utf-8")

    async def feed_events() -> None:
        await parser.feed(raw)
        await parser.finish()

    asyncio.run(feed_events())

    result = collector.normalize(b"", 0)
    assert result.success is True
    assert result.output == "late init still succeeds"
    assert collector.valid_event_count == 2
    assert collector.last_event_type == "result"
    assert parser.closed_cleanly is True


def test_stream_output_bound_failure_reports_bounded_non_content_counters() -> None:
    collector = codebuddy_module._StreamJsonResultCollector(
        max_output_chars=100,
        max_stream_chars=16,
    )
    collector.observe_text("x" * 17)
    collector.accept(_stream_success_event("private final output"))

    result = collector.normalize(b"", 0)

    assert result.success is False
    assert result.error is not None
    assert "CodeBuddy output exceeded the configured bound" in result.error
    assert "limit_chars=16" in result.error
    assert "observed_chars=17" in result.error
    assert "valid_events=1" in result.error
    assert "result_seen=true" in result.error
    assert "result_chars=20" in result.error
    assert "last_event_type_present=true" in result.error
    assert "private final output" not in result.error


def test_stream_json_parser_yields_and_caps_trace_on_high_volume_input(
    tmp_path: Path,
) -> None:
    trace_dir = tmp_path / "safe-trace"
    report = run_bounded_parser_probe(
        trace_dir,
        r'''
import asyncio, json, os
from pathlib import Path
from dsh_runtime.plugins import codebuddy as m
trace_dir = Path(os.environ["DSH_TEST_SAFE_TRACE_DIR"])
sink = m._SafeCodeBuddyEventSink(trace_dir, max_events=64)
observer = m._SafeStreamJsonEventObserver(sink)
collector = m._StreamJsonResultCollector(100000)
parser = m._StreamJsonLineParser(collector, observer, sink, max_line_chars=100000)
events = [{"type":"assistant","message":{"content":[]}} for _ in range(1024)]
events.append({"type":"result","subtype":"success","is_error":False,"result":"bounded stream result"})
raw = "".join(json.dumps(event,separators=(",",":"))+"\n" for event in events).encode("utf-8")
assert len(raw) <= 100_000
tick_seen = []
async def parse_all():
    for offset in range(0, len(raw), m._STREAM_JSON_READ_CHUNK):
        await parser.feed(raw[offset:offset+m._STREAM_JSON_READ_CHUNK])
    await parser.finish()
async def tick():
    await asyncio.sleep(0)
    tick_seen.append(True)
async def main():
    await asyncio.gather(parse_all(), tick())
asyncio.run(main())
result = collector.normalize(b"", 0)
sink.finish("completed")
print(json.dumps({"success":result.success,"output":result.output,"input_bytes":len(raw),"valid_event_count":collector.valid_event_count,"tick_seen":bool(tick_seen),"work_budget_yields":parser.work_budget_yields,"max_batch_work":parser.max_batch_work_observed,"sink_events":sink._event_count,"quota_exceeded":sink._quota_exceeded}))
''',
        watchdog=5.0,
    )

    path, records = _safe_trace_records(trace_dir)
    assert report["success"] is True
    assert report["output"] == "bounded stream result"
    assert report["input_bytes"] <= 100_000
    assert report["valid_event_count"] == 1_025
    assert report["tick_seen"] is True
    assert report["work_budget_yields"] > 0
    assert report["max_batch_work"] <= 128
    assert report["quota_exceeded"] is True
    assert report["sink_events"] <= 64
    assert len(records) <= 64
    assert path.stat().st_size <= codebuddy_module._SAFE_TRACE_MAX_BYTES
    assert records[-1]["progress_kind"] == "trace_quota_exceeded"


def test_stream_json_oversized_line_is_bounded_and_evidence_only(
    tmp_path: Path,
) -> None:
    trace_dir = tmp_path / "safe-trace"
    report = run_bounded_parser_probe(
        trace_dir,
        r'''
import asyncio, json, os
from pathlib import Path
from dsh_runtime.plugins import codebuddy as m
sink = m._SafeCodeBuddyEventSink(Path(os.environ["DSH_TEST_SAFE_TRACE_DIR"]))
observer = m._SafeStreamJsonEventObserver(sink)
collector = m._StreamJsonResultCollector(10000)
parser = m._StreamJsonLineParser(collector, observer, sink, max_line_chars=128)
raw = (json.dumps({"type":"assistant","message":"x"*2048})+"\n"+json.dumps({"type":"result","subtype":"success","is_error":False,"result":"kept"})+"\n").encode("utf-8")
async def main():
    await parser.feed(raw)
    await parser.finish()
asyncio.run(main())
result = collector.normalize(b"", 0)
sink.finish("completed")
print(json.dumps({"success":result.success,"output":result.output,"buffer_chars":len(parser._buffer),"discarding_line":parser._discarding_line,"trace_incomplete":sink.incomplete}))
''',
    )

    _, records = _safe_trace_records(trace_dir)
    assert report == {
        "success": True,
        "output": "kept",
        "buffer_chars": 0,
        "discarding_line": False,
        "trace_incomplete": True,
    }
    assert records[-1]["trace_complete"] is False


def test_stream_json_tool_correlation_map_has_hard_bound(tmp_path: Path) -> None:
    trace_dir = tmp_path / "safe-trace"
    sink = codebuddy_module._SafeCodeBuddyEventSink(trace_dir.resolve())
    observer = codebuddy_module._SafeStreamJsonEventObserver(sink)
    blocks = [
        {"type": "tool_use", "id": f"synthetic-tool-{index}", "name": "Read"}
        for index in range(codebuddy_module._STREAM_JSON_MAX_TOOL_CORRELATIONS + 44)
    ]

    observer.observe({"type": "assistant", "message": {"content": blocks}})
    sink.finish("completed")

    trace_path, records = _safe_trace_records(trace_dir)
    assert len(observer._tool_names_by_id) == (
        codebuddy_module._STREAM_JSON_MAX_TOOL_CORRELATIONS
    )
    assert sink.incomplete is True
    assert "synthetic-tool-" not in trace_path.read_text(encoding="utf-8")
    assert len(records) <= codebuddy_module._SAFE_TRACE_MAX_EVENTS


def test_stream_json_malformed_event_isolated_and_marks_trace_incomplete(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(codebuddy_module.SAFE_STREAM_JSON_ENV, "1")
    trace_dir = tmp_path / "safe-trace"
    chunks = [
        "{malformed event}\n",
        _stream_json_line(_stream_success_event("still successful")),
    ]
    result = run(
        _stream_json_plugin(tmp_path, chunks=chunks, trace_dir=trace_dir),
        context(tmp_path),
    )

    assert result.success is True
    _, records = _safe_trace_records(trace_dir)
    assert records[-1]["trace_complete"] is False
    assert records[-1]["progress_kind"] == "trace_incomplete"


def test_stream_json_incomplete_eof_is_evidence_incomplete(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(codebuddy_module.SAFE_STREAM_JSON_ENV, "1")
    trace_dir = tmp_path / "safe-trace"
    result = run(
        _stream_json_plugin(
            tmp_path,
            chunks=[_stream_json_line({"type": "system", "subtype": "init"}), '{"type":"assistant"'],
            trace_dir=trace_dir,
        ),
        context(tmp_path),
    )

    assert result.success is False
    assert "malformed JSON output" in (result.error or "")
    _, records = _safe_trace_records(trace_dir)
    assert records[-1]["trace_complete"] is False


def test_stream_json_tool_results_are_correlated_only_in_memory_and_ordered(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(codebuddy_module.SAFE_STREAM_JSON_ENV, "1")
    trace_dir = tmp_path / "safe-trace"
    secret = "SYNTHETIC_TOOL_RESULT_SECRET"
    chunks = [
        _stream_json_line(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "id": "id-read", "name": "Read", "input": {"path": secret}},
                        {"type": "tool_use", "id": "id-write", "name": "Write", "input": {"content": secret}},
                    ]
                },
            }
        ),
        _stream_json_line(
            {
                "type": "user",
                "message": {
                    "content": [
                        {"type": "tool_result", "tool_use_id": "id-write", "is_error": False, "content": secret},
                        {"type": "tool_result", "tool_use_id": "id-read", "is_error": False, "content": secret},
                    ]
                },
            }
        ),
        _stream_json_line(_stream_success_event()),
    ]
    result = run(
        _stream_json_plugin(tmp_path, chunks=chunks, trace_dir=trace_dir),
        context(tmp_path),
    )

    assert result.success is True
    trace_path, records = _safe_trace_records(trace_dir)
    assert secret not in trace_path.read_text(encoding="utf-8")
    assert "id-read" not in trace_path.read_text(encoding="utf-8")
    assert "id-write" not in trace_path.read_text(encoding="utf-8")
    calls = [record["tool_name"] for record in records if record["event_type"] == "tool_call"]
    results = [record["tool_name"] for record in records if record["event_type"] == "tool_result"]
    assert calls == ["Read", "Write"]
    assert results == ["Write", "Read"]
    assert all(
        record["tool_status"] == "completed"
        for record in records
        if record["event_type"] == "tool_result"
    )


def test_stream_json_tool_error_and_unknown_result_stay_safe(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(codebuddy_module.SAFE_STREAM_JSON_ENV, "1")
    trace_dir = tmp_path / "safe-trace"
    secret = "SYNTHETIC_UNKNOWN_TOOL_SECRET"
    chunks = [
        _stream_json_line(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "id": "unknown-id", "name": "UnlistedTool", "input": secret},
                        {"type": "tool_use", "id": "known-id", "name": "Bash", "input": {"command": secret}},
                    ]
                },
            }
        ),
        _stream_json_line(
            {
                "type": "user",
                "message": {
                    "content": [
                        {"type": "tool_result", "tool_use_id": "unmatched-id", "is_error": False, "content": secret},
                        {"type": "tool_result", "tool_use_id": "known-id", "is_error": True, "content": secret},
                    ]
                },
            }
        ),
        _stream_json_line(_stream_success_event()),
    ]
    result = run(
        _stream_json_plugin(tmp_path, chunks=chunks, trace_dir=trace_dir),
        context(tmp_path),
    )

    assert result.success is False
    assert result.error == "CodeBuddy native tool failed: native tool error"
    trace_path, records = _safe_trace_records(trace_dir)
    trace_text = trace_path.read_text(encoding="utf-8")
    assert secret not in trace_text
    assert "unknown-id" not in trace_text
    assert "unmatched-id" not in trace_text
    tool_records = [
        record for record in records if record["event_type"] in {"tool_call", "tool_result"}
    ]
    assert [(record["event_type"], record["tool_name"], record["tool_status"]) for record in tool_records] == [
        ("tool_call", "Bash", "running"),
        ("tool_result", None, "completed"),
        ("tool_result", "Bash", "error"),
    ]


@pytest.mark.parametrize(
    ("chunks", "stderr", "returncode", "expected_error"),
    [
        ([], "empty diagnostic", 0, "CodeBuddy returned empty output: empty diagnostic"),
        ([], "process diagnostic", 9, "CodeBuddy process exited with code 9: process diagnostic"),
        (
            [_stream_json_line({"type": "result", "subtype": "error_max_turns", "is_error": True, "result": "Max turns (12) exceeded"})],
            "",
            0,
            "CodeBuddy native session failed: Max turns (12) exceeded",
        ),
        (
            [_stream_json_line({"type": "result", "subtype": "error_during_execution", "is_error": True, "error": "synthetic result error"})],
            "",
            0,
            "CodeBuddy native session failed: synthetic result error",
        ),
    ],
)
def test_stream_json_terminal_failures_keep_runtime_normalization(
    monkeypatch,
    tmp_path: Path,
    chunks: list[str],
    stderr: str,
    returncode: int,
    expected_error: str,
) -> None:
    monkeypatch.setenv(codebuddy_module.SAFE_STREAM_JSON_ENV, "1")
    result = run(
        _stream_json_plugin(
            tmp_path, chunks=chunks, stderr=stderr, returncode=returncode
        ),
        context(tmp_path),
    )

    assert result.success is False
    assert result.error == expected_error


@pytest.mark.parametrize(
    "failure_mode", ["sink_open", "sink_write", "sink_serialize", "observer"]
)
def test_stream_json_observability_failures_do_not_change_worker_result(
    monkeypatch, tmp_path: Path, failure_mode: str
) -> None:
    monkeypatch.setenv(codebuddy_module.SAFE_STREAM_JSON_ENV, "1")
    trace_dir = tmp_path / "safe-trace"
    chunks = [_stream_json_line(_stream_success_event("stable worker result"))]
    expected = run(
        _stream_json_plugin(tmp_path, chunks=chunks),
        context(tmp_path),
    )
    if failure_mode == "sink_open":
        trace_dir.write_text("not a directory", encoding="utf-8")
    elif failure_mode == "sink_write":
        def fail_write(self, line: str) -> None:
            raise OSError("synthetic safe sink failure")

        monkeypatch.setattr(
            codebuddy_module._SafeCodeBuddyEventSink, "_write_line", fail_write
        )
    elif failure_mode == "sink_serialize":
        def fail_encode(record) -> str:
            raise ValueError("synthetic safe serialization failure")

        monkeypatch.setattr(codebuddy_module, "_encode_safe_event_record", fail_encode)
    else:
        def fail_observe(self, event) -> None:
            raise RuntimeError("synthetic safe observer parser failure")

        monkeypatch.setattr(
            codebuddy_module._SafeStreamJsonEventObserver, "observe", fail_observe
        )

    result = run(
        _stream_json_plugin(tmp_path, chunks=chunks, trace_dir=trace_dir),
        context(tmp_path),
    )

    assert (result.success, result.output, result.error, result.cleanup_error) == (
        expected.success,
        expected.output,
        expected.error,
        expected.cleanup_error,
    )
    if failure_mode == "observer":
        _, records = _safe_trace_records(trace_dir)
        assert records[-1]["trace_complete"] is False
