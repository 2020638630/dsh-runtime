/** Temporary observations from an active run. Terminal evidence has its own reader and closure rules. */
import { lstat, open, opendir, realpath } from 'node:fs/promises'
import { basename, dirname, join } from 'node:path'

const TRACE_NAME = /^(codebuddy-safe-worker|codex-safe-worker|api-agent-safe-role)-([0-9a-f]{32})\.jsonl$/u
const ADAPTERS = {
  'codebuddy-safe-worker': 'codebuddy', 'codex-safe-worker': 'codex', 'api-agent-safe-role': 'api_agent',
} as const
type Adapter = typeof ADAPTERS[keyof typeof ADAPTERS]
type Role = 'worker' | 'reviewer' | 'inspector'
type Phase = { role: Role; adapter: Adapter; atMs: number }
type Activity = { adapter: Adapter; atMs: number; kind: 'started' | 'model' | 'tool' | 'finishing';
  tool?: string; status?: 'called' | 'completed' | 'failed' }

const TOOLS: Record<Adapter, readonly string[]> = {
  codebuddy: ['Read', 'Edit', 'Write', 'Bash'],
  codex: ['commandExecution', 'fileChange'],
  api_agent: ['list_files', 'read_file', 'search_text'],
}
const MAX_FILES = 12
const TRACE_TAIL_BYTES = 16_384
const MAX_TRACE_BYTES = 1_048_576

function object(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null
}

function currentTime(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0 && value <= Date.now() + 60_000
}

async function ownedDirectory(parent: string, name: string): Promise<string | undefined> {
  const path = join(parent, name)
  const info = await lstat(path)
  if (info.isSymbolicLink() || !info.isDirectory()) return undefined
  const physical = await realpath(path)
  return dirname(physical) === parent && basename(physical) === name ? physical : undefined
}

async function records(root: string, name: string, tail: number, limit: number): Promise<Record<string, unknown>[]> {
  try {
    const path = join(root, name)
    const info = await lstat(path)
    if (info.isSymbolicLink() || !info.isFile() || info.nlink !== 1 || info.size > limit) return []
    const physical = await realpath(path)
    if (dirname(physical) !== root || basename(physical) !== name) return []
    const handle = await open(physical, 'r')
    try {
      const opened = await handle.stat()
      if (!opened.isFile() || opened.nlink !== 1 || opened.dev !== info.dev || opened.ino !== info.ino
        || opened.size > limit) return []
      const offset = Math.max(0, opened.size - tail)
      const buffer = Buffer.alloc(opened.size - offset)
      const { bytesRead } = await handle.read(buffer, 0, buffer.length, offset)
      // A live writer may leave either boundary record incomplete.
      const lines = buffer.subarray(0, bytesRead).toString('utf8').split('\n')
      lines.pop()
      if (offset > 0) lines.shift()
      return lines.reverse().flatMap(line => {
        try {
          const value = object(JSON.parse(line))
          return value === null ? [] : [value]
        } catch {
          return []
        }
      })
    } finally {
      await handle.close()
    }
  } catch {
    return []
  }
}

function phase(value: Record<string, unknown>, runId: string, workspaceId: string): Phase | undefined {
  if (value.schema_version !== 1 || value.run_id !== runId || value.workspace_id !== workspaceId
    || !currentTime(value.started_at_ms)) return
  const { role, adapter } = value
  if ((role === 'worker' && (adapter === 'codex' || adapter === 'codebuddy'))
    || ((role === 'reviewer' || role === 'inspector') && (adapter === 'codex' || adapter === 'api_agent'))) {
    return { role, adapter, atMs: value.started_at_ms }
  }
}

function activity(event: Record<string, unknown>, traceId: string, adapter: Adapter,
  active?: Phase): Activity | undefined {
  if (event.schema_version !== 1 || event.trace_id !== traceId
    || !Number.isSafeInteger(event.event_seq) || typeof event.captured_at_utc !== 'string') return
  const atMs = Date.parse(event.captured_at_utc)
  if (!currentTime(atMs) || (active && (adapter !== active.adapter || atMs <= active.atMs
    || (adapter === 'api_agent' && event.role_name !== active.role)))) return
  const fields = { atMs, adapter }
  if (event.event_type === 'tool_call' || event.event_type === 'tool_result') {
    const tool = event.tool_name
    if (typeof tool !== 'string' || !TOOLS[adapter].includes(tool)) return
    const status = event.tool_status === 'failed' || event.tool_status === 'error' ? 'failed'
      : event.tool_status === 'completed' ? 'completed' : 'called'
    return { ...fields, kind: 'tool', tool, status }
  }
  if (event.event_type === 'started' || event.progress_kind === 'worker_started') return { ...fields, kind: 'started' }
  if (event.event_type === 'model_event') return { ...fields, kind: 'model' }
  if (event.event_type === 'terminal' || event.event_type === 'native_terminal') return { ...fields, kind: 'finishing' }
}

/** Return allowlisted observations from bounded tails. Missing or incomplete inputs are normal during a run. */
export async function readLiveProgress(input: {
  evidenceRoot: string; runId: string; workspaceId: string;
}): Promise<{ phase?: Phase; activity?: Activity } | undefined> {
  const { evidenceRoot, runId, workspaceId } = input
  if (!/^dsh-runtime-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/u.test(runId)) return
  try {
    const parent = await ownedDirectory(await realpath(evidenceRoot), 'dsh-runtime')
    const run = parent && await ownedDirectory(parent, runId)
    if (!run) return
    const phases = await records(run, 'runtime-progress.jsonl', 8192, 8192)
    const active = phases.map(row => phase(row, runId, workspaceId)).find(value => value !== undefined)
    const traceDir = await ownedDirectory(run, 'safe-trace-' + runId).catch(() => undefined)
    let latest: Activity | undefined
    if (!active || active.adapter === 'codex') {
      const [item] = await records(run, 'runtime-codex-activity.jsonl', 4096, 4096)
      if (item?.schema_version === 1 && item.run_id === runId && item.workspace_id === workspaceId
        && currentTime(item.at_ms) && (!active || item.at_ms > active.atMs)
        && typeof item.tool === 'string' && TOOLS.codex.includes(item.tool)
        && (item.status === 'called' || item.status === 'completed' || item.status === 'failed')) {
        latest = { adapter: 'codex', kind: 'tool', tool: item.tool, status: item.status, atMs: item.at_ms }
      }
    }
    if (traceDir) {
      let visited = 0
      for await (const entry of await opendir(traceDir)) {
        if (++visited > MAX_FILES) break
        const match = TRACE_NAME.exec(entry.name)
        if (!entry.isFile() || !match) continue
        const adapter = ADAPTERS[match[1] as keyof typeof ADAPTERS]
        if (active && active.adapter !== adapter) continue
        const events = await records(traceDir, entry.name, TRACE_TAIL_BYTES, MAX_TRACE_BYTES)
        const current = events.map(event => activity(event, match[2], adapter, active))
          .find(value => value !== undefined)
        if (current && (!latest || current.atMs > latest.atMs)) latest = current
      }
    }
    return active || latest ? { phase: active, activity: latest } : undefined
  } catch {
    return undefined
  }
}
