/** Verify a copied historical run against its separate, unsigned copy receipt. */
import { createHash } from 'node:crypto'
import { constants } from 'node:fs'
import { lstat, open, readdir, realpath } from 'node:fs/promises'
import { basename, isAbsolute, join, relative, sep } from 'node:path'

const SAFE_FILE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$/u
const SHA256 = /^[0-9a-f]{64}$/u
const MAX_FILES = 32
const MAX_TOTAL_BYTES = 64 * 1_048_576
const MAX_FILE_BYTES = 32 * 1_048_576
const MAX_RECEIPT_BYTES = 64_000
const MAX_MANIFEST_BYTES = 1_048_576
const MAX_DIFF_BYTES = 8 * 1_048_576
const hash = (bytes: Buffer): string => createHash('sha256').update(bytes).digest('hex')

function object(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown> : null
}

function inside(root: string, child: string): boolean {
  const rel = relative(root, child)
  return rel === '' || (rel !== '..' && !rel.startsWith(`..${sep}`) && !isAbsolute(rel))
}

function safePart(part: string): boolean {
  return SAFE_FILE.test(part) && !part.endsWith('.')
    && !/^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/iu.test(part)
}

function safeArtifact(name: string, runId: string): boolean {
  const parts = name.split('/')
  return (parts.length === 1 && safePart(parts[0]!))
    || (parts.length === 2 && parts[0] === `safe-trace-${runId}` && safePart(parts[1]!))
}

async function readBounded(runDir: string, name: string, limit: number): Promise<Buffer> {
  const path = join(runDir, ...name.split('/'))
  const entry = await lstat(path)
  if (!entry.isFile() || entry.isSymbolicLink() || entry.nlink !== 1 || entry.size > limit) {
    throw new Error('unsafe relocated artifact')
  }
  const physical = await realpath(path)
  if (!inside(runDir, physical) || basename(physical) !== name.split('/').at(-1)) {
    throw new Error('relocated artifact escapes run')
  }
  const handle = await open(path, constants.O_RDONLY)
  try {
    const info = await handle.stat()
    if (!info.isFile() || info.nlink !== 1 || info.size > limit
      || info.dev !== entry.dev || info.ino !== entry.ino) {
      throw new Error('relocated artifact changed during read')
    }
    const bytes = await handle.readFile()
    if (bytes.length > limit || await realpath(path) !== physical) {
      throw new Error('relocated artifact changed during read')
    }
    return bytes
  } finally { await handle.close() }
}

async function inventory(runDir: string, runId: string): Promise<string[]> {
  const names: string[] = []
  for (const name of await readdir(runDir)) {
    if (name === 'evidence-relocation.v1.json') continue
    if (!safePart(name)) throw new Error('invalid relocated artifact name')
    const entry = await lstat(join(runDir, name))
    if (entry.isFile() && !entry.isSymbolicLink()) { names.push(name); continue }
    if (!entry.isDirectory() || entry.isSymbolicLink() || name !== `safe-trace-${runId}`) {
      throw new Error('unsafe relocated directory')
    }
    const physical = await realpath(join(runDir, name))
    if (!inside(runDir, physical) || basename(physical) !== name) throw new Error('unsafe relocated directory')
    const children = await readdir(physical)
    if (children.length === 0) throw new Error('empty relocated trace directory')
    for (const child of children) {
      if (!safePart(child)) throw new Error('invalid relocated trace name')
      names.push(`${name}/${child}`)
    }
  }
  if (names.length < 3 || names.length > MAX_FILES) throw new Error('invalid relocated inventory')
  return names.sort()
}

/** Hash-check every copied artifact, including trace files, without consulting the old Home. */
export async function verifyEvidenceRelocation(input: {
  readonly runDir: string
  readonly runId: string
  readonly workspaceId: string
  readonly manifestBytes: Buffer
  readonly diffBytes: Buffer
  readonly originalDiffRef: string
}): Promise<{ readonly status: 'verified_copy'; readonly createdAt: string }> {
  const { runDir, runId, workspaceId, manifestBytes, diffBytes, originalDiffRef } = input
  const receiptBytes = await readBounded(runDir, 'evidence-relocation.v1.json', MAX_RECEIPT_BYTES)
  const receipt = object(JSON.parse(receiptBytes.toString('utf8')))
  if (receipt?.schema_version !== 1 || receipt.run_id !== runId || receipt.workspace_id !== workspaceId
    || receipt.source_diff_content_ref !== originalDiffRef
    || !isAbsolute(originalDiffRef) || receipt.manifest_sha256 !== hash(manifestBytes)
    || receipt.diff_sha256 !== hash(diffBytes)
    || typeof receipt.source_run_fingerprint !== 'string' || !SHA256.test(receipt.source_run_fingerprint)
    || typeof receipt.created_at !== 'string' || !Number.isFinite(Date.parse(receipt.created_at))) {
    throw new Error('relocation receipt identity or digest mismatch')
  }
  const copied = receipt.copied_artifacts
  if (!Array.isArray(copied) || copied.length < 3 || copied.length > MAX_FILES) {
    throw new Error('invalid relocation receipt inventory')
  }
  const names = await inventory(runDir, runId)
  if (names.length !== copied.length) throw new Error('relocation inventory changed')
  const verified: { name: string; size: number; sha256: string }[] = []
  let total = 0
  for (let i = 0; i < copied.length; i++) {
    const item = object(copied[i])
    const name = item?.name
    if (typeof name !== 'string' || name !== names[i] || !safeArtifact(name, runId)
      || !Number.isSafeInteger(item?.size) || (item?.size as number) < 0
      || typeof item?.sha256 !== 'string' || !SHA256.test(item.sha256)) {
      throw new Error('invalid relocation receipt artifact')
    }
    const limit = name === 'evidence-manifest.v1.json' ? MAX_MANIFEST_BYTES
      : name === 'diff.patch' ? MAX_DIFF_BYTES : MAX_FILE_BYTES
    const bytes = await readBounded(runDir, name, limit)
    total += bytes.length
    if (total > MAX_TOTAL_BYTES || bytes.length !== item.size || hash(bytes) !== item.sha256) {
      throw new Error('relocated artifact digest mismatch')
    }
    verified.push({ name, size: bytes.length, sha256: hash(bytes) })
  }
  if (!verified.some(item => item.name === 'evidence-manifest.v1.json')
    || !verified.some(item => item.name === 'diff.patch')
    || !verified.some(item => item.name === 'run-state.json')
    || hash(Buffer.from(JSON.stringify(verified))) !== receipt.source_run_fingerprint) {
    throw new Error('relocation receipt fingerprint mismatch')
  }
  const state = object(JSON.parse((await readBounded(runDir, 'run-state.json', 4_096)).toString('utf8')))
  if (state?.schema_version !== 1 || state.run_id !== runId || state.workspace_id !== workspaceId
    || state.phase !== 'settled' || state.manifest_available !== true) {
    throw new Error('relocated run is not settled')
  }
  return { status: 'verified_copy', createdAt: receipt.created_at }
}
