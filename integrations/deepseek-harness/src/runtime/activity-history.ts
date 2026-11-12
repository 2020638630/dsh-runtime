/** Host-lifetime observations. Never persisted, never used to settle a task. */
import { randomUUID } from 'node:crypto'
import { realpathSync } from 'node:fs'
import { StringDecoder } from 'node:string_decoder'

/** Use one resolver for both registration and lookup: Node's sync and async
 * realpath implementations can return different path spellings on Windows.
 * Keep case and root boundaries intact; this is not an ownership check. */
export function resolveActivityEvidenceRoot(evidenceRoot: string): string {
  return realpathSync(evidenceRoot)
}

export const ACTIVITY_PREFIX = 'DSH_RUNTIME_ACTIVITY_V1 '
const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/u
const TOOLS = { codex: ['commandExecution', 'fileChange'], codebuddy: ['Read', 'Edit', 'Write', 'Bash'],
  api_agent: ['list_files', 'read_file', 'search_text'] } as const
type Adapter = keyof typeof TOOLS
type Role = 'worker' | 'reviewer' | 'inspector'
type Identity = { evidenceRoot: string; runId: string; workspaceId: string }
export type SafeActivity = {
  v: 1; type: 'event'; runId: string; workspaceId: string; streamId: string; seq: number;
  invocationId: string; invocationIndex: number; role: Role; adapter: Adapter; atMs: number;
  kind: 'phase' | 'tool' | 'message' | 'invocation'; status: string; tool?: string;
}
type Window = Identity & { streamId: string; taskKind: string; events: SafeActivity[]; bytes: number;
  lastSeq: number; trimmed: number; issues: Set<string>; established: boolean; sourceEnd: boolean; sealedAt?: number;
  active?: { id: string; index: number; role: Role; adapter: Adapter; returned: boolean } }
const key = (input: Identity) => JSON.stringify([input.evidenceRoot, input.runId, input.workspaceId])
const integer = (value: unknown): value is number => Number.isSafeInteger(value) && Number(value) >= 0
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)
const exact = (value: Record<string, unknown>, names: string[]) => Object.keys(value).sort().join() === names.sort().join()
const eventFields = ['v', 'type', 'runId', 'workspaceId', 'streamId', 'seq', 'invocationId', 'invocationIndex', 'role', 'adapter', 'atMs', 'kind', 'status']

