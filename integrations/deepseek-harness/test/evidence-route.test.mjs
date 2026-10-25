import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdtempSync, mkdirSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { isAbsolute, join, relative, sep } from 'node:path'
import { test } from 'node:test'
import { registerRuntimeEvidenceRoute } from '../.build/src/evidence-route.js'

const childId = '11111111-2222-3333-4444-555555555555'
const runId = `dsh-runtime-${childId}`
const workspaceId = 'session-22222222-3333-4444-5555-666666666666'
const sha = bytes => createHash('sha256').update(bytes).digest('hex')

test('parent ownership gates a verified historical copy and rejects a damaged receipt', async t => {
  const tempRoot = realpathSync(tmpdir())
  const base = mkdtempSync(join(tempRoot, 'dsh-route-copy-'))
  t.after(() => {
    const physical = realpathSync(base)
    const rel = relative(tempRoot, physical)
    assert.ok(rel !== '' && rel !== '..' && !rel.startsWith(`..${sep}`) && !isAbsolute(rel))
    rmSync(physical, { recursive: true, force: true })
  })
  const evidenceRoot = join(base, 'evidence')
  const runDir = join(evidenceRoot, 'dsh-runtime', runId)
  mkdirSync(runDir, { recursive: true })
  const oldDiff = join(base, 'old-home', 'diff.patch')
  const files = {
    'diff.patch': '+one\n',
    'evidence-manifest.v1.json': JSON.stringify({ schema_version: '1', run_id: runId,
      workspace_id: workspaceId, workspace_changes: { diff_content_ref: oldDiff } }),
    'run-state.json': JSON.stringify({ schema_version: 1, run_id: runId,
      workspace_id: workspaceId, phase: 'settled', manifest_available: true }),
  }
  for (const [name, body] of Object.entries(files)) writeFileSync(join(runDir, name), body)
  const artifacts = Object.keys(files).sort().map(name => ({ name,
    size: readFileSync(join(runDir, name)).length, sha256: sha(readFileSync(join(runDir, name))) }))
  const receipt = { schema_version: 1, run_id: runId, workspace_id: workspaceId,
    source_diff_content_ref: oldDiff,
    manifest_sha256: sha(readFileSync(join(runDir, 'evidence-manifest.v1.json'))),
    diff_sha256: sha(readFileSync(join(runDir, 'diff.patch'))),
    source_run_fingerprint: sha(Buffer.from(JSON.stringify(artifacts))),
    copied_artifacts: artifacts, created_at: '2026-10-25T00:00:00.000Z' }
  const receiptPath = join(runDir, 'evidence-relocation.v1.json')
  writeFileSync(receiptPath, JSON.stringify(receipt))

  let handler
  const warnings = []
  const ctx = { connection: { fetch: { register: spec => { handler = spec.fetch; return async () => {} } } },
    sessionQuery: { readSession: async () => ({ events: [{ type: 'subagent/catalog',
      data: { version: 2, childId } }] }) }, logger: { warn: msg => warnings.push(msg) } }
  registerRuntimeEvidenceRoute(ctx, evidenceRoot)
  const url = `http://localhost/api/dsh-runtime.evidence?sessionId=${workspaceId}&childId=${childId}`
  const response = await handler(new Request(url))
  assert.equal(response.status, 200)
  const payload = await response.json()
  assert.equal(payload.relocation.status, 'verified_copy')
  assert.equal(payload.manifest.run_id, runId)

  const wrong = await handler(new Request(`${url.slice(0, -childId.length)}aaaaaaaa-2222-3333-4444-555555555555`))
  assert.equal(wrong.status, 404)
  writeFileSync(receiptPath, JSON.stringify({ ...receipt, diff_sha256: '0'.repeat(64) }))
  const damaged = await handler(new Request(url))
  assert.equal(damaged.status, 500)
  assert.ok(warnings.some(msg => msg.includes('receipt identity or digest mismatch')))
})
