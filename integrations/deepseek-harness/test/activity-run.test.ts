import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, realpathSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve, relative, isAbsolute, sep } from 'node:path'
import { execFileSync, spawn } from 'node:child_process'
import { PassThrough } from 'node:stream'
import { test } from 'node:test'
import type { SubprocessHandle, SubprocessSpawnSpec } from '@deepseek-ai/dsh-subprocess'
import type { SubagentStartRequest } from '@deepseek-ai/dsh-subagent'
import { startDshRuntimeRun } from '../src/runtime/run.ts'
import { activityHistories, ACTIVITY_PREFIX } from '../src/runtime/activity-history.ts'

const fixture = (t: { after: (fn: () => void) => void }) => {
  const base = realpathSync(tmpdir()), root = mkdtempSync(join(base, 'dsh-history-run-'))
  const workspace = join(root, 'workspace'), evidence = join(root, 'evidence')
  mkdirSync(workspace); mkdirSync(evidence)
  mkdirSync(join(root, 'dsh_runtime', 'observability'), { recursive: true })
  writeFileSync(join(root, 'dsh_runtime', 'observability', 'activity.py'), '# fixture capability marker\n')
  writeFileSync(join(workspace, 'fixture.txt'), 'unchanged\n')
  execFileSync('git', ['init', '-q', workspace])
  t.after(() => { const rel = relative(base, realpathSync(root)); assert(rel && rel !== '..' && !rel.startsWith('..' + sep) && !isAbsolute(rel)); rmSync(root, { recursive: true, force: true }) })
  return { root, workspace, evidence }
}
const terminal = { task_id: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee', task_kind: 'repository_inspection', workspace_id: 'parent-session',
  status: 'completed', iteration: 1, result: 'inspection finished', error: null, last_invocation_result: 'inspection finished' }
const request = () => ({ prompt: [{ type: 'text', text: 'synthetic read-only inspection' }], signal: new AbortController().signal }) as SubagentStartRequest

test('the production run transport drains stderr EOF and leaves stdout settlement independent', async t => {
  const { root, workspace, evidence } = fixture(t)
  let identity!: { runId: string; workspaceId: string; evidenceRoot: string }
  let endAt = 0
  const launch = (spec: SubprocessSpawnSpec) => {
    const stdin = new PassThrough(), stdout = new PassThrough(), stderr = new PassThrough()
    const env = spec.env as Record<string, string>
    identity = { runId: env.DSH_RUNTIME_RUN_ID!, workspaceId: 'parent-session', evidenceRoot: realpathSync(evidence) }
    let exited!: (value: { exitCode: number }) => void
    const done = new Promise<{ exitCode: number }>(resolve => { exited = resolve })
    stdin.once('finish', () => {
      const common = { v: 1, runId: identity.runId, workspaceId: identity.workspaceId, streamId: env.DSH_RUNTIME_ACTIVITY_STREAM }
      const frame = (value: object) => stderr.write(ACTIVITY_PREFIX + JSON.stringify({ ...common, ...value }) + '\n')
      frame({ type: 'begin' })
      const row = { type: 'event', seq: 1, invocationId: 'cccccccc-dddd-4eee-8fff-aaaaaaaaaaaa', invocationIndex: 1,
        role: 'inspector', adapter: 'codex', atMs: Date.now(), kind: 'phase', status: 'dispatched' }
      frame(row)
      stderr.write(ACTIVITY_PREFIX + '{"private":"SECRET",bad}\nordinary diagnostic\n')
      stdout.end(JSON.stringify(terminal) + '\n')
      exited({ exitCode: 0 })
      setTimeout(() => {
        frame({ ...row, seq: 2, kind: 'tool', status: 'completed', tool: 'commandExecution' })
        frame({ ...row, seq: 3, kind: 'invocation', status: 'returned' })
        frame({ type: 'end', lastSeq: 3, dropped: 0 })
        endAt = Date.now(); stderr.end()
      }, 100)
    })
    return { stdin, stdout, stderr, done, terminate: () => { stderr.end() }, waitForExit: async () => { await done } } as unknown as SubprocessHandle
  }
  const run = await startDshRuntimeRun(request(), { cwd: workspace, workspaceId: 'parent-session', taskKind: 'repository_inspection',
    runtimeRoot: root, python: 'fixture', env: {}, evidenceRoot: evidence, disposeGraceMs: 500, spawn: launch })
  const result = await run.result
  const history = activityHistories.read(identity) as { events: unknown[]; closed: boolean; gaps: string[] }
  assert.equal(result.stopReason, 'completed')
  assert.equal(result.output[0]?.type, 'text')
  assert.equal(history.closed, true)
  assert.equal(history.events.length, 3)
  assert(Date.now() >= endAt && endAt > 0)
  assert.ok(history.gaps.includes('invalid_frame'))
  assert(!history.gaps.includes('missing_source_end'))
  assert.doesNotMatch(JSON.stringify(history), /SECRET|diagnostic/u)
  assert.equal(readFileSync(join(workspace, 'fixture.txt'), 'utf8'), 'unchanged\n')
  await run.dispose()
})

