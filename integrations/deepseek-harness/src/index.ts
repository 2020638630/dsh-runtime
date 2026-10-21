/** Installable official DeepSeekHarness Host entrypoint. */
import { statSync } from 'node:fs'
import { isAbsolute, dirname, resolve } from 'node:path'
import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-client-connection'
import type {} from '@deepseek-ai/dsh-session-query'
import { mountHostCore, type HostCoreConfig } from './host-core.ts'
import { registerRuntimeEvidenceRoute } from './evidence-route.ts'

export const name = 'dsh-runtime-standalone'
export const inject = ['subprocess', 'subagents', 'tools', 'connection', 'sessionQuery']
const ROLE_CONFIG_ENV = 'DSH_RUNTIME_ROLE_CONFIG_JSON'

export interface RoleSelectionConfig {
  adapter: 'codebuddy' | 'codex'
  model: string | null
}

export interface RoleConfig {
  schema_version: 1
  roles: {
    worker: RoleSelectionConfig
    reviewer: RoleSelectionConfig
    inspector: RoleSelectionConfig
  }
}

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
}

type ResolvedConfig = Required<Omit<Config, 'roleConfig'>> & { roleConfig?: RoleConfig }

function exactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  const actual = Object.keys(value)
  return actual.length === keys.length && actual.every(key => keys.includes(key))
}

function roleSelection(value: unknown, role: 'worker' | 'reviewer' | 'inspector'): RoleSelectionConfig {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new TypeError(`${role} must be an object`)
  const fields = value as Record<string, unknown>
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
  if (adapter === 'codebuddy' && model !== null) {
    throw new TypeError('CodeBuddy model overrides are not yet verified')
  }
  return { adapter, model: model as string | null }
}

function validateRoleConfig(value: unknown): RoleConfig {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new TypeError('roleConfig must be an object')
  const document = value as Record<string, unknown>
  if (!exactKeys(document, ['schema_version', 'roles']) || document.schema_version !== 1) {
    throw new TypeError('roleConfig requires schema_version 1 and roles')
  }
  const roles = document.roles
  if (!roles || typeof roles !== 'object' || Array.isArray(roles)
    || !exactKeys(roles as Record<string, unknown>, ['worker', 'reviewer', 'inspector'])) {
    throw new TypeError('roleConfig requires worker, reviewer and inspector')
  }
  const selected = roles as Record<string, unknown>
  return {
    schema_version: 1,
    roles: {
      worker: roleSelection(selected.worker, 'worker'),
      reviewer: roleSelection(selected.reviewer, 'reviewer'),
      inspector: roleSelection(selected.inspector, 'inspector'),
    },
  }
}

function absolutePath(value: unknown, label: string): string {
  if (typeof value !== 'string' || !isAbsolute(value)) throw new TypeError(`${label} must be an absolute path`)
  return resolve(value)
}

function directory(value: string, label: string): string {
  if (!statSync(value).isDirectory()) throw new TypeError(`${label} must be a directory`)
  return value
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
  const roleConfig = input.roleConfig === undefined ? undefined : validateRoleConfig(input.roleConfig)
  return { runtimeRoot, python: input.python, policySource, expectedPolicyHash: input.expectedPolicyHash, enabledWorkloads: input.enabledWorkloads, auditPath, pinRoot, evidenceRoot, disposeGraceMs, responseTimeoutMs, env, roleConfig }
}

export function hostCoreConfig(config: ResolvedConfig): HostCoreConfig {
  const runtimeEnv = config.roleConfig === undefined
    ? config.env
    : { ...config.env, [ROLE_CONFIG_ENV]: JSON.stringify(config.roleConfig) }
  return {
    governance: {
      runtimeRoot: config.runtimeRoot, python: config.python, env: config.env,
      policySource: config.policySource, expectedPolicyHash: config.expectedPolicyHash,
      enabledWorkloads: config.enabledWorkloads, auditPath: config.auditPath,
      pinRoot: config.pinRoot,
      disposeGraceMs: config.disposeGraceMs, responseTimeoutMs: config.responseTimeoutMs,
    },
    runtime: {
      runtimeRoot: config.runtimeRoot, python: config.python, env: runtimeEnv,
      evidenceRoot: config.evidenceRoot, disposeGraceMs: config.disposeGraceMs,
    },
  }
}

export async function apply(ctx: Context, rawConfig: Config): Promise<() => Promise<void>> {
  const config = validateConfig(rawConfig)
  const disposeCore = await mountHostCore(ctx, hostCoreConfig(config))
  try {
    const disposeRoute = registerRuntimeEvidenceRoute(ctx, config.evidenceRoot)
    return async () => {
      try { await disposeRoute() } finally { await disposeCore() }
    }
  } catch (error) {
    await disposeCore()
    throw error
  }
}
