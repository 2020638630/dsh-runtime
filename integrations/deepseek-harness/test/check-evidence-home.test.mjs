import { test } from 'node:test'
import assert from 'node:assert/strict'
import { copyFileSync, mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { checkEvidenceHome } from '../scripts/check-evidence-home.mjs'

const runId = 'dsh-runtime-11111111-2222-3333-4444-555555555555'
const workspaceId = 'session-22222222-3333-4444-5555-666666666666'

test('original evidence is ready; a byte-identical Home copy diagnoses its absolute Diff reference', t => {
  const fixture = mkdtempSync(join(tmpdir(), 'dsh-evidence-home-'))
  t.after(() => rmSync(fixture, { recursive: true, force: true }))
  const oldRoot = join(fixture, 'old', 'evidence')
  const newRoot = join(fixture, 'new', 'evidence')
  const oldRun = join(oldRoot, 'dsh-runtime', runId)
  const newRun = join(newRoot, 'dsh-runtime', runId)
  mkdirSync(oldRun, { recursive: true })
  mkdirSync(newRun, { recursive: true })
  const diff = Buffer.from('--- /dev/null\n+++ b/example.txt\n+example\n')
  writeFileSync(join(oldRun, 'diff.patch'), diff)
  writeFileSync(join(oldRun, 'evidence-manifest.v1.json'), JSON.stringify({
    schema_version: '1', run_id: runId, workspace_id: workspaceId,
    workspace_changes: { diff_content_ref: join(oldRun, 'diff.patch') },
  }))
  copyFileSync(join(oldRun, 'diff.patch'), join(newRun, 'diff.patch'))
  copyFileSync(join(oldRun, 'evidence-manifest.v1.json'), join(newRun, 'evidence-manifest.v1.json'))
  assert.deepEqual(checkEvidenceHome({ evidenceRoot: oldRoot, runId, workspaceId }), { status: 'READY' })
  assert.deepEqual(checkEvidenceHome({ evidenceRoot: newRoot, runId, workspaceId }),
    { status: 'RELOCATED_ABSOLUTE_REFERENCE' })
  assert.deepEqual(checkEvidenceHome({ evidenceRoot: oldRoot, runId, workspaceId: 'wrong' }),
    { status: 'IDENTITY_MISMATCH' })
})

test('missing or invalid evidence never reports ready', t => {
  const fixture = mkdtempSync(join(tmpdir(), 'dsh-evidence-home-'))
  t.after(() => rmSync(fixture, { recursive: true, force: true }))
  assert.deepEqual(checkEvidenceHome({ evidenceRoot: fixture, runId, workspaceId }),
    { status: 'MISSING_EVIDENCE' })
  assert.deepEqual(checkEvidenceHome({ evidenceRoot: fixture, runId: '../escape', workspaceId }),
    { status: 'INVALID_INPUT' })
})
