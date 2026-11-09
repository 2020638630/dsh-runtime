/** Installable official DeepSeekHarness Host entrypoint. */
import { lstatSync, realpathSync, statSync } from 'node:fs'
import { isAbsolute, dirname, relative, resolve, sep } from 'node:path'
import { isDeepStrictEqual } from 'node:util'
import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import type {} from '@deepseek-ai/dsh-client-connection'
import type {} from '@deepseek-ai/dsh-session-query'
import { mountHostCore, type HostCoreConfig } from './host-core.ts'
import { registerRuntimeEvidenceRoute } from './evidence-route.ts'
import { registerCliLoginRoute } from './cli-login-route.ts'

export const name = 'dsh-runtime-standalone'
export const inject = ['subprocess', 'subagents', 'tools', 'connection', 'sessionQuery']
const ROLE_CONFIG_ENV = 'DSH_RUNTIME_ROLE_CONFIG_JSON'
const API_AGENT_CONNECTIONS_PATH_ENV = 'DSH_API_AGENT_CONNECTIONS_PATH'

export interface CliRoleSelectionConfig {
  adapter: 'codebuddy' | 'codex'
  model: string | null
}

export interface ApiRoleSelectionConfig {
  adapter: 'api_agent'
  provider: 'openrouter' | 'siliconflow'
  model: string
  connection_ref: string
  max_requests: number
  max_tool_calls: number
  max_output_tokens: number
}

export interface RoleConfigV1 {
  schema_version: 1
  roles: {
    worker: CliRoleSelectionConfig
    reviewer: CliRoleSelectionConfig
    inspector: CliRoleSelectionConfig
  }
}

export interface RoleConfigV2 {
  schema_version: 2
  roles: {
    worker: CliRoleSelectionConfig
    reviewer: CliRoleSelectionConfig | ApiRoleSelectionConfig
    inspector: CliRoleSelectionConfig | ApiRoleSelectionConfig
  }
}

export type RoleConfig = RoleConfigV1 | RoleConfigV2

export interface Config {
  runtimeRoot: string
  python: string
  policySource: string
  expectedPolicyHash: string
  enabledWorkloads: Array<'repository_inspection' | 'repository_change'>
  auditPath: string
  pinRoot: string
  evidenceRoot: string
  disposeGraceMs?: number
  responseTimeoutMs?: number
  env?: Record<string, string>
  roleConfig?: RoleConfig
  apiAgentConnectionsPath?: string
}

type LiveRoleConfig = { get(): RoleConfig | undefined }
type EntryConfig = Omit<Config, 'roleConfig'> & { roleConfig?: RoleConfig | LiveRoleConfig }

// Expose only the role selection to the Host settings service. Existing
// Profile paths and governance fields continue through validateConfig.
export const Config = z.object({
  roleConfig: z.transform(z.any(), validateRoleConfig).volatile(),
})

type ResolvedConfig = Required<Omit<Config, 'roleConfig' | 'apiAgentConnectionsPath'>> & {
  roleConfig?: RoleConfig
  apiAgentConnectionsPath?: string
}

function exactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  const actual = Object.keys(value)
  return actual.length === keys.length && actual.every(key => keys.includes(key))
}

function roleSelection(
  value: unknown, role: 'worker' | 'reviewer' | 'inspector', version: 1 | 2,
): CliRoleSelectionConfig | ApiRoleSelectionConfig {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new TypeError(`${role} must be an object`)
  const fields = value as Record<string, unknown>
  if (version === 2 && fields.adapter === 'api_agent') {
    if (role === 'worker') throw new TypeError(`API Agent ${role} is not qualified in Host`)
    if (!exactKeys(fields, [
      'adapter', 'provider', 'model', 'connection_ref',
      'max_requests', 'max_tool_calls', 'max_output_tokens',
    ])) throw new TypeError(`${role} API role fields are invalid`)
    if (fields.provider !== 'openrouter' && fields.provider !== 'siliconflow') {
      throw new TypeError(`${role} provider is unsupported`)
    }
    if (typeof fields.model !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$/u.test(fields.model)) {
      throw new TypeError(`${role} model must be a bounded model ID`)
    }
    if (typeof fields.connection_ref !== 'string' || !/^[A-Za-z][A-Za-z0-9_-]{0,63}$/u.test(fields.connection_ref)) {
      throw new TypeError(`${role} connection_ref is invalid`)
    }
    for (const [name, limit] of [
      ['max_requests', 12], ['max_tool_calls', 40], ['max_output_tokens', 8192],
    ] as const) {
      const value = fields[name]
      if (!Number.isSafeInteger(value) || typeof value !== 'number' || value < 1 || value > limit) {
        throw new TypeError(`${role} ${name} is out of bounds`)
      }
    }
    return { ...fields } as unknown as ApiRoleSelectionConfig
  }
  if (!exactKeys(fields, ['adapter', 'model'])) {
    throw new TypeError(`${role} requires only adapter and model`)
  }
  const adapter = fields.adapter
  if (adapter !== 'codex' && !(role === 'worker' && adapter === 'codebuddy')) {
    throw new TypeError(`${role} adapter is unsupported`)
  }
  const model = fields.model
  if (model !== null && (typeof model !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$/.test(model))) {
    throw new TypeError(`${role} model must be a bounded model ID or null`)
  }
  return { adapter, model: model as string | null }
}

