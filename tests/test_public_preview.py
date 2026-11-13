"""C1 synthetic sources only: never starts a CLI or model."""
import asyncio
import io
import json
from types import SimpleNamespace

import pytest

from dsh_runtime.observability import activity, public_preview as preview
from dsh_runtime.plugins.codex import _CodexSession, CodexPlugin
from dsh_runtime.plugins.codebuddy import CodeBuddyPlugin

RUN = 'dsh-runtime-11111111-2222-4333-8444-555555555555'
STREAM = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'


def configure(monkeypatch, enabled=True):
    pipe = io.StringIO()
    monkeypatch.setattr('sys.stderr', pipe)
    monkeypatch.setenv('DSH_RUNTIME_RUN_ID', RUN)
    monkeypatch.setenv(activity.STREAM_ENV, STREAM)
    if enabled:
        monkeypatch.setenv(preview.STREAM_ENV, STREAM)
    else:
        monkeypatch.delenv(preview.STREAM_ENV, raising=False)
    return pipe


def frames(pipe, prefix=preview.PREFIX):
    return [json.loads(line[len(prefix):]) for line in pipe.getvalue().splitlines() if line.startswith(prefix)]


def session():
    value = object.__new__(_CodexSession)
    value.thread_id, value.turn_id = 'thread', 'turn'
    value.workspace_id, value.safe_trace = 'parent', None
    value._last_live_tool_at, value.max_output_chars = 0, 100_000
    return value


def notification(value, item_id='item-1', text='public commentary', method='item/completed',
                 kind='agentMessage', phase='commentary', thread='thread', turn='turn'):
    value.handle_notification({'method': method, 'params': {'threadId': thread, 'turnId': turn,
        'item': {'id': item_id, 'type': kind, 'phase': phase, 'text': text, 'status': 'completed'}}})


def test_only_completed_matching_known_turn_commentary_and_no_body_in_activity(monkeypatch):
    pipe = configure(monkeypatch)
    value = session()
    with activity.activity_stream('parent'), preview.public_preview_stream('parent'):
        with activity.invocation_activity('parent', 'worker', 'codex', 1):
            notification(value, method='item/started', text='started body')
            notification(value, method='item/agentMessage/delta', text='delta body')
            notification(value, kind='reasoning', text='reasoning body')
            notification(value, phase='final_answer', text='final body')
            notification(value, phase=None, text='unphased body')
            notification(value, thread='other', text='foreign thread')
            notification(value, turn='other', text='foreign turn')
            value.turn_id = None
            notification(value, text='turn not yet bound')
            value.turn_id = 'turn'
            notification(value)
            notification(value)  # same completed item is deduplicated
    messages = [v for v in frames(pipe) if v['type'] == 'message']
    assert [v['text'] for v in messages] == ['public commentary']
    assert all('text' not in v for v in frames(pipe, activity.PREFIX))
    assert 'public commentary' not in json.dumps(frames(pipe, activity.PREFIX))
    for body in ['started body', 'delta body', 'reasoning body', 'final body', 'unphased body',
                 'foreign thread', 'foreign turn', 'turn not yet bound']:
        assert body not in pipe.getvalue()


@pytest.mark.parametrize('role,adapter,index', [('reviewer','codex',1), ('inspector','codex',1),
    ('worker','codebuddy',1), ('worker','codex',2), (None,'codex',1)])
def test_role_adapter_and_index_must_all_match(monkeypatch, role, adapter, index):
    pipe = configure(monkeypatch)
    with activity.activity_stream('parent'), preview.public_preview_stream('parent'):
        with activity.invocation_activity('parent', role, adapter, index):
            notification(session(), text='excluded')
    assert not [v for v in frames(pipe) if v['type'] == 'message']
    assert 'excluded' not in pipe.getvalue()


