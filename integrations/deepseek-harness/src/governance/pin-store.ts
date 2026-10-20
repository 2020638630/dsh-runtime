/** Host-owned durable policy identity store for external Harness plugins. */
import { lstatSync, realpathSync, statSync } from 'node:fs'
import { open, readFile } from 'node:fs/promises'
import { isAbsolute, join } from 'node:path'
import { policyIdentitySchema, type PolicyIdentity } from './protocol.ts'

const SESSION_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/
const MAX_PIN_BYTES = 4096

function sameIdentity(left: PolicyIdentity, right: PolicyIdentity): boolean {
  return left.policy_id === right.policy_id
    && left.policy_version === right.policy_version
    && left.artifact_schema_version === right.artifact_schema_version
    && left.policy_hash === right.policy_hash
}

function isErrorCode(error: unknown, code: string): boolean {
  return error instanceof Error && 'code' in error && error.code === code
}

/** A missing, corrupt or conflicting pin cannot be interpreted as permission to start. */
export class GovernancePinStore {
  readonly root: string

  constructor(root: string) {
    if (!isAbsolute(root) || !statSync(root).isDirectory()) throw new TypeError('governance pinRoot must be an existing absolute directory')
    this.root = realpathSync(root)
  }

  private path(sessionId: string): string {
    if (!SESSION_ID.test(sessionId)) throw new TypeError('invalid governance session identity')
    return join(this.root, `${sessionId}.json`)
  }

  async read(sessionId: string): Promise<PolicyIdentity | undefined> {
    const path = this.path(sessionId)
    let info
    try { info = lstatSync(path) } catch (error) {
      if (isErrorCode(error, 'ENOENT')) return undefined
      throw error
    }
    if (!info.isFile() || info.size > MAX_PIN_BYTES || realpathSync(path) !== path) {
      throw new Error('governance pin file is invalid')
    }
    const bytes = await readFile(path)
    if (bytes.length > MAX_PIN_BYTES) throw new Error('governance pin file exceeds its read bound')
    const value: unknown = JSON.parse(bytes.toString('utf8'))
    if (typeof value !== 'object' || value === null || Array.isArray(value)) throw new Error('governance pin record is invalid')
    const record = value as Record<string, unknown>
    if (record.schema_version !== 1 || record.session_id !== sessionId) throw new Error('governance pin identity mismatch')
    return policyIdentitySchema.parse(record.policy_identity)
  }

  async pin(sessionId: string, identity: PolicyIdentity): Promise<PolicyIdentity> {
    const validated = policyIdentitySchema.parse(identity)
    const existing = await this.read(sessionId)
    if (existing !== undefined) {
      if (!sameIdentity(existing, validated)) throw new Error('governance policy pin conflict')
      return existing
    }
    const path = this.path(sessionId)
    let file
    try { file = await open(path, 'wx', 0o600) } catch (error) {
      if (isErrorCode(error, 'EEXIST')) {
        const concurrent = await this.read(sessionId)
        if (concurrent !== undefined && sameIdentity(concurrent, validated)) return concurrent
        throw new Error('governance policy pin conflict after concurrent create')
      }
      throw error
    }
    try {
      await file.writeFile(`${JSON.stringify({ schema_version: 1, session_id: sessionId, policy_identity: validated })}\n`)
      await file.sync()
    } finally {
      await file.close()
    }
    return validated
  }
}
