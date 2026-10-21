/**
 * One-shot DSH-Runtime child lifecycle over the product JSON stdio entrypoint
 * (`python -m dsh_runtime.entrypoint`). The provider owns only process
 * lifecycle and transport: it resolves the active workspace, writes one JSON
 * request, collects one terminal TaskState JSON response, and maps that
 * settled DSH-Runtime result to the seam `SubagentResult`. Every workflow,
 * planner, provider-selection, authority, verification, retry, and settlement
 * decision remains inside DSH-Runtime.
 *
 * @module @deepseek-ai/dsh-subagent-dsh-runtime/run
 */

import { randomUUID } from 'node:crypto'
import { existsSync, mkdirSync, realpathSync, writeFileSync } from 'node:fs'
import { rename, writeFile } from 'node:fs/promises'
import { isAbsolute, join, relative, sep, toNamespacedPath } from 'node:path'
import { StringDecoder } from 'node:string_decoder'
import { brandString } from '@deepseek-ai/dsh-brand'
import type { ContentBlock } from '@deepseek-ai/dsh-llm'
import type { SessionId } from '@deepseek-ai/dsh-session'
import {
  settleRunResult,
  subprocessRunHandle,
  type SubagentResult,
  type SubagentRun,
  type SubagentStartRequest,
  type SubagentStopReason,
} from '@deepseek-ai/dsh-subagent'
import {
  scrubbedParentEnv,
  type SubprocessHandle,
  type SubprocessSpawnSpec,
} from '@deepseek-ai/dsh-subprocess'
import { writeTerminalEvidence } from './evidence-manifest.ts'
import { captureWorkspace, type WorkspaceSnapshot } from './workspace-evidence.ts'

/** Default POSIX grace between subprocess termination tiers. */
export const DEFAULT_DISPOSE_GRACE_MS = 3_000

/** The frozen A1 product module entry (never a test adapter). */
export const PRODUCT_MODULE = 'dsh_runtime.entrypoint'

/** Environment key carrying the DSH-Runtime deploy root to the child. */
const RUNTIME_ROOT_ENV = 'PYTHONPATH'

/**
 * Terminal DSH-Runtime task statuses. A `completed` status is a successful
 * business settlement; the remaining valid statuses are settled business
 * outcomes that still publish through a JSON TaskState at process exit 0, and
 * are therefore NOT a transport failure.
 */
export type RuntimeTerminalStatus =
  | 'completed'
  | 'failed'
  | 'timed_out'
  | 'max_iterations'

/** Workload identities accepted by the DSH-Runtime product entrypoint. */
export type DshRuntimeTaskKind =
  | 'repository_change'
  | 'repository_inspection'

/** The frozen A1 terminal TaskState JSON envelope (production serialization). */
export interface RuntimeTaskState {
  readonly task_id: string
  readonly task_kind: string
  readonly workspace_id: string
  readonly status: string
  readonly iteration: number
  readonly result: string | null
  readonly error: string | null
  readonly last_invocation_result: string | null
}

/**
 * True when `status` is a settled DSH-Runtime terminal outcome.
 * @param status - TaskState status reported by the Runtime envelope.
 * @returns `true` for a settled terminal outcome, narrowing the status type.
 */
export function isTerminalRuntimeStatus(status: string): status is RuntimeTerminalStatus {
  return status === 'completed' || status === 'failed'
    || status === 'timed_out' || status === 'max_iterations'
}

/**
 * Build the fixed A1 product argv. The module entrypoint is resolved by the
 * child's `cwd`/`PYTHONPATH` (the configured Runtime root), never by the
 * harness process cwd and never by a hard-coded deploy path.
 * @param python - Python executable used to launch the product module.
 * @returns the frozen A1 argv sequence.
 */
export function productArgv(python: string): string[] {
  return [python, '-m', PRODUCT_MODULE]
}

/** Build the exact A1 request object for one delegated run. */
export interface RuntimeRequestInput {
  readonly goal: string
  readonly workspace_id: string
  readonly workspace_path: string
  readonly task_kind: DshRuntimeTaskKind
}

