/** Assemble one terminal manifest from independent Host and Runtime evidence. */

import { readdir, rename, writeFile } from 'node:fs/promises'
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

function verification(task: RuntimeTaskState, taskKind: DshRuntimeTaskKind) {
  if (taskKind !== 'repository_change' || task.iteration < 2) {
    return {
      source: 'runtime_terminal_json', verdict: 'UNAVAILABLE', verdict_raw_line: null,
      evidence_text: null, evidence_truncated: false, stage_duration_ms: null,
    }
  }
  const lines = task.last_invocation_result?.split(/\r?\n/u) ?? []
  const nonEmpty = lines.filter(line => line.trim().length > 0)
  const last = nonEmpty.at(-1)?.trim()
  const verdict = last === 'DSH_VERIFICATION: PASS' ? 'PASS'
    : last === 'DSH_VERIFICATION: FAIL' ? 'FAIL' : 'UNAVAILABLE'
  const evidence = verdict === 'UNAVAILABLE' ? null : nonEmpty.slice(0, -1).join('\n')
  return {
    source: 'runtime_terminal_json', verdict,
    verdict_raw_line: verdict === 'UNAVAILABLE' ? null : last,
    evidence_text: evidence === null ? null : evidence.slice(0, 20_000),
    evidence_truncated: evidence !== null && evidence.length > 20_000,
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
  readonly maxTurnsConfig: number | null
  readonly expectedApiInspector?: boolean
  readonly expectedApiReviewer?: boolean
  readonly expectedWorkerAdapter?: 'codebuddy' | 'codex'
}): Promise<void> {
  const { task, runId, runDir } = input
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
    verification: reviewVerified ? verification(task, input.taskKind) : {
      source: 'runtime_terminal_json', verdict: 'UNAVAILABLE', verdict_raw_line: null,
      evidence_text: null, evidence_truncated: false, stage_duration_ms: null,
    },
    audit: {
      source: 'call_trace', status: audit.status, call_id: audit.callId,
      call_trace_path: input.callTracePath, stdout_bytes: audit.stdoutBytes,
      stdout_sha256: audit.stdoutSha256,
    },
  }
  await writeFile(diffPath, changes.diff, { flag: 'wx' })
  const pending = join(runDir, 'evidence-manifest.v1.pending')
  await writeFile(pending, `${JSON.stringify(manifest, null, 2)}\n`, { flag: 'wx' })
  await rename(pending, join(runDir, 'evidence-manifest.v1.json'))
}
