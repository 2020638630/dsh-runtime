import { createHash } from 'node:crypto'
import { captureWorkspace, describeWorkspaceObservation } from './workspace-evidence.ts'
import type { readTerminalEvidence } from './read-terminal-evidence.ts'

const MAX_PATCH_BYTES = 24 * 1024
const SHA256 = /^[0-9a-f]{64}$/u
const COMMIT = /^(?:[0-9a-f]{40}|[0-9a-f]{64})$/u

function record(value: unknown): Record<string, unknown> | undefined {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown> : undefined
}

/** Prepare bounded, locally visible review material from a single owned run.
 * The worktree comparison is an observation at preview time. The frozen
 * material is the saved UTF-8 patch, whose digest is checked independently.
 */
export async function previewReviewMaterial(
  evidence: NonNullable<Awaited<ReturnType<typeof readTerminalEvidence>>>,
  workspace: string | undefined,
  requestSignal: AbortSignal,
) {
  const { manifest, reviewBytes, relocation } = evidence
  const verification = record(manifest.verification)
  if (relocation || manifest.task_kind !== 'repository_change' || manifest.status !== 'completed'
    || verification?.verdict !== 'PASS' || verification.invocation_binding !== 'matched') {
    return { status: 'unsupported_run' } as const
  }
  const observation = record(manifest.target_observation)
  const changes = record(manifest.workspace_changes)
  if (observation?.version !== 1 || observation.source !== 'post_run_worktree_observation'
    || observation.scope !== 'dsh_controlled_snapshot_v1'
    || typeof observation.base_commit !== 'string' || !COMMIT.test(observation.base_commit)
    || typeof observation.content_sha256 !== 'string' || !SHA256.test(observation.content_sha256)
    || typeof changes?.diff_sha256 !== 'string' || !SHA256.test(changes.diff_sha256)) {
    return { status: 'missing_binding' } as const
  }
  if (changes.patch_complete !== true || changes.patch_applicable !== true
    || !reviewBytes || reviewBytes.length === 0 || reviewBytes.length > MAX_PATCH_BYTES) {
    return { status: 'unsupported_patch' } as const
  }
  const digest = createHash('sha256').update(reviewBytes).digest('hex')
  if (digest !== changes.diff_sha256) return { status: 'material_changed' } as const
  let patch: string
  try {
    patch = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(reviewBytes)
  } catch {
    return { status: 'unsupported_patch' } as const
  }
  if (workspace === undefined) return { status: 'workspace_unavailable' } as const
  try {
    const signal = AbortSignal.any([requestSignal, AbortSignal.timeout(10_000)])
    const current = await describeWorkspaceObservation(await captureWorkspace(workspace, signal), signal)
    if (current.content_sha256 === null || current.base_commit === null) {
      return { status: 'workspace_unavailable' } as const
    }
    if (current.base_commit !== observation.base_commit || current.content_sha256 !== observation.content_sha256) {
      return { status: 'stale' } as const
    }
  } catch {
    requestSignal.throwIfAborted()
    return { status: 'workspace_unavailable' } as const
  }
  return {
    status: 'ready', scope: 'saved_text_patch', runId: manifest.run_id,
    baseCommit: observation.base_commit, worktreeSha256: observation.content_sha256,
    patchSha256: digest, patchBytes: reviewBytes.length, patch,
  } as const
}
