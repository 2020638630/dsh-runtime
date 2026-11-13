/** C1: bounded public Codex Worker commentary. Never persisted or treated as evidence. */
import { randomUUID } from 'node:crypto'
import { ActivityFrameDecoder } from './activity-history.ts'

export const PUBLIC_PREVIEW_PREFIX = 'DSH_RUNTIME_PUBLIC_PREVIEW_V1 '
export const PREVIEW_LIMITS = { messages: 8, bytes: 16 * 1024, textBytes: 1024, sourceItems: 128, runs: 32, terminalMs: 30 * 60_000 }
type Identity = { evidenceRoot: string; runId: string; workspaceId: string }
type Message = { v: 1; type: 'message'; runId: string; workspaceId: string; streamId: string;
  seq: number; invocationId: string; invocationIndex: 1; role: 'worker'; adapter: 'codex';
  itemId: string; phase: 'commentary'; atMs: number; text: string; truncated: boolean }
type Window = Identity & { streamId: string; messages: Message[]; bytes: number; lastSeq: number;
  seen: Set<string>; invocation?: string; trimmed: number; issues: Set<string>;
  established: boolean; sourceClosed: boolean; sealedAt?: number }
const key = (id: Identity) => JSON.stringify([id.evidenceRoot, id.runId, id.workspaceId])
const uuid = (value: unknown) => typeof value === 'string' && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/u.test(value)
const integer = (v: unknown): v is number => Number.isSafeInteger(v) && Number(v) >= 0
const fields = ['v', 'type', 'runId', 'workspaceId', 'streamId']
const exact = (v: Record<string, unknown>, names: string[]) => Object.keys(v).sort().join() === [...names].sort().join()

export class PublicPreviewStore {
  private windows = new Map<string, Window>()
  private removed = new Map<string, 'expired' | 'evicted'>()
  constructor(private now: () => number = Date.now) {}
  private forget(id: string, reason: 'expired' | 'evicted') {
    this.windows.delete(id); this.removed.set(id, reason)
    while (this.removed.size > PREVIEW_LIMITS.runs * 2) this.removed.delete(this.removed.keys().next().value!)
  }
  private prune() {
    for (const [id, value] of this.windows) if (value.sealedAt !== undefined
      && this.now() - value.sealedAt >= PREVIEW_LIMITS.terminalMs) this.forget(id, 'expired')
  }
  start(id: Identity): string {
    this.prune()
    if (this.windows.has(key(id))) throw Error('Public preview already registered')
    while (this.windows.size >= PREVIEW_LIMITS.runs) this.forget(this.windows.keys().next().value!, 'evicted')
    const streamId = randomUUID()
    this.removed.delete(key(id))
    this.windows.set(key(id), { ...id, streamId, messages: [], bytes: 0, lastSeq: 0,
      seen: new Set(), trimmed: 0, issues: new Set(), established: false, sourceClosed: false })
    return streamId
  }
  issue(id: Identity, reason: 'invalid_frame' | 'drain_timeout') {
    const window = this.windows.get(key(id))
    if (window && window.sealedAt === undefined) window.issues.add(reason)
  }
  accept(id: Identity, raw: unknown) {
    const w = this.windows.get(key(id))
    if (!w || w.sealedAt !== undefined) return
    const reject = (reason = 'invalid_frame') => { w.issues.add(reason) }
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return reject()
    const v = raw as Record<string, unknown>
    if (v.v !== 1 || v.runId !== w.runId || v.workspaceId !== w.workspaceId || v.streamId !== w.streamId) return reject()
    if (w.sourceClosed) return reject('after_source_end')
    if (v.type === 'begin') {
      if (!exact(v, fields) || w.established) return reject()
      w.established = true; return
    }
    if (!w.established) return reject('source_not_started')
    if (v.type === 'end') {
      if (!exact(v, [...fields, 'lastSeq', 'dropped']) || !integer(v.lastSeq) || !integer(v.dropped)) return reject()
      w.sourceClosed = true
      if (v.lastSeq !== w.lastSeq) reject('source_gap')
      if (v.dropped > 0) reject('source_dropped')
      return
    }
    if (v.type !== 'message' || !exact(v, [...fields, 'seq', 'invocationId', 'invocationIndex', 'role', 'adapter',
      'itemId', 'phase', 'atMs', 'text', 'truncated']) || !integer(v.seq) || v.seq < 1 || !uuid(v.invocationId)
      || v.invocationIndex !== 1 || v.role !== 'worker' || v.adapter !== 'codex' || v.phase !== 'commentary'
      || typeof v.itemId !== 'string' || !/^[A-Za-z0-9._:-]{1,128}$/u.test(v.itemId)
      || !integer(v.atMs) || v.atMs < 1 || v.atMs > this.now() + 60_000
      || typeof v.text !== 'string' || Buffer.byteLength(v.text) > PREVIEW_LIMITS.textBytes
      || typeof v.truncated !== 'boolean') return reject()
    const message = v as unknown as Message
    if (v.seq <= w.lastSeq) {
      const previous = w.messages.find(item => item.seq === v.seq)
      if (previous && Object.keys(v).every(name => v[name] === (previous as unknown as Record<string, unknown>)[name])) return
      return reject('conflict')
    }
    if (w.seen.has(v.itemId) || (w.invocation !== undefined && w.invocation !== v.invocationId)) return reject('conflict')
    if (w.seen.size >= PREVIEW_LIMITS.sourceItems) return reject('source_limit')
    if (v.seq !== w.lastSeq + 1) reject('source_gap')
    w.lastSeq = v.seq; w.invocation = message.invocationId; w.seen.add(v.itemId)
    w.messages.push({ ...message }); w.bytes += Buffer.byteLength(JSON.stringify(message))
    while (w.messages.length > PREVIEW_LIMITS.messages || w.bytes > PREVIEW_LIMITS.bytes) {
      w.bytes -= Buffer.byteLength(JSON.stringify(w.messages.shift()!)); w.trimmed++
    }
  }
  finish(id: Identity, drained: boolean) {
    const w = this.windows.get(key(id))
    if (!w || w.sealedAt !== undefined) return
    if (!drained) w.issues.add('drain_timeout')
    if (!w.established) w.issues.add('source_not_started')
    if (!w.sourceClosed) w.issues.add('missing_source_end')
    w.sealedAt = this.now()
  }
  read(id: Identity) {
    this.prune()
    const w = this.windows.get(key(id))
    if (!w) return { version: 1, status: 'unavailable', reason: this.removed.get(key(id)) ?? 'not_recorded_in_this_host' }
    return { version: 1, status: 'available', runId: w.runId, workspaceId: w.workspaceId, streamId: w.streamId,
      retention: 'host_memory', limitMessages: PREVIEW_LIMITS.messages, limitBytes: PREVIEW_LIMITS.bytes,
      limitTextBytes: PREVIEW_LIMITS.textBytes, retainedBytes: w.bytes, lastSeq: w.lastSeq,
      closed: w.sealedAt !== undefined, established: w.established, sourceClosed: w.sourceClosed,
      truncated: w.trimmed > 0, issues: [...w.issues], messages: w.messages.map(item => ({ ...item })) }
  }
}

export const publicPreviews = new PublicPreviewStore()
export class PublicPreviewDecoder extends ActivityFrameDecoder {
  constructor(accept: (value: unknown) => void, invalid: () => void) {
    super(accept, invalid, () => {}, PUBLIC_PREVIEW_PREFIX, 4096)
  }
}