function validateRoleConfig(value: unknown): RoleConfig {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new TypeError('roleConfig must be an object')
  const document = value as Record<string, unknown>
  if (!exactKeys(document, ['schema_version', 'roles'])
    || (document.schema_version !== 1 && document.schema_version !== 2)) {
    throw new TypeError('roleConfig requires schema_version 1 or 2 and roles')
  }
  const roles = document.roles
  if (!roles || typeof roles !== 'object' || Array.isArray(roles)
    || !exactKeys(roles as Record<string, unknown>, ['worker', 'reviewer', 'inspector'])) {
    throw new TypeError('roleConfig requires worker, reviewer and inspector')
  }
  const selected = roles as Record<string, unknown>
  const version = document.schema_version
  const worker = roleSelection(selected.worker, 'worker', version)
  const reviewer = roleSelection(selected.reviewer, 'reviewer', version)
  const inspector = roleSelection(selected.inspector, 'inspector', version)
  if (worker.adapter === 'api_agent') throw new TypeError('API Agent worker is not qualified')
  if (version === 1) return {
    schema_version: 1, roles: {
      worker, reviewer: reviewer as CliRoleSelectionConfig,
      inspector: inspector as CliRoleSelectionConfig,
    },
  }
  return { schema_version: 2, roles: {
    worker, reviewer, inspector,
  } }
}

function absolutePath(value: unknown, label: string): string {
  if (typeof value !== 'string' || !isAbsolute(value)) throw new TypeError(`${label} must be an absolute path`)
  return resolve(value)
}

function directory(value: string, label: string): string {
  if (!statSync(value).isDirectory()) throw new TypeError(`${label} must be a directory`)
  return value
}

function within(root: string, path: string): boolean {
  const rel = relative(root, path)
  return rel === '' || (rel !== '..' && !rel.startsWith(`..${sep}`) && !isAbsolute(rel))
}

/** Reject incomplete or ambiguous Profiles before the governance worker starts. */
export function validateConfig(input: Config): ResolvedConfig {
  if (!input || typeof input !== 'object') throw new TypeError('dsh runtime plugin requires a Profile config')
  const runtimeRoot = directory(absolutePath(input.runtimeRoot, 'runtimeRoot'), 'runtimeRoot')
  const policySource = absolutePath(input.policySource, 'policySource')
  if (!statSync(policySource).isFile()) throw new TypeError('policySource must be a file')
  if (typeof input.python !== 'string' || input.python.trim() === '') throw new TypeError('python must be a non-empty executable')
  if (typeof input.expectedPolicyHash !== 'string' || !/^[a-f0-9]{64}$/.test(input.expectedPolicyHash)) throw new TypeError('expectedPolicyHash must be a lowercase SHA-256 hex string')
  const allowed = new Set(['repository_inspection', 'repository_change'])
  if (!Array.isArray(input.enabledWorkloads) || input.enabledWorkloads.length === 0 || new Set(input.enabledWorkloads).size !== input.enabledWorkloads.length || input.enabledWorkloads.some(value => !allowed.has(value))) throw new TypeError('enabledWorkloads must contain unique supported workloads')
  const auditPath = absolutePath(input.auditPath, 'auditPath')
  directory(dirname(auditPath), 'auditPath parent')
  const pinRoot = directory(absolutePath(input.pinRoot, 'pinRoot'), 'pinRoot')
  const evidenceRoot = directory(absolutePath(input.evidenceRoot, 'evidenceRoot'), 'evidenceRoot')
  if (auditPath === policySource || evidenceRoot === runtimeRoot || pinRoot === runtimeRoot || pinRoot === evidenceRoot) throw new TypeError('governance and evidence paths must be distinct')
  const disposeGraceMs = input.disposeGraceMs ?? 3000
  const responseTimeoutMs = input.responseTimeoutMs ?? 10000
  if (!Number.isSafeInteger(disposeGraceMs) || disposeGraceMs <= 0 || !Number.isSafeInteger(responseTimeoutMs) || responseTimeoutMs <= 0) throw new TypeError('timeouts must be positive integer milliseconds')
  const env = input.env ?? {}
  if (typeof env !== 'object' || Array.isArray(env) || Object.values(env).some(value => typeof value !== 'string')) throw new TypeError('env must be a string map')
  if ('PYTHONPATH' in env) throw new TypeError('PYTHONPATH is owned by the Runtime launcher')
  if (ROLE_CONFIG_ENV in env) throw new TypeError(`${ROLE_CONFIG_ENV} is owned by roleConfig`)
  if (API_AGENT_CONNECTIONS_PATH_ENV in env) throw new TypeError(`${API_AGENT_CONNECTIONS_PATH_ENV} is owned by apiAgentConnectionsPath`)
  const roleConfig = input.roleConfig === undefined ? undefined : validateRoleConfig(input.roleConfig)
  const usesApi = roleConfig?.schema_version === 2 && (
    roleConfig.roles.inspector.adapter === 'api_agent'
      || roleConfig.roles.reviewer.adapter === 'api_agent'
  )
  let apiAgentConnectionsPath: string | undefined
  if (usesApi) {
    apiAgentConnectionsPath = absolutePath(input.apiAgentConnectionsPath, 'apiAgentConnectionsPath')
    const connectionInfo = lstatSync(apiAgentConnectionsPath)
    if (connectionInfo.isSymbolicLink() || !connectionInfo.isFile() || connectionInfo.nlink !== 1) {
      throw new TypeError('apiAgentConnectionsPath must be a regular file')
    }
    apiAgentConnectionsPath = realpathSync(apiAgentConnectionsPath)
    if (within(realpathSync(runtimeRoot), apiAgentConnectionsPath)) {
      throw new TypeError('apiAgentConnectionsPath must be outside Runtime source')
    }
  } else if (input.apiAgentConnectionsPath !== undefined) {
    throw new TypeError('apiAgentConnectionsPath requires an API role')
  }
  return { runtimeRoot, python: input.python, policySource, expectedPolicyHash: input.expectedPolicyHash, enabledWorkloads: input.enabledWorkloads, auditPath, pinRoot, evidenceRoot, disposeGraceMs, responseTimeoutMs, env, roleConfig, apiAgentConnectionsPath }
}

