import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { readFileSync, mkdtempSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { test } from 'node:test'
import type { Session } from '@deepseek-ai/dsh-session'
import type { SubprocessHandle, SubprocessSpawnSpec } from '@deepseek-ai/dsh-subprocess'
import { startGoverned } from '../src/admission.ts'
import { GovernanceBridge } from '../src/governance/bridge.ts'
import { GovernancePinStore } from '../src/governance/pin-store.ts'

const runtimeRoot = resolve(process.cwd(), '../..')
const policySource = join(runtimeRoot, 'dsh_runtime/resources/selection_policy/selection-v2.json')
const expectedPolicyHash = 'c1cb7d4350a94e9353dd445de41a741a66f01b2be88b8f073613dd548adad463'

function spawnWorker(spec: SubprocessSpawnSpec): SubprocessHandle {
  const child = spawn(spec.argv[0]!, spec.argv.slice(1), {
    cwd: spec.cwd,
    env: { ...process.env, ...spec.env },
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true,
  })
  const done = new Promise<{ exitCode: number | null }>((accept, reject) => {
    child.once('error', reject)
    child.once('close', code => accept({ exitCode: code }))
  })
  return {
    stdin: child.stdin,
    stdout: child.stdout,
    done,
    terminate: () => { child.kill() },
    waitForExit: async () => { await done },
  } as unknown as SubprocessHandle
}

test('public-package bridge governs a real isolated Python worker and persists audit', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'dsh-plugin-worker-'))
  const auditPath = join(directory, 'audit.jsonl')
  const pinRoot = join(directory, 'pins')
  const workspace = join(directory, 'workspace')
  mkdirSync(pinRoot)
  mkdirSync(workspace)
  const session = {
    id: 'official-host-probe-session',
    header: { cwd: workspace },
    append: () => { throw new Error('external plugin must not append an unknown official Session event') },
  } as unknown as Session
  const bridge = new GovernanceBridge(spawnWorker, {
    runtimeRoot,
    python: process.env.DSH_TEST_PYTHON ?? 'python',
    env: {},
    policySource,
    expectedPolicyHash,
    enabledWorkloads: ['repository_inspection'],
    auditPath,
    pinRoot,
    disposeGraceMs: 3000,
    responseTimeoutMs: 10000,
  })
  try {
    const ready = await bridge.waitForReady()
    assert.equal(ready.policy_identity.policy_hash, expectedPolicyHash)
    let launches = 0
    const allowed = await startGoverned(bridge, session, 'trusted-host', {
      taskKind: 'repository_inspection', reasonCode: 'host_v2_repository_inspection',
    }, new AbortController().signal, () => { launches++; return 'launched' })
    assert.equal(allowed, 'launched')
    assert.equal(launches, 1)
    await assert.rejects(startGoverned(bridge, session, 'trusted-host', {
      taskKind: 'repository_change', reasonCode: 'host_v1_repository_change',
    }, new AbortController().signal, () => { launches++ }), /governance denied start/)
    assert.equal(launches, 1)
    const unsafeSession = { id: 'unsafe-session', header: { cwd: pinRoot } } as unknown as Session
    await assert.rejects(startGoverned(bridge, unsafeSession, 'trusted-host', {
      taskKind: 'repository_inspection', reasonCode: 'host_v2_repository_inspection',
    }, new AbortController().signal, () => { launches++ }), /governance denied start/)
    assert.equal(launches, 1)
    assert.equal((await new GovernancePinStore(pinRoot).read(session.id))?.policy_hash, expectedPolicyHash)
    const records = readFileSync(auditPath, 'utf8').trim().split('\n').map(line => JSON.parse(line) as Record<string, unknown>)
    assert.equal(records.length, 2)
    const audit = records.map(record => record.record as { gate_decision: { proposal: { task_kind: string }, authorization_decision: { outcome: string } } })
    assert.deepEqual(audit.map(item => item.gate_decision.proposal.task_kind), ['repository_inspection', 'repository_change'])
    assert.deepEqual(audit.map(item => item.gate_decision.authorization_decision.outcome), ['ALLOW', 'DENY'])
  } finally {
    await bridge.dispose()
  }
})

test('real worker audit persistence failure cannot launch Runtime', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'dsh-plugin-audit-fail-'))
  const pinRoot = join(directory, 'pins')
  const workspace = join(directory, 'workspace')
  mkdirSync(pinRoot)
  mkdirSync(workspace)
  const session = { id: 'audit-failure-session', header: { cwd: workspace }, append: () => { throw new Error('unexpected Session event') } } as unknown as Session
  const bridge = new GovernanceBridge(spawnWorker, {
    runtimeRoot,
    python: process.env.DSH_TEST_PYTHON ?? 'python',
    env: {},
    policySource,
    expectedPolicyHash,
    enabledWorkloads: ['repository_inspection'],
    auditPath: directory,
    pinRoot,
    disposeGraceMs: 3000,
    responseTimeoutMs: 10000,
  })
  try {
    await bridge.waitForReady()
    let launches = 0
    await assert.rejects(startGoverned(bridge, session, 'trusted-host', {
      taskKind: 'repository_inspection', reasonCode: 'host_v2_repository_inspection',
    }, new AbortController().signal, () => { launches++ }), /governance denied start/)
    assert.equal(launches, 0)
  } finally {
    await bridge.dispose()
  }
})

test('unresponsive worker times out without launching Runtime', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'dsh-plugin-timeout-'))
  const pinRoot = join(directory, 'pins')
  const workspace = join(directory, 'workspace')
  mkdirSync(pinRoot)
  mkdirSync(workspace)
  const unresponsive = (_spec: SubprocessSpawnSpec): SubprocessHandle => spawnWorker({
    argv: [process.env.DSH_TEST_PYTHON ?? 'python', '-c', 'import time; time.sleep(10)'],
    cwd: runtimeRoot,
    env: {},
    stdio: { stdin: 'pipe', stdout: 'pipe', stderr: 'pipe' },
    graceMs: 3000,
  })
  const bridge = new GovernanceBridge(unresponsive, {
    runtimeRoot,
    python: process.env.DSH_TEST_PYTHON ?? 'python',
    env: {},
    policySource,
    expectedPolicyHash,
    enabledWorkloads: ['repository_inspection'],
    auditPath: join(directory, 'audit.jsonl'),
    pinRoot,
    disposeGraceMs: 3000,
    responseTimeoutMs: 150,
  })
  try {
    await assert.rejects(bridge.waitForReady(), /timed out/)
    let launches = 0
    const session = { id: 'timeout-session', header: { cwd: workspace }, append: () => undefined } as unknown as Session
    await assert.rejects(startGoverned(bridge, session, 'trusted-host', {
      taskKind: 'repository_inspection', reasonCode: 'host_v2_repository_inspection',
    }, new AbortController().signal, () => { launches++ }))
    assert.equal(launches, 0)
  } finally {
    await bridge.dispose()
  }
})