/**
 * The frozen A1 stdin request JSON.
 * @param input - goal, workspace identity, and resolved task identity for one delegated run.
 * @returns the exact JSON request written to the child stdin.
 */
export function encodeRequest(input: RuntimeRequestInput): string {
  return JSON.stringify({
    goal: input.goal,
    workspace_id: input.workspace_id,
    workspace_path: input.workspace_path,
    task_kind: input.task_kind,
  })
}

/**
 * Parse a complete production TaskState from one stdout line. Returns `undefined`
 * for a blank line and throws on malformed JSON or an invalid envelope, so the
 * caller can classify transport failure without shaping a fake TaskState.
 * @param line - one stdout line emitted by the product entrypoint.
 * @returns the parsed TaskState, or `undefined` for a blank line.
 */
export function parseTaskState(line: string): RuntimeTaskState | undefined {
  const trimmed = line.trim()
  if (trimmed.length === 0) return undefined
  const value: unknown = JSON.parse(trimmed)
  if (!isRuntimeTaskState(value)) {
    throw new Error('DSH-Runtime response does not match the TaskState JSON envelope')
  }
  return value
}

/** Narrow one parsed Runtime result to the complete production TaskState envelope. */
function isRuntimeTaskState(value: unknown): value is RuntimeTaskState {
  return isRecord(value)
    && typeof value.task_id === 'string'
    && typeof value.task_kind === 'string'
    && typeof value.workspace_id === 'string'
    && typeof value.status === 'string'
    && typeof value.iteration === 'number'
    && Number.isFinite(value.iteration)
    && isNullableString(value.result)
    && isNullableString(value.error)
    && isNullableString(value.last_invocation_result)
}

/** Narrow a parsed JSON object for keyed envelope validation. */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Check the nullable text fields emitted in every production TaskState. */
function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string'
}

/** Safe diagnostic text for a transport/envelope failure, never a fake TaskState. */
function transportDiagnostic(detail: string): string {
  return `DSH-Runtime transport failure: ${detail}`
}

/**
 * Map a settled DSH-Runtime TaskState to a seam result. Only a `completed`
 * status is success; a valid non-completed terminal status is a SETTLED
 * business failure (distinct from a transport failure), and its terminal
 * `result`/`error` are preserved safely.
 * @param task - terminal TaskState parsed from the product entrypoint.
 * @returns the seam result carrying the preserved output or the failure diagnostic.
 */
export function mapTaskState(task: RuntimeTaskState): SubagentResult {
  const preserved = task.result ?? task.last_invocation_result
  if (task.status === 'completed') {
    return {
      output: [{ type: 'text', text: preserved ?? '' }],
      stopReason: 'completed',
    }
  }
  const reason = task.error ?? `DSH-Runtime task settled as ${task.status}`
  const diagnostic = `DSH-Runtime business failure: ${reason}`
  return {
    output: preserved === null ? [] : [{ type: 'text', text: preserved }],
    ...(diagnostic.length === 0 ? {} : { diagnostic }),
    stopReason: 'error',
  }
}

/** Fully resolved inputs for one DSH-Runtime child run. */
export interface DshRuntimeRunSpec {
  /** Parent Session workspace, passed to the Runtime as `workspace_path`. */
  readonly cwd: string
  /** Parent Session id, passed to the Runtime as `workspace_id`. */
  readonly workspaceId: string
  /** Provider-resolved workload identity, passed to the Runtime as `task_kind`. */
  readonly taskKind: DshRuntimeTaskKind
  /** Absolute DSH-Runtime deploy root (module resolve base and child cwd). */
  readonly runtimeRoot: string
  /** Python executable used to launch the product module. */
  readonly python: string
  /** Explicit deployment/test environment layered after the shared scrub. */
  readonly env: Record<string, string>
  /** Optional Host-owned evidence root; omitted for existing one-shot runs. */
  readonly evidenceRoot?: string
  /** Subprocess termination grace passed to the shared managed-range owner. */
  readonly disposeGraceMs: number
  /** Shared subprocess service spawn operation. */
  readonly spawn: (spec: SubprocessSpawnSpec) => SubprocessHandle
  /** Diagnostic sink for a product failure kept outside model-visible text. */
  readonly onError?: (error: Error, stopReason: SubagentStopReason) => void
  /** Host-only diagnostic for evidence failures; never changes the task verdict. */
  readonly onEvidenceError?: (error: Error) => void
}

