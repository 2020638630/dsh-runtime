import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { inspectApiAgentTrace } from '../src/runtime/api-agent-trace-evidence.ts'
import { writeTerminalEvidence } from '../src/runtime/evidence-manifest.ts'
import { captureWorkspace } from '../src/runtime/workspace-evidence.ts'

const RUN_ID = 'dsh-runtime-00000000-0000-4000-8000-000000000005'
const TRACE_ID = 'a'.repeat(32)

function fixture() {
  const root = mkdtempSync(join(tmpdir(), 'dsh-api-agent-trace-'))
  const runDir = join(root, RUN_ID)
  mkdirSync(runDir)
  const traceDir = join(runDir, `safe-trace-${RUN_ID}`)
  mkdirSync(traceDir)
  const tracePath = join(traceDir, `api-agent-safe-role-${TRACE_ID}.jsonl`)
  const base = {
    schema_version: 1, trace_id: TRACE_ID,
    captured_at_utc: '2026-10-23T00:00:00+00:00', role_name: 'inspector',
  }
  const records = [
    { ...base, event_seq: 0, event_type: 'started', tool_name: null,
      tool_status: null, terminal_reason: null },
    { ...base, event_seq: 1, event_type: 'tool_call', tool_name: 'read_file',
      tool_status: 'completed', terminal_reason: null },
    { ...base, event_seq: 2, event_type: 'terminal', tool_name: null,
      tool_status: null, terminal_reason: 'completed' },
  ]
  const bytes = Buffer.from(records.map(event => JSON.stringify(event)).join('\n') + '\n')
  writeFileSync(tracePath, bytes)
  writeFileSync(`${tracePath}.closed`, JSON.stringify({
    schema_version: 1, run_id: RUN_ID, trace_id: TRACE_ID, final_bytes: bytes.length,
  }) + '\n')
  return { traceDir, tracePath }
}

test('API Agent trace reader returns only bounded metadata after closure', async () => {
  const { traceDir, tracePath } = fixture()
  const evidence = await inspectApiAgentTrace({
    runId: RUN_ID, traceDir, tracePath, processExited: true,
  })
  assert.deepEqual(evidence, {
    status: 'available', traceComplete: true, traceId: TRACE_ID,
    roleName: 'inspector',
    toolOperationsSummary: { list_files: 0, read_file: 1, search_text: 0 },
  })
})

test('API Agent trace reader rejects a mismatched closure marker', async () => {
  const { traceDir, tracePath } = fixture()
  writeFileSync(`${tracePath}.closed`, JSON.stringify({
    schema_version: 1, run_id: RUN_ID, trace_id: TRACE_ID, final_bytes: 1,
  }) + '\n')
  const evidence = await inspectApiAgentTrace({
    runId: RUN_ID, traceDir, tracePath, processExited: true,
  })
  assert.equal(evidence.status, 'incomplete')
  assert.equal(evidence.traceComplete, false)
})

test('API Agent trace remains unknown before child exit', async () => {
  const { traceDir, tracePath } = fixture()
  const evidence = await inspectApiAgentTrace({
    runId: RUN_ID, traceDir, tracePath, processExited: false,
  })
  assert.equal(evidence.status, 'unknown')
})

test('inspection Manifest uses API Agent trace source when a closed trace exists', async () => {
  const { traceDir } = fixture()
  const runDir = join(traceDir, '..')
  const workspace = mkdtempSync(join(tmpdir(), 'dsh-api-agent-workspace-'))
  execFileSync('git', ['init', '-q', workspace])
  writeFileSync(join(workspace, 'README.md'), 'isolated inspection\n')
  const before = await captureWorkspace(workspace)
  const task = {
    task_id: '00000000-0000-4000-8000-000000000006',
    task_kind: 'repository_inspection', workspace_id: 'api.fixture',
    status: 'completed', iteration: 1, result: 'done', error: null,
    last_invocation_result: 'done',
  }
  await writeTerminalEvidence({
    runId: RUN_ID, runDir, safeTraceDir: traceDir,
    callTracePath: join(runDir, `${RUN_ID}-runtime-call-trace.jsonl`),
    workspace, workspaceId: 'api.fixture', before,
    taskKind: 'repository_inspection', task, exitCode: 0,
    durationMs: 1, stdout: '{}\n', maxTurnsConfig: null,
  })
  const manifest = JSON.parse(readFileSync(join(runDir, 'evidence-manifest.v1.json'), 'utf8'))
  assert.equal(manifest.execution_trajectory.source, 'api_agent_safe_event_trace')
  assert.equal(manifest.execution_trajectory.status, 'available')
  assert.equal(manifest.execution_trajectory.trace_complete, true)
  assert.deepEqual(manifest.execution_trajectory.tool_operations_summary,
    { list_files: 0, read_file: 1, search_text: 0 })
  assert.deepEqual(manifest.workspace_changes.modified_files, [])
})

test('inspection Manifest marks missing expected API trace unavailable', async () => {
  const root = mkdtempSync(join(tmpdir(), 'dsh-api-agent-missing-'))
  const runDir = join(root, RUN_ID)
  const traceDir = join(runDir, `safe-trace-${RUN_ID}`)
  mkdirSync(traceDir, { recursive: true })
  const workspace = mkdtempSync(join(tmpdir(), 'dsh-api-agent-workspace-'))
  execFileSync('git', ['init', '-q', workspace])
  writeFileSync(join(workspace, 'README.md'), 'isolated inspection\n')
  const before = await captureWorkspace(workspace)
  await writeTerminalEvidence({
    runId: RUN_ID, runDir, safeTraceDir: traceDir,
    callTracePath: join(runDir, `${RUN_ID}-runtime-call-trace.jsonl`),
    workspace, workspaceId: 'api.fixture', before,
    taskKind: 'repository_inspection',
    task: {
      task_id: '00000000-0000-4000-8000-000000000007',
      task_kind: 'repository_inspection', workspace_id: 'api.fixture',
      status: 'failed', iteration: 0, result: null, error: 'preflight failed',
      last_invocation_result: null,
    },
    exitCode: 0, durationMs: 1, stdout: '{}\n', maxTurnsConfig: null,
    expectedApiInspector: true,
  })
  const manifest = JSON.parse(readFileSync(join(runDir, 'evidence-manifest.v1.json'), 'utf8'))
  assert.equal(manifest.execution_trajectory.source, 'api_agent_safe_event_trace')
  assert.equal(manifest.execution_trajectory.status, 'unavailable')
})
