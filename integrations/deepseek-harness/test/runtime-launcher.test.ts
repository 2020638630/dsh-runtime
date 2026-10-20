import assert from 'node:assert/strict'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'
import type { ResolvedSubagentStartRequest, SubagentRun } from '@deepseek-ai/dsh-subagent'
import type { DshRuntimeRunSpec } from '../src/runtime/run.ts'
import { createRuntimeLauncher } from '../src/runtime-launcher.ts'

const workspace = mkdtempSync(join(tmpdir(), 'dsh-launcher-parent-'))
const unrelatedChildCwd = mkdtempSync(join(tmpdir(), 'dsh-launcher-child-'))
const fakeRun = { id: 'test-run' } as SubagentRun
const config = { runtimeRoot: workspace, python: 'python', env: {}, disposeGraceMs: 3000, spawn: () => { throw new Error('unexpected process spawn') } }

function request(parentCwd?: string): ResolvedSubagentStartRequest {
  return {
    parent: { session: { id: 'parent-session', header: { cwd: parentCwd } } },
    cwd: unrelatedChildCwd,
    prompt: [{ type: 'text', text: 'inspect' }],
    signal: new AbortController().signal,
  } as ResolvedSubagentStartRequest
}

test('Runtime target is the parent Session cwd, never child request cwd', async () => {
  let captured: DshRuntimeRunSpec | undefined
  const launch = createRuntimeLauncher(config, async (_request, spec) => { captured = spec; return fakeRun })
  assert.equal(await launch(request(workspace), 'repository_inspection'), fakeRun)
  assert.equal(captured?.cwd, workspace)
  assert.equal(captured?.workspaceId, 'parent-session')
  assert.equal(captured?.taskKind, 'repository_inspection')
})

test('missing parent workspace fails before product entrypoint', async () => {
  let entered = false
  const launch = createRuntimeLauncher(config, async () => { entered = true; return fakeRun })
  await assert.rejects(async () => launch(request(), 'repository_change'), /no workspace directory/)
  assert.equal(entered, false)
})
