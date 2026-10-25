import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { copyFileSync, linkSync, mkdtempSync, mkdirSync, readFileSync, realpathSync, renameSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { isAbsolute, join, relative, sep } from 'node:path'
import { test } from 'node:test'
import { readTerminalEvidence } from '../src/runtime/read-terminal-evidence.ts'

const runId = 'dsh-runtime-11111111-2222-3333-4444-555555555555'
const workspaceId = 'session-22222222-3333-4444-5555-666666666666'
const sha = (bytes: Buffer): string => createHash('sha256').update(bytes).digest('hex')

test('original settled evidence reads, but a copied absolute Diff reference fails closed', async t => {
  const base = realpathSync(tmpdir())
  const fixture = mkdtempSync(join(base, 'dsh-terminal-evidence-'))
  t.after(() => {
    const rel = relative(base, realpathSync(fixture))
    assert.ok(rel !== '' && rel !== '..' && !rel.startsWith(`..${sep}`) && !isAbsolute(rel))
    rmSync(fixture, { recursive: true, force: true })
  })
  const original = join(fixture, 'original', 'evidence')
  const copied = join(fixture, 'copied', 'evidence')
  const originalRun = join(original, 'dsh-runtime', runId)
  const copiedRun = join(copied, 'dsh-runtime', runId)
  mkdirSync(originalRun, { recursive: true })
  mkdirSync(copiedRun, { recursive: true })
  writeFileSync(join(originalRun, 'diff.patch'), '+example\n')
  writeFileSync(join(originalRun, 'evidence-manifest.v1.json'), JSON.stringify({
    schema_version: '1', run_id: runId, workspace_id: workspaceId,
    workspace_changes: { diff_content_ref: join(originalRun, 'diff.patch') },
  }))
  writeFileSync(join(originalRun, 'run-state.json'), JSON.stringify({ schema_version: 1,
    run_id: runId, workspace_id: workspaceId, phase: 'settled', manifest_available: true }))
  writeFileSync(join(originalRun, 'trace.jsonl'), 'complete\n')
  copyFileSync(join(originalRun, 'diff.patch'), join(copiedRun, 'diff.patch'))
  copyFileSync(join(originalRun, 'evidence-manifest.v1.json'), join(copiedRun, 'evidence-manifest.v1.json'))
  copyFileSync(join(originalRun, 'run-state.json'), join(copiedRun, 'run-state.json'))
  copyFileSync(join(originalRun, 'trace.jsonl'), join(copiedRun, 'trace.jsonl'))
  const input = { runId, workspaceId }
  assert.equal((await readTerminalEvidence({ ...input, evidenceRoot: original }))?.diff, '+example\n')
  await assert.rejects(readTerminalEvidence({ ...input, evidenceRoot: copied }), /ENOENT/u)
  const artifacts = ['diff.patch', 'evidence-manifest.v1.json', 'run-state.json', 'trace.jsonl']
    .map(name => { const bytes = readFileSync(join(originalRun, name))
      return { name, size: bytes.length, sha256: sha(bytes) } })
  const receipt = { schema_version: 1, run_id: runId, workspace_id: workspaceId,
    source_diff_content_ref: join(originalRun, 'diff.patch'),
    manifest_sha256: sha(readFileSync(join(originalRun, 'evidence-manifest.v1.json'))),
    diff_sha256: sha(readFileSync(join(originalRun, 'diff.patch'))),
    source_run_fingerprint: sha(Buffer.from(JSON.stringify(artifacts))),
    copied_artifacts: artifacts, created_at: '2026-10-25T00:00:00.000Z' }
  writeFileSync(join(copiedRun, 'evidence-relocation.v1.json'), JSON.stringify(receipt))
  assert.equal((await readTerminalEvidence({ ...input, evidenceRoot: copied }))?.relocation?.status, 'verified_copy')
  const parkedRun = join(original, 'dsh-runtime', `${runId}.parked`)
  renameSync(originalRun, parkedRun)
  assert.equal((await readTerminalEvidence({ ...input, evidenceRoot: copied }))?.relocation?.status, 'verified_copy')
  renameSync(parkedRun, originalRun)
  writeFileSync(join(copiedRun, 'trace.jsonl'), 'changed\n')
  await assert.rejects(readTerminalEvidence({ ...input, evidenceRoot: copied }), /digest mismatch/u)
  copyFileSync(join(originalRun, 'trace.jsonl'), join(copiedRun, 'trace.jsonl'))
  writeFileSync(join(copiedRun, 'diff.patch'), '+changed\n')
  await assert.rejects(readTerminalEvidence({ ...input, evidenceRoot: copied }), /digest mismatch/u)
  copyFileSync(join(originalRun, 'diff.patch'), join(copiedRun, 'diff.patch'))
  writeFileSync(join(copiedRun, 'evidence-relocation.v1.json'), JSON.stringify({
    ...receipt, workspace_id: 'wrong-parent',
  }))
  await assert.rejects(readTerminalEvidence({ ...input, evidenceRoot: copied }), /receipt identity/u)
  writeFileSync(join(copiedRun, 'evidence-relocation.v1.json'), JSON.stringify(receipt))
  const alias = join(fixture, 'trace-hardlink-alias')
  linkSync(join(copiedRun, 'trace.jsonl'), alias)
  await assert.rejects(readTerminalEvidence({ ...input, evidenceRoot: copied }), /unsafe relocated artifact/u)
  rmSync(alias)
  writeFileSync(join(copiedRun, 'unexpected.txt'), 'extra')
  await assert.rejects(readTerminalEvidence({ ...input, evidenceRoot: copied }), /inventory changed/u)
  await assert.rejects(readTerminalEvidence({ ...input, evidenceRoot: original,
    workspaceId: 'wrong-parent' }), /terminal evidence identities do not match/u)
  const empty = join(fixture, 'empty')
  mkdirSync(empty)
  assert.equal(await readTerminalEvidence({ ...input, evidenceRoot: empty }), null)
})