def test_old_host_no_capability_no_preview_bytes(monkeypatch):
    pipe = configure(monkeypatch, enabled=False)
    with activity.activity_stream('parent'), preview.public_preview_stream('parent'):
        with activity.invocation_activity('parent', 'worker', 'codex', 1):
            notification(session(), text='not enabled')
    assert frames(pipe) == []
    assert 'not enabled' not in pipe.getvalue()


@pytest.mark.parametrize('plugin_type', [CodexPlugin, CodeBuddyPlugin])
def test_capability_stripped_even_from_environment_overlay(monkeypatch, plugin_type):
    monkeypatch.setenv(preview.STREAM_ENV, STREAM)
    plugin = object.__new__(plugin_type)
    plugin._environment_overlay = {preview.STREAM_ENV: STREAM, 'NORMAL_TEST_VALUE': 'keep'}
    env = plugin._environment()
    assert preview.STREAM_ENV not in env
    assert env['NORMAL_TEST_VALUE'] == 'keep'


def test_unicode_bound_plain_text_and_dedup(monkeypatch):
    pipe = configure(monkeypatch)
    text = '<script>alert(1)</script> [link](https://example.invalid)\n' + '中🙂' * 1000
    with activity.activity_stream('parent'), preview.public_preview_stream('parent'):
        with activity.invocation_activity('parent', 'worker', 'codex', 1):
            notification(session(), text=text)
            notification(session(), text='replacement body')
    messages = [v for v in frames(pipe) if v['type'] == 'message']
    assert len(messages) == 1
    value = messages[0]
    assert value['truncated'] is True
    assert len(value['text'].encode('utf-8')) <= preview.MAX_TEXT_BYTES
    assert value['text'].startswith('<script>alert(1)</script> [link]')
    assert '\ufffd' not in value['text']
    assert 'replacement body' not in pipe.getvalue()
    assert all(len(line.encode()) <= 4096 for line in pipe.getvalue().splitlines() if line.startswith(preview.PREFIX))


def test_copied_async_scope_cannot_emit_after_worker_return(monkeypatch):
    pipe = configure(monkeypatch)
    async def run():
        gate = asyncio.Event()
        async def late():
            await gate.wait()
            notification(session(), text='late body')
        with activity.invocation_activity('parent', 'worker', 'codex', 1):
            child = asyncio.create_task(late())
        gate.set()
        await child
    with activity.activity_stream('parent'), preview.public_preview_stream('parent'):
        asyncio.run(run())
    assert 'late body' not in pipe.getvalue()
    assert not [v for v in frames(pipe) if v['type'] == 'message']


@pytest.mark.parametrize('field,bad', [('runId', 'another-run'), ('workspaceId', 'other-session')])
def test_writer_identity_mismatch_cannot_cross_run_or_workspace(monkeypatch, field, bad):
    pipe = configure(monkeypatch)
    with activity.activity_stream('parent'), preview.public_preview_stream('parent'):
        writer = preview._writer.get()
        writer.identity[field] = bad
        with activity.invocation_activity('parent', 'worker', 'codex', 1):
            notification(session(), text='wrong identity body')
    assert 'wrong identity body' not in pipe.getvalue()


def test_independent_source_budget_bounded_without_growing_queue(monkeypatch):
    pipe = configure(monkeypatch)
    # Hold the sender before draining to make overflow deterministic, not timing-dependent.
    import threading
    gate = threading.Event()
    original = preview.PreviewWriter._pump
    def blocked(self):
        gate.wait(2)
        original(self)
    monkeypatch.setattr(preview.PreviewWriter, '_pump', blocked)
    writer = preview.PreviewWriter(RUN, STREAM, 'parent')
    try:
        for index in range(200):
            writer.emit(SimpleNamespace(id=STREAM), f'item-{index}', 'x' * 2000)
        assert len(writer.seen) == preview.MAX_SOURCE_ITEMS
        assert len(writer.queue) <= 8
        assert writer.queued_bytes <= 32 * 1024
        assert writer.seq == preview.MAX_SOURCE_ITEMS
        assert writer.dropped > 0
    finally:
        gate.set()
        writer.close()
    assert frames(pipe)[-1]['type'] == 'end'


