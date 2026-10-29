import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync, symlinkSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
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

test('entry freezes role models and refuses unsupported adapters or fields', () => {
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
  const codeBuddy = validateConfig({ ...base, roleConfig: {
    schema_version: 1,
    roles: {
      worker: { adapter: 'codebuddy', model: 'glm-5.3-flash' },
      reviewer: { adapter: 'codex', model: null },
      inspector: { adapter: 'codex', model: null },
    },
  } })
  assert.equal(codeBuddy.roleConfig?.roles.worker.model, 'glm-5.3-flash')
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

test('entry accepts bounded API inspector only with an external connection path', () => {
  const base = fixture()
  const apiAgentConnectionsPath = join(dirname(base.runtimeRoot), 'connections.local.json')
  writeFileSync(apiAgentConnectionsPath, '{}')
  const roleConfig = {
    schema_version: 2 as const,
    roles: {
      worker: { adapter: 'codebuddy' as const, model: null },
      reviewer: { adapter: 'codex' as const, model: null },
      inspector: {
        adapter: 'api_agent' as const, provider: 'siliconflow' as const,
        model: 'Qwen/Qwen3-Coder-30B-A3B-Instruct', connection_ref: 'trial_siliconflow',
        max_requests: 3, max_tool_calls: 3, max_output_tokens: 512,
      },
    },
  }
  const resolved = validateConfig({ ...base, roleConfig, apiAgentConnectionsPath })
  const processes = hostCoreConfig(resolved)
  assert.equal(processes.runtime.env.DSH_API_AGENT_CONNECTIONS_PATH, apiAgentConnectionsPath)
  assert.equal('DSH_API_AGENT_CONNECTIONS_PATH' in processes.governance.env, false)
  assert.equal(JSON.parse(processes.runtime.env.DSH_RUNTIME_ROLE_CONFIG_JSON).schema_version, 2)
  assert.throws(() => validateConfig({ ...base, roleConfig }), /apiAgentConnectionsPath/)
  assert.throws(() => validateConfig({ ...base, env: {
    DSH_API_AGENT_CONNECTIONS_PATH: apiAgentConnectionsPath,
  }, roleConfig, apiAgentConnectionsPath }), /owned by apiAgentConnectionsPath/)
  assert.throws(() => validateConfig({ ...base, roleConfig: {
    ...roleConfig, roles: { ...roleConfig.roles, worker: roleConfig.roles.inspector },
  } as unknown as Config['roleConfig'], apiAgentConnectionsPath }), /worker is not qualified/)
  const apiReviewConfig = { ...roleConfig, roles: {
    ...roleConfig.roles, reviewer: roleConfig.roles.inspector,
    inspector: { adapter: 'codex' as const, model: null },
  } }
  const reviewResolved = validateConfig({ ...base, roleConfig: apiReviewConfig, apiAgentConnectionsPath })
  assert.equal(reviewResolved.roleConfig?.roles.reviewer.adapter, 'api_agent')
  assert.throws(() => validateConfig({ ...base, roleConfig: apiReviewConfig }), /apiAgentConnectionsPath/)
  assert.throws(() => validateConfig({ ...base, roleConfig: {
    ...roleConfig, roles: { ...roleConfig.roles, inspector: {
      ...roleConfig.roles.inspector, max_requests: 13,
    } },
  }, apiAgentConnectionsPath }), /max_requests/)

  if (process.platform === 'win32') {
    const nested = join(base.runtimeRoot, 'settings')
    mkdirSync(nested)
    writeFileSync(join(nested, 'local.json'), '{}')
    const alias = join(dirname(base.runtimeRoot), 'settings-alias')
    symlinkSync(nested, alias, 'junction')
    assert.throws(() => validateConfig({ ...base, roleConfig,
      apiAgentConnectionsPath: join(alias, 'local.json') }), /outside Runtime source/)
  }
})
