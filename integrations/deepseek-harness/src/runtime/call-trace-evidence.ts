/** Bounded audit metadata from the Runtime's run-dedicated Call Trace. */

import { createHash } from 'node:crypto'
import { readFile, realpath, stat } from 'node:fs/promises'
import { basename, dirname, isAbsolute, resolve } from 'node:path'

const RUN_ID = /^dsh-runtime-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/u
const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/u
const HASH = /^[0-9a-f]{64}$/u
const MAX_BYTES = 16_384

/** Audit facts retained after validating the dedicated two-record Call Trace. */
export interface CallTraceEvidence {
  readonly status: 'settled' | 'unavailable' | 'incomplete'
  readonly callId: string | null
  readonly stdoutBytes: number | null
  readonly stdoutSha256: string | null
  readonly durationMs: number | null
}

function empty(status: 'unavailable' | 'incomplete'): CallTraceEvidence {
  return { status, callId: null, stdoutBytes: null, stdoutSha256: null, durationMs: null }
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

/** Read only a trace physically contained in the Host-created run directory.
 * @param input - run path, child exit, stdout, and terminal status to bind.
 * @returns validated audit facts or a missing/incomplete status.
 */
export async function inspectCallTrace(input: {
  readonly runId: string
  readonly runDir: string
  readonly tracePath: string
  readonly processExited: boolean
  readonly exitCode: number | null
  readonly stdout: string
  readonly taskStatus: string | null
}): Promise<CallTraceEvidence> {
  const { runId, runDir, tracePath } = input
  if (!RUN_ID.test(runId) || !isAbsolute(runDir) || !isAbsolute(tracePath)
    || basename(runDir) !== runId
    || resolve(dirname(tracePath)) !== resolve(runDir)
    || basename(tracePath) !== `${runId}-runtime-call-trace.jsonl`) {
    throw new Error('Call Trace requires this run dedicated absolute path')
  }
  if (!input.processExited) return empty('incomplete')
  try {
    if (dirname(await realpath(tracePath)) !== await realpath(runDir)) return empty('incomplete')
  } catch (error: unknown) {
    return record(error)?.code === 'ENOENT' ? empty('unavailable') : empty('incomplete')
  }
  let bytes: Buffer
  try {
    const info = await stat(tracePath)
    if (!info.isFile() || info.size > MAX_BYTES) return empty('incomplete')
    bytes = await readFile(tracePath)
    if (bytes.length > MAX_BYTES || bytes.length === 0 || bytes.at(-1) !== 10) return empty('incomplete')
  } catch {
    return empty('incomplete')
  }
  let start: Record<string, unknown> | null
  let terminal: Record<string, unknown> | null
  try {
    const lines = bytes.toString('utf8').trimEnd().split('\n')
    if (lines.length !== 2) return empty('incomplete')
    start = record(JSON.parse(lines[0] ?? ''))
    terminal = record(JSON.parse(lines[1] ?? ''))
  } catch {
    return empty('incomplete')
  }
  if (start?.schema_version !== '1' || start.event !== 'call_started'
    || start.state !== 'started' || typeof start.call_id !== 'string'
    || !UUID.test(start.call_id) || terminal?.schema_version !== '1'
    || terminal.event !== 'call_terminal' || terminal.call_id !== start.call_id
    || !['returned', 'process_error', 'transport_error'].includes(String(terminal.state))
    || terminal.runtime_exit_code !== input.exitCode
    || terminal.task_status !== input.taskStatus
    || typeof terminal.duration_ms !== 'number' || !Number.isInteger(terminal.duration_ms)
    || terminal.duration_ms < 0 || typeof terminal.stdout_bytes !== 'number'
    || !Number.isInteger(terminal.stdout_bytes) || terminal.stdout_bytes < 0
    || typeof terminal.stdout_sha256 !== 'string' || !HASH.test(terminal.stdout_sha256)) {
    return empty('incomplete')
  }
  const stdout = Buffer.from(input.stdout, 'utf8')
  if (terminal.stdout_bytes !== stdout.length
    || terminal.stdout_sha256 !== createHash('sha256').update(stdout).digest('hex')) {
    return empty('incomplete')
  }
  return {
    status: 'settled', callId: start.call_id, stdoutBytes: stdout.length,
    stdoutSha256: terminal.stdout_sha256, durationMs: terminal.duration_ms,
  }
}