/**
 * The complete resolved spawn spec the provider issues through the seam.
 * @param spec - resolved workspace, runtime root, python and process policy.
 * @param evidenceEnv - Host-generated paths owned by this run.
 * @returns the subprocess spawn spec for the one-shot Runtime child.
 */
export function buildSpawnSpec(
  spec: DshRuntimeRunSpec,
  evidenceEnv: Record<string, string> = {},
): SubprocessSpawnSpec {
  return {
    argv: productArgv(spec.python),
    cwd: spec.runtimeRoot,
    stdio: { stdin: 'pipe', stdout: 'pipe', stderr: 'pipe' },
    graceMs: spec.disposeGraceMs,
    env: { ...scrubbedParentEnv(), [RUNTIME_ROOT_ENV]: spec.runtimeRoot, ...spec.env, ...evidenceEnv },
  }
}

/** Normalize an unknown thrown value to an Error (the catch binding is `unknown`). */
function toError(value: unknown): Error {
  /* v8 ignore next -- typed subprocess failures reject with Error. */
  return value instanceof Error ? value : new Error(String(value))
}

/** Replace only this new run's state after the complete JSON is on disk. */
async function settleEvidenceState(
  runDir: string,
  state: { readonly runId: string; readonly workspaceId: string; readonly stopReason: string; readonly manifestAvailable: boolean },
): Promise<void> {
  const pending = join(runDir, 'run-state.pending')
  await writeFile(pending, `${JSON.stringify({
    schema_version: 1, run_id: state.runId, workspace_id: state.workspaceId,
    phase: 'settled', stop_reason: state.stopReason, manifest_available: state.manifestAvailable,
  })}\n`, { flag: 'wx' })
  await rename(pending, join(runDir, 'run-state.json'))
}

/**
 * Validate and preserve the one-shot task before crossing the process boundary.
 * @param prompt - task content accepted from the shared subagent service.
 * @returns the exact non-blank text block sequence.
 */
export function textTask(prompt: readonly ContentBlock[]): string {
  if (prompt.length === 0) {
    throw new Error('subagent-dsh-runtime: the one-shot task must contain only text blocks')
  }
  const texts: string[] = []
  for (const block of prompt) {
    if (block.type !== 'text') {
      throw new Error('subagent-dsh-runtime: the one-shot task must contain only text blocks')
    }
    texts.push(block.text)
  }
  if (texts.every(text => text.trim().length === 0)) {
    throw new Error('subagent-dsh-runtime: the one-shot task must not be empty')
  }
  return texts.join('')
}

/**
 * Close the child's stdin, terminate the managed range, and wait for the
 * subprocess owner to prove it is quiescent.
 * @param child - shared-service handle that owns the managed range.
 */
export async function disposeDshRuntimeChild(child: SubprocessHandle): Promise<void> {
  try {
    child.stdin?.end()
  } catch {
    // A concurrently closed stdin does not change range ownership below.
  }
  child.terminate()
  try {
    await child.waitForExit()
  } catch (error: unknown) {
    throw new Error(
      `subagent-dsh-runtime: dispose failed (${transportDiagnostic('process teardown')})`,
      { cause: toError(error) },
    )
  }
  await child.done.catch(() => {})
}

/** Collect a full piped stream as UTF-8 text. */
async function collectText(stream: NonNullable<SubprocessHandle['stdout']>): Promise<string> {
  let text = ''
  const decoder = new StringDecoder('utf8')
  for await (const chunk of stream) {
    text += decoder.write(Buffer.isBuffer(chunk) ? chunk : Buffer.from(String(chunk)))
  }
  text += decoder.end()
  return text
}

/**
 * Start `python -m dsh_runtime.entrypoint` and publish its one-shot run.
 * @param request - resolved shared subagent request.
 * @param spec - resolved task and workspace identity, runtime root, process service, and policy.
 * @returns the published run after the child is spawned and the request is written.
 */
