import assert from 'node:assert/strict'
import { test } from 'node:test'
import { PublicPreviewStore, PublicPreviewDecoder, PUBLIC_PREVIEW_PREFIX, PREVIEW_LIMITS } from '../src/runtime/public-preview.ts'
const id = { evidenceRoot: '/one', runId: 'dsh-runtime-11111111-2222-3333-4444-555555555555', workspaceId: 'session' }
function fixture() {
  let now = 1_000
  const store = new PublicPreviewStore(() => now), streamId = store.start(id)
  const common = { v: 1, runId: id.runId, workspaceId: id.workspaceId, streamId }
  store.accept(id, { ...common, type: 'begin' })
  const row = (seq: number, extra = {}) => ({ ...common, type: 'message', seq,
    invocationId: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee', invocationIndex: 1, role: 'worker', adapter: 'codex',
    itemId: `item-${seq}`, phase: 'commentary', atMs: now, text: '<script>not HTML</script> **plain**', truncated: false, ...extra })
  return { store, common, row, advance: () => { now += PREVIEW_LIMITS.terminalMs } }
}
test('preview has independent bounded plaintext window, copy-on-read and source cap', () => {
  const { store, row } = fixture()
  for (let i = 1; i <= 140; i++) store.accept(id, row(i))
  const view = store.read(id)
  assert.equal(view.messages?.length, 8); assert.equal(view.lastSeq, 128)
  assert(view.truncated); assert(view.issues?.includes('source_limit'))
  assert((view.retainedBytes ?? Infinity) <= PREVIEW_LIMITS.bytes)
  assert.equal(view.messages?.[0]?.text, '<script>not HTML</script> **plain**')
  view.messages![0]!.text = 'mutated'
  assert.notEqual(store.read(id).messages?.[0]?.text, 'mutated')
})
test('preview rejects foreign identities, roles, non-commentary, unknown fields and oversize', () => {
  const { store, row } = fixture()
  for (const extra of [{ runId: 'other' }, { workspaceId: 'other' }, { streamId: 'other' }, { role: 'reviewer' },
    { adapter: 'codebuddy' }, { invocationIndex: 2 }, { phase: 'final_answer' }, { secret: 'no' }, { text: '界'.repeat(342) }]) store.accept(id, row(1, extra))
  assert.equal(store.read(id).messages?.length, 0)
  for (const extra of [{ evidenceRoot: '/two' }, { workspaceId: 'two' }, { runId: 'two' }]) {
    store.accept({ ...id, ...extra }, row(1)); assert.equal(store.read({ ...id, ...extra }).status, 'unavailable')
  }
  store.accept(id, row(1)); store.accept(id, row(1))
  assert.equal(store.read(id).messages?.length, 1)
  store.accept(id, row(2, { invocationId: 'bbbbbbbb-bbbb-4ccc-8ddd-eeeeeeeeeeee' }))
  store.accept(id, row(2, { itemId: 'item-1' }))
  assert.equal(store.read(id).messages?.length, 1)
})
test('end and Host close reject late text; expiry and eviction are explicit', () => {
  const { store, row, common, advance } = fixture()
  store.accept(id, row(1)); store.accept(id, { ...common, type: 'end', lastSeq: 1, dropped: 0 })
  store.accept(id, row(2)); store.finish(id, true); store.accept(id, row(3))
  assert.equal(store.read(id).messages?.length, 1)
  advance(); assert.equal(store.read(id).reason, 'expired')
  store.start(id)
  for (let i = 0; i < 32; i++) store.start({ ...id, runId: String(i) })
  assert.equal(store.read(id).reason, 'evicted')
})
test('dedicated decoder handles split frames and discards ordinary logs and overlong lines', () => {
  const values: unknown[] = []; let invalid = 0
  const decoder = new PublicPreviewDecoder(value => values.push(value), () => invalid++)
  const line = PUBLIC_PREVIEW_PREFIX + JSON.stringify({ text: '界<script>' }) + '\n'
  const bytes = Buffer.from(line)
  for (const byte of bytes) decoder.feed(Buffer.from([byte]))
  decoder.feed('ordinary diagnostic\nDSH_RUNTIME_ACTIVITY_V1 {}\n')
  decoder.feed(PUBLIC_PREVIEW_PREFIX + 'x'.repeat(5000) + '\n')
  decoder.end()
  assert.deepEqual(values, [{ text: '界<script>' }]); assert.equal(invalid, 1)
})