export function hostCoreConfig(config: ResolvedConfig, live?: LiveRoleConfig): HostCoreConfig {
  return {
    governance: {
      runtimeRoot: config.runtimeRoot, python: config.python, env: config.env,
      policySource: config.policySource, expectedPolicyHash: config.expectedPolicyHash,
      enabledWorkloads: config.enabledWorkloads, auditPath: config.auditPath,
      pinRoot: config.pinRoot,
      disposeGraceMs: config.disposeGraceMs, responseTimeoutMs: config.responseTimeoutMs,
    },
    runtime: {
      runtimeRoot: config.runtimeRoot, python: config.python, env: runtimeEnv(config, config.roleConfig),
      ...live === undefined ? {} : { readEnv: () => liveRuntimeEnv(config, live) },
      evidenceRoot: config.evidenceRoot, disposeGraceMs: config.disposeGraceMs,
    },
  }
}

function runtimeEnv(config: ResolvedConfig, roles: RoleConfig | undefined): Record<string, string> {
  return {
    ...config.env,
    ...roles === undefined ? {} : { [ROLE_CONFIG_ENV]: JSON.stringify(roles) },
    ...config.apiAgentConnectionsPath === undefined ? {}
      : { [API_AGENT_CONNECTIONS_PATH_ENV]: config.apiAgentConnectionsPath },
  }
}

function liveRuntimeEnv(config: ResolvedConfig, source: LiveRoleConfig): Record<string, string> {
  const current = source.get()
  const roles = current === undefined ? undefined : validateRoleConfig(current)
  const original = config.roleConfig
  if (original?.schema_version === 2 || roles?.schema_version === 2) {
    if (original?.schema_version !== 2 || roles?.schema_version !== 2) {
      throw new TypeError('Changing an API role configuration schema requires reopening Harness')
    }
    for (const role of ['reviewer', 'inspector'] as const) {
      const before = original.roles[role]
      const after = roles.roles[role]
      if ((before.adapter === 'api_agent' || after.adapter === 'api_agent') && !isDeepStrictEqual(before, after)) {
        throw new TypeError('Changing API role settings requires reopening Harness')
      }
    }
  }
  return runtimeEnv(config, roles)
}

export async function apply(ctx: Context, rawConfig: EntryConfig): Promise<() => Promise<void>> {
  const selection = rawConfig?.roleConfig
  const source = selection && typeof selection === 'object' && 'get' in selection
    && typeof selection.get === 'function' ? selection : undefined
  const config = validateConfig(source ? { ...rawConfig, roleConfig: source.get() } : rawConfig as Config)
  const disposeCore = await mountHostCore(ctx, hostCoreConfig(config, source))
  try {
    if (source) ctx.inject(['settings'], (child) => {
      const settings = (child as Context & { settings: {
        configure?: (options: { auto: boolean }, fiber: Context['fiber']) => () => void
      } }).settings
      if (typeof settings.configure === 'function') {
        child.effect(() => settings.configure!({ auto: false }, ctx.fiber))
      }
    })
    const disposeRoute = registerRuntimeEvidenceRoute(ctx, config.evidenceRoot)
    try {
      const disposeLogin = registerCliLoginRoute(ctx, config)
      return async () => {
        try { await disposeLogin() }
        finally {
          try { await disposeRoute() } finally { await disposeCore() }
        }
      }
    } catch (error) {
      await disposeRoute()
      throw error
    }
  } catch (error) {
    await disposeCore()
    throw error
  }
}
