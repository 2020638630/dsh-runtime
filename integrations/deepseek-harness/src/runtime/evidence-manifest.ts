/** Assemble one terminal manifest from independent Host and Runtime evidence. */

import { createHash } from 'node:crypto'
import { renameSync } from 'node:fs'
import { readdir, unlink, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { inspectCallTrace } from './call-trace-evidence.ts'
import { inspectApiAgentTrace } from './api-agent-trace-evidence.ts'
import { inspectCodexTrace } from './codex-trace-evidence.ts'
import { inspectSafeTrace } from './safe-trace-evidence.ts'
import { captureWorkspace, compareWorkspace, type WorkspaceSnapshot } from './workspace-evidence.ts'
import type { DshRuntimeTaskKind, RuntimeTaskState } from './run.ts'

const TRACE_NAME = /^codebuddy-safe-worker-[0-9a-f]{32}\.jsonl$/u
const CODEX_TRACE_NAME = /^codex-safe-worker-[0-9a-f]{32}\.jsonl$/u
const API_TRACE_NAME = /^api-agent-safe-role-[0-9a-f]{32}\.jsonl$/u
const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/u
const MODEL_ID = /^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$/u

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function modelId(value: unknown): value is string | null {
  return value === null || (typeof value === 'string' && MODEL_ID.test(value))
}

function modelObservations(
  task: RuntimeTaskState, runId: string, taskKind: DshRuntimeTaskKind,
  expectedWorkerAdapter: 'codebuddy' | 'codex', expectedApiReviewer: boolean,
) {
  const evidence = task.model_observations
  if (taskKind !== 'repository_change' || !Number.isInteger(task.iteration)
    || task.iteration < 1 || task.iteration > 2 || !record(evidence)
    || (evidence.version !== 1 && evidence.version !== 2) || evidence.run_id !== runId
    || evidence.task_id !== task.task_id || evidence.workspace_id !== task.workspace_id
    || !Array.isArray(evidence.entries) || evidence.entries.length === 0
    || evidence.entries.length > 2) return undefined

  const version = evidence.version
  let previousIndex = 0
  const entries = []
  for (const entry of evidence.entries as unknown[]) {
    if (!record(entry)
      || !modelId(entry.requested_model) || !modelId(entry.reported_model)) return undefined
    const index = entry.invocation_index
    const role = entry.role
    if (typeof index !== 'number' || (index !== 1 && index !== 2)
      || index <= previousIndex || index > task.iteration) return undefined
    const adapter = index === 1 ? expectedWorkerAdapter : expectedApiReviewer ? undefined : 'codex'
    if (adapter === undefined || entry.adapter !== adapter
      || role !== (index === 1 ? 'worker' : 'reviewer')) return undefined
    const source = version === 1 ? 'codex_thread_start' : entry.source
    const expectedSource = adapter === 'codex' ? 'codex_thread_start'
      : entry.reported_model === null ? 'unobserved' : 'codebuddy_json_assistant'
    if (source !== expectedSource) return undefined
    if (index === task.iteration) {
      const current = task.invocation_evidence
      if (!record(current) || current.version !== 1 || current.run_id !== runId
        || current.task_id !== task.task_id || current.workspace_id !== task.workspace_id
        || current.adapter !== adapter || current.role !== role || current.invocation_index !== index
        || current.stop_reason !== 'completed' || current.success !== true
        || current.cleanup_ok !== true) return undefined
    }
    previousIndex = index
    entries.push({
      role, adapter, invocation_index: index,
      requested_model: entry.requested_model, reported_model: entry.reported_model,
      ...(version === 2 ? { source } : {}),
    })
  }
  return version === 1 ? { version, source: 'codex_thread_start', entries } : { version, entries }
}

function verification(
  task: RuntimeTaskState, runId: string, taskKind: DshRuntimeTaskKind,
  expectedAdapter: 'codex' | 'api_agent', reviewTraceVerified: boolean,
) {
  const unavailable = {
    source: 'runtime_terminal_json', verdict: 'UNAVAILABLE', verdict_raw_line: null,
    evidence_text: null, evidence_truncated: false, stage_duration_ms: null,
  }
  if (taskKind !== 'repository_change') return unavailable
  if (task.invocation_evidence === undefined) {
    return { ...unavailable, invocation_binding: 'missing' }
  }
  const evidence = task.invocation_evidence
  const output = task.last_invocation_result
  if (!record(evidence) || typeof output !== 'string') {
    return { ...unavailable, invocation_binding: 'invalid' }
  }
  const bytes = Buffer.from(output, 'utf8')
  if (evidence.version !== 1 || evidence.run_id !== runId
    || evidence.task_id !== task.task_id || evidence.workspace_id !== task.workspace_id
    || evidence.role !== 'reviewer' || evidence.adapter !== expectedAdapter
    || task.iteration !== 2 || evidence.invocation_index !== task.iteration
    || evidence.allow_workspace_write !== false || evidence.stop_reason !== 'completed'
    || evidence.success !== true || evidence.cleanup_ok !== true
    || evidence.output_bytes !== bytes.length
    || evidence.output_sha256 !== createHash('sha256').update(bytes).digest('hex')) {
    return { ...unavailable, invocation_binding: 'invalid' }
  }
  if (!reviewTraceVerified) return { ...unavailable, invocation_binding: 'matched' }
  const lines = output.split(/\r?\n/u)
  const nonEmpty = lines.filter(line => line.trim().length > 0)
  const last = nonEmpty.at(-1)?.trim()
  const verdict = last === 'DSH_VERIFICATION: PASS' && task.status === 'completed' ? 'PASS'
    : last === 'DSH_VERIFICATION: FAIL' && task.status === 'failed' ? 'FAIL' : 'UNAVAILABLE'
  if (verdict === 'UNAVAILABLE') return { ...unavailable, invocation_binding: 'matched' }
  const evidenceText = nonEmpty.slice(0, -1).join('\n')
  return {
    source: 'runtime_terminal_json', verdict, invocation_binding: 'matched',
    verdict_raw_line: last,
    evidence_text: evidenceText.slice(0, 20_000),
    evidence_truncated: evidenceText.length > 20_000,
    stage_duration_ms: null,
  }
}

/** Write both artifacts only after the child has exited and the post-run workspace was observed.
 * @param input - bound child result, Host paths, and pre-run workspace observation.
 */
export async function writeTerminalEvidence(input: {
  readonly runId: string
  readonly runDir: string
  readonly safeTraceDir: string
  readonly callTracePath: string
  readonly workspace: string
  readonly workspaceId: string
  readonly before: WorkspaceSnapshot
  readonly taskKind: DshRuntimeTaskKind
  readonly task: RuntimeTaskState
  readonly exitCode: number
  readonly durationMs: number
  readonly stdout: string
  readonly signal?: AbortSignal
  readonly maxTurnsConfig: number | null
  readonly expectedApiInspector?: boolean
  readonly expectedApiReviewer?: boolean
  readonly expectedWorkerAdapter?: 'codebuddy' | 'codex'
}): Promise<void> {
  const { task, runId, runDir } = input
  input.signal?.throwIfAborted()
  if (!UUID.test(task.task_id) || task.task_kind !== input.taskKind
    || task.workspace_id !== input.workspaceId || task.iteration < 0) {
    throw new Error('Runtime TaskState cannot be bound to a terminal Evidence Manifest')
  }
  const after = await captureWorkspace(input.workspace)
  const changes = compareWorkspace(input.before, after)
  const safeTraceNames = await readdir(input.safeTraceDir)
  const traceNames = safeTraceNames.filter(name => TRACE_NAME.test(name))
  const codexTraceNames = safeTraceNames.filter(name => CODEX_TRACE_NAME.test(name))
  const workerTraceNames = input.expectedWorkerAdapter === 'codex'
    ? codexTraceNames : traceNames
  const apiTraceNames = safeTraceNames.filter(name => API_TRACE_NAME.test(name))
  const traceName = workerTraceNames.length === 1 ? workerTraceNames[0] : undefined
  const apiTraceName = apiTraceNames.length === 1 ? apiTraceNames[0] : undefined
  const apiInspection = input.taskKind === 'repository_inspection'
    && (input.expectedApiInspector === true || apiTraceNames.length > 0)
  const apiReview = input.taskKind === 'repository_change'
    && ((input.expectedApiReviewer === true && task.iteration >= 2)
      || apiTraceNames.length > 0)
  const traceFile = apiInspection
    ? apiTraceName === undefined ? null : join(input.safeTraceDir, apiTraceName)
    : traceName === undefined ? null : join(input.safeTraceDir, traceName)
  const rawTrajectory = apiInspection
    ? traceFile === null
      ? { status: apiTraceNames.length === 0 ? 'unavailable' as const : 'unknown' as const,
        traceComplete: false, toolOperationsSummary: null }
      : await inspectApiAgentTrace({
        runId, traceDir: input.safeTraceDir, tracePath: traceFile, processExited: true,
      })
    : input.taskKind === 'repository_inspection'
      ? { status: 'not_applicable' as const, traceComplete: false, toolOperationsSummary: null }
    : traceFile === null
      ? { status: workerTraceNames.length === 0 ? 'unavailable' as const : 'unknown' as const,
        traceComplete: false, turnsUsed: null, toolOperationsSummary: null }
      : input.expectedWorkerAdapter === 'codex'
        ? await inspectCodexTrace({
          runId, traceDir: input.safeTraceDir, tracePath: traceFile, processExited: true,
        })
        : await inspectSafeTrace({
          runId, traceDir: input.safeTraceDir, tracePath: traceFile, processExited: true,
        })
  const trajectory = apiInspection && 'roleName' in rawTrajectory
    && rawTrajectory.status === 'available' && rawTrajectory.roleName !== 'inspector'
    ? { ...rawTrajectory, status: 'incomplete' as const, traceComplete: false,
      toolOperationsSummary: null }
    : rawTrajectory
  const reviewTraceFile = apiReview && apiTraceName !== undefined
    ? join(input.safeTraceDir, apiTraceName) : null
  const rawReviewTrajectory = reviewTraceFile === null ? null : await inspectApiAgentTrace({
    runId, traceDir: input.safeTraceDir, tracePath: reviewTraceFile, processExited: true,
  })
  const reviewStatus = !apiReview ? 'not_applicable'
    : apiTraceNames.length > 1 ? 'unknown'
      : rawReviewTrajectory === null ? 'unavailable'
        : rawReviewTrajectory.roleName === 'reviewer'
          ? rawReviewTrajectory.status : 'incomplete'
  const reviewVerified = !apiReview || (reviewStatus === 'available'
    && rawReviewTrajectory?.terminalReason === 'completed')
  const audit = await inspectCallTrace({
    runId, runDir, tracePath: input.callTracePath, processExited: true,
    exitCode: input.exitCode, stdout: input.stdout, taskStatus: task.status,
  })
  const diffPath = join(runDir, 'diff.patch')
  const models = modelObservations(task, runId, input.taskKind,
    input.expectedWorkerAdapter ?? 'codebuddy', input.expectedApiReviewer === true)
  const manifest = {
    schema_version: '1', task_id: task.task_id, run_id: runId,
    workspace_id: task.workspace_id, task_kind: input.taskKind, status: task.status,
    exit_code: input.exitCode, duration_ms: input.durationMs,
    authority_phases: {
      task_ceiling_allow_write: input.taskKind === 'repository_change',
      phase_1_codebuddy_effective_write: input.taskKind === 'repository_change'
        && task.iteration > 0 && input.expectedWorkerAdapter !== 'codex' ? true : null,
      phase_1_codex_effective_write: input.taskKind === 'repository_change'
        && task.iteration > 0 && input.expectedWorkerAdapter === 'codex' ? true : null,
      phase_2_codex_effective_write: apiInspection || input.expectedApiReviewer === true || apiReview ? null
        : task.iteration >= (input.taskKind === 'repository_change' ? 2 : 1) ? false : null,
      phase_2_api_agent_effective_write: apiReview && task.iteration >= 2 ? false : null,
    },
    workspace_changes: { ...changes, diff: undefined, diff_content_ref: diffPath },
    evidence_scope: {
      review_verdict_basis: 'runtime_terminal_model_report',
      workspace_change_basis: 'bounded_git_pre_post_snapshot',
      change_attribution: 'not_established_shared_workspace',
    },
    execution_trajectory: {
      source: apiInspection ? 'api_agent_safe_event_trace'
        : input.expectedWorkerAdapter === 'codex' ? 'codex_safe_event_trace'
          : 'safe_event_trace',
      status: trajectory.status,
      trace_complete: trajectory.traceComplete,
      trace_scope: 'observed_stream_complete', trace_file: traceFile,
      turns_used: null, turns_metrics_status: input.taskKind === 'repository_inspection'
        ? 'not_applicable' : trajectory.status === 'available' ? 'unverified_base' : 'unavailable',
      max_observed_turn_index: null, turn_index_source: 'unavailable',
      max_turns_config: apiInspection ? null : input.maxTurnsConfig,
      tool_operations_summary: trajectory.toolOperationsSummary,
    },
    review_trajectory: {
      source: apiReview ? 'api_agent_safe_event_trace' : 'not_applicable',
      status: reviewStatus,
      trace_complete: reviewStatus === 'available' && rawReviewTrajectory?.traceComplete === true,
      trace_file: reviewTraceFile,
      role_name: reviewStatus === 'available' ? 'reviewer' : null,
      tool_operations_summary: reviewStatus === 'available'
        ? rawReviewTrajectory?.toolOperationsSummary : null,
      terminal_reason: reviewStatus === 'available'
        ? rawReviewTrajectory?.terminalReason : null,
      failure_code: reviewStatus === 'available'
        ? rawReviewTrajectory?.failureCode : null,
    },
    verification: verification(task, runId, input.taskKind,
      input.expectedApiReviewer === true ? 'api_agent' : 'codex', reviewVerified),
    ...(models === undefined ? {} : { model_observations: models }),
    audit: {
      source: 'call_trace', status: audit.status, call_id: audit.callId,
      call_trace_path: input.callTracePath, stdout_bytes: audit.stdoutBytes,
      stdout_sha256: audit.stdoutSha256,
    },
  }
  await writeFile(diffPath, changes.diff, { flag: 'wx' })
  const pending = join(runDir, 'evidence-manifest.v1.pending')
  await writeFile(pending, `${JSON.stringify(manifest, null, 2)}\n`, { flag: 'wx' })
  try {
    input.signal?.throwIfAborted()
    renameSync(pending, join(runDir, 'evidence-manifest.v1.json'))
  } catch (error) {
    await unlink(pending).catch(() => {})
    throw error
  }
}
