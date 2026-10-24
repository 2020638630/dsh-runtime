/** Inspect bounded, content-free Codex worker events after the child exits. */

import { readFile, realpath, stat } from 'node:fs/promises'
import { basename, dirname, isAbsolute, resolve } from 'node:path'

const RUN_ID = /^dsh-runtime-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/u
const TRACE_NAME = /^codex-safe-worker-([0-9a-f]{32})\.jsonl$/u
const MAX_TRACE_BYTES = 65_536
const MAX_MARKER_BYTES = 4_096
const MAX_EVENTS = 256
const EVENT_FIELDS = [
  'captured_at_utc', 'event_seq', 'event_type', 'native_status',
  'schema_version', 'terminal_reason', 'tool_name', 'tool_status',
  'trace_complete', 'trace_id',
].join('|')

export interface CodexTraceEvidence {
  readonly status: 'available' | 'unavailable' | 'unknown' | 'incomplete'
  readonly traceComplete: boolean
  readonly toolOperationsSummary: Readonly<{ commandExecution: number; fileChange: number }> | null
}

function empty(status: CodexTraceEvidence['status']): CodexTraceEvidence {
  return { status, traceComplete: false, toolOperationsSummary: null }
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown> : null
}

export async function inspectCodexTrace(input: {
  readonly runId: string
  readonly traceDir: string
  readonly tracePath: string
  readonly processExited: boolean
}): Promise<CodexTraceEvidence> {
  const { runId, traceDir, tracePath, processExited } = input
  if (!RUN_ID.test(runId) || !isAbsolute(traceDir) || !isAbsolute(tracePath)
    || basename(traceDir) !== `safe-trace-${runId}`
    || resolve(dirname(tracePath)) !== resolve(traceDir)) {
    throw new Error('Codex Safe Trace requires this run dedicated absolute directory')
  }
  const match = TRACE_NAME.exec(basename(tracePath))
  if (match === null) throw new Error('Codex Safe Trace path has an invalid file name')
  if (!processExited) return empty('unknown')

  const markerPath = `${tracePath}.closed`
  try {
    const expectedDir = await realpath(traceDir)
    if (dirname(await realpath(tracePath)) !== expectedDir
      || dirname(await realpath(markerPath)) !== expectedDir) return empty('incomplete')
  } catch (error: unknown) {
    if (record(error)?.code === 'ENOENT') {
      try { await stat(tracePath) } catch (traceError: unknown) {
        if (record(traceError)?.code === 'ENOENT') return empty('unavailable')
      }
    }
    return empty('incomplete')
  }

  let bytes: Buffer
  let marker: Record<string, unknown> | null
  try {
    const info = await stat(tracePath)
    if (!info.isFile() || info.size > MAX_TRACE_BYTES) return empty('incomplete')
    bytes = await readFile(tracePath)
    const markerInfo = await stat(markerPath)
    if (bytes.byteLength > MAX_TRACE_BYTES || !markerInfo.isFile()
      || markerInfo.size > MAX_MARKER_BYTES) return empty('incomplete')
    const markerBytes = await readFile(markerPath)
    if (markerBytes.byteLength > MAX_MARKER_BYTES) return empty('incomplete')
    marker = record(JSON.parse(markerBytes.toString('utf8')))
  } catch { return empty('incomplete') }
  if (marker?.schema_version !== 1 || marker.run_id !== runId
    || marker.trace_id !== match[1] || marker.final_bytes !== bytes.byteLength
    || bytes.length === 0 || bytes.at(-1) !== 10) return empty('incomplete')

  const counts = { commandExecution: 0, fileChange: 0 }
  const lines = bytes.toString('utf8').trimEnd().split('\n')
  if (lines.length < 3 || lines.length > MAX_EVENTS) return empty('incomplete')
  let nativeTerminal: 'completed' | 'failed' | null = null
  let terminal: Record<string, unknown> | null = null
  for (const [index, line] of lines.entries()) {
    let event: Record<string, unknown> | null
    try { event = record(JSON.parse(line)) } catch { return empty('incomplete') }
    if (event === null || Object.keys(event).sort().join('|') !== EVENT_FIELDS
      || event.schema_version !== 1 || event.trace_id !== match[1]
      || event.event_seq !== index || event.trace_complete !== true
      || typeof event.captured_at_utc !== 'string'
      || event.captured_at_utc.length > 40) {
      return empty('incomplete')
    }
    if (index === 0 && event.event_type !== 'started') return empty('incomplete')
    if (event.event_type === 'tool_call') {
      if (index === 0 || nativeTerminal !== null || event.native_status !== null
        || event.terminal_reason !== null) return empty('incomplete')
      if ((event.tool_name !== 'commandExecution' && event.tool_name !== 'fileChange')
        || (event.tool_status !== 'completed' && event.tool_status !== 'failed')) {
        return empty('incomplete')
      }
      counts[event.tool_name] += 1
    } else if (event.event_type === 'native_terminal') {
      if (index === 0 || nativeTerminal !== null
        || event.tool_name !== null || event.tool_status !== null
        || event.terminal_reason !== null
        || (event.native_status !== 'completed' && event.native_status !== 'failed')) {
        return empty('incomplete')
      }
      nativeTerminal = event.native_status
    } else if (event.event_type === 'started') {
      if (index !== 0 || event.tool_name !== null || event.tool_status !== null
        || event.native_status !== null || event.terminal_reason !== null) {
        return empty('incomplete')
      }
    } else if (event.event_type === 'terminal') {
      if (index !== lines.length - 1 || event.tool_name !== null
        || event.tool_status !== null || event.native_status !== null) {
        return empty('incomplete')
      }
    } else {
      return empty('incomplete')
    }
    terminal = event
  }
  if (nativeTerminal === null || terminal?.event_type !== 'terminal'
    || terminal.trace_complete !== true
    || terminal.terminal_reason !== nativeTerminal) {
    return empty('incomplete')
  }
  return { status: 'available', traceComplete: true, toolOperationsSummary: counts }
}
