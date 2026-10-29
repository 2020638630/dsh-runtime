/** Bounded Host-only read of a settled run's saved manifest and Diff. */

import { readFile, realpath, stat } from 'node:fs/promises'
import { basename, isAbsolute, join, relative, sep } from 'node:path'
import { verifyEvidenceRelocation } from './verify-evidence-relocation.ts'

const RUN_ID = /^dsh-runtime-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/u
const MAX_MANIFEST_BYTES = 1_048_576
const MAX_DIFF_BYTES = 8 * 1_048_576
const MAX_STATE_BYTES = 4_096

function within(root: string, path: string): boolean {
  const rel = relative(root, path)
  return rel === '' || (rel !== '..' && !rel.startsWith(`..${sep}`) && !isAbsolute(rel))
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

/** Read exact Host-owned filenames only; callers authorize the workspace id before returning data to a client.
 * @param input - absolute evidence root and parent-bound run identities.
 * @returns saved Manifest and Diff, or null before the Manifest exists.
 */
export async function readTerminalEvidence(input: {
  readonly evidenceRoot: string
  readonly runId: string
  readonly workspaceId: string
}): Promise<{ readonly manifest: Record<string, unknown>; readonly diff: string;
  readonly relocation?: { readonly status: 'verified_copy'; readonly createdAt: string } } | null> {
  const { evidenceRoot, runId, workspaceId } = input
  if (!isAbsolute(evidenceRoot) || !RUN_ID.test(runId) || workspaceId.length === 0) {
    throw new Error('terminal evidence read requires an absolute root and valid identities')
  }
  const root = await realpath(evidenceRoot)
  const runDir = join(root, 'dsh-runtime', runId)
  let physicalRunDir: string
  try {
    physicalRunDir = await realpath(runDir)
  } catch (error: unknown) {
    if (record(error)?.code === 'ENOENT') return null
    throw error
  }
  if (!within(root, physicalRunDir) || basename(physicalRunDir) !== runId) {
    throw new Error('terminal evidence directory is outside the Host root')
  }
  const manifestPath = join(physicalRunDir, 'evidence-manifest.v1.json')
  const diffPath = join(physicalRunDir, 'diff.patch')
  let physicalManifest: string
  let physicalDiff: string
  try {
    physicalManifest = await realpath(manifestPath)
    physicalDiff = await realpath(diffPath)
  } catch (error: unknown) {
    if (record(error)?.code === 'ENOENT') return null
    throw error
  }
  if (!within(physicalRunDir, physicalManifest) || !within(physicalRunDir, physicalDiff)) {
    throw new Error('terminal evidence file escapes the run directory')
  }
  const [manifestInfo, diffInfo] = await Promise.all([stat(physicalManifest), stat(physicalDiff)])
  if (!manifestInfo.isFile() || !diffInfo.isFile()
    || manifestInfo.size > MAX_MANIFEST_BYTES || diffInfo.size > MAX_DIFF_BYTES) {
    throw new Error('terminal evidence exceeds its read bounds')
  }
  const [manifestBytes, diffBytes] = await Promise.all([readFile(physicalManifest), readFile(physicalDiff)])
  if (manifestBytes.length > MAX_MANIFEST_BYTES || diffBytes.length > MAX_DIFF_BYTES) {
    throw new Error('terminal evidence exceeds its read bounds')
  }
  const manifest = record(JSON.parse(manifestBytes.toString('utf8')))
  const referencedDiff = record(manifest?.workspace_changes)?.diff_content_ref
  if (manifest?.schema_version !== '1' || manifest.run_id !== runId
    || manifest.workspace_id !== workspaceId || typeof referencedDiff !== 'string'
    || !isAbsolute(referencedDiff)) {
    throw new Error('terminal evidence identities do not match this run and workspace')
  }
  const originalPathMatches = await realpath(referencedDiff).then(path => path === physicalDiff, () => false)
  if (originalPathMatches) return { manifest, diff: diffBytes.toString('utf8') }
  const relocation = await verifyEvidenceRelocation({ runDir: physicalRunDir, runId,
    workspaceId, manifestBytes, diffBytes, originalDiffRef: referencedDiff })
  return { manifest, diff: diffBytes.toString('utf8'), relocation }
}

/** Read the Host's run lifecycle marker when a terminal Manifest is absent.
 * @param input - absolute evidence root and parent-bound run identities.
 * @returns validated lifecycle marker, or null when it is absent.
 */
export async function readTerminalRunState(input: {
  readonly evidenceRoot: string
  readonly runId: string
  readonly workspaceId: string
}): Promise<{ readonly phase: 'running' | 'settled'; readonly stopReason: string | null; readonly manifestAvailable: boolean } | null> {
  const { evidenceRoot, runId, workspaceId } = input
  if (!isAbsolute(evidenceRoot) || !RUN_ID.test(runId) || workspaceId.length === 0) {
    throw new Error('terminal evidence state requires an absolute root and valid identities')
  }
  const root = await realpath(evidenceRoot)
  const path = join(root, 'dsh-runtime', runId, 'run-state.json')
  let physical: string
  try {
    physical = await realpath(path)
  } catch (error: unknown) {
    if (record(error)?.code === 'ENOENT') return null
    throw error
  }
  if (!within(root, physical) || basename(physical) !== 'run-state.json') {
    throw new Error('terminal evidence state escapes the Host root')
  }
  const info = await stat(physical)
  if (!info.isFile() || info.size > MAX_STATE_BYTES) throw new Error('terminal evidence state exceeds its read bounds')
  const bytes = await readFile(physical)
  if (bytes.length > MAX_STATE_BYTES) throw new Error('terminal evidence state exceeds its read bounds')
  const state = record(JSON.parse(bytes.toString('utf8')))
  if (state?.schema_version !== 1 || state.run_id !== runId || state.workspace_id !== workspaceId
    || (state.phase !== 'running' && state.phase !== 'settled')) {
    throw new Error('terminal evidence state identities do not match')
  }
  return {
    phase: state.phase,
    stopReason: state.phase === 'settled' && typeof state.stop_reason === 'string' ? state.stop_reason : null,
    manifestAvailable: state.manifest_available === true,
  }
}
