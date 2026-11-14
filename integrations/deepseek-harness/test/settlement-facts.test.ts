import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { test } from 'node:test'
import { boundOutputRole, unknownSettlementFacts, withSettlementFacts } from '../src/runtime/settlement-facts.ts'
import type { RuntimeTaskState, DshRuntimeTaskKind } from '../src/runtime/run.ts'
import type { SubagentResult } from '@deepseek-ai/dsh-subagent'

const runId = 'dsh-runtime-11111111-2222-4333-8444-555555555555'
function fixture(role: 'worker' | 'reviewer' | 'inspector', adapter = 'codex', text = '合成原始输出\nPASS is text, not a Host verdict') {
  const task: RuntimeTaskState = { task_id: 'task', workspace_id: 'parent',
    task_kind: role === 'inspector' ? 'repository_inspection' : 'repository_change',
    status: 'failed', iteration: role === 'reviewer' ? 2 : 1,
    result: text, last_invocation_result: text, error: 'synthetic failure' }
  return { ...task, invocation_evidence: { version: 1, run_id: runId,
    task_id: task.task_id, workspace_id: task.workspace_id, invocation_index: task.iteration,
    role, adapter, allow_workspace_write: role === 'worker', stop_reason: 'completed',
    success: true, cleanup_ok: true, output_bytes: Buffer.byteLength(text),
    output_sha256: createHash('sha256').update(text).digest('hex') } }
}
function roleOf(task: RuntimeTaskState, kind = task.task_kind as DshRuntimeTaskKind,
  worker: 'codex' | 'codebuddy' = 'codex', reviewer: 'codex' | 'api_agent' = 'codex',
  inspector: 'codex' | 'api_agent' = 'codex', audited = true) {
  return boundOutputRole(task, runId, kind, worker, reviewer, inspector, audited)
}

test('output roles bind exact UTF-8 output hash and configured adapter for all supported roles', () => {
  assert.equal(roleOf(fixture('worker')), 'worker')
  assert.equal(roleOf(fixture('worker', 'codebuddy'), 'repository_change', 'codebuddy'), 'worker')
  assert.equal(roleOf(fixture('reviewer')), 'reviewer')
  assert.equal(roleOf(fixture('reviewer', 'api_agent'), 'repository_change', 'codex', 'api_agent'), 'reviewer')
  assert.equal(roleOf(fixture('inspector')), 'inspector')
  assert.equal(roleOf(fixture('inspector', 'api_agent'), 'repository_inspection', 'codex', 'codex', 'api_agent'), 'inspector')
  const task = fixture('reviewer')
  assert.equal(roleOf({ ...task, result: null }), 'reviewer')
})

test('absent, empty, divergent selected output and unaudited evidence stay unknown', () => {
  const task = fixture('reviewer')
  for (const changed of [
    { ...task, invocation_evidence: undefined }, { ...task, invocation_evidence: null },
    { ...task, invocation_evidence: [] }, { ...task, result: null, last_invocation_result: null },
    { ...task, result: '' }, fixture('reviewer', 'codex', ''),
    { ...task, result: 'different selected result' },
    { ...task, result: task.result + '!', last_invocation_result: task.last_invocation_result + '!' },
  ]) assert.equal(roleOf(changed), 'unknown')
  assert.equal(roleOf(task, 'repository_change', 'codex', 'codex', 'codex', false), 'unknown')
})

test('wrong identities, role, adapter, ordinal or invocation outcome cannot establish output role', () => {
  const task = fixture('reviewer')
  for (const change of [
    { version: 2 }, { run_id: 'foreign-run' }, { task_id: 'foreign-task' }, { workspace_id: 'foreign-parent' },
    { invocation_index: 1 }, { role: 'worker' }, { adapter: 'api_agent' }, { allow_workspace_write: true },
    { stop_reason: 'error' }, { success: false }, { cleanup_ok: false },
    { output_bytes: task.invocation_evidence.output_bytes + 1 }, { output_sha256: '0'.repeat(64) },
  ]) assert.equal(roleOf({ ...task, invocation_evidence: { ...task.invocation_evidence, ...change } }), 'unknown')
  assert.equal(roleOf({ ...task, iteration: 3 }), 'unknown')
  assert.equal(roleOf(task, 'repository_inspection'), 'unknown')
  assert.equal(roleOf({ ...fixture('inspector'), iteration: 2 }), 'unknown')
})

