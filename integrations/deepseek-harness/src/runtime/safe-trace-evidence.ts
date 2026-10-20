/** Read only bounded, non-content CodeBuddy trace metadata after child exit. */

import { readFile, realpath, stat } from 'node:fs/promises'
import { basename, dirname, isAbsolute, resolve } from 'node:path'

const RUN_ID = /^dsh-runtime-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/u
const TRACE_NAME = /^codebuddy-safe-worker-([0-9a-f]{32})\.jsonl$/u
const MAX_TRACE_BYTES = 1_048_576
const MAX_MARKER_BYTES = 4_096
const TOOL_NAMES = ['Read', 'Edit', 'Write', 'Bash'] as const

/** Trace availability is independent of the Runtime task's business verdict. */
export type SafeTraceStatus = 'available' | 'unavailable' | 'unknown' | 'incomplete'

/** Metadata safe to place in a terminal Evidence Manifest. */
export interface SafeTraceEvidence {
  readonly status: SafeTraceStatus
  readonly traceComplete: boolean
  readonly traceId: string | null
  readonly turnsUsed: null
  readonly toolOperationsSummary: Readonly<Record<(typeof TOOL_NAMES)[number], number>>
}

function emptyEvidence(status: SafeTraceStatus, traceId: string | null): SafeTraceEvidence {
  return {
    status,
    traceComplete: false,
    traceId,
    turnsUsed: null,
    toolOperationsSummary: { Read: 0, Edit: 0, Write: 0, Bash: 0 },
  }
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

/**
 * Inspect one Runtime-owned Safe Trace after its writing process has exited.
 * The trace and marker must resolve inside this run's dedicated trace directory.
 * No raw event text, model output, tool arguments, or file paths are returned.
 * @param input - run identity, dedicated directory, trace path, and child-exit evidence.
 * @returns bounded metadata, downgraded unless terminal and closure evidence agree.
 */
export async function inspectSafeTrace(input: {
  readonly runId: string
  readonly traceDir: string
  readonly tracePath: string
  readonly processExited: boolean
}): Promise<SafeTraceEvidence> {
  const { runId, traceDir, tracePath, processExited } = input
  if (!RUN_ID.test(runId) || !isAbsolute(traceDir) || !isAbsolute(tracePath)
    || basename(traceDir) !== `safe-trace-${runId}`
    || resolve(dirname(tracePath)) !== resolve(traceDir)) {
    throw new Error('Safe Trace requires this run dedicated absolute trace directory')
  }
  const match = TRACE_NAME.exec(tracePath.replaceAll('\\', '/').split('/').at(-1) ?? '')
  if (match === null) throw new Error('Safe Trace path has an invalid file name')
  const traceId = match[1] ?? null
  if (!processExited) return emptyEvidence('unknown', traceId)

  const markerPath = `${tracePath}.closed`
  try {
    const expectedDir = await realpath(traceDir)
    if (dirname(await realpath(tracePath)) !== expectedDir
      || dirname(await realpath(markerPath)) !== expectedDir) {
      return emptyEvidence('incomplete', traceId)
    }
  } catch (error: unknown) {
    if (record(error)?.code === 'ENOENT') {
      try {
        await stat(tracePath)
      } catch (traceError: unknown) {
        if (record(traceError)?.code === 'ENOENT') return emptyEvidence('unavailable', traceId)
      }
    }
    return emptyEvidence('incomplete', traceId)
  }
  let traceBytes: Buffer
  try {
    const info = await stat(tracePath)
    if (!info.isFile() || info.size > MAX_TRACE_BYTES) return emptyEvidence('incomplete', traceId)
    traceBytes = await readFile(tracePath)
    if (traceBytes.byteLength > MAX_TRACE_BYTES) return emptyEvidence('incomplete', traceId)
  } catch (error: unknown) {
    if (record(error)?.code === 'ENOENT') return emptyEvidence('unavailable', traceId)
    return emptyEvidence('unknown', traceId)
  }

  let marker: Record<string, unknown> | null
  try {
    const info = await stat(markerPath)
    if (!info.isFile() || info.size > MAX_MARKER_BYTES) return emptyEvidence('incomplete', traceId)
    const markerBytes = await readFile(markerPath)
    if (markerBytes.byteLength > MAX_MARKER_BYTES) return emptyEvidence('incomplete', traceId)
    marker = record(JSON.parse(markerBytes.toString('utf8')))
  } catch {
    return emptyEvidence('incomplete', traceId)
  }
  if (marker?.schema_version !== 1 || marker.run_id !== runId || marker.trace_id !== traceId
    || marker.final_bytes !== traceBytes.byteLength) {
    return emptyEvidence('incomplete', traceId)
  }
  if (traceBytes.length === 0 || traceBytes.at(-1) !== 10) {
    return emptyEvidence('incomplete', traceId)
  }

  const counts = { Read: 0, Edit: 0, Write: 0, Bash: 0 }
  const lines = traceBytes.toString('utf8').trimEnd().split('\n')
  let terminal: Record<string, unknown> | null = null
  let nativeTerminalObserved = false
  for (const [index, line] of lines.entries()) {
    let event: Record<string, unknown> | null
    try {
      event = record(JSON.parse(line))
    } catch {
      return emptyEvidence('incomplete', traceId)
    }
    if (event?.trace_id !== traceId || event.event_seq !== index) {
      return emptyEvidence('incomplete', traceId)
    }
    if (event.event_type === 'tool_call'
      && typeof event.tool_name === 'string'
      && Object.hasOwn(counts, event.tool_name)) {
      counts[event.tool_name as keyof typeof counts] += 1
    }
    if (event.event_type === 'terminal'
      && event.worker_phase === 'worker_output'
      && event.progress_kind === 'native_terminal_observed') {
      nativeTerminalObserved = true
    }
    terminal = event
  }
  if (!nativeTerminalObserved || terminal?.event_type !== 'terminal'
    || terminal.worker_phase !== 'settled'
    || terminal.progress_kind !== 'worker_settled'
    || terminal.trace_complete !== true) {
    return emptyEvidence('incomplete', traceId)
  }
  return {
    status: 'available',
    traceComplete: true,
    traceId,
    turnsUsed: null,
    toolOperationsSummary: counts,
  }
}
