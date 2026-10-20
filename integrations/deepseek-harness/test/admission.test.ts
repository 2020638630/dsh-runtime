import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Session } from '@deepseek-ai/dsh-session'
import { startGoverned } from '../src/admission.ts'
import type { GovernanceBridge, GovernedRoute } from '../src/governance/bridge.ts'
import type { GovernanceDecision, GovernanceFailure } from '../src/governance/protocol.ts'

const route: GovernedRoute = { taskKind: 'repository_inspection', reasonCode: 'host_v2_repository_inspection' }
const session = { id: 'isolated-session' } as Session
const policy_identity = { policy_id: 'test', policy_version: '1', artifact_schema_version: '1', policy_hash: '0'.repeat(64) }
const decisionBase = { request_id: 'test', session_id: session.id, policy_identity, task_kind: 'repository_inspection' } as const
const eligible: GovernanceDecision = { kind: 'EXECUTION_ELIGIBLE', ...decisionBase, reason_code: 'execution_eligible' }
const blocked: GovernanceDecision = { kind: 'BLOCKED', ...decisionBase, reason_code: 'gate_denied', gate_reason_code: 'test_denial' }
const failure: GovernanceFailure = { kind: 'FAILURE', request_id: 'test', reason_code: 'bridge_failure', diagnostic: 'worker unavailable' }

function evaluator(decision: GovernanceDecision | GovernanceFailure): Pick<GovernanceBridge, 'evaluatePreStart'> {
  return { evaluatePreStart: async () => decision }
}

test('eligible decision launches exactly once', async () => {
  let launches = 0
  const result = await startGoverned(evaluator(eligible), session, 'caller', route, new AbortController().signal, () => {
    launches++
    return 'started'
  })
  assert.equal(result, 'started')
  assert.equal(launches, 1)
})

for (const [label, decision] of [['blocked', blocked], ['worker failure', failure]] as const) {
  test(`${label} cannot launch Runtime`, async () => {
    let launches = 0
    await assert.rejects(startGoverned(evaluator(decision), session, 'caller', route, new AbortController().signal, () => { launches++ }), /governance denied start/)
    assert.equal(launches, 0)
  })
}

test('bridge rejection cannot launch Runtime', async () => {
  let launches = 0
  const broken = { evaluatePreStart: async () => { throw new Error('worker died') } } as Pick<GovernanceBridge, 'evaluatePreStart'>
  await assert.rejects(startGoverned(broken, session, 'caller', route, new AbortController().signal, () => { launches++ }), /worker died/)
  assert.equal(launches, 0)
})

test('already aborted call does not evaluate or launch', async () => {
  const controller = new AbortController()
  controller.abort()
  let evaluations = 0
  let launches = 0
  const probe = { evaluatePreStart: async () => { evaluations++; return eligible } }
  await assert.rejects(startGoverned(probe, session, 'caller', route, controller.signal, () => { launches++ }))
  assert.equal(evaluations, 0)
  assert.equal(launches, 0)
})

test('cancellation during governance evaluation does not launch', async () => {
  const controller = new AbortController()
  let resolve!: (value: GovernanceDecision) => void
  const pending = new Promise<GovernanceDecision>(accepted => { resolve = accepted })
  let launches = 0
  const probe = { evaluatePreStart: () => pending }
  const start = startGoverned(probe, session, 'caller', route, controller.signal, () => { launches++ })
  controller.abort()
  resolve(eligible)
  await assert.rejects(start)
  assert.equal(launches, 0)
})