@pytest.mark.parametrize('unknown', ['thread_id', 'turn_id'])
def test_unbound_source_identity_never_accepts_body(monkeypatch, unknown):
    pipe = configure(monkeypatch)
    value = session()
    setattr(value, unknown, None)
    with activity.activity_stream('parent'), preview.public_preview_stream('parent'):
        with activity.invocation_activity('parent', 'worker', 'codex', 1):
            notification(value, thread=value.thread_id, turn=value.turn_id, text='unbound body')
    assert 'unbound body' not in pipe.getvalue()


@pytest.mark.parametrize('item_id', [None, '', 'bad/id', 'x' * 129])
def test_missing_or_unbounded_item_identity_is_not_previewed(monkeypatch, item_id):
    pipe = configure(monkeypatch)
    with activity.activity_stream('parent'), preview.public_preview_stream('parent'):
        with activity.invocation_activity('parent', 'worker', 'codex', 1):
            notification(session(), item_id=item_id, text='invalid source body')
    assert 'invalid source body' not in pipe.getvalue()


def test_blocked_run_sender_does_not_lock_another_run(monkeypatch):
    import threading
    entered, release = threading.Event(), threading.Event()
    class Blocked(io.StringIO):
        def write(self, text):
            entered.set()
            assert release.wait(3)
            return super().write(text)
    blocked = Blocked()
    monkeypatch.setattr('sys.stderr', blocked)
    first = activity.ActivityWriter(RUN, STREAM, 'parent')
    assert entered.wait(1)
    other = io.StringIO()
    monkeypatch.setattr('sys.stderr', other)
    second = activity.ActivityWriter(RUN, STREAM, 'other')
    try:
        second.close()
        assert not second.sender.is_alive()
        assert frames(other, activity.PREFIX)[0]['workspaceId'] == 'other'
        assert first.sender.is_alive()
    finally:
        release.set()
        first.close()


@pytest.mark.parametrize('broken', [False, True])
def test_os_pipe_backpressure_or_disconnect_cannot_delay_task_settlement(broken):
    import os
    import subprocess
    import sys
    script = '''
import json,time
from dsh_runtime.observability.activity import activity_stream,invocation_activity,record_activity,_writer
from dsh_runtime.observability.public_preview import public_preview_stream,record_public_commentary
start=time.monotonic()
with activity_stream('parent'),public_preview_stream('parent'):
 with invocation_activity('parent','worker','codex',1):
  for i in range(128):
   record_public_commentary(str(i),'x'*1024)
   record_activity('codex','message','observed')
   time.sleep(.002)
print(json.dumps({'settled':True,'seconds':time.monotonic()-start}),flush=True)
'''
    env = {**os.environ, 'DSH_RUNTIME_RUN_ID': RUN, activity.STREAM_ENV: STREAM, preview.STREAM_ENV: STREAM}
    child = subprocess.Popen([sys.executable, '-B', '-c', script], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env=env)
    try:
        if broken:
            child.stderr.close()
        # Deliberately do not drain stderr until the entire child has settled.
        child.wait(timeout=5)
        result = json.loads(child.stdout.read())
        assert child.returncode == 0 and result['settled']
        assert result['seconds'] < 2
        if not broken:
            lines = child.stderr.read().decode().splitlines()
            assert lines
            # Concurrent senders never produce mixed prefixes/JSON fragments.
            for line in lines:
                prefix = preview.PREFIX if line.startswith(preview.PREFIX) else activity.PREFIX
                assert line.startswith(prefix)
                json.loads(line[len(prefix):])
    finally:
        if child.poll() is None:
            child.kill(); child.wait()
        child.stdout.close()
        child.stderr.close()
