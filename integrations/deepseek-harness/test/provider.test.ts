import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { ResolvedSubagentStartRequest, SubagentRun } from '@deepseek-ai/dsh-subagent'
import { createGovernedProvider, RUNTIME_PROVIDER_NAMES } from '../src/provider.ts'
import type { GovernanceBridge } from '../src/governance/bridge.ts'
import type { GovernanceDecision, GovernanceFailure } from '../src/governance/protocol.ts'

const identity = { policy_id: 'test', policy_version: '2', artifact_schema_version: '1', policy_hash: '0'.repeat(64) }
const request = {
  parent: { id: 'trusted-parent', session: { id: 'trusted-session' } },
  prompt: [{ type: 'text', text: 'test' }],
  cwd: 'D:/isolated',
  signal: new AbortController().signal,
} as ResolvedSubagentStartRequest

function evaluator(decision: GovernanceDecision | GovernanceFailure): Pick<GovernanceBridge, 'evaluatePreStart'> {
  return { evaluatePreStart: async (session, callerId, route) => {
    assert.equal(session.id, 'trusted-session')
    assert.equal(callerId, 'trusted-parent')
    assert.equal(route.taskKind, 'repository_inspection')
    assert.equal(route.reasonCode, 'host_v2_repository_inspection')
    return decision
  } }
}

test('direct inspection provider start is blocked before Runtime launch', async () => {
  let launches = 0
  const denied: GovernanceDecision = {
    kind: 'BLOCKED', request_id: 'r', session_id: 'trusted-session', policy_identity: identity,
    task_kind: 'repository_inspection', reason_code: 'gate_denied', gate_reason_code: 'test',
  }
  const provider = createGovernedProvider('repository_inspection', evaluator(denied), async () => { launches++; return {} as SubagentRun })
  assert.equal(provider.name, RUNTIME_PROVIDER_NAMES.repository_inspection)
  await assert.rejects(provider.start!(request), /governance denied start/)
  assert.equal(launches, 0)
})

test('direct inspection provider start launches once on explicit allow', async () => {
  let launches = 0
  const allowed: GovernanceDecision = {
    kind: 'EXECUTION_ELIGIBLE', request_id: 'r', session_id: 'trusted-session', policy_identity: identity,
    task_kind: 'repository_inspection', reason_code: 'execution_eligible',
  }
  const run = { id: 'only-run', result: Promise.resolve({ stopReason: 'completed' }), dispose: async () => undefined } as SubagentRun
  const provider = createGovernedProvider('repository_inspection', evaluator(allowed), async (_request, kind) => {
    assert.equal(kind, 'repository_inspection')
    launches++
    return run
  })
  assert.equal(await provider.start!(request), run)
  assert.equal(launches, 1)
})

test('change provider pins its own workload and cannot launch on bridge failure', async () => {
  let launches = 0
  const failure: GovernanceFailure = { kind: 'FAILURE', request_id: 'r', reason_code: 'bridge_failure', diagnostic: 'unavailable' }
  const provider = createGovernedProvider('repository_change', {
    evaluatePreStart: async (_session, _callerId, route) => {
      assert.equal(route.taskKind, 'repository_change')
      assert.equal(route.reasonCode, 'host_v1_repository_change')
      return failure
    },
  }, async () => { launches++; return {} as SubagentRun })
  assert.equal(provider.name, RUNTIME_PROVIDER_NAMES.repository_change)
  await assert.rejects(provider.start!(request), /governance denied start/)
  assert.equal(launches, 0)
})