export class ActivityHistoryStore {
  private windows = new Map<string, Window>()
  private removed = new Map<string, 'expired' | 'evicted'>()
  constructor(private options = { events: 50, bytes: 32 * 1024, runs: 32, terminalMs: 30 * 60_000 },
    private now: () => number = Date.now) {
    if (Object.values(options).some(value => !Number.isSafeInteger(value) || value <= 0)) throw new Error('Invalid activity bounds')
  }
  private forget(id: string, reason: 'expired' | 'evicted') {
    this.windows.delete(id)
    this.removed.set(id, reason)
    while (this.removed.size > this.options.runs * 2) this.removed.delete(this.removed.keys().next().value!)
  }
  private prune() {
    for (const [id, window] of this.windows) if (window.sealedAt !== undefined
      && this.now() - window.sealedAt >= this.options.terminalMs) this.forget(id, 'expired')
  }
  start(input: Identity, taskKind: string): string {
    this.prune()
    const id = key(input)
    if (this.windows.has(id)) throw new Error('Activity stream already registered')
    while (this.windows.size >= this.options.runs) this.forget(this.windows.keys().next().value!, 'evicted')
    const streamId = randomUUID()
    this.removed.delete(id)
    this.windows.set(id, { ...input, streamId, taskKind, events: [], bytes: 0, lastSeq: 0,
      trimmed: 0, issues: new Set(), established: false, sourceEnd: false })
    return streamId
  }
  issue(input: Identity, reason: string) {
    const window = this.windows.get(key(input))
    if (window && window.sealedAt === undefined) window.issues.add(reason)
  }
  accept(input: Identity, value: unknown): void {
    const window = this.windows.get(key(input))
    if (!window || window.sealedAt !== undefined) return
    const reject = (reason = 'invalid_frame') => { window.issues.add(reason) }
    if (!object(value) || value.v !== 1 || value.runId !== window.runId
      || value.workspaceId !== window.workspaceId || value.streamId !== window.streamId) return reject()
    if (window.sourceEnd) return reject('after_source_end')
    if (value.type === 'begin') {
      if (!exact(value, ['v', 'type', 'runId', 'workspaceId', 'streamId']) || window.established) return reject()
      window.established = true
      return
    }
    if (!window.established) return reject('source_not_started')
    if (value.type === 'end') {
      if (!exact(value, ['v', 'type', 'runId', 'workspaceId', 'streamId', 'lastSeq', 'dropped'])
        || !integer(value.lastSeq) || !integer(value.dropped)) return reject()
      window.sourceEnd = true
      if (value.lastSeq !== window.lastSeq) reject('source_gap')
      if (value.dropped > 0) reject('source_dropped')
      return
    }
    if (value.type !== 'event' || !exact(value, [...eventFields, ...('tool' in value ? ['tool'] : [])])
      || !integer(value.seq) || value.seq < 1 || !UUID.test(String(value.invocationId))
      || !integer(value.invocationIndex) || !integer(value.atMs) || value.atMs < 1 || value.atMs > this.now() + 60_000
      || !Object.hasOwn(TOOLS, String(value.adapter))) return reject()
    const adapter = value.adapter as Adapter
    const validKind = value.kind === 'phase' && value.status === 'dispatched' && !('tool' in value)
      || value.kind === 'invocation' && ['returned', 'interrupted'].includes(String(value.status)) && !('tool' in value)
      || value.kind === 'message' && value.status === 'observed' && !('tool' in value)
      || value.kind === 'tool' && ['called', 'completed', 'failed', 'observed'].includes(String(value.status))
        && (TOOLS[adapter] as readonly string[]).includes(String(value.tool))
    if (!validKind) return reject()
    const event = value as unknown as SafeActivity
    if (event.seq <= window.lastSeq) {
      const prior = window.events.find(item => item.seq === event.seq)
      if (prior && eventFields.concat('tool').every(field => (prior as unknown as Record<string, unknown>)[field] === value[field])) return
      return reject(prior ? 'conflict' : 'out_of_order')
    }
    if (event.kind === 'phase') {
      const index = (window.active?.index ?? 0) + 1
      const role = window.taskKind === 'repository_inspection' ? 'inspector' : index === 1 ? 'worker' : 'reviewer'
      if (event.invocationIndex !== index || index > (window.taskKind === 'repository_inspection' ? 1 : 2)
        || event.role !== role || (role === 'worker' ? !['codex', 'codebuddy'].includes(adapter) : !['codex', 'api_agent'].includes(adapter))
        || (window.active && (!window.active.returned || window.active.id === event.invocationId))) return reject('invocation_binding')
      window.active = { id: event.invocationId, index, role, adapter, returned: false }
    } else {
      const active = window.active
      if (!active || active.returned || active.id !== event.invocationId || active.index !== event.invocationIndex
        || active.role !== event.role || active.adapter !== event.adapter) return reject('invocation_binding')
      if (event.kind === 'invocation') active.returned = true
    }
    if (event.seq !== window.lastSeq + 1) reject('source_gap')
    window.lastSeq = event.seq
    window.events.push({ ...event })
    window.bytes += Buffer.byteLength(JSON.stringify(event), 'utf8')
    while (window.events.length > this.options.events || window.bytes > this.options.bytes) {
      window.bytes -= Buffer.byteLength(JSON.stringify(window.events.shift()!), 'utf8')
      window.trimmed++
    }
  }
  finish(input: Identity, drained: boolean) {
    const window = this.windows.get(key(input))
    if (!window || window.sealedAt !== undefined) return
    if (!drained) window.issues.add('drain_timeout')
    if (!window.established) window.issues.add('source_not_started')
    if (!window.sourceEnd) window.issues.add('missing_source_end')
    if (window.active && !window.active.returned) window.issues.add('invocation_unclosed')
    window.sealedAt = this.now()
  }
  read(input: Identity, after = 0, streamId?: string) {
    this.prune()
    const id = key(input), window = this.windows.get(id)
    if (!window) return { version: 1, status: 'unavailable', reason: this.removed.get(id) ?? 'not_recorded_in_this_host' }
    const reset = streamId !== undefined && streamId !== window.streamId
    const ahead = !reset && after > window.lastSeq
    const earliestSeq = window.events[0]?.seq ?? window.lastSeq + 1
    const gaps = [...window.issues]
    if (window.trimmed > 0 && (reset || after < earliestSeq - 1)) gaps.push('window_truncated')
    if (reset) gaps.push('stream_changed')
    if (ahead) gaps.push('cursor_ahead')
    return { version: 1, status: 'available', streamId: window.streamId, runId: window.runId,
      retention: 'host_memory', limitEvents: this.options.events, limitBytes: this.options.bytes,
      retainedBytes: window.bytes, earliestSeq, lastSeq: window.lastSeq,
      nextCursor: window.lastSeq, closed: window.sealedAt !== undefined,
      established: window.established, sourceClosed: window.sourceEnd, truncated: window.trimmed > 0, gaps, reset: reset || ahead,
      events: window.events.filter(event => reset || ahead || event.seq > after).map(event => ({ ...event })) }
  }
}

/** Per-line framing with fixed bounds. Bad reserved frames never become diagnostics. */
export class ActivityFrameDecoder {
  private decoder = new StringDecoder('utf8')
  private line = ''
  private discarding = false
  private ended = false
  constructor(private accept: (value: unknown) => void, private invalid: () => void,
    private diagnostic: (text: string) => void = () => {}) {}
  feed(chunk: Buffer | string) {
    if (this.ended) return
    this.consume(this.decoder.write(typeof chunk === 'string' ? Buffer.from(chunk) : chunk))
  }
  private consume(text: string) {
    for (const part of text.split(/(?<=\n)/u)) {
      if (!part) continue
      const newline = part.endsWith('\n')
      if (this.discarding) { if (newline) this.discarding = false; continue }
      if (this.line.length + part.length > 2048) {
        if (this.line.startsWith(ACTIVITY_PREFIX) || (this.line + part.slice(0, ACTIVITY_PREFIX.length)).startsWith(ACTIVITY_PREFIX)) this.invalid()
        this.line = ''; this.discarding = !newline; continue
      }
      this.line += part
      if (!newline) continue
      const line = this.line; this.line = ''
      if (line.startsWith(ACTIVITY_PREFIX)) {
        try { this.accept(JSON.parse(line.slice(ACTIVITY_PREFIX.length))) } catch { this.invalid() }
      } else this.diagnostic(line)
    }
  }
  end() {
    if (this.ended) return
    this.consume(this.decoder.end())
    if (this.line.startsWith(ACTIVITY_PREFIX)) this.invalid()
    else if (this.line) this.diagnostic(this.line)
    this.line = ''; this.ended = true
  }
}

export const activityHistories = new ActivityHistoryStore()
