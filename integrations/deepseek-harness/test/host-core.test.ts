import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Context } from '@deepseek-ai/cordis'
import { mountHostCore } from '../src/host-core.ts'

test('failed governance worker startup exposes no provider or tool', async () => {
  let providerRegistrations = 0
  let toolRegistrations = 0
  const ctx = {
    subprocess: { spawn: () => { throw new Error('isolated worker unavailable') } },
    subagents: { registerProvider: () => { providerRegistrations++; return () => undefined } },
    tools: { register: () => { toolRegistrations++; return () => undefined } },
  } as unknown as Context
  await assert.rejects(mountHostCore(ctx, {
    governance: {
      runtimeRoot: 'D:/isolated', python: 'python', env: {}, policySource: 'D:/isolated/policy.json',
      expectedPolicyHash: '0'.repeat(64), enabledWorkloads: ['repository_inspection'],
      auditPath: 'D:/isolated/audit.jsonl', pinRoot: process.cwd(), disposeGraceMs: 3000, responseTimeoutMs: 100,
    },
    runtime: { runtimeRoot: 'D:/isolated', python: 'python', env: {}, disposeGraceMs: 3000 },
  }), /isolated worker unavailable/)
  assert.equal(providerRegistrations, 0)
  assert.equal(toolRegistrations, 0)
})
