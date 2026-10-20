/** Installable official DeepSeekHarness Host entrypoint. */
import { statSync } from 'node:fs'
import { isAbsolute, dirname, resolve } from 'node:path'
import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-client-connection'
import type {} from '@deepseek-ai/dsh-session-query'
import { mountHostCore } from './host-core.ts'
import { registerRuntimeEvidenceRoute } from './evidence-route.ts'

export const name = 'dsh-runtime-standalone'
export const inject = ['subprocess', 'subagents', 'tools', 'connection', 'sessionQuery']

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
export function validateConfig(input: Config): Required<Config> {
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
  return { runtimeRoot, python: input.python, policySource, expectedPolicyHash: input.expectedPolicyHash, enabledWorkloads: input.enabledWorkloads, auditPath, pinRoot, evidenceRoot, disposeGraceMs, responseTimeoutMs, env }
}

export async function apply(ctx: Context, rawConfig: Config): Promise<() => Promise<void>> {
  const config = validateConfig(rawConfig)
  const disposeCore = await mountHostCore(ctx, {
    governance: {
      runtimeRoot: config.runtimeRoot, python: config.python, env: config.env,
      policySource: config.policySource, expectedPolicyHash: config.expectedPolicyHash,
      enabledWorkloads: config.enabledWorkloads, auditPath: config.auditPath,
      pinRoot: config.pinRoot,
      disposeGraceMs: config.disposeGraceMs, responseTimeoutMs: config.responseTimeoutMs,
    },
    runtime: {
      runtimeRoot: config.runtimeRoot, python: config.python, env: config.env,
      evidenceRoot: config.evidenceRoot, disposeGraceMs: config.disposeGraceMs,
    },
  })
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
