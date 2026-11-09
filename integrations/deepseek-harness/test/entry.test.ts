import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync, symlinkSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { test } from 'node:test'
import type { Context } from '@deepseek-ai/cordis'
import { Config, hostCoreConfig, validateConfig, type RoleConfig } from '../src/index.ts'
import { registerCliLoginRoute } from '../src/cli-login-route.ts'

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

test('Desktop login route starts only fixed CLI actions and keeps the result private', {
  skip: process.platform !== 'win32',
}, async () => {
  let fetch: ((request: Request) => Promise<Response>) | undefined
  let finishLogin: (() => void) | undefined
  let invoked = 0
  let disposed = false
  const ctx = {
    connection: { fetch: { register: (route: { fetch: typeof fetch }) => {
      fetch = route.fetch
      return async () => { disposed = true }
    } } },
    subprocess: { spawn: ({ argv }: { argv: string[] }) => {
      invoked++
      assert.deepEqual(argv.slice(0, 2), ['python', '-B'])
      assert.match(argv[2], /[/\\]scripts[/\\]cli-login\.py$/u)
      assert.equal(argv[4], 'codex')
      const login = argv[3] === 'login'
      const done = login ? new Promise(resolve => { finishLogin = () => resolve({ exitCode: 0 }) })
        : Promise.resolve({ exitCode: 0 })
      const text = login ? 'closed\n' : 'unexpected account details\n'
      return { done, collected: { stdout: { readFrom: () => ({ text, lossy: false }) } } }
    } },
  } as unknown as Context
  const previous = process.env.ELECTRON_RUN_AS_NODE
  delete process.env.ELECTRON_RUN_AS_NODE
  await registerCliLoginRoute(ctx, validateConfig(fixture()))()
  assert.equal(fetch, undefined)
  process.env.ELECTRON_RUN_AS_NODE = '1'
  try {
    const dispose = registerCliLoginRoute(ctx, validateConfig(fixture()))
    assert.ok(fetch)
    const handle = fetch as (request: Request) => Promise<Response>
    const request = (query: string, headers: HeadersInit = { 'x-dsh-runtime-cli': '1' }, body?: string) =>
      handle(new Request('http://localhost/api/dsh-runtime.cli-login?' + query, { method: 'POST', headers, body }))
    assert.equal((await request('operation=login&cli=codex', {})).status, 403)
    assert.equal((await request('operation=login&cli=codex',
      { 'x-dsh-runtime-cli': '1', origin: 'http://localhost' })).status, 403)
    assert.equal((await request('operation=login&cli=codex', undefined, 'shell')).status, 403)
    assert.equal((await request('operation=login&cli=other')).status, 400)
    assert.equal((await request('operation=login&cli=codex&argv=arbitrary')).status, 400)
    assert.equal(invoked, 0)
    assert.deepEqual(await (await request('operation=status&cli=codex')).json(), { status: 'unknown' })
    const running = request('operation=login&cli=codex')
    assert.equal((await request('operation=login&cli=codex')).status, 409)
    assert.deepEqual(await (await request('operation=status&cli=codex')).json(), { status: 'running' })
    finishLogin!()
    assert.deepEqual(await (await running).json(), { status: 'closed' })
    assert.equal(invoked, 2)
    await dispose()
    assert.equal(disposed, true)
  } finally {
    if (previous === undefined) delete process.env.ELECTRON_RUN_AS_NODE
    else process.env.ELECTRON_RUN_AS_NODE = previous
  }
})

test('new launches snapshot saved CLI defaults independently of governance and earlier launches', () => {
  const base = fixture()
  const composed = Config(base)
  assert.equal((composed as unknown as Config).runtimeRoot, base.runtimeRoot)
  assert.equal(composed.roleConfig.get(), undefined)
  let roleConfig: RoleConfig | undefined
  const core = hostCoreConfig(validateConfig(base), { get: () => roleConfig })
  const before = core.runtime.readEnv!()
  assert.equal(before.DSH_RUNTIME_ROLE_CONFIG_JSON, undefined)
  roleConfig = { schema_version: 1, roles: {
    worker: { adapter: 'codebuddy', model: null },
    reviewer: { adapter: 'codex', model: 'reviewer-model' },
    inspector: { adapter: 'codex', model: null },
  } }
  const after = core.runtime.readEnv!()
  assert.deepEqual(JSON.parse(after.DSH_RUNTIME_ROLE_CONFIG_JSON), roleConfig)
  roleConfig.roles.worker.model = 'later'
  assert.equal(JSON.parse(after.DSH_RUNTIME_ROLE_CONFIG_JSON).roles.worker.model, null)
  assert.equal(before.DSH_RUNTIME_ROLE_CONFIG_JSON, undefined)
  assert.equal(core.governance.env?.DSH_RUNTIME_ROLE_CONFIG_JSON, undefined)
})

test('live defaults preserve the Profile API roles and connection path', () => {
  const base = fixture()
  const apiAgentConnectionsPath = join(dirname(base.runtimeRoot), 'connections.local.json')
  writeFileSync(apiAgentConnectionsPath, '{}')
  const roleConfig: RoleConfig = { schema_version: 2, roles: {
    worker: { adapter: 'codebuddy', model: null },
    reviewer: { adapter: 'codex', model: null },
    inspector: { adapter: 'api_agent', provider: 'siliconflow', model: 'api-model',
      connection_ref: 'example', max_requests: 3, max_tool_calls: 3, max_output_tokens: 512 },
  } }
  const live = structuredClone(roleConfig)
  const core = hostCoreConfig(validateConfig({ ...base, roleConfig, apiAgentConnectionsPath }), { get: () => live })
  live.roles.reviewer.model = 'new-cli-model'
  const env = core.runtime.readEnv!()
  assert.equal(env.DSH_API_AGENT_CONNECTIONS_PATH, apiAgentConnectionsPath)
  assert.deepEqual(JSON.parse(env.DSH_RUNTIME_ROLE_CONFIG_JSON), live)
  live.roles.inspector.model = 'different-api-model'
  assert.throws(() => core.runtime.readEnv!(), /Changing API role settings/)
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
