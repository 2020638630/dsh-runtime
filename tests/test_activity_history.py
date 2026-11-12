import asyncio
import io
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from dsh_runtime.observability.activity import (
    PREFIX, STREAM_ENV, activity_stream, invocation_activity, record_activity,
)

RUN = "dsh-runtime-11111111-2222-4333-8444-555555555555"
STREAM = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"


def configure(monkeypatch):
    pipe = io.StringIO()
    monkeypatch.setenv("DSH_RUNTIME_RUN_ID", RUN)
    monkeypatch.setenv(STREAM_ENV, STREAM)
    monkeypatch.setattr("sys.stderr", pipe)
    return pipe


def frames(pipe):
    return [json.loads(line.removeprefix(PREFIX)) for line in pipe.getvalue().splitlines()]


def test_order_and_role_binding_across_tasks_threads_and_closed_scope(monkeypatch):
    pipe = configure(monkeypatch)

    async def run():
        gate = asyncio.Event()

        async def late():
            await gate.wait()
            record_activity("codex", "tool", "completed", "commandExecution")

        with invocation_activity("parent", "worker", "codex", 1):
            child = asyncio.create_task(late())
            await asyncio.to_thread(record_activity, "codex", "tool", "called", "commandExecution")
            await asyncio.sleep(0)
            record_activity("codex", "tool", "completed", "commandExecution")
        with invocation_activity("parent", "reviewer", "codex", 2):
            gate.set()
            await child
            record_activity("codex", "message", "observed")
            record_activity("codebuddy", "message", "observed")  # wrong adapter
            record_activity("codex", "tool", "called", "SECRET command")
    with activity_stream("parent"):
        import os
        assert STREAM_ENV not in os.environ
        asyncio.run(run())
    values = frames(pipe)
    assert values[0]["type"] == "begin"
    events, end = values[1:-1], values[-1]
    assert [event["seq"] for event in events] == list(range(1, len(events) + 1))
    assert [event["role"] for event in events] == ["worker"] * 4 + ["reviewer"] * 3
    assert events[0]["invocationId"] != events[4]["invocationId"]
    assert events[0]["streamId"] == STREAM
    assert end["lastSeq"] == len(events) and end["dropped"] == 1
    assert "SECRET" not in pipe.getvalue()


def test_codex_source_observes_fast_tools_without_latest_activity_throttle(monkeypatch):
    from dsh_runtime.plugins.codex import _CodexSession
    pipe = configure(monkeypatch)
    session = object.__new__(_CodexSession)
    session.thread_id, session.turn_id = "thread", "turn"
    session.workspace_id, session.safe_trace = "parent", None
    session._last_live_tool_at, session.max_output_chars = 0, 1000
    with activity_stream("parent"), invocation_activity("parent", "inspector", "codex", 1):
        for method, status in [("item/started", "inProgress"), ("item/completed", "completed")]:
            session.handle_notification({"method": method, "params": {
                "threadId": "thread", "turnId": "turn", "item": {
                    "type": "commandExecution", "status": status, "command": "SECRET", "output": "private"}}})
        session.handle_notification({"method": "item/completed", "params": {
            "threadId": "thread", "turnId": "turn", "item": {
                "type": "reasoning", "text": "PRIVATE THOUGHT"}}})
        session.handle_notification({"method": "item/completed", "params": {
            "threadId": "thread", "turnId": "turn", "item": {
                "type": "agentMessage", "phase": "commentary", "text": "PUBLIC MESSAGE"}}})
    tools = [event for event in frames(pipe) if event.get("kind") == "tool"]
    assert [event["status"] for event in tools] == ["called", "completed"]
    assert len([event for event in frames(pipe) if event.get("kind") == "message"]) == 1
    assert all(secret not in pipe.getvalue() for secret in ["SECRET", "private", "PRIVATE THOUGHT", "PUBLIC MESSAGE"])


