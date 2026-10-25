import assert from 'node:assert/strict'
import { copyFileSync, mkdtempSync, mkdirSync, realpathSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { isAbsolute, join, relative, sep } from 'node:path'
import { test } from 'node:test'
import { readTerminalEvidence } from '../src/runtime/read-terminal-evidence.ts'

const runId = 'dsh-runtime-11111111-2222-3333-4444-555555555555'
const workspaceId = 'session-22222222-3333-4444-5555-666666666666'

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
  copyFileSync(join(originalRun, 'diff.patch'), join(copiedRun, 'diff.patch'))
  copyFileSync(join(originalRun, 'evidence-manifest.v1.json'), join(copiedRun, 'evidence-manifest.v1.json'))
  const input = { runId, workspaceId }
  assert.equal((await readTerminalEvidence({ ...input, evidenceRoot: original }))?.diff, '+example\n')
  await assert.rejects(readTerminalEvidence({ ...input, evidenceRoot: copied }),
    /terminal evidence identities do not match/u)
  await assert.rejects(readTerminalEvidence({ ...input, evidenceRoot: original,
    workspaceId: 'wrong-parent' }), /terminal evidence identities do not match/u)
  const empty = join(fixture, 'empty')
  mkdirSync(empty)
  assert.equal(await readTerminalEvidence({ ...input, evidenceRoot: empty }), null)
})
