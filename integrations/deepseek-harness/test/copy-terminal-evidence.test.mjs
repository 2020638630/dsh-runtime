import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { existsSync, linkSync, mkdtempSync, mkdirSync, readFileSync, realpathSync, readdirSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { isAbsolute, join, relative, sep } from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { copyTerminalEvidence } from '../scripts/copy-terminal-evidence.mjs'

const runId = 'dsh-runtime-11111111-2222-3333-4444-555555555555'
const workspaceId = 'session-22222222-3333-4444-5555-666666666666'
const digest = bytes => createHash('sha256').update(bytes).digest('hex')

function fixture(t) {
  const tempRoot = realpathSync(tmpdir())
  const base = mkdtempSync(join(tempRoot, 'dsh-evidence-copy-'))
  t.after(() => {
    const physical = realpathSync(base)
    const rel = relative(tempRoot, physical)
    assert.ok(rel !== '' && rel !== '..' && !rel.startsWith(`..${sep}`) && !isAbsolute(rel))
    rmSync(physical, { recursive: true, force: true })
  })
  const sourceEvidenceRoot = join(base, 'source', 'evidence')
  const targetEvidenceRoot = join(base, 'target', 'evidence')
  const run = join(sourceEvidenceRoot, 'dsh-runtime', runId)
  mkdirSync(run, { recursive: true })
  mkdirSync(targetEvidenceRoot, { recursive: true })
  writeFileSync(join(run, 'diff.patch'), '+one\n')
  writeFileSync(join(run, 'evidence-manifest.v1.json'), JSON.stringify({
    schema_version: '1', run_id: runId, workspace_id: workspaceId,
    workspace_changes: { diff_content_ref: join(run, 'diff.patch') },
  }))
  writeFileSync(join(run, 'run-state.json'), JSON.stringify({
    schema_version: 1, run_id: runId, workspace_id: workspaceId,
    phase: 'settled', manifest_available: true,
  }))
  writeFileSync(join(run, `${runId}-runtime-call-trace.jsonl`), '{"event":"done"}\n')
  const trace = join(run, `safe-trace-${runId}`)
  mkdirSync(trace)
  writeFileSync(join(trace, 'worker.jsonl.closed'), '{"closed":true}\n')
  return { sourceEvidenceRoot, targetEvidenceRoot, run,
    input: { sourceEvidenceRoot, targetEvidenceRoot, runId, workspaceId } }
}

test('copy preserves source bytes, writes receipt, and refuses replacement', async t => {
  const f = fixture(t)
  const names = readdirSync(f.run).flatMap(name => name.startsWith('safe-trace-')
    ? readdirSync(join(f.run, name)).map(child => `${name}/${child}`) : [name])
  const before = Object.fromEntries(names.map(name => [name, digest(readFileSync(join(f.run, ...name.split('/'))))]))
  const result = await copyTerminalEvidence(f.input)
  assert.equal(result.status, 'COPIED')
  const destination = join(f.targetEvidenceRoot, 'dsh-runtime', runId)
  const receipt = JSON.parse(readFileSync(join(destination, 'evidence-relocation.v1.json'), 'utf8'))
  assert.equal(receipt.run_id, runId)
  assert.equal(receipt.workspace_id, workspaceId)
  assert.equal(receipt.source_diff_content_ref, join(f.run, 'diff.patch'))
  assert.deepEqual(receipt.copied_artifacts.map(item => item.name), Object.keys(before).sort())
  for (const [name, originalHash] of Object.entries(before)) {
    assert.equal(digest(readFileSync(join(f.run, ...name.split('/')))), originalHash)
    assert.equal(digest(readFileSync(join(destination, ...name.split('/')))), originalHash)
  }
  assert.equal(receipt.manifest_sha256, before['evidence-manifest.v1.json'])
  assert.equal(receipt.diff_sha256, before['diff.patch'])
  assert.deepEqual(readdirSync(join(f.targetEvidenceRoot, 'dsh-runtime')), [runId])
  await assert.rejects(copyTerminalEvidence(f.input), /TARGET_EXISTS/u)
  assert.deepEqual(readdirSync(join(f.targetEvidenceRoot, 'dsh-runtime')), [runId])
})

test('mismatched identity and unsettled source fail before destination creation', async t => {
  const f = fixture(t)
  await assert.rejects(copyTerminalEvidence({ ...f.input, workspaceId: 'wrong' }), /SOURCE_IDENTITY_MISMATCH/u)
  assert.equal(existsSync(join(f.targetEvidenceRoot, 'dsh-runtime')), false)
  const statePath = join(f.run, 'run-state.json')
  const state = JSON.parse(readFileSync(statePath, 'utf8'))
  state.phase = 'running'
  writeFileSync(statePath, JSON.stringify(state))
  await assert.rejects(copyTerminalEvidence(f.input), /SOURCE_NOT_SETTLED/u)
  assert.equal(existsSync(join(f.targetEvidenceRoot, 'dsh-runtime')), false)
})

test('invalid absolute Diff reference and overlapping roots fail closed', async t => {
  const f = fixture(t)
  const manifestPath = join(f.run, 'evidence-manifest.v1.json')
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
  manifest.workspace_changes.diff_content_ref = join(f.targetEvidenceRoot, 'diff.patch')
  writeFileSync(manifestPath, JSON.stringify(manifest))
  await assert.rejects(copyTerminalEvidence(f.input), /ENOENT|SOURCE_IDENTITY_MISMATCH/u)
  await assert.rejects(copyTerminalEvidence({ ...f.input, targetEvidenceRoot: f.sourceEvidenceRoot }), /ROOTS_OVERLAP/u)
})

test('linked artifact and preexisting destination are rejected without overwrite', async t => {
  const f = fixture(t)
  const outside = join(f.sourceEvidenceRoot, 'outside.txt')
  writeFileSync(outside, 'outside')
  try {
    symlinkSync(outside, join(f.run, 'linked.txt'))
    await assert.rejects(copyTerminalEvidence(f.input), /UNSAFE_ARTIFACT/u)
    rmSync(join(f.run, 'linked.txt'))
  } catch (error) {
    if (error?.code !== 'EPERM') throw error
    t.diagnostic('Windows symlink privilege unavailable; other rejection cases still run')
  }
  linkSync(outside, join(f.run, 'hardlinked.txt'))
  await assert.rejects(copyTerminalEvidence(f.input), /UNSAFE_ARTIFACT/u)
  rmSync(join(f.run, 'hardlinked.txt'))
  const destination = join(f.targetEvidenceRoot, 'dsh-runtime', runId)
  mkdirSync(destination, { recursive: true })
  writeFileSync(join(destination, 'marker'), 'untouched')
  await assert.rejects(copyTerminalEvidence(f.input), /TARGET_EXISTS/u)
  assert.equal(readFileSync(join(destination, 'marker'), 'utf8'), 'untouched')
})

test('concurrent copies expose one complete final run', async t => {
  const f = fixture(t)
  const outcomes = await Promise.allSettled([copyTerminalEvidence(f.input), copyTerminalEvidence(f.input)])
  assert.equal(outcomes.filter(item => item.status === 'fulfilled').length, 1)
  assert.equal(outcomes.filter(item => item.status === 'rejected').length, 1)
  const destination = join(f.targetEvidenceRoot, 'dsh-runtime', runId)
  const receipt = JSON.parse(readFileSync(join(destination, 'evidence-relocation.v1.json'), 'utf8'))
  assert.equal(receipt.copied_artifacts.length, 5)
  for (const item of receipt.copied_artifacts) {
    assert.equal(digest(readFileSync(join(destination, ...item.name.split('/')))), item.sha256)
  }
})

test('direct CLI exits with a copy receipt and nonzero on a repeat', t => {
  const f = fixture(t)
  const script = fileURLToPath(new URL('../scripts/copy-terminal-evidence.mjs', import.meta.url))
  const args = ['--source-evidence-root', f.sourceEvidenceRoot,
    '--target-evidence-root', f.targetEvidenceRoot, '--run-id', runId, '--workspace-id', workspaceId]
  const first = spawnSync(process.execPath, [script, ...args], { encoding: 'utf8' })
  if (first.error?.code === 'EPERM') {
    t.skip('the sandbox blocks child processes; installed CLI is checked in the isolated Host environment')
    return
  }
  assert.equal(first.status, 0, first.stderr)
  assert.equal(JSON.parse(first.stdout).status, 'COPIED')
  const second = spawnSync(process.execPath, [script, ...args], { encoding: 'utf8' })
  assert.equal(second.status, 1)
  assert.equal(JSON.parse(second.stdout).status, 'TARGET_EXISTS')
})
