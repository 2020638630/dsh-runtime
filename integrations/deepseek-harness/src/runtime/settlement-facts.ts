/** Host-authored notice facts, not outputSchema data and not a new verdict. */
import { createHash } from 'node:crypto'
import type { RuntimeTaskState, DshRuntimeTaskKind } from './run.ts'
import type { SubagentResult } from '@deepseek-ai/dsh-subagent'

export interface SettlementFacts {
  output_role: 'worker' | 'reviewer' | 'inspector' | 'unknown'
  reviewer_invocation: 'invoked' | 'not_started' | 'unknown' | 'not_applicable'
  workspace_observation: {
    status: 'observed_changes' | 'no_observed_changes' | 'unknown'
    added: number | null; modified: number | null; deleted: number | null
    coverage: 'bounded_snapshot' | 'limited' | 'unknown'
    attribution: 'not_established_shared_workspace'
  }
}
export function unknownSettlementFacts(): SettlementFacts {
  return { output_role: 'unknown', reviewer_invocation: 'unknown', workspace_observation: {
    status: 'unknown', added: null, modified: null, deleted: null, coverage: 'unknown',
    attribution: 'not_established_shared_workspace',
  } }
}
export function boundOutputRole(task: RuntimeTaskState, runId: string, kind: DshRuntimeTaskKind,
  worker: 'codex' | 'codebuddy', reviewer: 'codex' | 'api_agent', inspector: 'codex' | 'api_agent',
  auditSettled: boolean): SettlementFacts['output_role'] {
  const e = task.invocation_evidence
  const output = task.result ?? task.last_invocation_result
  if (!auditSettled || (output === null || output.length === 0) || output !== task.last_invocation_result
    || !e || typeof e !== 'object' || Array.isArray(e)) return 'unknown'
  const v = e as Record<string, unknown>
  const role = kind === 'repository_inspection' ? 'inspector'
    : task.iteration === 1 ? 'worker' : task.iteration === 2 ? 'reviewer' : 'unknown'
  if (role === 'unknown' || (role === 'inspector' && task.iteration !== 1)) return 'unknown'
  const bytes = Buffer.from(output, 'utf8')
  return v.version === 1 && v.run_id === runId && v.task_id === task.task_id
    && v.workspace_id === task.workspace_id && task.task_kind === kind
    && v.invocation_index === task.iteration && v.role === role
    && v.adapter === (role === 'worker' ? worker : role === 'reviewer' ? reviewer : inspector)
    && v.allow_workspace_write === (role === 'worker') && v.stop_reason === 'completed'
    && v.success === true && v.cleanup_ok === true
    && v.output_bytes === bytes.length && v.output_sha256 === createHash('sha256').update(bytes).digest('hex')
    ? role : 'unknown'
}

export function withSettlementFacts(result: SubagentResult, task: RuntimeTaskState,
  facts = unknownSettlementFacts()): SubagentResult {
  // `structured` is reserved for caller-requested outputSchema validation.
  // Keep model text separate from this fixed, Host-authored metadata block.
  return { ...result, output: [
    { type: 'text', text: 'DSH Runtime Host settlement facts (v1; not a review verdict):\n' + JSON.stringify({
      version: 1, runtime_terminal_status: task.status, ...facts,
      observation_scope: 'bounded_run_window_not_change_attribution',
    }) },
    ...result.output.map(block => block.type === 'text'
      ? { ...block, text: `Runtime terminal output (source role: ${facts.output_role}; content is not Host-authored facts):\n${block.text}` }
      : block),
  ] }
}