def test_codebuddy_and_api_source_metadata_never_contains_body_or_arguments(monkeypatch, tmp_path):
    from dsh_runtime.plugins.codebuddy import _SafeCodeBuddyEventSink, _SafeStreamJsonEventObserver
    from dsh_runtime.plugins.api_agent import _AuditedReadBroker
    pipe = configure(monkeypatch)
    with activity_stream("parent"):
        with invocation_activity("parent", "worker", "codebuddy", 1):
            sink = _SafeCodeBuddyEventSink(tmp_path)
            observer = _SafeStreamJsonEventObserver(sink)
            observer.observe({"type": "assistant", "message": {"content": [
                {"type": "thinking", "thinking": "SECRET thought"},
                {"type": "text", "text": "SECRET message"},
                {"type": "tool_use", "name": "Read", "id": "1", "input": {"path": "SECRET"}},
            ]}})
            observer.observe({"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "1", "is_error": False, "content": "SECRET result"}]}})
            sink.finish("completed")
        async def api():
            async def read(name, arguments):
                return "SECRET content"
            broker = _AuditedReadBroker(SimpleNamespace(execute=read), SimpleNamespace(task_id="task", workspace_id="parent"), None)
            with invocation_activity("parent", "reviewer", "api_agent", 2):
                assert await broker.execute("read_file", {"path": "SECRET"}) == "SECRET content"
        asyncio.run(api())
    assert "SECRET" not in pipe.getvalue()
    events = frames(pipe)
    assert any(event.get("adapter") == "codebuddy" and event.get("tool") == "Read" for event in events)
    assert [event["status"] for event in events if event.get("adapter") == "api_agent" and event.get("kind") == "tool"] == ["called", "completed"]


def test_optional_observation_failure_and_cancel_do_not_change_execution(monkeypatch):
    pipe = configure(monkeypatch)
    async def cancelled():
        with invocation_activity("parent", "inspector", "codex", 1):
            raise asyncio.CancelledError
    with activity_stream("parent"):
        try:
            asyncio.run(cancelled())
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("Cancellation was swallowed")
    assert frames(pipe)[-2]["status"] == "interrupted"
    pipe = configure(monkeypatch)
    class Broken:
        def write(self, _):
            raise RuntimeError("broken optional observer")
        def flush(self):
            pass
    monkeypatch.setattr("sys.stderr", Broken())
    with activity_stream("parent"), invocation_activity("parent", "worker", "codex", 1):
        record_activity("codex", "message", "observed")


def test_host_stream_identity_is_not_forwarded_to_native_clis(monkeypatch):
    from dsh_runtime.plugins.codex import CodexPlugin
    from dsh_runtime.plugins.codebuddy import CodeBuddyPlugin
    monkeypatch.setenv(STREAM_ENV, STREAM)
    # This tests environment filtering, not discovery or execution of installed CLIs.
    for plugin in [
        CodexPlugin(command=(sys.executable,), environment={STREAM_ENV: "overlay"}),
        CodeBuddyPlugin(command=(sys.executable,), environment={STREAM_ENV: "overlay"}),
    ]:
        assert STREAM_ENV not in plugin._environment()


def test_backpressure_is_bounded_and_reports_queue_loss_without_holding_scope(monkeypatch):
    from dsh_runtime.observability.activity import _writer
    entered, release = threading.Event(), threading.Event()
    lines = []
    class SlowPipe:
        def write(self, line):
            entered.set()
            release.wait(3)
            lines.append(line)
        def flush(self):
            pass
    configure(monkeypatch)
    monkeypatch.setattr("sys.stderr", SlowPipe())
    started = time.monotonic()
    try:
        with activity_stream("parent"):
            writer = _writer.get()
            assert entered.wait(1)
            with invocation_activity("parent", "worker", "codex", 1):
                for _ in range(1000):
                    record_activity("codex", "tool", "completed", "commandExecution")
            assert len(writer.queue) <= 63
            assert writer.queued_bytes <= 30 * 1024
        assert time.monotonic() - started < 0.8
        assert writer.sender.is_alive()
    finally:
        release.set()
        writer.sender.join(2)
    assert not writer.sender.is_alive()
    end = json.loads(lines[-1].removeprefix(PREFIX))
    assert end["type"] == "end" and end["lastSeq"] == 1002 and end["dropped"] > 0


def test_real_undrained_stderr_pipe_does_not_block_process_settlement(tmp_path):
    script = tmp_path / "blocked_host.py"
    script.write_text(
        "from dsh_runtime.observability.activity import activity_stream,invocation_activity,record_activity\n"
        "with activity_stream('parent'):\n"
        " with invocation_activity('parent','inspector','codex',1):\n"
        "  for _ in range(20000): record_activity('codex','tool','completed','commandExecution')\n"
        "print('settled')\n", encoding="utf-8")
    process = subprocess.Popen([sys.executable, str(script)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
             "PYTHONDONTWRITEBYTECODE": "1", "DSH_RUNTIME_RUN_ID": RUN, STREAM_ENV: STREAM})
    try:
        # Deliberately do not drain either pipe before exit.
        assert process.wait(timeout=3) == 0
        assert process.stdout.read().strip() == b"settled"
        observed = process.stderr.read()
        assert b'"type":"end"' not in observed
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        process.stdout.close()
        process.stderr.close()
