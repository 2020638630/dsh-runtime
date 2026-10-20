/** Run-window workspace observations, independent of Runtime's narrative. */

import { createHash } from 'node:crypto'
import { execFile } from 'node:child_process'
import { createReadStream } from 'node:fs'
import { readFile, realpath, stat } from 'node:fs/promises'
import { isAbsolute, join, relative, sep } from 'node:path'
import { promisify } from 'node:util'

const run = promisify(execFile)
const MAX_FILE_BYTES = 2 * 1024 * 1024
const MAX_CAPTURE_BYTES = 64 * 1024 * 1024
const MAX_DIFF_BYTES = 8 * 1024 * 1024
const MAX_PATHS = 20_000
const EXCLUSIONS = [
  '.git/', 'node_modules/', 'dist/', 'build/', '__pycache__/',
  '.venv/', '.node-v24/', '.tmp/', '*.log', '*.tmp',
] as const

interface FileState {
  readonly size: number
  readonly hash: string
  readonly bytes: Buffer | null
}

/** Bounded Git workspace file observations captured at one point in time. */
export interface WorkspaceSnapshot {
  readonly workspace: string
  readonly files: ReadonlyMap<string, FileState>
  readonly scopeExclusions: readonly string[]
}

/** Per-file content status used when a complete text patch is unavailable. */
export interface WorkspaceFileMetadata {
  readonly path: string
  readonly status: 'text' | 'binary' | 'oversized' | 'encoding_warning' | 'unavailable'
  readonly beforeBytes: number | null
  readonly afterBytes: number | null
  readonly beforeSha256: string | null
  readonly afterSha256: string | null
}

/** Run-window changes and a view-only or machine-applicable Diff. */
export interface WorkspaceEvidence {
  readonly source: 'workspace_pre_post_snapshot_delta'
  readonly baseline_compared: true
  readonly physical_isolation: 'none_shared_workspace'
  readonly observation_boundary: 'window_observed_changes'
  readonly exclusion_policy_id: 'dsh_controlled_snapshot_v1'
  readonly scope_exclusions: readonly string[]
  readonly patch_complete: boolean
  readonly patch_applicable: boolean
  readonly patch_applicability_status: 'machine_applicable_patch' | 'view_only_review'
  readonly modified_files: readonly string[]
  readonly added_files: readonly string[]
  readonly deleted_files: readonly string[]
  readonly diff_stat: string
  readonly file_metadata: readonly WorkspaceFileMetadata[]
  readonly diff: string
}

function excluded(path: string): boolean {
  const parts = path.split('/')
  return parts.some(part => ['.git', 'node_modules', 'dist', 'build', '__pycache__', '.venv', '.node-v24', '.tmp'].includes(part))
    || path.endsWith('.log') || path.endsWith('.tmp')
}

function within(root: string, path: string): boolean {
  const rel = relative(root, path)
  return rel === '' || (rel !== '..' && !rel.startsWith(`..${sep}`) && !isAbsolute(rel))
}

async function hashFile(path: string): Promise<string> {
  const hash = createHash('sha256')
  for await (const chunk of createReadStream(path) as AsyncIterable<Buffer>) hash.update(chunk)
  return hash.digest('hex')
}

/** Capture tracked and non-ignored untracked files without changing the index.
 * @param workspace - absolute Git workspace root to observe.
 * @returns bounded snapshot of file hashes and eligible text bytes.
 */
export async function captureWorkspace(workspace: string): Promise<WorkspaceSnapshot> {
  if (!isAbsolute(workspace)) throw new Error('workspace snapshot requires an absolute directory')
  const physicalRoot = await realpath(workspace)
  const { stdout } = await run('git', [
    '-c', `safe.directory=${physicalRoot}`, 'ls-files', '-z', '--cached', '--others', '--exclude-standard',
  ], { cwd: physicalRoot, encoding: 'buffer', maxBuffer: 4 * 1024 * 1024, timeout: 30_000 })
  const paths = [...new Set(stdout.toString('utf8').split('\0').filter(Boolean))]
    .filter(path => !excluded(path)).sort()
  if (paths.length > MAX_PATHS) throw new Error('workspace snapshot exceeds the file-count bound')
  const files = new Map<string, FileState>()
  let capturedBytes = 0
  for (const path of paths) {
    const absolute = join(physicalRoot, path)
    let physical: string
    let info
    try {
      physical = await realpath(absolute)
      if (!within(physicalRoot, physical)) continue
      info = await stat(absolute)
    } catch (error: unknown) {
      if (typeof error === 'object' && error !== null && 'code' in error && error.code === 'ENOENT') continue
      throw error
    }
    if (!info.isFile()) continue
    let bytes: Buffer | null = null
    if (info.size <= MAX_FILE_BYTES && capturedBytes + info.size <= MAX_CAPTURE_BYTES) {
      bytes = await readFile(absolute)
      capturedBytes += bytes.length
      if (bytes.length > MAX_FILE_BYTES) bytes = null
    }
    const hash = bytes === null ? await hashFile(absolute) : createHash('sha256').update(bytes).digest('hex')
    files.set(path, { size: info.size, hash, bytes })
  }
  return { workspace: physicalRoot, files, scopeExclusions: [...EXCLUSIONS] }
}