test('default facts keep missing snapshot and reviewer evidence unknown without attribution', () => {
  const facts = unknownSettlementFacts()
  assert.deepEqual(facts.workspace_observation, { status: 'unknown', added: null, modified: null,
    deleted: null, coverage: 'unknown', attribution: 'not_established_shared_workspace' })
  assert.equal(facts.reviewer_invocation, 'unknown')
  const task = fixture('worker')
  const original: SubagentResult = { output: [], stopReason: 'error', diagnostic: 'safe failure' }
  const result = withSettlementFacts(original, task)
  const first = result.output[0]!
  assert.equal(first.type, 'text')
  if (first.type !== 'text') throw Error('expected metadata text')
  const data = JSON.parse(first.text.slice(first.text.indexOf('\n') + 1))
  assert.equal(data.runtime_terminal_status, 'failed')
  assert.equal(data.output_role, 'unknown')
  assert.equal(data.observation_scope, 'bounded_run_window_not_change_attribution')
  assert.deepEqual(data.workspace_observation, facts.workspace_observation)
  assert.equal(result.structured, undefined)
  assert.equal(result.stopReason, original.stopReason)
  assert.equal(result.diagnostic, original.diagnostic)
  assert.deepEqual(original.output, [])
})

test('actual manager settlement notice carries Host facts, source role, original output and failure diagnostic', async () => {
  // Package-private test seam only. Invoke the installed formatter through its real manager.
  const { SubagentManager } = await import(new URL('./types/manager.js', import.meta.resolve('@deepseek-ai/dsh-subagent')).href)
  const task = fixture('reviewer')
  const facts = unknownSettlementFacts()
  facts.output_role = roleOf(task)
  facts.reviewer_invocation = 'invoked'
  facts.workspace_observation = { status: 'observed_changes', added: 1, modified: 2, deleted: 0,
    coverage: 'bounded_snapshot', attribution: 'not_established_shared_workspace' }
  const original: SubagentResult = { output: [{ type: 'text', text: task.result! }], stopReason: 'error', diagnostic: 'safe diagnostic' }
  const result = withSettlementFacts(original, task, facts)
  const parent = { id: 'parent', status: 'idle' }
  let delivered: { content: { type: string; text: string }[]; source: Record<string, unknown> } | undefined
  let lane: string | undefined
  const receiver = { ctx: { agents: { get: () => parent }, logger: { warn: (message: string) => { throw Error(message) } } },
    closingTeardownFor: () => undefined,
    sendWaking: (target: unknown, message: typeof delivered, selectedLane: string) => {
      assert.equal(target, parent); delivered = message; lane = selectedLane
    } }
  SubagentManager.prototype.notifySettlement.call(receiver,
    { announced: true, delivery: 'parent', parent, childId: 'child', kind: 'external' }, result)
  assert(delivered)
  assert.equal(lane, 'queue')
  assert.equal(delivered.source.kind, 'subagent-settled')
  assert.equal(delivered.source.senderSessionId, 'child')
  assert.match(delivered.content[0]!.text, /failed before it finished/u)
  const texts = delivered.content.map(block => block.text)
  assert(texts.some(text => text.startsWith('DSH Runtime Host settlement facts') && text.includes('"runtime_terminal_status":"failed"')
    && text.includes('"reviewer_invocation":"invoked"') && text.includes('"attribution":"not_established_shared_workspace"')))
  assert(texts.some(text => text.startsWith('Runtime terminal output (source role: reviewer;') && text.endsWith(task.result!)))
  assert(texts.includes('safe diagnostic'))
  assert.equal(texts.some(text => text.startsWith('Structured result:')), false)
  assert.equal(result.structured, undefined)
  assert.equal(original.output[0]!.type === 'text' && original.output[0]!.text, task.result)
})
