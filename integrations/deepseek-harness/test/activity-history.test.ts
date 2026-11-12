import assert from 'node:assert/strict'
import { test } from 'node:test'
import { execFileSync } from 'node:child_process'
import { ActivityHistoryStore, ActivityFrameDecoder, ACTIVITY_PREFIX, activityHistories } from '../src/runtime/activity-history.ts'

const id = { evidenceRoot: 'fixture-root', runId: 'dsh-runtime-11111111-2222-4333-8444-555555555555', workspaceId: 'session-parent' }
const invocation = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'
const second = 'bbbbbbbb-cccc-4ddd-8eee-ffffffffffff'
const at = Date.now()

test('activity identity preserves root case and exact run and parent boundaries', () => {
  const store = new ActivityHistoryStore()
  const identities = [id, { ...id, evidenceRoot: 'Fixture-root' },
    { ...id, evidenceRoot: 'fixture-root-sibling' }, { ...id, runId: id.runId + '-other' },
    { ...id, workspaceId: id.workspaceId + '-other' }]
  const streams = identities.map(identity => store.start(identity, 'repository_inspection'))
  assert.equal(new Set(streams).size, identities.length)
  identities.forEach((identity, index) => {
    const result = store.read(identity)
    assert.equal(result.status, 'available')
    assert.equal(result.streamId, streams[index])
  })
})

function setup(options?: { events: number; bytes: number; runs: number; terminalMs: number }, now?: () => number) {
  const store = new ActivityHistoryStore(options, now)
  const stream = store.start(id, 'repository_change')
  store.accept(id, { v: 1, type: 'begin', runId: id.runId, workspaceId: id.workspaceId, streamId: stream })
  const event = (seq: number, rest = {}) => ({ v: 1, type: 'event',
    runId: id.runId, workspaceId: id.workspaceId, streamId: stream, seq, invocationId: invocation,
    invocationIndex: 1, role: 'worker', adapter: 'codex', atMs: at,
    kind: seq === 1 ? 'phase' : 'tool', status: seq === 1 ? 'dispatched' : 'completed',
    ...(seq === 1 ? {} : { tool: 'commandExecution' }), ...rest })
  const send = (seq: number, rest = {}) => {
    const value = event(seq, rest)
    store.accept(id, value)
    return value
  }
  const end = (lastSeq: number, dropped = 0) => store.accept(id, { v: 1, type: 'end', runId: id.runId,
    workspaceId: id.workspaceId, streamId: stream, lastSeq, dropped })
  const read = (after = 0, selected = stream) => store.read(id, after, selected) as ReturnType<typeof store.read> & {
    events: Array<Record<string, unknown>>; gaps: string[]; earliestSeq: number; lastSeq: number;
    nextCursor: number; closed: boolean; reset: boolean; retainedBytes: number;
  }
  return { store, stream, event, send, end, read }
}

test('source binding survives role switches; duplicate, conflict and late old-role events are explicit', () => {
  const { store, stream, send, read, end } = setup()
  const first = send(1)
  store.accept(id, { ...first })
  assert.equal(read().events.length, 1)
  send(2)
  send(3, { kind: 'invocation', status: 'returned', tool: undefined }) // extra key is rejected
  assert.ok(read().gaps.includes('invalid_frame'))
  const returned = { ...first, seq: 3, kind: 'invocation', status: 'returned' }
  store.accept(id, returned)
  store.accept(id, { ...first, seq: 4, invocationIndex: 2, role: 'reviewer' })
  assert.ok(read().gaps.includes('invocation_binding'))
  const reviewer = { ...first, seq: 4, invocationId: second, invocationIndex: 2, role: 'reviewer' }
  store.accept(id, reviewer)
  store.accept(id, { ...first, seq: 5, kind: 'message', status: 'observed' })
  assert.ok(read().gaps.includes('invocation_binding'))
  store.accept(id, { ...reviewer, seq: 6, kind: 'message', status: 'observed' })
  store.accept(id, { ...reviewer, seq: 6, kind: 'invocation', status: 'returned' })
  assert.ok(read().gaps.includes('conflict'))
  assert.ok(read().gaps.includes('source_gap'))
  assert.equal(read().events.at(-1)?.role, 'reviewer')
  assert.equal(read().events.at(-1)?.invocationId, second)
  end(6, 1)
  store.finish(id, true)
  const frozen = JSON.stringify(read())
  store.accept(id, { ...reviewer, seq: 7, kind: 'message', status: 'observed' })
  assert.equal(JSON.stringify(read()), frozen)
  assert.equal(store.read({ ...id, workspaceId: 'another-parent' }).status, 'unavailable')
  assert.equal(read().streamId, stream)
})