test('missing stderr EOF seals an incomplete bounded window and discards late frames', async t => {
  const { root, workspace, evidence } = fixture(t)
  let stderr!: PassThrough
  const run = await startDshRuntimeRun(request(), { cwd: workspace, workspaceId: 'parent-session', taskKind: 'repository_inspection',
    runtimeRoot: root, python: 'fixture', env: {}, evidenceRoot: evidence, disposeGraceMs: 500, spawn: () => {
      const stdin = new PassThrough(), stdout = new PassThrough(); stderr = new PassThrough()
      stdin.once('finish', () => { stdout.end(JSON.stringify(terminal) + '\n') })
      return { stdin, stdout, stderr, done: Promise.resolve({ exitCode: 0 }), terminate: () => stderr.end(), waitForExit: async () => {} } as unknown as SubprocessHandle
    } })
  assert.equal((await run.result).stopReason, 'completed')
  const identity = { evidenceRoot: realpathSync(evidence), runId: `dsh-runtime-${run.id}`, workspaceId: 'parent-session' }
  const before = activityHistories.read(identity)
  assert.match(JSON.stringify(before), /drain_timeout[\s\S]*missing_source_end/u)
  stderr.write(ACTIVITY_PREFIX + '{"private":"SECRET"}\n')
  assert.deepEqual(activityHistories.read(identity), before)
  await run.dispose()
})

test('real Python source frames reach a 50-row Host window without any frontend sampling or model', async t => {
  const { root, workspace, evidence } = fixture(t)
  const runtimeRoot = process.env.DSH_TEST_RUNTIME_ROOT ?? resolve(process.cwd(), '../..')
  const script = join(root, 'source.py')
  writeFileSync(script, `import json,sys,os,time\nfrom dsh_runtime.observability.activity import activity_stream,invocation_activity,record_activity\nr=json.load(sys.stdin)\nwith activity_stream(r['workspace_id']):\n assert 'DSH_RUNTIME_ACTIVITY_STREAM' not in os.environ\n with invocation_activity(r['workspace_id'],'inspector','codex',1):\n  for _ in range(100):\n   record_activity('codex','tool','completed','commandExecution')\n   time.sleep(.001)\nprint(json.dumps(${JSON.stringify(terminal).replaceAll('null', 'None')}))\n`)
  const run = await startDshRuntimeRun(request(), { cwd: workspace, workspaceId: 'parent-session', taskKind: 'repository_inspection',
    runtimeRoot, python: process.env.DSH_TEST_PYTHON ?? 'python', env: { PYTHONDONTWRITEBYTECODE: '1' }, evidenceRoot: evidence,
    disposeGraceMs: 500, spawn: spec => {
      const child = spawn(spec.argv[0]!, [script], { cwd: spec.cwd, env: { ...process.env, ...spec.env }, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true })
      const done = new Promise<{ exitCode: number | null }>((resolve, reject) => { child.once('close', code => resolve({ exitCode: code })); child.once('error', reject) })
      return { stdin: child.stdin, stdout: child.stdout, stderr: child.stderr, done, terminate: () => child.kill(), waitForExit: async () => { await done } } as unknown as SubprocessHandle
    } })
  assert.equal((await run.result).stopReason, 'completed')
  const result = activityHistories.read({ evidenceRoot: realpathSync(evidence), runId: `dsh-runtime-${run.id}`, workspaceId: 'parent-session' }) as {
    events: Array<{ seq: number; role: string }>; truncated: boolean; closed: boolean; gaps: string[]; retainedBytes: number;
  }
  assert.equal(result.events.length, 50)
  assert.equal(result.events[0]?.seq, 53)
  assert.equal(result.events.at(-1)?.seq, 102)
  assert.equal(result.closed, true)
  assert.equal(result.truncated, true)
  assert.deepEqual(result.gaps, ['window_truncated'])
  assert(result.retainedBytes <= 32768)
  assert(result.events.every(event => event.role === 'inspector'))
  await run.dispose()
})
