import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { mkdtempSync, mkdirSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs'
import fsPromises from 'node:fs/promises'
import { syncBuiltinESMExports } from 'node:module'
import { tmpdir } from 'node:os'
import { isAbsolute, join, relative, sep } from 'node:path'
import { test } from 'node:test'
import { setTimeout as wait } from 'node:timers/promises'
import { registerRuntimeEvidenceRoute } from '../.build/src/evidence-route.js'
import { captureWorkspace, describeWorkspaceObservation } from '../.build/src/runtime/workspace-evidence.js'
import { mountSnapshotReview } from '../.build/src/snapshot-review-route.js'
import { activityHistories, resolveActivityEvidenceRoot } from '../.build/src/runtime/activity-history.js'

const childId = '11111111-2222-3333-4444-555555555555'
const runId = `dsh-runtime-${childId}`
const workspaceId = 'session-22222222-3333-4444-5555-666666666666'
const sha = bytes => createHash('sha256').update(bytes).digest('hex')

test('activity reads reuse parent ownership, strict cursors and no-store without starting a task', async t => {
  const root = mkdtempSync(join(realpathSync(tmpdir()), 'dsh-history-route-'))
  t.after(() => rmSync(root, { recursive: true, force: true }))
  let handle
  let starts = 0
  const ctx = {
    connection: { fetch: { register(route) { handle = route.fetch; return async () => {} } } },
    sessionQuery: { readSession: async id => ({ events: id === workspaceId
      ? [{ type: 'subagent/catalog', data: { version: 2, childId } }] : [] }) },
    subagents: { start: () => { starts++; throw Error('Read must not start') } },
    logger: { warn: () => {} },
  }
  const release = registerRuntimeEvidenceRoute(ctx, root)
  t.after(release)
  const identity = { evidenceRoot: resolveActivityEvidenceRoot(root), runId, workspaceId }
  const streamId = activityHistories.start(identity, 'repository_inspection')
  activityHistories.accept(identity, { v: 1, type: 'begin', runId, workspaceId, streamId })
  const event = { v: 1, type: 'event', runId, workspaceId, streamId, seq: 1,
    invocationId: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee', invocationIndex: 1,
    role: 'inspector', adapter: 'codex', atMs: Date.now(), kind: 'phase', status: 'dispatched' }
  activityHistories.accept(identity, event)
  const query = new URLSearchParams({ sessionId: workspaceId, childId, view: 'activity' })
  const read = suffix => handle(new Request('http://fixture/api/dsh-runtime.evidence?' + query + suffix))
  const first = await read('')
  assert.equal(first.status, 200)
  assert.equal(first.headers.get('cache-control'), 'no-store')
  assert.equal((await first.json()).events.length, 1)
  assert.equal((await (await read('&after=1&stream=' + streamId)).json()).events.length, 0)
  assert.equal((await read('&after=-1')).status, 400)
  assert.equal((await read('&after=9007199254740992')).status, 400)
  assert.equal((await read('&after=0&after=1')).status, 400)
  assert.equal((await read('&filename=private')).status, 400)
  query.set('sessionId', 'unrelated-parent')
  assert.equal((await read('')).status, 404)
  assert.equal(starts, 0)
})

test('activity lookup uses the registration resolver without merging roots, runs or parents', async t => {
  const base = mkdtempSync(join(realpathSync(tmpdir()), 'dsh-history-identity-'))
  t.after(() => rmSync(base, { recursive: true, force: true }))
  const root = join(base, 'evidence'), otherRoot = join(base, 'other-evidence')
  mkdirSync(root); mkdirSync(otherRoot); mkdirSync(join(root, 'nested'))
  const alias = root + sep + 'nested' + sep + '..'
  assert.equal(resolveActivityEvidenceRoot(alias), resolveActivityEvidenceRoot(root))

  // Model the Windows sync/async spelling discrepancy on every test platform.
  // A regression back to async realpath must miss the recorded window, not pass
  // merely because the Linux resolvers happen to agree.
  const asyncRealpath = fsPromises.realpath
  let divergentReads = 0
  t.mock.method(fsPromises, 'realpath', async (...args) => {
    const physical = await asyncRealpath(...args)
    if (args[0] === alias) {
      divergentReads++
      return physical + '-different-resolver-spelling'
    }
    return physical
  })
  syncBuiltinESMExports()
  t.after(() => { fsPromises.realpath = asyncRealpath; syncBuiltinESMExports() })
  const identity = { evidenceRoot: resolveActivityEvidenceRoot(root), runId, workspaceId }
  const streamId = activityHistories.start(identity, 'repository_inspection')
  activityHistories.accept(identity, { v: 1, type: 'begin', runId, workspaceId, streamId })
  activityHistories.accept(identity, { v: 1, type: 'event', runId, workspaceId, streamId, seq: 1,
    invocationId: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee', invocationIndex: 1,
    role: 'inspector', adapter: 'codex', atMs: Date.now(), kind: 'phase', status: 'dispatched' })
  const otherChild = '22222222-3333-4444-5555-666666666666'
  const route = evidenceRoot => {
    let handle
    const ctx = {
      connection: { fetch: { register(value) { handle = value.fetch; return async () => {} } } },
      sessionQuery: { readSession: async id => ({ events: id === 'not-owned' ? [] : [childId, otherChild]
        .map(childId => ({ type: 'subagent/catalog', data: { version: 2, childId } })) }) },
      logger: { warn: () => {} },
    }
    t.after(registerRuntimeEvidenceRoute(ctx, evidenceRoot))
    return (sessionId = workspaceId, child = childId) => handle(new Request('http://fixture/api/dsh-runtime.evidence?'
      + new URLSearchParams({ sessionId, childId: child, view: 'activity' })))
  }
  const read = route(alias)
  const found = await (await read()).json()
  assert.equal(found.status, 'available')
  assert.equal(found.streamId, streamId)
  assert.equal(found.events.length, 1)
  assert.equal(divergentReads, 0)
  for (const response of [await route(otherRoot)(), await read('other-owner'), await read(workspaceId, otherChild)]) {
    const missing = await response.json()
    assert.equal(missing.status, 'unavailable')
    assert.equal(missing.reason, 'not_recorded_in_this_host')
    assert.equal(Object.hasOwn(missing, 'events'), false)
  }
  assert.equal((await read('not-owned')).status, 404)
})

test('review preview verifies ownership, saved patch bytes, and drift within one Git commit', async t => {
  const root = realpathSync(tmpdir())
  const base = mkdtempSync(join(root, 'dsh-review-preview-'))
  t.after(() => {
    const physical = realpathSync(base)
    const rel = relative(root, physical)
    assert.ok(rel !== '' && rel !== '..' && !rel.startsWith(`..${sep}`) && !isAbsolute(rel))
    rmSync(physical, { recursive: true, force: true })
  })
  const workspace = join(base, 'worktree')
  mkdirSync(workspace)
  const git = (...args) => execFileSync('git', ['-C', workspace, ...args], { encoding: 'utf8' }).trim()
  git('init', '-q')
  const file = join(workspace, 'fixture.txt')
  writeFileSync(file, 'before\n')
  git('add', 'fixture.txt')
  git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'Fixture')
  writeFileSync(file, 'after\n')
  const status = git('--no-optional-locks', 'status', '--porcelain=v1')
  const target = await describeWorkspaceObservation(await captureWorkspace(workspace))
  const evidenceRoot = join(base, 'evidence')
  const runDir = join(evidenceRoot, 'dsh-runtime', runId)
  mkdirSync(runDir, { recursive: true })
  const diff = '--- a/fixture.txt\n+++ b/fixture.txt\n@@ -1 +1 @@\n-before\n+after �\n'
  const diffPath = join(runDir, 'diff.patch')
  const manifestPath = join(runDir, 'evidence-manifest.v1.json')
  const manifest = { schema_version: '1', workspace_id: workspaceId, run_id: runId, task_id: '00000000-0000-4000-8000-000000000007', status: 'completed',
    task_kind: 'repository_change', target_observation: target,
    verification: { verdict: 'PASS', invocation_binding: 'matched' },
    workspace_changes: { diff_content_ref: diffPath, diff_sha256: sha(diff), patch_complete: true, patch_applicable: true },
  }
  writeFileSync(diffPath, diff)
  writeFileSync(manifestPath, JSON.stringify(manifest))
  let handle, review, provider, receivedPatch
  let starts = 0
  let admissions = 0
  let finish
  const childDone = new Promise(resolve => { finish = resolve })
  const session = { id: workspaceId, header: { cwd: workspace } }
  const parent = { id: workspaceId, session }
  manifest.model_observations = {
    version: 1, source: 'codex_thread_start',
    entries: [{ role: 'worker', invocation_index: 1, adapter: 'codex', reported_model: 'gpt-5.6-luna' }],
  }
  writeFileSync(manifestPath, JSON.stringify(manifest))
  const ctx = {
    connection: { fetch: { register(route) {
      if (route.path.endsWith('.evidence')) handle = route.fetch
      else review = route.fetch
      return async () => {}
    } } },
    sessionQuery: { readSession: async id => ({ session: { cwd: workspace },
      events: id === workspaceId ? [{ type: 'subagent/catalog', data: { version: 2, childId } }] : [] }) },
    logger: { warn: () => {} },
    get: key => key === 'agents' ? { get: id => id === workspaceId ? parent : undefined } : undefined,
    subagents: {
      registerProvider(value) { provider = value; return () => {} },
      async startActivation(spec) {
        assert.equal(spec.request.parent, parent)
        assert.equal(spec.delivery, 'caller')
        const child = await provider.start({ ...spec.request, signal: spec.signal, cwd: workspace })
        return { result: child.result, dispose: child.dispose }
      },
    },
    subprocess: { spawn(spec) {
      starts += 1
      assert.equal(spec.cwd, base)
      assert.equal(spec.argv.at(-1), 'dsh_runtime.snapshot_review')
      receivedPatch = JSON.parse(spec.stdio.stdin.data)
      return {
        done: childDone, terminate() { finish({ exitCode: 1 }) }, waitForExit: async () => {},
        collected: { stdout: { readFrom: () => ({ lossy: false, text: JSON.stringify({
          patch_sha256: sha(diff), observed_model: 'deepseek-ai/DeepSeek-V3.2', verdict: 'FAIL', report: 'fixture finding',
        }) }) } },
      }
    } },
  }
  registerRuntimeEvidenceRoute(ctx, evidenceRoot)
  const config = {
    runtimeRoot: base, python: 'python', env: {}, disposeGraceMs: 500, evidenceRoot,
    reviewer: { adapter: 'api_agent', provider: 'siliconflow', model: 'deepseek-ai/DeepSeek-V3.2' },
  }
  const bridge = { evaluatePreStart: async (live, caller, route) => {
    admissions += 1
    assert.equal(live, session)
    assert.equal(caller, workspaceId)
    assert.equal(route.taskKind, 'repository_inspection')
    return { kind: 'EXECUTION_ELIGIBLE' }
  } }
  let unmount = await mountSnapshotReview(ctx, config, bridge)
  t.after(() => unmount())
  const url = `http://localhost/api/dsh-runtime.evidence?sessionId=${workspaceId}&childId=${childId}&view=review-preview`
  const preview = async () => (await handle(new Request(url))).json()
  const ready = await preview()
  assert.equal(ready.status, 'ready')
  assert.equal(ready.scope, 'saved_text_patch')
  assert.equal(ready.patch, diff)
  assert.equal(ready.patchSha256, sha(diff))
  assert.doesNotMatch(JSON.stringify(ready), /diff_content_ref|worktree[/\\]/u)
  const regular = await handle(new Request(url.replace('&view=review-preview', '')))
  assert.equal((await regular.json()).reviewBytes, undefined)
  assert.equal((await handle(new Request(url.replace(workspaceId, 'other-session')))).status, 404)
  assert.equal(git('--no-optional-locks', 'status', '--porcelain=v1'), status)
  await assert.rejects(provider.start({
    parent, prompt: [{ type: 'text', text: 'not-a-grant' }], signal: new AbortController().signal, cwd: workspace,
  }), /Host grant/u)
  const reviewUrl = 'http://localhost/api/dsh-runtime.snapshot-review'
  const statusUrl = `${reviewUrl}?sessionId=${workspaceId}&childId=${childId}`
  const approval = await (await review(new Request(statusUrl))).json()
  assert.equal(approval.status, 'ready')
  assert.equal(approval.requestedModel, config.reviewer.model)
  assert.equal(starts, 0)
  const post = (overrides = {}, headers = {}) => new Request(reviewUrl, {
    method: 'POST', headers: { 'content-type': 'application/json', 'x-dsh-runtime-review': '1', ...headers },
    body: JSON.stringify({ sessionId: workspaceId, childId, patchSha256: approval.patchSha256,
      worktreeSha256: approval.worktreeSha256, approvalToken: approval.approvalToken, ...overrides }),
  })
  assert.equal((await review(post({}, { origin: 'https://example.invalid' }))).status, 403)
  assert.equal((await review(post({ patchSha256: '0'.repeat(64) }))).status, 409)
  assert.equal((await review(post({ sessionId: 'other-session' }))).status, 404)
  const replay = await Promise.all([review(post()), review(post())])
  assert.ok(replay.some(res => res.status === 202))
  assert.equal(starts, 1)
  assert.equal(admissions, 1)
  assert.equal(receivedPatch, diff)
  finish({ exitCode: 0 })
  let settled
  for (let attempt = 0; attempt < 100; attempt += 1) {
    settled = await (await review(new Request(statusUrl))).json()
    if (settled.status !== 'running') break
    await wait(10)
  }
  assert.equal(settled?.status, 'completed')
  await unmount()
  unmount = await mountSnapshotReview(ctx, config, bridge)
  const completed = await (await review(new Request(statusUrl))).json()
  assert.equal(completed.status, 'completed')
  assert.equal(completed.freshness, 'matched')
  assert.equal(completed.verdict, 'FAIL')
  assert.equal((await (await review(post())).json()).reviewId, completed.reviewId)
  assert.equal(starts, 1)
  writeFileSync(join(workspace, 'extra.txt'), 'untracked change\n')
  assert.equal(git('rev-parse', 'HEAD'), target.base_commit)
  assert.deepEqual(await preview(), { status: 'stale' })
  assert.equal((await (await review(new Request(statusUrl))).json()).freshness, 'stale')
  assert.equal(JSON.parse(readFileSync(manifestPath, 'utf8')).verification.verdict, 'PASS')
  const invalidUtf8 = Buffer.concat([Buffer.from(diff.split('�')[0]), Buffer.from([0xff, 0x0a])])
  assert.equal(invalidUtf8.toString('utf8'), diff)
  writeFileSync(diffPath, invalidUtf8)
  assert.deepEqual(await preview(), { status: 'material_changed' })
  writeFileSync(manifestPath, JSON.stringify({ ...manifest,
    workspace_changes: { ...manifest.workspace_changes, diff_sha256: sha(invalidUtf8) } }))
  assert.deepEqual(await preview(), { status: 'unsupported_patch' })
  writeFileSync(manifestPath, JSON.stringify({ ...manifest, target_observation: undefined }))
  assert.deepEqual(await preview(), { status: 'missing_binding' })
})

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
