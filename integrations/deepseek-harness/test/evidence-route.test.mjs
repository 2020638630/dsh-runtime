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

test('live progress shows the active phase and only safe recent activity to the parent Session', async t => {
  const tempRoot = realpathSync(tmpdir())
  const base = mkdtempSync(join(tempRoot, 'dsh-route-progress-'))
  t.after(() => {
    const physical = realpathSync(base)
    assert.equal(physical, base)
    assert.equal(relative(tempRoot, physical).includes(sep), false)
    rmSync(physical, { recursive: true, force: true })
  })
  const runDir = join(base, 'dsh-runtime', runId)
  const traceDir = join(runDir, 'safe-trace-' + runId)
  mkdirSync(traceDir, { recursive: true })
  const identity = { schema_version: 1, run_id: runId, workspace_id: workspaceId }
  const started = Date.now() - 5000
  const traces = 'a'.repeat(32)
  writeFileSync(join(runDir, 'run-state.json'), JSON.stringify({ ...identity, phase: 'running' }))
  writeFileSync(join(runDir, 'runtime-progress.jsonl'), JSON.stringify({
    ...identity, role: 'worker', adapter: 'codebuddy', started_at_ms: started,
  }) + '\n')
  writeFileSync(join(traceDir, 'codebuddy-safe-worker-' + traces + '.jsonl'), JSON.stringify({
    schema_version: 1, trace_id: traces, event_seq: 1,
    event_type: 'tool_result', tool_name: 'Edit', tool_status: 'completed',
    captured_at_utc: new Date(started + 1000).toISOString(), prompt: 'private prompt',
  }) + '\n{"private":"incomplete tail"')
  let handler
  const ctx = {
    connection: { fetch: { register: spec => { handler = spec.fetch; return async () => {} } } },
    sessionQuery: { readSession: async id => ({ events: id === workspaceId
      ? [{ type: 'subagent/catalog', data: { version: 2, childId } }] : [] }) },
    logger: { warn: () => {} },
  }
  registerRuntimeEvidenceRoute(ctx, base)
  const url = 'http://localhost/api/dsh-runtime.evidence?childId=' + childId + '&sessionId='
  assert.equal((await handler(new Request(url + 'unrelated'))).status, 404)
  const response = await handler(new Request(url + workspaceId))
  assert.equal(response.status, 202)
  const payload = await response.json()
  assert.deepEqual(payload.progress, {
    phase: { role: 'worker', adapter: 'codebuddy', atMs: started },
    activity: { adapter: 'codebuddy', kind: 'tool', tool: 'Edit', status: 'completed', atMs: started + 1000 },
  })

  writeFileSync(join(runDir, 'runtime-progress.jsonl'), JSON.stringify({
    ...identity, role: 'reviewer', adapter: 'codex', started_at_ms: started + 2000,
  }) + '\n', { flag: 'a' })
  writeFileSync(join(runDir, 'runtime-codex-activity.jsonl'), JSON.stringify({
    ...identity, tool: 'commandExecution', status: 'called', at_ms: started + 3000,
    command: 'private command',
  }) + '\n')
  const review = await (await handler(new Request(url + workspaceId))).json()
  assert.deepEqual(review.progress, {
    phase: { role: 'reviewer', adapter: 'codex', atMs: started + 2000 },
    activity: { adapter: 'codex', kind: 'tool', tool: 'commandExecution', status: 'called', atMs: started + 3000 },
  })
  writeFileSync(join(runDir, 'run-state.json'), JSON.stringify({
    ...identity, phase: 'settled', stop_reason: 'aborted',
  }))
  const cancelled = await handler(new Request(url + workspaceId))
  assert.equal(cancelled.status, 200)
  assert.equal((await cancelled.json()).progress, undefined)
})
