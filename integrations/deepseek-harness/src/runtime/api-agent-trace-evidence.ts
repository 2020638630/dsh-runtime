/** Read bounded, metadata-only API Agent traces after the Runtime child exits. */

import { readFile, realpath, stat } from 'node:fs/promises'
import { basename, dirname, isAbsolute, resolve } from 'node:path'

const RUN_ID = /^dsh-runtime-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/u
const TRACE_NAME = /^api-agent-safe-role-([0-9a-f]{32})\.jsonl$/u
const MAX_TRACE_BYTES = 65_536
const MAX_MARKER_BYTES = 4_096
const MAX_EVENTS = 128
const TOOLS = ['list_files', 'read_file', 'search_text'] as const
const FAILURE_CODES = [
  'execution_error', 'http_client_unavailable', 'unsupported_tool_schema',
  'provider_timeout', 'provider_network_error', 'provider_auth_error',
  'provider_rate_limited', 'provider_http_error', 'provider_response_too_large',
  'provider_response_invalid', 'provider_error', 'invalid_role', 'invalid_prompt',
  'token_budget_exhausted', 'invalid_model_reply', 'invalid_observed_model',
  'model_changed', 'model_mismatch', 'missing_or_invalid_token_count',
  'invalid_tool_companion_text', 'tool_budget_exhausted', 'invalid_tool_call',
  'invalid_tool_arguments', 'tool_error', 'invalid_tool_result',
  'invalid_final_text', 'reviewer_no_file_read', 'request_budget_exhausted',
] as const
type ToolName = (typeof TOOLS)[number]
type FailureCode = (typeof FAILURE_CODES)[number]
type Status = 'available' | 'unavailable' | 'unknown' | 'incomplete'

export interface ApiAgentTraceEvidence {
  readonly status: Status
  readonly traceComplete: boolean
  readonly traceId: string | null
  readonly roleName: 'inspector' | 'reviewer' | null
  readonly terminalReason: 'completed' | 'failed' | 'cancelled' | null
  readonly failureCode: FailureCode | null
  readonly toolOperationsSummary: Readonly<Record<ToolName, number>> | null
}

function empty(status: Status, traceId: string | null): ApiAgentTraceEvidence {
  return { status, traceComplete: false, traceId, roleName: null,
    terminalReason: null, failureCode: null, toolOperationsSummary: null }
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown> : null
}

function isMissing(error: unknown): boolean {
  return record(error)?.code === 'ENOENT'
}

/** Inspect one run-bound API Agent trace without returning model or tool contents. */
export async function inspectApiAgentTrace(input: {
  readonly runId: string
  readonly traceDir: string
  readonly tracePath: string
  readonly processExited: boolean
}): Promise<ApiAgentTraceEvidence> {
  const { runId, traceDir, tracePath, processExited } = input
  if (!RUN_ID.test(runId) || !isAbsolute(traceDir) || !isAbsolute(tracePath)
    || basename(traceDir) !== `safe-trace-${runId}`
    || resolve(dirname(tracePath)) !== resolve(traceDir)) {
    throw new Error('API Agent trace requires this run dedicated absolute directory')
  }
  const match = TRACE_NAME.exec(basename(tracePath))
  if (match === null) throw new Error('API Agent trace path has an invalid file name')
  const traceId = match[1] ?? null
  if (!processExited) return empty('unknown', traceId)

  const markerPath = `${tracePath}.closed`
  try {
    const physicalDir = await realpath(traceDir)
    if (dirname(await realpath(tracePath)) !== physicalDir
      || dirname(await realpath(markerPath)) !== physicalDir) {
      return empty('incomplete', traceId)
    }
  } catch (error: unknown) {
    if (isMissing(error)) {
      try {
        await stat(tracePath)
      } catch (traceError: unknown) {
        if (isMissing(traceError)) return empty('unavailable', traceId)
      }
    }
    return empty('incomplete', traceId)
  }
  let trace: Buffer
  let marker: Record<string, unknown> | null
  try {
    const [traceInfo, markerInfo] = await Promise.all([stat(tracePath), stat(markerPath)])
    if (!traceInfo.isFile() || !markerInfo.isFile()
      || traceInfo.size > MAX_TRACE_BYTES || markerInfo.size > MAX_MARKER_BYTES) {
      return empty('incomplete', traceId)
    }
    const [traceBytes, markerBytes] = await Promise.all([readFile(tracePath), readFile(markerPath)])
    if (traceBytes.length > MAX_TRACE_BYTES || markerBytes.length > MAX_MARKER_BYTES) {
      return empty('incomplete', traceId)
    }
    trace = traceBytes
    marker = record(JSON.parse(markerBytes.toString('utf8')))
  } catch {
    return empty('incomplete', traceId)
  }
  if (marker?.schema_version !== 1 || marker.run_id !== runId || marker.trace_id !== traceId
    || marker.final_bytes !== trace.length || trace.at(-1) !== 10) {
    return empty('incomplete', traceId)
  }
  const lines = trace.toString('utf8').trimEnd().split('\n')
  if (lines.length < 2 || lines.length > MAX_EVENTS) return empty('incomplete', traceId)
  const counts = { list_files: 0, read_file: 0, search_text: 0 }
  let role: 'inspector' | 'reviewer' | null = null
  let terminalReason: 'completed' | 'failed' | 'cancelled' | null = null
  const fields = [
    'captured_at_utc', 'event_seq', 'event_type', 'role_name', 'schema_version',
    'terminal_reason', 'tool_name', 'tool_status', 'trace_id',
  ]
  for (const [index, line] of lines.entries()) {
    let event: Record<string, unknown> | null
    try {
      event = record(JSON.parse(line))
    } catch {
      return empty('incomplete', traceId)
    }
    if (event === null || Object.keys(event).sort().join('|') !== fields.join('|')
      || event.schema_version !== 1 || event.trace_id !== traceId
      || event.event_seq !== index || typeof event.captured_at_utc !== 'string'
      || event.captured_at_utc.length > 40
      || (event.role_name !== 'inspector' && event.role_name !== 'reviewer')) {
      return empty('incomplete', traceId)
    }
    if (role !== null && role !== event.role_name) return empty('incomplete', traceId)
    role = event.role_name
    if (index === 0) {
      if (event.event_type !== 'started' || event.tool_name !== null
        || event.tool_status !== null || event.terminal_reason !== null) {
        return empty('incomplete', traceId)
      }
    } else if (index === lines.length - 1) {
      if (event.event_type !== 'terminal' || event.tool_name !== null
        || event.tool_status !== null
        || !['completed', 'failed', 'cancelled'].includes(String(event.terminal_reason))) {
        return empty('incomplete', traceId)
      }
      terminalReason = event.terminal_reason as 'completed' | 'failed' | 'cancelled'
    } else {
      if (event.event_type !== 'tool_call' || event.terminal_reason !== null
        || !TOOLS.includes(event.tool_name as ToolName)
        || (event.tool_status !== 'completed' && event.tool_status !== 'failed')) {
        return empty('incomplete', traceId)
      }
      counts[event.tool_name as ToolName] += 1
    }
  }
  const failureCode = marker.failure_code
  if (failureCode !== undefined && (terminalReason !== 'failed'
    || !FAILURE_CODES.includes(failureCode as FailureCode))) {
    return empty('incomplete', traceId)
  }
  return { status: 'available', traceComplete: true, traceId,
    roleName: role, terminalReason,
    failureCode: failureCode === undefined ? null : failureCode as FailureCode,
    toolOperationsSummary: counts }
}