function textLines(text: string): string[] {
  if (text === '') return []
  return text.endsWith('\n') ? text.slice(0, -1).split('\n') : text.split('\n')
}

function renderHunk(before: string, after: string): { text: string; added: number; deleted: number; empty: boolean } {
  const oldLines = textLines(before)
  const newLines = textLines(after)
  if (oldLines.length === 0 && newLines.length === 0) return { text: '', added: 0, deleted: 0, empty: true }
  const lines = [
    `@@ -${oldLines.length === 0 ? 0 : 1},${oldLines.length} +${newLines.length === 0 ? 0 : 1},${newLines.length} @@`,
  ]
  for (const line of oldLines) lines.push(`-${line}`)
  if (before !== '' && !before.endsWith('\n')) lines.push('\\ No newline at end of file')
  for (const line of newLines) lines.push(`+${line}`)
  if (after !== '' && !after.endsWith('\n')) lines.push('\\ No newline at end of file')
  return { text: `${lines.join('\n')}\n`, added: newLines.length, deleted: oldLines.length, empty: false }
}

/** Compare actual pre/post bytes; pre-existing dirty files count only if they changed during this run.
 * @param before - pre-run workspace observation.
 * @param after - post-run workspace observation from the same root.
 * @returns changed paths, file metadata, and the bounded Diff.
 */
export function compareWorkspace(before: WorkspaceSnapshot, after: WorkspaceSnapshot): WorkspaceEvidence {
  if (before.workspace !== after.workspace) throw new Error('workspace snapshots refer to different roots')
  const modified: string[] = []
  const added: string[] = []
  const deleted: string[] = []
  const metadata: WorkspaceFileMetadata[] = []
  const patches: string[] = []
  let additions = 0
  let deletions = 0
  let patchComplete = true
  let patchApplicable = true
  const decoder = new TextDecoder('utf-8', { fatal: true })
  for (const path of new Set([...before.files.keys(), ...after.files.keys()])) {
    const old = before.files.get(path)
    const next = after.files.get(path)
    if (old?.hash === next?.hash && old?.size === next?.size) continue
    if (old === undefined) added.push(path)
    else if (next === undefined) deleted.push(path)
    else modified.push(path)
    let status: WorkspaceFileMetadata['status'] = 'text'
    const oldBytes = old?.bytes
    const newBytes = next?.bytes
    if ((old !== undefined && oldBytes === null) || (next !== undefined && newBytes === null)) {
      status = 'oversized'
      patchComplete = false
      patchApplicable = false
    } else if (oldBytes?.includes(0) || newBytes?.includes(0)) {
      status = 'binary'
      patchApplicable = false
    }
    let oldText = ''
    let newText = ''
    if (status === 'text') {
      try {
        oldText = oldBytes == null ? '' : decoder.decode(oldBytes)
        newText = newBytes == null ? '' : decoder.decode(newBytes)
      } catch {
        status = 'encoding_warning'
        patchApplicable = false
        oldText = oldBytes == null ? '' : new TextDecoder().decode(oldBytes)
        newText = newBytes == null ? '' : new TextDecoder().decode(newBytes)
      }
    }
    const oldLabel = old === undefined ? '/dev/null' : `a/${path}`
    const newLabel = next === undefined ? '/dev/null' : `b/${path}`
    const header = `--- ${oldLabel}\n+++ ${newLabel}\n`
    if (status === 'binary') patches.push(`Binary files ${oldLabel} and ${newLabel} differ\n`)
    else if (status === 'oversized') patches.push(`${header}[Diff truncated: file size exceeds 2MB or capture limit]\n`)
    else {
      const hunk = renderHunk(oldText, newText)
      patches.push(header + hunk.text)
      additions += hunk.added
      deletions += hunk.deleted
      if (hunk.empty) patchApplicable = false
      if (status === 'encoding_warning') patchApplicable = false
    }
    metadata.push({
      path, status, beforeBytes: old?.size ?? null, afterBytes: next?.size ?? null,
      beforeSha256: old?.hash ?? null, afterSha256: next?.hash ?? null,
    })
  }
  let diff = patches.join('')
  if (Buffer.byteLength(diff, 'utf8') > MAX_DIFF_BYTES) {
    diff = `${Buffer.from(diff, 'utf8').subarray(0, MAX_DIFF_BYTES - 128).toString('utf8')}\n[Diff truncated: total output exceeds 8MB]\n`
    patchComplete = false
    patchApplicable = false
  }
  return {
    source: 'workspace_pre_post_snapshot_delta', baseline_compared: true,
    physical_isolation: 'none_shared_workspace', observation_boundary: 'window_observed_changes',
    exclusion_policy_id: 'dsh_controlled_snapshot_v1', scope_exclusions: before.scopeExclusions,
    patch_complete: patchComplete, patch_applicable: patchApplicable,
    patch_applicability_status: patchApplicable ? 'machine_applicable_patch' : 'view_only_review',
    modified_files: modified, added_files: added, deleted_files: deleted,
    diff_stat: `+${additions} -${deletions}`, file_metadata: metadata, diff,
  }
}
