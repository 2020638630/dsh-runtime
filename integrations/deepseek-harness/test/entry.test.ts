import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'
import { hostCoreConfig, validateConfig, type Config } from '../src/index.ts'

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
    auditPath: join(auditRoot, 'governance.jsonl'), pinRoot: auditRoot, evidenceRoot,
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

test('entry freezes distinct Codex role models and refuses unsupported overrides', () => {
  const base = fixture()
  const roleConfig = {
    schema_version: 1 as const,
    roles: {
      worker: { adapter: 'codex' as const, model: 'gpt-worker' },
      reviewer: { adapter: 'codex' as const, model: 'gpt-reviewer' },
      inspector: { adapter: 'codex' as const, model: 'gpt-inspector' },
    },
  }
  const resolved = validateConfig({ ...base, roleConfig })
  assert.deepEqual(resolved.roleConfig, roleConfig)
  const processes = hostCoreConfig(resolved)
  assert.equal('DSH_RUNTIME_ROLE_CONFIG_JSON' in processes.governance.env, false)
  assert.deepEqual(JSON.parse(processes.runtime.env.DSH_RUNTIME_ROLE_CONFIG_JSON), roleConfig)
  roleConfig.roles.reviewer.model = 'changed-later'
  assert.equal(resolved.roleConfig?.roles.reviewer.model, 'gpt-reviewer')
  assert.equal(JSON.parse(processes.runtime.env.DSH_RUNTIME_ROLE_CONFIG_JSON).roles.reviewer.model, 'gpt-reviewer')

  assert.throws(() => validateConfig({ ...base, env: { DSH_RUNTIME_ROLE_CONFIG_JSON: '{}' } }))
  assert.throws(() => validateConfig({ ...base, roleConfig: {
    schema_version: 1,
    roles: {
      worker: { adapter: 'codebuddy', model: 'unverified-model' },
      reviewer: { adapter: 'codex', model: null },
      inspector: { adapter: 'codex', model: null },
    },
  } }), /not yet verified/)
  assert.throws(() => validateConfig({ ...base, roleConfig: {
    schema_version: 1,
    roles: {
      worker: { adapter: 'codebuddy', model: null },
      reviewer: { adapter: 'codebuddy', model: null },
      inspector: { adapter: 'codex', model: null },
    },
  } }), /reviewer adapter/)
  assert.throws(() => validateConfig({ ...base, roleConfig: {
    schema_version: 1,
    roles: {
      worker: { adapter: 'codebuddy', model: null },
      reviewer: { adapter: 'codex', model: null, reasoning: 'high' },
      inspector: { adapter: 'codex', model: null },
    },
  } as unknown as Config['roleConfig'] }), /requires only adapter and model/)
})
