import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'
import { validateConfig, type Config } from '../src/index.ts'

function fixture(): Config {
  const root = mkdtempSync(join(tmpdir(), 'dsh-plugin-entry-'))
  const runtimeRoot = join(root, 'runtime')
  const auditRoot = join(root, 'audit')
  const evidenceRoot = join(root, 'evidence')
  mkdirSync(runtimeRoot)
  mkdirSync(auditRoot)
  mkdirSync(evidenceRoot)
  const policySource = join(runtimeRoot, 'policy.json')
  writeFileSync(policySource, '{}')
  return {
    runtimeRoot, python: 'python', policySource,
    expectedPolicyHash: 'a'.repeat(64), enabledWorkloads: ['repository_inspection'],
    auditPath: join(auditRoot, 'governance.jsonl'), evidenceRoot,
  }
}

test('entry accepts a complete isolated Profile and fills safe defaults', () => {
  const config = validateConfig(fixture())
  assert.equal(config.disposeGraceMs, 3000)
  assert.equal(config.responseTimeoutMs, 10000)
  assert.deepEqual(config.env, {})
})

test('entry rejects missing governance identity, unsupported workload and missing evidence root', () => {
  const base = fixture()
  assert.throws(() => validateConfig({ ...base, expectedPolicyHash: '' }))
  assert.throws(() => validateConfig({ ...base, enabledWorkloads: ['other'] as unknown as Config['enabledWorkloads'] }))
  assert.throws(() => validateConfig({ ...base, evidenceRoot: join(base.runtimeRoot, 'missing') }))
  assert.throws(() => validateConfig({ ...base, env: { PYTHONPATH: 'override' } }))
})