export function startDshRuntimeRun(
  request: SubagentStartRequest,
  spec: DshRuntimeRunSpec,
): Promise<SubagentRun> {
  try {
    return Promise.resolve(createDshRuntimeRun(request, spec))
  } catch (error: unknown) {
    return Promise.reject(toError(error))
  }
}

async function createDshRuntimeRun(
  request: SubagentStartRequest,
  spec: DshRuntimeRunSpec,
): Promise<SubagentRun> {
  const goal = textTask(request.prompt)
  if (request.signal.aborted) {
    throw new Error('subagent-dsh-runtime: request was aborted before the Runtime child started')
  }

  const childId = brandString<SessionId>(randomUUID())
  let evidenceEnv: Record<string, string> = {}
  let evidencePaths: { runId: string; runDir: string; safeTraceDir: string; callTracePath: string } | undefined
  let before: WorkspaceSnapshot | undefined
  if (spec.evidenceRoot !== undefined) {
    if (!isAbsolute(spec.evidenceRoot)) {
      throw new Error('subagent-dsh-runtime: evidenceRoot must be absolute')
    }
    mkdirSync(spec.evidenceRoot, { recursive: true })
    const physicalEvidenceRoot = realpathSync(spec.evidenceRoot)
    const fromWorkspace = relative(realpathSync(spec.cwd), physicalEvidenceRoot)
    if (fromWorkspace === '' || (fromWorkspace !== '..'
      && !fromWorkspace.startsWith(`..${sep}`) && !isAbsolute(fromWorkspace))) {
      throw new Error('subagent-dsh-runtime: evidenceRoot must be outside the user workspace')
    }
    for (const key of ['DSH_RUNTIME_RUN_ID', 'DSH_RUNTIME_CALL_TRACE_PATH', 'DSH_CODEBUDDY_SAFE_EVENT_TRACE_DIR']) {
      if (Object.hasOwn(spec.env, key)) {
        throw new Error(`subagent-dsh-runtime: ${key} conflicts with Host-owned evidence paths`)
      }
    }
    const runId = `dsh-runtime-${childId}`
    const runDir = join(physicalEvidenceRoot, 'dsh-runtime', runId)
    mkdirSync(join(physicalEvidenceRoot, 'dsh-runtime'), { recursive: true })
    mkdirSync(runDir)
    const safeTraceDir = join(runDir, `safe-trace-${runId}`)
    mkdirSync(safeTraceDir)
    const callTracePath = join(runDir, `${runId}-runtime-call-trace.jsonl`)
    evidenceEnv = {
      DSH_RUNTIME_RUN_ID: runId,
      // Python's Windows file APIs need the extended path form once the
      // Host-generated evidence filename crosses the legacy MAX_PATH limit.
      DSH_RUNTIME_CALL_TRACE_PATH: toNamespacedPath(callTracePath),
      DSH_CODEBUDDY_SAFE_EVENT_TRACE_DIR: toNamespacedPath(safeTraceDir),
    }
    evidencePaths = {
      runId, runDir, safeTraceDir,
      callTracePath,
    }
    try {
      writeFileSync(join(runDir, 'run-state.json'), `${JSON.stringify({
        schema_version: 1, run_id: runId, workspace_id: spec.workspaceId, phase: 'running',
        started_at: new Date().toISOString(),
      })}\n`, { flag: 'wx' })
    } catch (error: unknown) {
      spec.onEvidenceError?.(toError(error))
    }
    try {
      before = await captureWorkspace(spec.cwd)
    } catch (error: unknown) {
      spec.onEvidenceError?.(toError(error))
    }
  }

  const startedAt = performance.now()
  let child: SubprocessHandle
  try {
    child = spec.spawn(buildSpawnSpec(spec, evidenceEnv))
  } catch (error: unknown) {
    if (evidencePaths !== undefined) {
      try {
        await settleEvidenceState(evidencePaths.runDir, {
          runId: evidencePaths.runId, workspaceId: spec.workspaceId,
          stopReason: 'error', manifestAvailable: false,
        })
      } catch (stateError: unknown) {
        spec.onEvidenceError?.(toError(stateError))
      }
    }
    throw new Error(
      `subagent-dsh-runtime: ${transportDiagnostic('spawn failed')}`,
      { cause: toError(error) },
    )
  }

  let stderrText = ''
  const onStderr = (chunk: Buffer | string): void => {
    const bytes = typeof chunk === 'string' ? Buffer.from(chunk) : chunk
    stderrText += bytes.toString('utf8')
  }
  child.stderr?.on('data', onStderr)
  const disposeProcess = async (): Promise<void> => {
    try {
      await disposeDshRuntimeChild(child)
    } finally {
      child.stderr?.off('data', onStderr)
    }
  }

  const requestCancel = (): void => {
    // The child owns no cooperative protocol cancellation; dispose reaches
    // quiescence through the seam's termination ladder.
  }
  const onAbort = (): void => { requestCancel() }
  request.signal.addEventListener('abort', onAbort, { once: true })

  let diagnostic: string | undefined
  const settledResult: Promise<SubagentResult> = settleRunResult({
    attempt: async () => {
      try {
        const stdin = child.stdin
        if (stdin === undefined) {
          throw new Error('subagent-dsh-runtime: child stdin is not piped')
        }
        stdin.write(encodeRequest({
          goal,
          workspace_id: spec.workspaceId,
          workspace_path: spec.cwd,
          task_kind: spec.taskKind,
        }))
        stdin.end()
        const stdout = await collectText(child.stdout as NonNullable<SubprocessHandle['stdout']>)
        const outcome = await child.done
        if (outcome.exitCode !== 0) {
          throw new Error(transportDiagnostic('non-zero process exit'))
        }
        const line = stdout.split(/\r?\n/u).map(part => part.trim()).find(Boolean) ?? ''
        if (line.length === 0) {
          throw new Error(transportDiagnostic('empty stdout'))
        }
        const task = parseTaskState(line)
        if (task === undefined) {
          throw new Error(transportDiagnostic('missing TaskState JSON'))
        }
        if (!isTerminalRuntimeStatus(task.status)) {
          throw new Error(transportDiagnostic(`invalid runtime status "${task.status}"`))
        }
        if (evidencePaths !== undefined && before !== undefined) {
          try {
            await writeTerminalEvidence({
              ...evidencePaths, before, workspace: spec.cwd, workspaceId: spec.workspaceId,
              taskKind: spec.taskKind,
              task, exitCode: outcome.exitCode, stdout,
              durationMs: Math.max(0, Math.round(performance.now() - startedAt)),
              maxTurnsConfig: (() => {
                const raw = spec.env.DSH_CODEBUDDY_MAX_TURNS
                if (raw === undefined) return 12
                const parsed = Number(raw)
                return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null
              })(),
            })
          } catch (error: unknown) {
            spec.onEvidenceError?.(toError(error))
          }
        }
        return mapTaskState(task)
      } catch (error: unknown) {
        // A transport/envelope failure is normalizable: preserve the safe
        // diagnostic so the seam can flatten it to a provider/process error.
        const message = toError(error).message
        diagnostic = message.startsWith('DSH-Runtime transport failure:')
          ? message
          : transportDiagnostic(message)
        throw error
      }
    },
    collectOutput: () => [],
    collectDiagnostic: () => diagnostic,
    cancelled: () => request.signal.aborted,
    onError: spec.onError,
    signal: request.signal,
    onAbort,
  })
  const result: Promise<SubagentResult> = settledResult.then(async (outcome) => {
    if (evidencePaths !== undefined) {
      try {
        await settleEvidenceState(evidencePaths.runDir, {
          runId: evidencePaths.runId, workspaceId: spec.workspaceId,
          stopReason: outcome.stopReason,
          manifestAvailable: existsSync(join(evidencePaths.runDir, 'evidence-manifest.v1.json')),
        })
      } catch (error: unknown) {
        spec.onEvidenceError?.(toError(error))
      }
    }
    return outcome
  })

  return subprocessRunHandle({
    id: childId,
    result,
    signal: request.signal,
    onAbort,
    requestCancel,
    teardown: disposeProcess,
  })
}