test('50-event window, byte budget and incremental reconnect report independent truncation and source gaps', () => {
  const { send, read, store } = setup()
  send(1)
  for (let seq = 2; seq <= 10_000; seq++) send(seq)
  const latest = read()
  assert.equal(latest.events.length, 50)
  assert.equal(latest.earliestSeq, 9951)
  assert(latest.retainedBytes <= 32768)
  assert.ok(latest.gaps.includes('window_truncated'))
  assert.equal(read(9997).events.length, 3)
  assert(!read(9997).gaps.includes('window_truncated'))
  assert.equal(read(10_000).events.length, 0)
  assert.equal(read(10_001).reset, true)
  assert.ok(read(10_001).gaps.includes('cursor_ahead'))
  const changed = read(9999, 'cccccccc-dddd-4eee-8fff-aaaaaaaaaaaa')
  assert.equal(changed.reset, true)
  assert.equal(changed.events.length, 50)
  assert.ok(changed.gaps.includes('stream_changed'))
  const small = setup({ events: 50, bytes: 1200, runs: 2, terminalMs: 100 })
  small.send(1); for (let seq = 2; seq <= 10; seq++) small.send(seq)
  assert(small.read().retainedBytes <= 1200)
  assert(small.read().events.length < 10)
  assert.ok(small.read().gaps.includes('window_truncated'))
  assert.equal(store.read({ ...id, evidenceRoot: 'other-profile' }).status, 'unavailable')
})

test('restart, expiry and capacity eviction never appear as empty available histories', () => {
  let now = at
  const { store, send, end, read } = setup({ events: 50, bytes: 32768, runs: 1, terminalMs: 100 }, () => now)
  send(1); end(1); store.finish(id, true)
  assert.equal(read().closed, true)
  now += 101
  assert.equal(store.read(id).reason, 'expired')
  const next = { ...id, runId: id.runId.replace('11111111', '22222222') }
  store.start(next, 'repository_inspection')
  store.start(id, 'repository_change')
  assert.equal(store.read(next).reason, 'evicted')
  const restarted = new ActivityHistoryStore()
  assert.deepEqual(restarted.read(id), { version: 1, status: 'unavailable', reason: 'not_recorded_in_this_host' })
})

test('missing end frames, source drops, out-of-order events and EOF drain failure remain visible', () => {
  const { store, send, read } = setup()
  send(1); send(3); send(2)
  assert.ok(read().gaps.includes('out_of_order'))
  store.finish(id, false)
  assert.ok(read().gaps.includes('source_gap'))
  assert.ok(read().gaps.includes('drain_timeout'))
  assert.ok(read().gaps.includes('missing_source_end'))
  const clean = setup()
  clean.end(0); clean.store.finish(id, true)
  assert.equal(clean.read().events.length, 0)
  assert.equal(clean.read().gaps.length, 0)
})

test('strict fields reject secrets, wrong binding and tool arguments, including after transport chunking', () => {
  const { store, send, read } = setup()
  const first = send(1)
  for (const extra of [{ text: 'SECRET' }, { command: 'cat private' }, { runId: 'wrong' },
    { streamId: 'wrong' }, { workspaceId: 'wrong' }, { tool: 'Bash SECRET' }]) {
    store.accept(id, { ...first, seq: 2, ...extra })
  }
  assert.equal(read().events.length, 1)
  assert.doesNotMatch(JSON.stringify(read()), /SECRET|private/u)
  const received: unknown[] = [], diagnostics: string[] = []
  let bad = 0
  const parser = new ActivityFrameDecoder(v => received.push(v), () => bad++, t => diagnostics.push(t))
  const frame = ACTIVITY_PREFIX + JSON.stringify(first) + '\n'
  for (const byte of Buffer.from('中文 diagnostic\n' + frame)) parser.feed(Buffer.from([byte]))
  parser.feed(ACTIVITY_PREFIX + 'SECRET\n')
  parser.feed(ACTIVITY_PREFIX + 'x'.repeat(10_000))
  parser.feed('tail\n')
  parser.feed(ACTIVITY_PREFIX + '{"private":"SECRET"}')
  parser.end(); parser.feed(frame)
  assert.equal(received.length, 1)
  assert.equal(diagnostics.join(''), '中文 diagnostic\n')
  assert.equal(bad, 3)
})

test('a new Host process has no previous window; legal maximal identities remain within measured limits', () => {
  activityHistories.start(id, 'repository_change')
  const module = new URL('../src/runtime/activity-history.js', import.meta.url).href
  const child = execFileSync(process.execPath, ['--input-type=module', '-e',
    `import {activityHistories} from ${JSON.stringify(module)};console.log(JSON.stringify(activityHistories.read(${JSON.stringify(id)})))`],
  { encoding: 'utf8', windowsHide: true })
  assert.equal(JSON.parse(child).reason, 'not_recorded_in_this_host')
  const store = new ActivityHistoryStore()
  const longId = { ...id, workspaceId: 's'.repeat(128) }
  const streamId = store.start(longId, 'repository_inspection')
  store.accept(longId, { v: 1, type: 'begin', runId: longId.runId, workspaceId: longId.workspaceId, streamId })
  for (let seq = 1; seq <= 10_000; seq++) store.accept(longId, {
    v: 1, type: 'event', runId: longId.runId, workspaceId: longId.workspaceId, streamId,
    seq, invocationId: invocation, invocationIndex: 1, role: 'inspector', adapter: 'codex', atMs: at,
    kind: seq === 1 ? 'phase' : 'tool', status: seq === 1 ? 'dispatched' : 'completed',
    ...(seq === 1 ? {} : { tool: 'commandExecution' }),
  })
  const response = store.read(longId)
  assert.equal(response.events?.length, 50)
  assert(Buffer.byteLength(JSON.stringify(response)) <= 32768)
})
